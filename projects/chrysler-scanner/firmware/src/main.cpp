// SPDX-License-Identifier: GPL-3.0-only
#include "board.hpp"
#include "core.hpp"
#include "expander.hpp"
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <utility>
#include "driver/gpio.h"
#include "driver/i2c.h"
#include "driver/spi_common.h"
#include "driver/sdspi_host.h"
#include "driver/uart.h"
#include "esp_err.h"
#include "esp_efuse.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_vfs_fat.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "sdmmc_cmd.h"
#include "soc/efuse_defs.h"
#include "hal/uart_ll.h" // Pinned-IDF interrupt-mask names used by public UART APIs.

using scanner::Worker;
using scanner::Capture;
using scanner::Bus;
namespace {
std::uint64_t now_us() { return esp_timer_get_time(); }
gpio_num_t pin(int n) { return static_cast<gpio_num_t>(n); }
std::atomic<bool> fault{false}, ready{false}, permit{false};
std::atomic<bool> logging{false}, sd_error{false}, storage_draining{false};
scanner::StorageGate storage_gate;
portMUX_TYPE storage_mux=portMUX_INITIALIZER_UNLOCKED;
std::atomic<std::uint8_t> sci_selected{0};
std::atomic<std::uint8_t> sci_speed_index{1};
std::atomic<std::uint32_t> usb_lost{0}, sd_lost{0}, edge_lost{0}, uart_lost{0};
std::atomic<std::uint32_t> ccd_count{0}, pci_count{0}, sci_count{0}, rejected{0};
std::atomic<std::uint32_t> parse_errors{0};
scanner::Health health;
portMUX_TYPE health_mux=portMUX_INITIALIZER_UNLOCKED;
QueueHandle_t usb_capture_q, sd_capture_q, response_q, sci_request_q;
QueueHandle_t ccd_event_q, sci_event_q, pci_edge_q;
SemaphoreHandle_t aw_bus_mutex;
struct Response { std::uint16_t size=0; std::uint8_t data[scanner::max_wire]{}; };
struct SciRequest { std::uint8_t route, speed; std::uint32_t baud; };
struct Edge { std::uint64_t us; std::uint8_t level; };
constexpr unsigned ccd_baud=7812;
constexpr std::uint32_t capture_rx_interrupts=UART_INTR_RXFIFO_FULL|UART_INTR_RXFIFO_TOUT|
    UART_INTR_RXFIFO_OVF|UART_INTR_BRK_DET|UART_INTR_PARITY_ERR|UART_INTR_FRAM_ERR;
constexpr std::uint32_t sd_rotate_bytes=64*1024*1024;
constexpr TickType_t tick_ms(unsigned ms) { return pdMS_TO_TICKS(ms); }

void fail() {
    fault=true; ready=false;
    portENTER_CRITICAL(&health_mux); health.fail(); portEXIT_CRITICAL(&health_mux);
}
void vote(Worker w) {
    portENTER_CRITICAL(&health_mux); health.vote(w,now_us()); portEXIT_CRITICAL(&health_mux);
}
bool check(esp_err_t error) { if(error!=ESP_OK) { fail(); return false; } return true; }
void request_logging(bool value) {
    portENTER_CRITICAL(&storage_mux); storage_gate.request(value); portEXIT_CRITICAL(&storage_mux);
}
bool claim_storage() {
    portENTER_CRITICAL(&storage_mux);
    const bool claimed=storage_gate.claim(ready.load() && !fault.load());
    portEXIT_CRITICAL(&storage_mux); return claimed;
}
void storage_complete() {
    portENTER_CRITICAL(&storage_mux);
    logging=false; storage_gate.complete(); storage_draining=false;
    portEXIT_CRITICAL(&storage_mux);
}

// No UART TX signal is ever routed to the three vehicle TX GPIOs. They remain
// at the physically passive levels; expander TX, VBB and VPP bits stay zero.
bool safe_pins() {
    for(auto spec:{std::pair<int,int>{board::ccd_tx,1}, {board::sci_tx,1},
                   {board::pci_tx,0}, {board::sd_cs,1}}) {
        gpio_config_t output{};
        output.pin_bit_mask=1ULL<<spec.first; output.mode=GPIO_MODE_OUTPUT;
        if(!check(gpio_set_level(pin(spec.first),spec.second)) ||
           !check(gpio_config(&output))) return false;
    }
    gpio_config_t inputs{};
    inputs.pin_bit_mask=(1ULL<<board::button)|(1ULL<<board::card_detect);
    inputs.mode=GPIO_MODE_INPUT; // External pullups; GPIO37/38 have none internally.
    if(!check(gpio_config(&inputs))) return false;
    if(!check(gpio_set_level(pin(board::heartbeat),0))) return false;
    gpio_config_t heartbeat{};
    heartbeat.pin_bit_mask=1ULL<<board::heartbeat; heartbeat.mode=GPIO_MODE_OUTPUT;
    return check(gpio_config(&heartbeat));
}

void safety_task(void*) {
    auto wake=xTaskGetTickCount();
    const auto start=now_us();
    for(;;) {
        const auto now=now_us();
        bool healthy, latched;
        portENTER_CRITICAL(&health_mux);
        // Sample inside the same critical section as votes: a newer vote from
        // the other core must not look like unsigned timestamp underflow.
        healthy=health.poll(now_us()); latched=health.failed();
        portEXIT_CRITICAL(&health_mux);
        if(now-start>1500000 && !ready.load()) { fail(); healthy=false; }
        if(healthy && !fault.load()) {
            permit=true;
            // Sole GPIO13 writer after initial safe-low setup. Task delay is
            // deliberate: no timer/PWM/DMA can continue pulses after task failure.
            gpio_set_level(pin(board::heartbeat),1);
            vTaskDelay(tick_ms(1));
            gpio_set_level(pin(board::heartbeat),0);
        } else {
            gpio_set_level(pin(board::heartbeat),0);
            if(latched) { fault=true; ready=false; }
        }
        vTaskDelayUntil(&wake,tick_ms(10));
    }
}

bool aw_write(std::uint8_t reg,std::uint8_t value) {
    const std::uint8_t bytes[]{reg,value};
    return i2c_master_write_to_device(I2C_NUM_0,board::aw_address,bytes,2,tick_ms(5))==ESP_OK;
}
bool aw_read(std::uint8_t reg,std::uint8_t& value) {
    return i2c_master_write_read_device(I2C_NUM_0,board::aw_address,&reg,1,&value,1,tick_ms(5))==ESP_OK;
}
struct AwIo {
    bool read(std::uint8_t reg,std::uint8_t& value) { return aw_read(reg,value); }
    bool write(std::uint8_t reg,std::uint8_t value) { return aw_write(reg,value); }
};
bool aw_verify(std::uint8_t p1) { AwIo io; return scanner::verify_expander(io,p1); }
bool aw_init() {
    AwIo io; return scanner::initialize_expander(io);
}

void control_task(void*) {
    vote(Worker::Control);
    while(!permit.load() && !fault.load()) { vote(Worker::Control); vTaskDelay(tick_ms(2)); }
    // Covers the supervisor's nominal release delay during initial power-up.
    // Workers keep voting; no interface is declared ready during this interval.
    const auto settle=now_us()+300000;
    while(now_us()<settle && !fault.load()) { vote(Worker::Control); vTaskDelay(tick_ms(2)); }
    if(fault.load() || !aw_init() || fault.load()) { fail(); vTaskDelete(nullptr); return; }
    ready=true;
    bool last_button=false, stable_button=false;
    auto button_changed=now_us();
    for(;;) {
        if(fault.load()) {
            // Best effort immediate disconnect; watchdog is the independent
            // fallback when I2C or this task cannot run. No automatic re-arm.
            if(xSemaphoreTake(aw_bus_mutex,tick_ms(5))==pdTRUE) {
                aw_write(2,0); aw_write(3,board::p1_safe); xSemaphoreGive(aw_bus_mutex);
            }
            sci_selected=0; vTaskDelete(nullptr); return;
        }
        if(xSemaphoreTake(aw_bus_mutex,tick_ms(5))!=pdTRUE) { fail(); continue; }
        const bool safe=aw_verify(board::p1_safe|sci_selected.load());
        xSemaphoreGive(aw_bus_mutex);
        if(!safe) { fail(); continue; }
        const bool pressed=gpio_get_level(pin(board::button))==0;
        const auto now=now_us();
        if(pressed!=last_button) { last_button=pressed; button_changed=now; }
        if(now-button_changed>=50000 && stable_button!=pressed) {
            stable_button=pressed;
            if(pressed) {
                portENTER_CRITICAL(&storage_mux); storage_gate.toggle(); portEXIT_CRITICAL(&storage_mux);
            }
        }
        vote(Worker::Control);
        vTaskDelay(tick_ms(5));
    }
}

bool setup_uart(uart_port_t uart,unsigned baud,int rx,int tx,QueueHandle_t* events) {
    uart_config_t cfg{};
    cfg.baud_rate=baud; cfg.data_bits=UART_DATA_8_BITS; cfg.parity=UART_PARITY_DISABLE;
    cfg.stop_bits=UART_STOP_BITS_1; cfg.flow_ctrl=UART_HW_FLOWCTRL_DISABLE;
    cfg.source_clk=UART_SCLK_APB;
    if(!check(uart_param_config(uart,&cfg)) ||
       !check(uart_set_pin(uart,tx,rx,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE))) return false;
    return check(uart_driver_install(uart,4096,uart==UART_NUM_0?4096:0,64,events,0));
}

void publish(Capture c) {
    static std::uint32_t sequence=0;
    if(!ready.load() || fault.load()) return;
    c.sequence=sequence++;
    if(c.bus==Bus::Ccd) ++ccd_count;
    if(c.bus==Bus::Pci) ++pci_count;
    if(c.bus==Bus::Sci) ++sci_count;
    if(xQueueSend(usb_capture_q,&c,0)!=pdTRUE) ++usb_lost;
    if(storage_gate.requested() && logging.load() && !storage_draining.load() &&
       xQueueSend(sd_capture_q,&c,0)!=pdTRUE) ++sd_lost;
}

struct UartCapture {
    uart_port_t uart;
    QueueHandle_t events;
    scanner::BurstBatch burst;
    portMUX_TYPE event_mux=portMUX_INITIALIZER_UNLOCKED;
    explicit UartCapture(uart_port_t u,QueueHandle_t q,Bus bus):uart(u),events(q),burst(bus) {}
    void reset() {
        uart_lost+=burst.gap();
        // Prevent an ISR from queuing fresh event metadata between the ring
        // flush and event reset. Any subsequently received prefix is quarantined.
        if(!check(uart_disable_intr_mask(uart,capture_rx_interrupts))) return;
        check(uart_flush_input(uart)); xQueueReset(events);
        check(uart_clear_intr_status(uart,capture_rx_interrupts));
        check(uart_enable_intr_mask(uart,capture_rx_interrupts));
    }
    void poll() {
        uart_event_t event;
        for(unsigned count=0;count<64;++count) {
            // This UART's sole producer ISR runs on our core. Make the full
            // check and nonblocking pop indivisible, so a full queue cannot lose
            // an error event then hide that evidence behind our next pop.
            portENTER_CRITICAL(&event_mux);
            const bool full=uxQueueSpacesAvailable(events)==0;
            const bool got=!full && xQueueReceive(events,&event,0)==pdTRUE;
            portEXIT_CRITICAL(&event_mux);
            if(full) { reset(); return; }
            if(!got) break;
            if(event.type==UART_DATA) {
                std::size_t remaining=event.size;
                while(remaining) {
                    std::uint8_t bytes[128];
                    const auto want=remaining<sizeof(bytes)?remaining:sizeof(bytes);
                    const int n=uart_read_bytes(uart,bytes,want,0);
                    if(n<=0) { reset(); return; } // This event's timeout is no longer trustworthy.
                    remaining-=n;
                    for(int i=0;i<n;++i) {
                        if(!burst.append(bytes[i],now_us())) ++uart_lost;
                    }
                }
                if(event.timeout_flag) uart_lost+=burst.timeout();
            } else if(event.type==UART_FIFO_OVF || event.type==UART_BUFFER_FULL) {
                reset(); return;
            } else if(event.type==UART_PARITY_ERR || event.type==UART_FRAME_ERR || event.type==UART_BREAK) {
                // Do not label a damaged burst as a complete validated frame.
                reset(); return;
            }
        }
        // The capture UART ISR is installed on this task's core. It finishes
        // queueing both DATA and error events before this task can inspect them.
        // If more than a bounded batch remains, retain completions for next poll.
        if(uxQueueMessagesWaiting(events)==0) burst.publish(publish);
    }
};

std::atomic<bool> edge_gap{false};
void IRAM_ATTR pci_isr(void*) {
    const Edge e{static_cast<std::uint64_t>(esp_timer_get_time()),
                 static_cast<std::uint8_t>(gpio_get_level(static_cast<gpio_num_t>(board::pci_rx)))};
    BaseType_t higher=pdFALSE;
    if(xQueueSendFromISR(pci_edge_q,&e,&higher)!=pdTRUE) { edge_gap=true; ++edge_lost; }
    if(higher) portYIELD_FROM_ISR();
}

void acquisition_task(void*) {
    // Install receive ISRs on core 1, the same core as this pinned task; a
    // cross-core consumer could observe DATA before the ISR queues its error.
    if(!setup_uart(UART_NUM_1,ccd_baud,board::ccd_rx,UART_PIN_NO_CHANGE,&ccd_event_q) ||
       !setup_uart(UART_NUM_2,7812,board::sci_rx,UART_PIN_NO_CHANGE,&sci_event_q) ||
       !check(uart_set_rx_full_threshold(UART_NUM_1,120)) ||
       !check(uart_set_rx_timeout(UART_NUM_1,10)) ||
       !check(uart_set_rx_full_threshold(UART_NUM_2,120)) ||
       !check(uart_set_rx_timeout(UART_NUM_2,100)) ||
       !check(uart_enable_intr_mask(UART_NUM_1,capture_rx_interrupts)) ||
       !check(uart_enable_intr_mask(UART_NUM_2,capture_rx_interrupts))) {
        vTaskDelete(nullptr); return;
    }
    uart_set_always_rx_timeout(UART_NUM_1,true);
    uart_set_always_rx_timeout(UART_NUM_2,true);
    // Pending batches are static, not ~9 KiB on the 6 KiB task stack.
    static UartCapture ccd(UART_NUM_1,ccd_event_q,Bus::Ccd), sci(UART_NUM_2,sci_event_q,Bus::Sci);
    scanner::Vpw vpw;
    Edge last{};
    bool have_edge=false;
    for(;;) {
        if(fault.load()) { vTaskDelete(nullptr); return; }
        vote(Worker::Acquisition);
        SciRequest request;
        if(xQueueReceive(sci_request_q,&request,0)==pdTRUE && ready.load()) {
            // Two-step break-before-make. Always zero P0 and all TX/bias bits.
            // I2C ownership is serialized below by suspending changes to the
            // verification task through the shared mutex (see aw_bus_mutex).
            if(xSemaphoreTake(aw_bus_mutex,tick_ms(10))!=pdTRUE) { fail(); continue; }
            AwIo io;
            const bool ok=scanner::select_receiver(io,request.route,[&]() {
                sci_selected=0;
                sci.reset();
                return uart_set_baudrate(UART_NUM_2,request.baud)==ESP_OK;
            });
            if(ok) {
                sci.burst.source(request.route==board::rx7?7:request.route==board::rx15?15:0,request.speed);
                sci_speed_index=request.speed; sci_selected=request.route;
            }
            xSemaphoreGive(aw_bus_mutex);
            if(!ok) fail();
        }
        ccd.poll();
        if(sci_selected.load()) sci.poll();
        else if(uxQueueMessagesWaiting(sci_event_q)) sci.reset();
        if(edge_gap.exchange(false)) {
            xQueueReset(pci_edge_q); vpw.reset(); have_edge=false;
        }
        Edge e;
        unsigned drained=0;
        while(drained++<512 && xQueueReceive(pci_edge_q,&e,0)==pdTRUE) {
            if(have_edge) {
                if(!scanner::continuous_edge(last.us,last.level,e.us,e.level)) {
                    ++edge_lost; vpw.reset(); last=e; continue;
                }
                // Comparator output is inverted: bus dominant/high -> GPIO LOW.
                const auto width=e.us-last.us;
                vpw.pulse(last.level==0,width>0xffffffffULL?0xffffffffu:width,e.us,publish);
            }
            last=e; have_edge=true;
        }
        if(edge_gap.load()) { vpw.reset(); have_edge=false; }
        if(have_edge && last.level==1 && uxQueueMessagesWaiting(pci_edge_q)==0)
            vpw.idle(now_us(),last.us,publish);
        vTaskDelay(tick_ms(1));
    }
}

void respond(std::uint8_t command,std::uint8_t mode,const void* p=nullptr,std::size_t n=0) {
    Response r;
    r.size=scanner::wire(r.data,0x80|command,mode,static_cast<const std::uint8_t*>(p),n);
    if(!r.size || xQueueSend(response_q,&r,0)!=pdTRUE) ++usb_lost;
}
void deny(std::uint8_t reason=2) { ++rejected; respond(15,reason); }
void status(bool capabilities) {
    char text[scanner::max_data];
    int n;
    if(capabilities) {
        n=snprintf(text,sizeof(text),"{\"fw\":\"rev-c-passive-0.1.1\",\"protocol\":2,\"tx\":false,\"programming\":false,\"can\":false,\"ble\":false,\"adc_calibrated\":false,\"ccd\":true,\"pci\":true,\"sci_raw\":true,\"sd\":true}");
    } else {
        constexpr unsigned rates[]{976,7812,62500,125000};
        portENTER_CRITICAL(&storage_mux);
        const bool requested=storage_gate.requested(),busy=storage_gate.busy(),recording=logging.load(),error=sd_error.load();
        portEXIT_CRITICAL(&storage_mux);
        n=snprintf(text,sizeof(text),"{\"ready\":%d,\"fault\":%d,\"logging\":%d,\"sd_error\":%d,\"requested\":%d,\"sd_busy\":%d,\"sci\":%u,\"baud\":%u,\"rx\":[%lu,%lu,%lu],\"lost\":[%lu,%lu,%lu,%lu],\"reject\":%lu,\"parse\":%lu}",
            ready.load(),fault.load(),recording,error,requested,busy,sci_selected.load(),
            rates[sci_speed_index.load()],
            static_cast<unsigned long>(ccd_count.load()),static_cast<unsigned long>(pci_count.load()),
            static_cast<unsigned long>(sci_count.load()),static_cast<unsigned long>(usb_lost.load()),
            static_cast<unsigned long>(sd_lost.load()),static_cast<unsigned long>(edge_lost.load()),
            static_cast<unsigned long>(uart_lost.load()),static_cast<unsigned long>(rejected.load()),
            static_cast<unsigned long>(parse_errors.load()));
    }
    if(n<0 || std::size_t(n)>=sizeof(text)) { deny(0xfe); return; }
    respond(5,capabilities?0x7f:0x80,text,n);
}
void command(const std::uint8_t* p,std::size_t size) {
    // Exact routing allowlist: rejects direction spoofing, all vehicle buses,
    // reset, settings, TX, bootstrap, raw expander writes and legacy LED commands.
    const auto mode=p[4];
    const auto action=scanner::classify(p,size,ready.load(),fault.load());
    if(action==scanner::Action::Handshake) {
        constexpr char name[]="CHRYSLERSCANNER"; respond(1,0,name,15); return;
    }
    if(action==scanner::Action::Capabilities || action==scanner::Action::Status) { status(mode==0x7f); return; }
    if(action==scanner::Action::Log) {
        request_logging(p[5]==1); respond(5,mode,p+5,1); return;
    }
    if(action==scanner::Action::Sci) {
        constexpr std::uint32_t rates[]{976,7812,62500,125000};
        const SciRequest r{p[5]==1?board::rx7:p[5]==2?board::rx15:std::uint8_t{0},p[6],rates[p[6]]};
        if(xQueueSend(sci_request_q,&r,0)!=pdTRUE) { deny(7); return; }
        // Accepted for processing, not confirmation of physical application.
        respond(5,mode,p+5,2); return;
    }
    deny(3);
}

void usb_task(void*) {
    scanner::Parser parser;
    for(;;) {
        vote(Worker::Usb);
        std::uint8_t bytes[128];
        const int n=uart_read_bytes(UART_NUM_0,bytes,sizeof(bytes),0);
        parser.expire(now_us(),command);
        for(int i=0;i<n;++i) parser.feed(bytes[i],now_us(),command);
        parse_errors=parser.errors;
        Response r;
        if(xQueueReceive(response_q,&r,0)==pdTRUE) uart_write_bytes(UART_NUM_0,r.data,r.size);
        else {
            Capture c;
            if(xQueueReceive(usb_capture_q,&c,0)==pdTRUE) {
                r.size=scanner::capture_wire(c,r.data); uart_write_bytes(UART_NUM_0,r.data,r.size);
            }
        }
        vTaskDelay(tick_ms(1));
    }
}

struct SdSession {
    sdmmc_card_t* card=nullptr;
    FILE* file=nullptr;
    int fd=-1;
    std::uint32_t sequence=0,bytes=0;
    std::uint64_t synced=0,opened_us=0;
    bool mounted=false;
    char path[64]{};
    bool mount() {
        sdmmc_host_t host=SDSPI_HOST_DEFAULT();
        host.slot=SPI2_HOST; host.max_freq_khz=4000;
        sdspi_device_config_t device=SDSPI_DEVICE_CONFIG_DEFAULT();
        device.gpio_cs=pin(board::sd_cs); device.host_id=SPI2_HOST;
        esp_vfs_fat_sdmmc_mount_config_t cfg{};
        cfg.format_if_mount_failed=false; cfg.max_files=2; cfg.allocation_unit_size=16*1024;
        mounted=esp_vfs_fat_sdspi_mount("/sd",&host,&device,&cfg,&card)==ESP_OK;
        return mounted;
    }
    bool append(std::uint8_t type,const std::uint8_t* p,std::size_t n,std::uint64_t us) {
        std::uint8_t record[scanner::max_wire+40];
        const auto size=scanner::journal(record,type,sequence++,us,sd_lost.load(),p,n);
        if(!file || !size || fwrite(record,1,size,file)!=size) return false;
        bytes+=size; return true;
    }
    bool sync() {
        if(!file || fflush(file)!=0 || fsync(fd)!=0) return false;
        synced=now_us(); return true;
    }
    bool open(bool continuation=false) {
        sequence=0; bytes=8;
        if(!continuation) opened_us=now_us();
        // O_EXCL protects existing recordings. No formatting or truncation.
        for(unsigned attempt=0;attempt<16;++attempt) {
            snprintf(path,sizeof(path),"/sd/RC%08lx.cbr",static_cast<unsigned long>(esp_random()));
            fd=::open(path,O_CREAT|O_EXCL|O_WRONLY,0666);
            if(fd>=0) break;
            if(errno!=EEXIST) return false;
        }
        if(fd<0) return false;
        file=fdopen(fd,"wb");
        if(!file) { ::close(fd); fd=-1; return false; }
        if(fwrite("CBSDRAW1",1,8,file)!=8) return false;
        const char metadata[]="rev-c-passive-0.1.1 pcb=e794b86979228ba2275eb4262df848acd16e56ef97a4ccf45402d65b119308d4 utc=unknown tx=disabled sci=per-frame";
        return append(4,reinterpret_cast<const std::uint8_t*>(metadata),strlen(metadata),now_us()) && sync();
    }
    bool close(bool clean) {
        bool ok=true;
        if(file) {
            if(clean) {
                const char event[]="session_clean_stop";
                ok=append(4,reinterpret_cast<const std::uint8_t*>(event),strlen(event),now_us());
            }
            ok=sync() && ok;
            ok=(fclose(file)==0) && ok; file=nullptr; fd=-1;
        }
        return ok;
    }
    bool unmount() {
        if(mounted && esp_vfs_fat_sdcard_unmount("/sd",card)!=ESP_OK) { sd_error=true; fail(); return false; }
        mounted=false; card=nullptr; return true;
    }
};

void discard_sd_queue() {
    Capture discarded;
    while(xQueueReceive(sd_capture_q,&discarded,0)==pdTRUE) ++sd_lost;
}
bool append_capture(SdSession& sd,const Capture& c) {
    // A publisher racing a previous stop cannot splice its old capture into a
    // later session, even if it enqueues after that session's queue drain.
    if(c.us<sd.opened_us) { ++sd_lost; return true; }
    std::uint8_t frame[scanner::max_wire];
    const auto size=scanner::capture_wire(c,frame);
    if(!sd.append(2,frame,size,c.us)) { ++sd_lost; return false; }
    return true;
}

void storage_task(void*) {
    SdSession sd;
    bool failed_card=false;
    for(;;) {
        vote(Worker::Storage);
        const bool present=gpio_get_level(pin(board::card_detect))==0;
        if(!present) failed_card=false;
        if((fault.load() || !present || !storage_gate.requested()) && sd.file) {
            storage_draining=true; // Keep logging busy until drain/close/unmount finish.
            if(!present) sd_error=true;
            // Drain only a bounded snapshot; publisher stops adding while this
            // flag is set. Removal/fault cannot be called a clean stop.
            scanner::complete_stop([&]() {
                Capture c;
                if(present && !fault.load()) {
                    while(xQueueReceive(sd_capture_q,&c,0)==pdTRUE) {
                        if(!append_capture(sd,c)) { sd_error=true; break; }
                        vote(Worker::Storage);
                    }
                }
                return present && !fault.load() && !sd_error.load();
            },[&](bool clean) { return sd.close(clean && !fault.load()); },
              [&]() { return sd.unmount(); },[&](bool ok) {
                if(!ok) sd_error=true;
                storage_complete();
            });
            discard_sd_queue();
        }
        if(fault.load()) { request_logging(false); vTaskDelay(tick_ms(5)); continue; }
        if(!present) { request_logging(false); discard_sd_queue(); }
        if(present && !sd.file && !failed_card && claim_storage()) {
            sd_error=false;
            if(!sd.mount() || !sd.open()) {
                sd_error=true; failed_card=true; request_logging(false);
                sd.close(false); sd.unmount(); discard_sd_queue(); storage_complete();
            } else logging=true;
        }
        if(sd.file && storage_gate.requested()) {
            Capture c;
            for(unsigned batch=0;batch<8 && xQueueReceive(sd_capture_q,&c,0)==pdTRUE;++batch) {
                if(!append_capture(sd,c)) { sd_error=true; break; }
            }
            if(!sd_error.load() && sd.bytes>=sd_rotate_bytes) {
                if(!sd.close(true) || !sd.open(true)) sd_error=true;
            }
            if(!sd_error.load() && now_us()-sd.synced>=250000 && !sd.sync()) sd_error=true;
            if(sd_error.load()) {
                failed_card=true; request_logging(false); sd.close(false); sd.unmount();
                discard_sd_queue(); storage_complete();
            }
        }
        if(!storage_gate.requested() && !sd.file) discard_sd_queue();
        vTaskDelay(tick_ms(2));
    }
}
} // namespace

extern "C" void app_main() {
    // Read-only package guard before touching GPIO7/8/20. Those pins are not
    // interchangeable with a generic ESP32/PICO-D4 board's flash connections.
    if(esp_efuse_get_pkg_ver()!=EFUSE_RD_CHIP_VER_PKG_ESP32PICOV302) return;
    if(!safe_pins()) return;
    usb_capture_q=xQueueCreate(64,sizeof(Capture));
    sd_capture_q=xQueueCreate(128,sizeof(Capture));
    response_q=xQueueCreate(8,sizeof(Response));
    sci_request_q=xQueueCreate(4,sizeof(SciRequest));
    pci_edge_q=xQueueCreate(512,sizeof(Edge));
    aw_bus_mutex=xSemaphoreCreateMutex();
    if(!usb_capture_q || !sd_capture_q || !response_q || !sci_request_q || !pci_edge_q || !aw_bus_mutex) { fail(); return; }
    if(!setup_uart(UART_NUM_0,board::usb_baud,board::usb_rx,board::usb_tx,nullptr)) return;
    i2c_config_t i2c{};
    i2c.mode=I2C_MODE_MASTER; i2c.sda_io_num=pin(board::sda); i2c.scl_io_num=pin(board::scl);
    i2c.master.clk_speed=400000;
    if(!check(i2c_param_config(I2C_NUM_0,&i2c)) ||
       !check(i2c_driver_install(I2C_NUM_0,I2C_MODE_MASTER,0,0,0))) return;
    spi_bus_config_t spi{};
    spi.mosi_io_num=board::sd_mosi; spi.miso_io_num=board::sd_miso; spi.sclk_io_num=board::sd_sck;
    spi.quadwp_io_num=-1; spi.quadhd_io_num=-1; spi.max_transfer_sz=4096;
    if(!check(spi_bus_initialize(SPI2_HOST,&spi,SPI_DMA_CH_AUTO))) return;
    gpio_config_t pci{};
    pci.pin_bit_mask=1ULL<<board::pci_rx; pci.mode=GPIO_MODE_INPUT; pci.intr_type=GPIO_INTR_ANYEDGE;
    if(!check(gpio_config(&pci)) || !check(gpio_install_isr_service(ESP_INTR_FLAG_IRAM)) ||
       !check(gpio_isr_handler_add(pin(board::pci_rx),pci_isr,nullptr))) return;
    // All required workers must have actually run before the first permit edge.
    if(xTaskCreatePinnedToCore(usb_task,"usb",6144,nullptr,7,nullptr,0)!=pdPASS ||
       xTaskCreatePinnedToCore(storage_task,"sd",6144,nullptr,5,nullptr,0)!=pdPASS ||
       xTaskCreatePinnedToCore(acquisition_task,"capture",6144,nullptr,12,nullptr,1)!=pdPASS ||
       xTaskCreatePinnedToCore(control_task,"control",4096,nullptr,15,nullptr,1)!=pdPASS ||
       xTaskCreatePinnedToCore(safety_task,"health",3072,nullptr,20,nullptr,1)!=pdPASS) fail();
}

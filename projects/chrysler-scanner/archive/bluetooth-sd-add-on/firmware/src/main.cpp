// SPDX-License-Identifier: GPL-3.0-or-later
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <SD.h>
#include <SPI.h>
#include <esp_timer.h>
#include <atomic>
#include <memory>
#include "board_pins.hpp"
#include "capture_format.hpp"
#include "logger_core.hpp"
#include "control_policy.hpp"
#include "producer_gate.hpp"
#include "scanner_state.hpp"
#include "session_storage.hpp"
#include "chrysler/protocol.hpp"

namespace {
constexpr unsigned kQueueDepth = 64;
constexpr unsigned kChunkSize = 514; // ATT MTU517 minus notification header.
struct Input {
    std::uint64_t time_us;
    std::uint32_t generation, drops, notification_sequence;
    std::uint16_t size;
    bool event;
    std::uint8_t bytes[kChunkSize];
};
QueueHandle_t input_queue = nullptr;
std::atomic<bool> want_connection{false}, accepting{false}, ble_stopped{true};
logger_core::ScannerState scanner_state;
logger_core::ProducerGate queue_gate;
std::atomic<std::uint32_t> notifications{0}, dropped_chunks{0}, dropped_bytes{0};
std::atomic<std::uint32_t> generation{0}, reconnects{0};
logger_core::Config config;
std::string config_text;
capture::SessionStorage storage;
logger_core::Counters counters;
std::unique_ptr<chrysler::StreamParser> parser;
std::uint32_t seen_generation = 0, seen_drops = 0, last_flush = 0, last_stats = 0;
std::uint64_t event_time = 0, last_input_us = 0;
std::uint32_t event_generation = 0;
enum class State { Error, Safe, Recording, Stopping };
State state = State::Error;
std::string error_message;
std::uint32_t stopping_at = 0;

std::uint64_t now_us() { return static_cast<std::uint64_t>(esp_timer_get_time()); }
std::uint64_t utc_us(std::uint64_t host) {
    // Optional card anchor explicitly means UTC at THIS boot, not persistent RTC.
    return config.utc_epoch_at_boot ? config.utc_epoch_at_boot * 1000000ull + host : 0;
}
void note(const char* message, std::uint32_t epoch = generation.load()) {
    logger_core::ProducerGate::Guard producer(queue_gate);
    if (!producer) return;
    Input item{};
    item.event = true; item.time_us = now_us(); item.generation = epoch;
    item.drops = dropped_chunks.load();
    item.size = std::min(std::strlen(message), static_cast<std::size_t>(kChunkSize));
    std::memcpy(item.bytes, message, item.size);
    // No heap allocation, blocking filesystem I/O, or parsing in BLE callbacks.
    if (xQueueSend(input_queue, &item, 0) != pdTRUE) {
        dropped_chunks.fetch_add(1); dropped_bytes.fetch_add(item.size);
    }
}
void notify_callback(NimBLERemoteCharacteristic*, std::uint8_t* data,
                     std::size_t size, std::uint32_t epoch) {
    logger_core::ProducerGate::Guard producer(queue_gate);
    if (!producer || !accepting.load()) return;
    const auto sequence = notifications.fetch_add(1);
    if (size > kChunkSize) { dropped_chunks.fetch_add(1); dropped_bytes.fetch_add(size); return; }
    Input item{};
    item.time_us = now_us(); item.generation = epoch;
    item.notification_sequence = sequence; item.drops = dropped_chunks.load();
    item.size = static_cast<std::uint16_t>(size);
    if (size) std::memcpy(item.bytes, data, size);
    if (xQueueSend(input_queue, &item, 0) != pdTRUE) {
        dropped_chunks.fetch_add(1); dropped_bytes.fetch_add(size);
    }
}
class ClientCallbacks : public NimBLEClientCallbacks {
public:
    std::uint32_t epoch = 0; // Written only after previous disconnect callback ended.
    std::atomic<bool> ended{true};
    void onDisconnect(NimBLEClient*, int reason) override {
        scanner_state.disconnected(epoch);
        char text[80]; std::snprintf(text, sizeof(text), "ble_disconnected reason=%d", reason);
        note(text, epoch); ended.store(true);
    }
} client_callbacks;

// This is the ONLY scanner write boundary. Callers supply reviewed protocol
// library requests; no card command/hex bytes or vehicle TX interface exists.
bool send_control(NimBLERemoteCharacteristic* tx, const chrysler::Bytes& request) {
    if (!logger_core::safe_control_request(request)) return false;
    const bool response = tx->canWrite();
    const bool ok = tx->writeValue(request.data(), request.size(), response);
    note(ok ? "scanner_control_sent allowlisted_internal_only" : "scanner_control_failed");
    return ok;
}

void bluetooth_task(void*) {
    auto* client = NimBLEDevice::createClient();
    if (!client) { note("ble_client_allocation_failed"); vTaskDelete(nullptr); return; }
    client->setClientCallbacks(&client_callbacks, false);
    client->setConnectTimeout(5000); client->setConnectRetries(0);
    client->setConnectionParams(12, 24, 0, 400);
    NimBLERemoteCharacteristic* tx = nullptr;
    std::uint32_t next_attempt = 0, connected_at = 0, last_status_request = 0;
    bool controls_attempted = false;
    for (;;) {
        if (!want_connection.load()) {
            if (client->isConnected()) { client->disconnect(); vTaskDelay(pdMS_TO_TICKS(50)); }
            else ble_stopped.store(true);
            tx = nullptr; vTaskDelay(pdMS_TO_TICKS(20)); continue;
        }
        ble_stopped.store(false);
        if (!client->isConnected()) {
            tx = nullptr;
            if (static_cast<std::int32_t>(millis() - next_attempt) < 0) {
                vTaskDelay(pdMS_TO_TICKS(50)); continue;
            }
            next_attempt = millis() + 3000;
            if (!client_callbacks.ended.load()) { vTaskDelay(pdMS_TO_TICKS(20)); continue; }
            const auto epoch = scanner_state.begin_connection(); generation.store(epoch);
            client_callbacks.epoch = epoch; client_callbacks.ended.store(false);
            ++reconnects; controls_attempted = false;
            note("ble_connect_attempt exact_configured_address");
            const NimBLEAddress address(config.scanner_address,
                config.random_address ? BLE_ADDR_RANDOM : BLE_ADDR_PUBLIC);
            if (!client->connect(address)) { client_callbacks.ended.store(true); continue; }
            if (!want_connection.load()) { client->disconnect(); continue; }
            auto* service = client->getService(chrysler::kNusServiceUuid);
            auto* rx = service ? service->getCharacteristic(chrysler::kNusNotifyUuid) : nullptr;
            tx = service ? service->getCharacteristic(chrysler::kNusWriteUuid) : nullptr;
            if (!rx || !tx || !rx->canNotify() || (!tx->canWrite() && !tx->canWriteNoResponse()) ||
                !rx->subscribe(true, [epoch](NimBLERemoteCharacteristic* characteristic, std::uint8_t* bytes,
                    std::size_t size, bool) { notify_callback(characteristic, bytes, size, epoch); })) {
                note("ble_service_or_subscription_failed"); client->disconnect(); continue;
            }
            note("ble_subscribed nordic_uart_tx");
            connected_at = millis(); last_status_request = connected_at;
            send_control(tx, chrysler::build_read_request(chrysler::ReadRequest::Handshake));
            send_control(tx, chrysler::build_read_request(chrysler::ReadRequest::HardwareFirmwareInfo));
            send_control(tx, chrysler::build_read_request(chrysler::ReadRequest::Status));
        }
        if (tx && client->isConnected()) {
            const auto scanner = scanner_state.snapshot();
            if (!scanner.handshake && millis() - connected_at > 5000) {
                note("v2_handshake_missing refusing_rx_configuration"); client->disconnect(); continue;
            }
            const bool known = scanner.status_valid;
            const auto& snapshot = scanner.status;
            if (!known && scanner.handshake && millis() - connected_at > 12000) {
                note("scanner_status_missing reconnecting"); client->disconnect(); continue;
            }
            if (known && scanner.handshake) {
                if (!controls_attempted) {
                    controls_attempted = true;
                    if (config.enable_pci_rx) {
                        auto bytes = chrysler::build_receive_enable_request(chrysler::Bus::Pci, snapshot);
                        if (bytes && !send_control(tx, *bytes)) {
                            note("rx_enable_write_failed reconnecting"); client->disconnect(); continue;
                        }
                    }
                    if (config.enable_ccd_rx) {
                        auto bytes = chrysler::build_receive_enable_request(chrysler::Bus::Ccd, snapshot);
                        if (bytes && !send_control(tx, *bytes)) {
                            note("rx_enable_write_failed reconnecting"); client->disconnect(); continue;
                        }
                    }
                    send_control(tx, chrysler::build_read_request(chrysler::ReadRequest::Status));
                }
                const bool ready = (!config.enable_pci_rx || (snapshot.pci_settings & 0x80)) &&
                                   (!config.enable_ccd_rx || (snapshot.ccd_settings & 0x80));
                scanner_state.set_receive_ready(scanner.generation, ready);
                if (!ready && millis() - connected_at > 12000) {
                    note("rx_enable_not_confirmed reconnecting"); client->disconnect(); continue;
                }
            }
            if (millis() - last_status_request >= 5000) {
                send_control(tx, chrysler::build_read_request(chrysler::ReadRequest::Status));
                last_status_request = millis();
            }
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

void append(capture::Type type, const std::uint8_t* bytes, std::size_t size) {
    storage.append(type, event_time, utc_us(event_time), dropped_chunks.load(), bytes, size);
}
void append_text(const std::string& text) {
    append(capture::Type::Event, reinterpret_cast<const std::uint8_t*>(text.data()), text.size());
}
const char* bus_name(chrysler::Bus bus) {
    switch (bus) {
        case chrysler::Bus::Ccd: return "CCD";
        case chrysler::Bus::Pci: return "PCI";
        case chrysler::Bus::SciPcm: return "SCI_PCM";
        case chrysler::Bus::SciTcm: return "SCI_TCM";
        default: return "INTERNAL";
    }
}
void parser_event(const chrysler::ParseEvent& event) {
    if (event.kind != chrysler::ParseEventKind::Packet) {
        ++counters.parser_errors;
        if (!event.bytes.empty()) append(capture::Type::ParserError, event.bytes.data(), event.bytes.size());
        append_text("parser_event=" + std::to_string(static_cast<unsigned>(event.kind)) +
                    " lost_bytes=" + std::to_string(event.lost_bytes));
        return;
    }
    ++counters.frames;
    append(capture::Type::ScannerFrame, event.frame.raw.data(), event.frame.raw.size());
    if (chrysler::is_v2_handshake(event.frame)) {
        const bool current = want_connection.load() && scanner_state.accept_handshake(event_generation);
        append_text(current ? "v2_handshake_verified" : "old_connection_handshake_ignored");
    }
    if (auto status = chrysler::decode_status(event.frame)) {
        if (want_connection.load()) scanner_state.accept_status(event_generation, *status);
        append_text("scanner_status uptime_ms=" + std::to_string(status->uptime_ms) +
            " ccd_settings=" + std::to_string(status->ccd_settings) +
            " pci_settings=" + std::to_string(status->pci_settings) +
            " sci_settings=" + std::to_string(status->sci_settings) +
            " ccd_rx=" + std::to_string(status->ccd_rx) + " ccd_tx=" + std::to_string(status->ccd_tx) +
            " pci_rx=" + std::to_string(status->pci_rx) + " pci_tx=" + std::to_string(status->pci_tx) +
            " sci_rx=" + std::to_string(status->sci_rx) + " sci_tx=" + std::to_string(status->sci_tx));
    }
    const auto message = chrysler::decode_receive(event.frame);
    if (!message) return;
    const auto result = chrysler::decode_metrics(*message, config.upstream_profile ?
        chrysler::DecoderProfile::UpstreamBroadcast2023 : chrysler::DecoderProfile::None);
    if (result.disposition == chrysler::DecodeDisposition::InvalidBusChecksum ||
        result.disposition == chrysler::DecodeDisposition::InvalidMessageLength) ++counters.invalid_bus_messages;
    else if (result.disposition != chrysler::DecodeDisposition::Decoded) ++counters.unsupported;
    for (const auto& metric : result.metrics) {
        if (!logger_core::wanted(config, metric.id)) continue;
        char value[48]; std::snprintf(value, sizeof(value), "%.6f", metric.value);
        storage.row(std::to_string(event_time) + "," + std::to_string(utc_us(event_time)) + "," +
            std::to_string(message->scanner_ms) + "," + bus_name(message->bus) +
            ",upstream_broadcast_2023," + logger_core::csv(metric.id) + "," + value + "," +
            logger_core::csv(metric.unit) + "\n");
        ++counters.decoded_rows;
    }
}
std::string stats() {
    return "notifications=" + std::to_string(notifications.load()) +
        " dropped_chunks=" + std::to_string(dropped_chunks.load()) +
        " dropped_bytes=" + std::to_string(dropped_bytes.load()) +
        " frames=" + std::to_string(counters.frames) + " parser_errors=" + std::to_string(counters.parser_errors) +
        " connection_attempts=" + std::to_string(reconnects.load()) +
        " decoded_rows=" + std::to_string(counters.decoded_rows) +
        " unsupported=" + std::to_string(counters.unsupported) +
        " invalid_bus_messages=" + std::to_string(counters.invalid_bus_messages) +
        " receive_ready=" + std::to_string(scanner_state.snapshot().receive_ready) + "\n";
}
void error(const std::exception& ex) {
    accepting.store(false); want_connection.store(false); queue_gate.close();
    error_message = ex.what(); Serial.printf("ERROR: %s\n", error_message.c_str());
    storage.abandon(); state = State::Error;
}
void start_session() {
    if (state != State::Safe) return;
    try {
        storage.start("/sd/logs", "firmware=chrysler-bluetooth-sd-0.1.0\nboard=xiao_esp32s3_base\n"
            "time_source=host_monotonic_optional_card_utc_at_boot\nvehicle_transmit=not_implemented\n" + config_text);
        counters = {}; notifications.store(0); dropped_chunks.store(0); dropped_bytes.store(0); reconnects.store(0);
        seen_generation = generation.load(); seen_drops = 0;
        parser = std::make_unique<chrysler::StreamParser>(parser_event, 4096);
        event_time = now_us(); last_input_us = event_time;
        append_text("session_started passive_bus_capture");
        last_flush = last_stats = millis(); queue_gate.open(); accepting.store(true); want_connection.store(true);
        ble_stopped.store(false); state = State::Recording;
    } catch (const std::exception& ex) { error(ex); }
}
void stop_session() {
    if (state != State::Recording) return;
    accepting.store(false); want_connection.store(false);
    stopping_at = millis(); state = State::Stopping;
}
void process_input() {
    Input item{};
    unsigned processed = 0;
    while (processed++ < kQueueDepth && xQueueReceive(input_queue, &item, 0) == pdTRUE) {
        event_time = item.time_us; event_generation = item.generation;
        if (seen_generation != item.generation) {
            parser->finish(); seen_generation = item.generation; append_text("connection_generation=" + std::to_string(seen_generation));
        }
        if (item.drops != seen_drops) {
            parser->notify_loss(); seen_drops = item.drops;
            append_text("queue_loss cumulative_chunks=" + std::to_string(seen_drops));
        }
        if (item.event) {
            append(capture::Type::Event, item.bytes, item.size);
            const std::string text(reinterpret_cast<const char*>(item.bytes), item.size);
            if (text.find("ble_disconnected") == 0) parser->finish();
        } else {
            append(capture::Type::BleChunk, item.bytes, item.size);
            parser->feed(item.bytes, item.size); last_input_us = item.time_us;
        }
    }
    if (uxQueueMessagesWaiting(input_queue) == 0 && seen_drops != dropped_chunks.load()) {
        event_time = now_us(); parser->notify_loss(); seen_drops = dropped_chunks.load();
        append_text("queue_loss cumulative_chunks=" + std::to_string(seen_drops));
    }
    // Bound retention of a partial packet across long idle periods.
    if (parser->pending_bytes() && now_us() - last_input_us > 2000000ull) {
        event_time = now_us(); parser->finish(); append_text("partial_frame_idle_timeout");
    }
}
void button() {
    static bool previous = true, stable = true;
    static std::uint32_t changed = 0;
    const bool level = digitalRead(logger_board::button);
    if (level != previous) { previous = level; changed = millis(); }
    if (level != stable && millis() - changed >= 40) {
        stable = level;
        if (!stable) { if (state == State::Recording) stop_session(); else if (state == State::Safe) start_session(); }
    }
}
void led() {
    const auto phase = millis() % 2000;
    bool on = false;
    if (state == State::Safe) on = true; // No open log; previous Stop completed.
    else if (state == State::Stopping) on = (phase % 100) < 50;
    else if (state == State::Error) on = phase < 100 || (phase >= 200 && phase < 300) || (phase >= 400 && phase < 500);
    else if (scanner_state.snapshot().receive_ready) on = (phase % 500) < 250;
    else on = phase < 100 || (phase >= 200 && phase < 300);
    digitalWrite(logger_board::led, on ? HIGH : LOW);
}
} // namespace

void setup() {
    pinMode(logger_board::button, INPUT_PULLUP); pinMode(logger_board::led, OUTPUT);
    digitalWrite(logger_board::led, LOW); Serial.begin(115200);
    input_queue = xQueueCreate(kQueueDepth, sizeof(Input));
    if (!input_queue) { error_message = "input queue allocation failed"; return; }
    SPI.begin(logger_board::sd_sck, logger_board::sd_miso, logger_board::sd_mosi, logger_board::sd_cs);
    if (!SD.begin(logger_board::sd_cs, SPI, 10000000, "/sd", 10, false)) {
        error_message = "SD mount failed; format FAT32 and check card"; Serial.println(error_message.c_str()); return;
    }
    try {
        auto cfg = SD.open("/logger.cfg", FILE_READ);
        if (!cfg || cfg.size() > 4096) throw std::runtime_error("missing/oversized /logger.cfg");
        config_text.reserve(cfg.size());
        while (cfg.available()) config_text.push_back(static_cast<char>(cfg.read()));
        cfg.close(); config = logger_core::parse_config(config_text);
        NimBLEDevice::init("Chrysler-SD-Logger"); NimBLEDevice::setMTU(247);
        if (xTaskCreate(bluetooth_task, "logger_ble", 8192, nullptr, 1, nullptr) != pdPASS)
            throw std::runtime_error("BLE task allocation failed");
        state = State::Safe;
        if (config.auto_start) start_session();
    } catch (const std::exception& ex) { error(ex); }
}
void loop() {
    button(); led();
    if (state == State::Recording || state == State::Stopping) {
        try {
            process_input(); event_time = now_us();
            if (millis() - last_stats >= 1000) { append_text(stats()); last_stats = millis(); }
            if (millis() - last_flush >= config.flush_ms) { storage.flush(); last_flush = millis(); }
            if (state == State::Stopping && ble_stopped.load()) queue_gate.close();
            if (state == State::Stopping && ble_stopped.load() && client_callbacks.ended.load() &&
                queue_gate.quiescent() &&
                uxQueueMessagesWaiting(input_queue) == 0) {
                parser->finish(); append_text("session_stop " + stats()); storage.stop(stats());
                parser.reset(); state = State::Safe; Serial.println("SAFE: log files synced and closed");
            } else if (state == State::Stopping && millis() - stopping_at > 15000) {
                throw std::runtime_error("Bluetooth stop timeout; no safe-stop indication");
            }
        } catch (const std::exception& ex) { error(ex); }
    }
    delay(2);
}

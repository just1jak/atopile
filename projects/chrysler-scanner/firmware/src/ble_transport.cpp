// SPDX-License-Identifier: GPL-3.0-only
// NUS framing follows the original project; peripheral lifecycle follows the
// pinned ESP-IDF NimBLE interfaces. No BLE callback can drive vehicle controls.
#include "ble_transport.hpp"
#include "core.hpp"
#include <atomic>
#include <cstdio>
#include <cstring>
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "host/ble_gap.h"
#include "host/ble_gatt.h"
#include "host/ble_sm.h"
#include "host/ble_store.h"
#include "host/util/util.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
extern "C" void ble_store_config_init(void);
namespace scanner_ble {
namespace {
std::atomic<std::uint32_t> epoch{1},dropped{0};
std::atomic<std::uint16_t> connection{BLE_HS_CONN_HANDLE_NONE};
std::atomic<bool> secured{false},subscribed{false};
portMUX_TYPE pairing_mux=portMUX_INITIALIZER_UNLOCKED;
std::int64_t pair_until=0;unsigned pair_key=0;
std::uint8_t own_addr_type=0;std::uint16_t tx_handle=0;
QueueHandle_t rxq=nullptr,txq=nullptr;
ble_npl_event tx_event{};std::atomic<bool> tx_scheduled{false};
void pump_on_host(ble_npl_event*);
ble_store_write_fn* persist_write=nullptr;
ble_store_delete_fn* persist_delete=nullptr;
// Bond changes are restricted to commissioning, when capture is inhibited.
// CCCDs remain volatile; clients subscribe on every connection.
int store_write(int type,const union ble_store_value* value) {
    if(pairing_seconds())return persist_write(type,value);
    if(type==BLE_STORE_OBJ_TYPE_CCCD||type==BLE_STORE_OBJ_TYPE_PEER_DEV_REC||type==BLE_STORE_OBJ_TYPE_CSFC)return 0;
    return BLE_HS_EBUSY;
}
int store_delete(int type,const union ble_store_key* key) {
    if(pairing_seconds())return persist_delete(type,key);
    return BLE_HS_EBUSY;
}
struct Packet {std::uint32_t generation;std::uint16_t size;std::uint8_t bytes[scanner::max_wire];};
ble_uuid128_t service_uuid=BLE_UUID128_INIT(0x9e,0xca,0xdc,0x24,0x0e,0xe5,0xa9,0xe0,0x93,0xf3,0xa3,0xb5,0x01,0x00,0x40,0x6e);
ble_uuid128_t rx_uuid=BLE_UUID128_INIT(0x9e,0xca,0xdc,0x24,0x0e,0xe5,0xa9,0xe0,0x93,0xf3,0xa3,0xb5,0x02,0x00,0x40,0x6e);
ble_uuid128_t tx_uuid=BLE_UUID128_INIT(0x9e,0xca,0xdc,0x24,0x0e,0xe5,0xa9,0xe0,0x93,0xf3,0xa3,0xb5,0x03,0x00,0x40,0x6e);
ble_gatt_chr_def characteristics[3]{};ble_gatt_svc_def services[2]{};
bool authorized(std::uint16_t conn) {
    ble_gap_conn_desc d{};
    return ble_gap_conn_find(conn,&d)==0 && d.sec_state.encrypted && d.sec_state.authenticated;
}
int access(std::uint16_t conn,std::uint16_t,ble_gatt_access_ctxt* ctx,void*) {
    if(!authorized(conn))return BLE_ATT_ERR_INSUFFICIENT_AUTHEN;
    if(ctx->op==BLE_GATT_ACCESS_OP_READ_CHR)return 0; // Authenticated empty TX read triggers OS pairing.
    if(ctx->op!=BLE_GATT_ACCESS_OP_WRITE_CHR)return BLE_ATT_ERR_WRITE_NOT_PERMITTED;
    const auto size=OS_MBUF_PKTLEN(ctx->om);
    if(size==0||size>244)return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
    Chunk c{};c.generation=epoch.load();c.size=size;
    if(os_mbuf_copydata(ctx->om,0,size,c.data)!=0)return BLE_ATT_ERR_UNLIKELY;
    if(xQueueSend(rxq,&c,0)!=pdTRUE){++dropped;++epoch;return BLE_ATT_ERR_INSUFFICIENT_RES;}
    return 0;
}
void advertise();
int gap(ble_gap_event* event,void*) {
    switch(event->type){
    case BLE_GAP_EVENT_CONNECT:
        if(event->connect.status==0){
            connection=event->connect.conn_handle;secured=false;subscribed=false;++epoch;
            const auto rc=ble_gap_security_initiate(event->connect.conn_handle);
            if(rc!=0&&rc!=BLE_HS_EALREADY)ble_gap_terminate(event->connect.conn_handle,BLE_ERR_AUTH_FAIL);
        }
        else advertise();
        return 0;
    case BLE_GAP_EVENT_DISCONNECT:
        connection=BLE_HS_CONN_HANDLE_NONE;secured=false;subscribed=false;++epoch;advertise();return 0;
    case BLE_GAP_EVENT_ENC_CHANGE:
        secured=event->enc_change.status==0&&authorized(event->enc_change.conn_handle);
        if(!secured.load())ble_gap_terminate(event->enc_change.conn_handle,BLE_ERR_AUTH_FAIL);
        return 0;
    case BLE_GAP_EVENT_SUBSCRIBE:
        if(event->subscribe.attr_handle==tx_handle)subscribed=event->subscribe.cur_notify;
        return 0;
    case BLE_GAP_EVENT_PASSKEY_ACTION: {
        if(!pairing_seconds()||event->passkey.params.action!=BLE_SM_IOACT_DISP){ble_gap_terminate(event->passkey.conn_handle,BLE_ERR_AUTH_FAIL);return 0;}
        ble_sm_io io{};io.action=BLE_SM_IOACT_DISP;io.passkey=passkey();
        return ble_sm_inject_io(event->passkey.conn_handle,&io);
    }
    case BLE_GAP_EVENT_REPEAT_PAIRING: {
        if(!pairing_seconds())return BLE_GAP_REPEAT_PAIRING_IGNORE;
        ble_gap_conn_desc d{};
        if(ble_gap_conn_find(event->repeat_pairing.conn_handle,&d)==0)ble_store_util_delete_peer(&d.peer_id_addr);
        return BLE_GAP_REPEAT_PAIRING_RETRY;
    }
    default:return 0;
    }
}
void advertise() {
    ble_hs_adv_fields fields{};fields.flags=BLE_HS_ADV_F_DISC_GEN|BLE_HS_ADV_F_BREDR_UNSUP;
    fields.uuids128=&service_uuid;fields.num_uuids128=1;fields.uuids128_is_complete=1;
    if(ble_gap_adv_set_fields(&fields)!=0)return;
    ble_hs_adv_fields scan{};const char* name=ble_svc_gap_device_name();
    scan.name=reinterpret_cast<const std::uint8_t*>(name);scan.name_len=strlen(name);scan.name_is_complete=1;
    if(ble_gap_adv_rsp_set_fields(&scan)!=0)return;
    ble_gap_adv_params params{};params.conn_mode=BLE_GAP_CONN_MODE_UND;params.disc_mode=BLE_GAP_DISC_MODE_GEN;
    ble_gap_adv_start(own_addr_type,nullptr,BLE_HS_FOREVER,&params,gap,nullptr);
}
void synced() {if(ble_hs_util_ensure_addr(0)==0&&ble_hs_id_infer_auto(0,&own_addr_type)==0)advertise();}
void reset(int) {secured=false;subscribed=false;connection=BLE_HS_CONN_HANDLE_NONE;++epoch;}
void host(void*) {nimble_port_run();nimble_port_freertos_deinit();}
}
bool initialize() {
    // Bond keys persist in NVS. Never erase flash automatically on an NVS error.
    if(nvs_flash_init()!=ESP_OK)return false;
    rxq=xQueueCreate(8,sizeof(Chunk));txq=xQueueCreate(8,sizeof(Packet));
    if(!rxq||!txq||nimble_port_init()!=ESP_OK)return false;
    ble_hs_cfg.reset_cb=reset;ble_hs_cfg.sync_cb=synced;ble_hs_cfg.store_status_cb=ble_store_util_status_rr;
    ble_hs_cfg.sm_io_cap=BLE_HS_IO_DISPLAY_ONLY;ble_hs_cfg.sm_mitm=1;ble_hs_cfg.sm_sc=1;ble_hs_cfg.sm_bonding=1;
    ble_hs_cfg.sm_our_key_dist=BLE_SM_PAIR_KEY_DIST_ENC|BLE_SM_PAIR_KEY_DIST_ID;
    ble_hs_cfg.sm_their_key_dist=BLE_SM_PAIR_KEY_DIST_ENC|BLE_SM_PAIR_KEY_DIST_ID;
    ble_svc_gap_init();ble_svc_gatt_init();
    std::uint8_t mac[6]{};if(esp_read_mac(mac,ESP_MAC_BT)!=ESP_OK)return false;
    char name[26];snprintf(name,sizeof(name),"Chrysler-RC-%02X%02X%02X",mac[3],mac[4],mac[5]);
    if(ble_svc_gap_device_name_set(name)!=0)return false;
    characteristics[0].uuid=&rx_uuid.u;characteristics[0].access_cb=access;
    characteristics[0].flags=BLE_GATT_CHR_F_WRITE|BLE_GATT_CHR_F_WRITE_ENC|BLE_GATT_CHR_F_WRITE_AUTHEN;
    characteristics[0].min_key_size=16;
    characteristics[1].uuid=&tx_uuid.u;characteristics[1].access_cb=access;characteristics[1].val_handle=&tx_handle;
    characteristics[1].flags=BLE_GATT_CHR_F_NOTIFY|BLE_GATT_CHR_F_READ|BLE_GATT_CHR_F_READ_ENC|BLE_GATT_CHR_F_READ_AUTHEN;
    characteristics[1].min_key_size=16;
    services[0].type=BLE_GATT_SVC_TYPE_PRIMARY;services[0].uuid=&service_uuid.u;services[0].characteristics=characteristics;
    if(ble_gatts_count_cfg(services)!=0||ble_gatts_add_svcs(services)!=0)return false;
    ble_npl_event_init(&tx_event,pump_on_host,nullptr);
    ble_store_config_init();
    persist_write=ble_hs_cfg.store_write_cb;persist_delete=ble_hs_cfg.store_delete_cb;
    ble_hs_cfg.store_write_cb=store_write;ble_hs_cfg.store_delete_cb=store_delete;
    nimble_port_freertos_init(host);return true;
}
void open_pairing() {
    const auto key=esp_random()%1000000;
    portENTER_CRITICAL(&pairing_mux);pair_key=key;pair_until=esp_timer_get_time()+90000000;portEXIT_CRITICAL(&pairing_mux);
}
unsigned pairing_seconds() {
    portENTER_CRITICAL(&pairing_mux);const auto remaining=pair_until-esp_timer_get_time();portEXIT_CRITICAL(&pairing_mux);
    return remaining>0?static_cast<unsigned>((remaining+999999)/1000000):0;
}
unsigned passkey() {portENTER_CRITICAL(&pairing_mux);const auto key=pair_key;portEXIT_CRITICAL(&pairing_mux);return key;}
std::uint32_t generation(){return epoch.load();}
bool streaming(){return secured.load()&&subscribed.load()&&connection.load()!=BLE_HS_CONN_HANDLE_NONE;}
bool receive(Chunk& c){return xQueueReceive(rxq,&c,0)==pdTRUE;}
bool send(const std::uint8_t* bytes,std::size_t size,std::uint32_t gen) {
    if(!streaming()||gen!=epoch.load()||size>scanner::max_wire)return false;
    Packet p{};p.generation=gen;p.size=size;std::memcpy(p.bytes,bytes,size);
    if(xQueueSend(txq,&p,0)!=pdTRUE){++dropped;return false;}return true;
}
namespace {
void pump_on_host(ble_npl_event*) {
    // Security, disconnect, epoch updates and notifications are serialized on
    // the NimBLE host. Never re-use a connection handle after a cross-core check.
    []() {
    static Packet p{};static unsigned offset=0;static std::int64_t began=0;
    if(!p.size&&xQueueReceive(txq,&p,0)==pdTRUE){offset=0;began=esp_timer_get_time();}
    if(!p.size)return;
    if(!streaming()||p.generation!=epoch.load()||esp_timer_get_time()-began>1000000){p.size=0;++dropped;return;}
    const auto conn=connection.load();
    if(!authorized(conn)){p.size=0;++dropped;return;}
    const auto room=ble_att_mtu(conn)-3;
    const unsigned n=p.size-offset<room?p.size-offset:room;
    os_mbuf* data=ble_hs_mbuf_from_flat(p.bytes+offset,n);
    if(!data)return;
    if(ble_gatts_notify_custom(conn,tx_handle,data)==0){offset+=n;if(offset==p.size)p.size=0;}
    }();
    tx_scheduled=false;
}
}
void pump() {bool expected=false;if(tx_scheduled.compare_exchange_strong(expected,true))ble_npl_eventq_put(nimble_port_get_dflt_eventq(),&tx_event);}
std::uint32_t lost(){return dropped.load();}
}

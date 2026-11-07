// SPDX-License-Identifier: GPL-3.0-only
#include "rev_d_can.hpp"

#ifdef SCANNER_REV_D
#include <algorithm>
#include "driver/gpio.h"
#include "driver/twai.h"

namespace scanner::can_diag {
namespace {
constexpr std::uint64_t relay_wait_us = 150000; // provisional bench interval, not a contact sensor
constexpr std::uint8_t can_route = 1, legacy_route = 2, tx_arm = 4;
}

bool Controller::start_driver(bool active) {
    twai_general_config_t config = TWAI_GENERAL_CONFIG_DEFAULT(GPIO_NUM_2, GPIO_NUM_39,
        active ? TWAI_MODE_NORMAL : TWAI_MODE_LISTEN_ONLY);
    config.tx_queue_len = 0; // Only one shot per request. No stale queued transmission.
    config.rx_queue_len = 64;
    config.alerts_enabled = TWAI_ALERT_BUS_OFF | TWAI_ALERT_TX_FAILED |
                            TWAI_ALERT_RX_QUEUE_FULL | TWAI_ALERT_ERR_PASS;
    const twai_timing_config_t slow = TWAI_TIMING_CONFIG_250KBITS();
    const twai_timing_config_t fast = TWAI_TIMING_CONFIG_500KBITS();
    const twai_filter_config_t filter = TWAI_FILTER_CONFIG_ACCEPT_ALL();
    if (twai_driver_install(&config, rate_ ? &slow : &fast, &filter) != ESP_OK) return false;
    installed_ = true;
    if (twai_start() == ESP_OK && gpio_input_enable(GPIO_NUM_2) == ESP_OK) return true;
    stop_driver();
    return false;
}

void Controller::stop_driver() {
    if (!installed_) return;
    twai_stop();
    if (twai_driver_uninstall() == ESP_OK) installed_ = false;
}

bool Controller::route(Mode mode, std::uint8_t rate, std::uint64_t now, Select select) {
    if (rate > 1 || armed_ || switching_) return false;
    if (!select(0, true)) return false;
    selector_used_ = true;
    stop_driver();
    if (installed_) return false;
    mode_ = Mode::Open;
    target_ = mode;
    rate_ = rate;
    switching_ = mode != Mode::Open;
    due_ = now + relay_wait_us;
    return true;
}

bool Controller::request(std::uint8_t service, std::uint8_t pid, std::uint64_t now, Select select) {
    if (!supported(service, pid) || !can_request(now)) return false;
    // Establish the controller's idle output with the physical buffer disabled.
    if (!select(can_route, true)) return false;
    stop_driver();
    if (installed_ || !start_driver(true) || gpio_get_level(GPIO_NUM_2) != 1) return false;

    snapshot_ = {};
    snapshot_.result = Result::Waiting;
    service_ = service;
    pid_ = pid;
    expected_ = 0;
    next_seq_ = 1;
    deadline_ = now + active_window_ms * 1000ULL;
    next_request_ = now + 1200000;
    // Mark armed before the write. A failed readback still needs disarming.
    armed_ = true;
    if (!select(can_route | tx_arm, true)) return false;
    twai_message_t msg{};
    msg.identifier = 0x7df;
    msg.data_length_code = 8;
    msg.flags = TWAI_MSG_FLAG_SS;
    msg.data[0] = service == 3 ? 1 : 2;
    msg.data[1] = service;
    msg.data[2] = pid;
    return twai_transmit(&msg, 0) == ESP_OK;
}

bool Controller::disarm(Select select, bool resume) {
    const bool cleared = select(resume ? can_route : 0, true);
    armed_ = false;
    stop_driver();
    if (!cleared || installed_) return false;
    if (!resume) {
        mode_ = Mode::Open;
        switching_ = false;
        return true;
    }
    return start_driver(false);
}

bool Controller::consume(std::uint16_t id, const std::uint8_t* bytes, std::uint8_t dlc) {
    if (id < 0x7e8 || id > 0x7ef || dlc < 2) return true;
    if (snapshot_.response_id && snapshot_.response_id != id) return true;
    const auto kind = bytes[0] >> 4;
    if (kind == 2 && snapshot_.response_id && expected_ > snapshot_.size) {
        if ((bytes[0] & 0xf) != (next_seq_ & 0xf)) return false;
        ++next_seq_;
        const auto count = std::min<unsigned>(expected_ - snapshot_.size, dlc - 1);
        std::memcpy(snapshot_.data + snapshot_.size, bytes + 1, count);
        snapshot_.size += count;
    } else if (!snapshot_.response_id && (kind == 0 || kind == 1)) {
        const unsigned first = kind == 0 ? 1 : 2;
        if (dlc < first + (service_ == 3 ? 1 : 2)) return true;
        if (bytes[first] != service_ + 0x40 ||
            (service_ != 3 && bytes[first + 1] != pid_)) return true;
        const unsigned length = kind == 0 ? bytes[0] & 0xf :
                                ((bytes[0] & 0xf) << 8) | bytes[1];
        if (length < (service_ == 3 ? 1U : 2U) || length > sizeof(snapshot_.data) ||
            (kind == 0 && length > dlc - first) ||
            (kind == 1 && (dlc != 8 || length <= dlc - first))) return true;
        expected_ = length;
        snapshot_.response_id = id;
        snapshot_.size = std::min<unsigned>(length, dlc - first);
        std::memcpy(snapshot_.data, bytes + first, snapshot_.size);
        if (kind == 1) {
            twai_message_t flow{};
            flow.identifier = id - 8;
            flow.data_length_code = 8;
            flow.flags = TWAI_MSG_FLAG_SS;
            flow.data[0] = 0x30;
            flow.data[2] = 10; // minimum separation in ms
            if (twai_transmit(&flow, 0) != ESP_OK) return false;
        }
    }
    if (expected_ && snapshot_.size == expected_) snapshot_.result = Result::Complete;
    return true;
}

bool Controller::service(std::uint64_t now, bool healthy, bool usb_owner, Select select, Publish publish) {
    if (!healthy) {
        if (selector_used_) {
            disarm(select, false);
            selector_used_ = false;
        }
        return true;
    }
    if (!selector_used_) return true;
    if (switching_ && now >= due_) {
        switching_ = false;
        mode_ = target_;
        if (!select(mode_ == Mode::Legacy ? legacy_route : can_route, true)) return false;
        due_ = now + relay_wait_us;
        if (mode_ == Mode::Passive && !start_driver(false)) return false;
    }
    if (armed_ && (!usb_owner || now >= deadline_)) {
        snapshot_.result = Result::Timeout;
        return disarm(select, true);
    }
    if (now >= verify_at_) {
        verify_at_ = now + 20000;
        const std::uint8_t route_bits = mode_ == Mode::Legacy ? legacy_route :
                                       mode_ == Mode::Passive ? can_route : 0;
        if (!select(route_bits | (armed_ ? tx_arm : 0), false)) return false;
    }
    if (!installed_) return true;
    std::uint32_t alerts = 0;
    twai_read_alerts(&alerts, 0);
    if (armed_ && (alerts & (TWAI_ALERT_BUS_OFF | TWAI_ALERT_TX_FAILED |
                            TWAI_ALERT_RX_QUEUE_FULL | TWAI_ALERT_ERR_PASS))) {
        snapshot_.result = Result::Fault;
        return disarm(select, false);
    }
    twai_message_t msg{};
    for (unsigned i=0; i<12 && twai_receive(&msg, 0)==ESP_OK; ++i) {
        if (msg.data_length_code > 8) continue;
        Capture frame{};
        frame.bus = Bus::Can;
        frame.us = now;
        frame.flags = Raw;
        be32(frame.data.data(), msg.identifier);
        frame.data[4] = (msg.extd ? 1 : 0) | (msg.rtr ? 2 : 0) | (armed_ ? 4 : 0);
        frame.data[5] = msg.data_length_code;
        frame.size = 6 + (msg.rtr ? 0 : msg.data_length_code);
        if (!msg.rtr) std::memcpy(frame.data.data()+6, msg.data, msg.data_length_code);
        publish(frame);
        if (armed_ && !msg.extd && !msg.rtr &&
            !consume(msg.identifier, msg.data, msg.data_length_code)) {
            snapshot_.result = Result::Fault;
        }
        if (armed_ && snapshot_.result != Result::Waiting)
            return disarm(select, snapshot_.result == Result::Complete);
    }
    return true;
}
}
#endif

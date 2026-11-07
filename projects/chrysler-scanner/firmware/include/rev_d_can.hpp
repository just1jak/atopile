#pragma once

#include "core.hpp"

namespace scanner::can_diag {
constexpr unsigned tx_gpio = 2;
constexpr unsigned rx_gpio = 39;
constexpr unsigned selector_address = 0x20;
constexpr unsigned active_window_ms = 900;

enum class Mode : std::uint8_t { Open, Legacy, Passive };
enum class Result : std::uint8_t { Idle, Waiting, Complete, Timeout, Fault };

inline bool supported(std::uint8_t service, std::uint8_t pid) {
    if (service == 3) return pid == 0; // Stored DTCs
    if (service == 9) return pid == 2; // VIN
    if (service != 1) return false;
    switch (pid) {
        case 0x00: case 0x01: case 0x04: case 0x05: case 0x0b:
        case 0x0c: case 0x0d: case 0x0f: case 0x11: case 0x20:
        case 0x40: return true;
        default: return false;
    }
}

struct Snapshot {
    Result result = Result::Idle;
    std::uint16_t response_id = 0;
    std::uint8_t size = 0;
    std::uint8_t data[64]{};
};

class Controller {
public:
    using Select = bool (*)(std::uint8_t, bool);
    using Publish = void (*)(Capture);

    bool route(Mode mode, std::uint8_t rate, std::uint64_t now, Select select);
    bool request(std::uint8_t service, std::uint8_t pid, std::uint64_t now, Select select);
    bool service(std::uint64_t now, bool healthy, bool usb_owner, Select select, Publish publish);
    Mode mode() const { return mode_; }
    bool transitioning(std::uint64_t now) const { return switching_ || now < due_; }
    bool can_request(std::uint64_t now) const {
        return mode_ == Mode::Passive && !transitioning(now) && !armed_ && now >= next_request_;
    }
    bool armed() const { return armed_; }
    const Snapshot& snapshot() const { return snapshot_; }

private:
    bool start_driver(bool active);
    void stop_driver();
    bool disarm(Select select, bool resume);
    bool consume(std::uint16_t id, const std::uint8_t* bytes, std::uint8_t dlc);
    Mode mode_ = Mode::Open, target_ = Mode::Open;
    std::uint8_t rate_ = 0, service_ = 0, pid_ = 0, next_seq_ = 1, expected_ = 0;
    bool installed_ = false, armed_ = false, switching_ = false, selector_used_ = false;
    std::uint64_t due_ = 0, verify_at_ = 0, deadline_ = 0, next_request_ = 0;
    Snapshot snapshot_{};
};
}

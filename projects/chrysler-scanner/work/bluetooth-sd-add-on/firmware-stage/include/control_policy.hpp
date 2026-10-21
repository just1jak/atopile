#pragma once
#include "chrysler/protocol.hpp"

namespace logger_core {
// Last boundary before a Bluetooth write: deny vehicle routes/TX/SCI/flash.
inline bool safe_control_request(const chrysler::Bytes& request) {
    const auto f = chrysler::parse_frame(request);
    if (!f || f->from_scanner || f->bus != 0) return false;
    const bool read = (f->command == 1 && f->mode == 0) ||
        (f->command == 2 && f->mode == 0) ||
        (f->command == 4 && f->mode >= 1 && f->mode <= 3);
    if (read) return f->payload.empty();
    return f->command == 3 && (f->mode == 2 || f->mode == 6) &&
           f->payload.size() == 1 && (f->payload[0] & 0x80);
}
} // namespace logger_core

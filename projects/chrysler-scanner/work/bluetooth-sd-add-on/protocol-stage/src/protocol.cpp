// SPDX-License-Identifier: GPL-3.0-only
// Broadcast formulas adapted from Laszlo Daniel's ChryslerScanner GUI (GPLv3).
// See SOURCES.md for pinned source locations, limitations, and attribution.
#include "chrysler/protocol.hpp"

#include <algorithm>
#include <utility>

namespace chrysler {
namespace {
constexpr std::uint8_t kSync = 0x3d;
std::uint16_t be16(const std::uint8_t* p) {
    return static_cast<std::uint16_t>((static_cast<std::uint16_t>(p[0]) << 8) | p[1]);
}
std::uint32_t be32(const std::uint8_t* p) {
    return (static_cast<std::uint32_t>(p[0]) << 24) |
           (static_cast<std::uint32_t>(p[1]) << 16) |
           (static_cast<std::uint32_t>(p[2]) << 8) | p[3];
}
Bytes control(std::uint8_t command, std::uint8_t mode, const Bytes& payload = {}) {
    const auto length = payload.size() + 2;
    Bytes b{kSync, static_cast<std::uint8_t>(length >> 8),
            static_cast<std::uint8_t>(length), command, mode};
    b.insert(b.end(), payload.begin(), payload.end());
    b.push_back(frame_checksum(b.data(), b.size()));
    return b;
}
std::uint8_t pci_crc(const std::uint8_t* p, std::size_t n) {
    std::uint8_t crc = 0xff;
    for (std::size_t i = 0; i < n; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = static_cast<std::uint8_t>((crc << 1) ^ ((crc & 0x80) ? 0x1d : 0));
    }
    return static_cast<std::uint8_t>(crc ^ 0xff);
}
} // namespace

std::uint8_t frame_checksum(const std::uint8_t* bytes, std::size_t size) {
    std::uint8_t sum = 0;
    for (std::size_t i = 0; i < size; ++i)
        sum = static_cast<std::uint8_t>(sum + bytes[i]);
    return sum;
}

std::optional<Frame> parse_frame(const Bytes& b) {
    if (b.size() < 6 || b[0] != kSync || be16(b.data() + 1) < 2 ||
        static_cast<std::size_t>(be16(b.data() + 1)) + 4 != b.size() ||
        frame_checksum(b.data(), b.size() - 1) != b.back()) return std::nullopt;
    Frame frame;
    frame.raw = b;
    frame.from_scanner = (b[3] & 0x80) != 0;
    frame.bus = static_cast<std::uint8_t>((b[3] >> 4) & 7);
    frame.command = b[3] & 0x0f;
    frame.mode = b[4];
    frame.payload.assign(b.begin() + 5, b.end() - 1);
    return frame;
}

StreamParser::StreamParser(Sink sink, std::size_t maximum)
    : sink_(std::move(sink)), maximum_(std::clamp(maximum, std::size_t{6}, std::size_t{65539})) {
    pending_.reserve(std::min(maximum_, std::size_t{4096}));
}

void StreamParser::emit(ParseEventKind kind, const Bytes& bytes) {
    if (sink_) sink_(ParseEvent{kind, {}, bytes, 0});
}

void StreamParser::drain() {
    for (;;) {
        const auto sync = std::find(pending_.begin(), pending_.end(), kSync);
        if (sync != pending_.begin()) {
            emit(ParseEventKind::Noise, Bytes(pending_.begin(), sync));
            pending_.erase(pending_.begin(), sync);
        }
        if (pending_.size() < 3) return;
        const std::size_t size = static_cast<std::size_t>(be16(pending_.data() + 1)) + 4;
        if (size < 6 || size > maximum_) {
            emit(ParseEventKind::InvalidLength, Bytes(pending_.begin(), pending_.begin() + 3));
            pending_.erase(pending_.begin()); // Reconsider a later sync, including within the header.
            continue;
        }
        if (pending_.size() < size) return;
        Bytes bytes(pending_.begin(), pending_.begin() + static_cast<std::ptrdiff_t>(size));
        auto frame = parse_frame(bytes);
        if (!frame) {
            emit(ParseEventKind::ChecksumMismatch, bytes);
            pending_.erase(pending_.begin()); // Recover following frames without trusting bad length.
            continue;
        }
        pending_.erase(pending_.begin(), pending_.begin() + static_cast<std::ptrdiff_t>(size));
        if (sink_) sink_(ParseEvent{ParseEventKind::Packet, std::move(*frame), {}, 0});
    }
}

void StreamParser::feed(const std::uint8_t* bytes, std::size_t size) {
    if (bytes == nullptr && size != 0) { notify_loss(size); return; }
    for (std::size_t i = 0; i < size; ++i) {
        if (pending_.empty() && bytes[i] != kSync) {
            const auto begin = i;
            while (i + 1 < size && i - begin < 511 && bytes[i + 1] != kSync) ++i;
            emit(ParseEventKind::Noise, Bytes(bytes + begin, bytes + i + 1));
            continue;
        }
        pending_.push_back(bytes[i]);
        drain(); // Bounded even if the caller passes a very large notification batch.
    }
}

void StreamParser::finish() {
    if (!pending_.empty()) emit(ParseEventKind::Truncated, pending_);
    pending_.clear();
}

void StreamParser::notify_loss(std::size_t lost_bytes) {
    if (sink_) sink_(ParseEvent{ParseEventKind::TransportLoss, {}, pending_, lost_bytes});
    pending_.clear();
}

Bytes build_read_request(ReadRequest request) {
    switch (request) {
        case ReadRequest::Handshake: return control(1, 0);
        case ReadRequest::Status: return control(2, 0);
        case ReadRequest::HardwareFirmwareInfo: return control(4, 1);
        case ReadRequest::Timestamp: return control(4, 2);
        case ReadRequest::BatteryVoltage: return control(4, 3);
    }
    return {}; // No generic command fallback.
}

bool is_v2_handshake(const Frame& f) {
    static const Bytes expected{'C','H','R','Y','S','L','E','R','S','C','A','N','N','E','R'};
    return f.from_scanner && f.bus == 0 && f.command == 1 && f.mode == 0 && f.payload == expected;
}

std::optional<ReceivedMessage> decode_receive(const Frame& f) {
    if (!f.from_scanner || f.command != 7 || f.bus < 1 || f.bus > 4 || f.payload.size() < 5)
        return std::nullopt;
    if (f.mode != 1 && !(f.mode == 2 && (f.bus == 2 || f.bus == 3))) return std::nullopt;
    return ReceivedMessage{static_cast<Bus>(f.bus), f.mode == 2, be32(f.payload.data()),
                           Bytes(f.payload.begin() + 4, f.payload.end())};
}

std::optional<ScannerStatus> decode_status(const Frame& f) {
    if (!f.from_scanner || f.bus != 0 || f.command != 2 || f.mode != 0 || f.payload.size() != 45)
        return std::nullopt;
    const auto* p = f.payload.data();
    ScannerStatus s;
    s.uptime_ms = be32(p); s.ram_used_bytes = be32(p + 4); s.battery_mv = be16(p + 8);
    s.ccd_settings = p[14]; s.ccd_rx = be32(p + 15); s.ccd_tx = be32(p + 19);
    s.pci_settings = p[23]; s.pci_rx = be32(p + 24); s.pci_tx = be32(p + 28);
    s.sci_settings = p[32]; s.sci_rx = be32(p + 33); s.sci_tx = be32(p + 37);
    return s;
}

std::optional<Bytes> build_receive_enable_request(Bus bus, const ScannerStatus& status) {
    std::uint8_t value = 0, mode = 0;
    if (bus == Bus::Ccd) { value = status.ccd_settings; mode = 2; }
    else if (bus == Bus::Pci) { value = status.pci_settings; mode = 6; }
    else return std::nullopt;
    if ((value & 0x80) != 0) return std::nullopt;
    return control(3, mode, Bytes{static_cast<std::uint8_t>(value | 0x80)});
}

DecodeResult decode_metrics(const ReceivedMessage& message, DecoderProfile profile) {
    DecodeResult result;
    if (profile != DecoderProfile::UpstreamBroadcast2023) { result.disposition = DecodeDisposition::ProfileDisabled; return result; }
    if (message.high_speed) { result.disposition = DecodeDisposition::UnsupportedMode; return result; }
    const auto& m = message.raw_bus_bytes;
    if (m.empty()) { result.disposition = DecodeDisposition::InvalidMessageLength; return result; }
    std::size_t expected = 0;
    if (message.bus == Bus::Pci) {
        if (m[0] == 0x10) expected = 7;
        else if (m[0] == 0xc0) expected = 6;
    } else if (message.bus == Bus::Ccd) {
        if (m[0] == 0x0c) expected = 6;
        else if (m[0] == 0x24 || m[0] == 0xe4) expected = 4;
    }
    if (expected == 0) return result;
    if (m.size() != expected) { result.disposition = DecodeDisposition::InvalidMessageLength; return result; }
    const auto checksum = message.bus == Bus::Pci ? pci_crc(m.data(), m.size() - 1)
                                                 : frame_checksum(m.data(), m.size() - 1);
    if (checksum != m.back()) { result.disposition = DecodeDisposition::InvalidBusChecksum; return result; }
    auto add = [&](const char* id, double value, const char* unit) { result.metrics.push_back(Metric{id, value, unit}); };
    if (message.bus == Bus::Pci && m[0] == 0x10) {
        add("engine_rpm", be16(m.data() + 1) * 0.25, "rpm");
        add("vehicle_speed_kph", be16(m.data() + 3) * 0.0049 * 1.609344, "km/h");
        add("manifold_absolute_pressure_kpa", m[5], "kPa");
    } else if ((message.bus == Bus::Pci && m[0] == 0xc0) || (message.bus == Bus::Ccd && m[0] == 0x0c)) {
        const bool pci = message.bus == Bus::Pci;
        add("battery_voltage_v", m[1] * (pci ? 0.0625 : 0.125), "V");
        add("oil_pressure_kpa", m[2] * 0.5 * 6.894757, "kPa");
        add("coolant_temperature_c", static_cast<int>(m[3]) - (pci ? 40 : 64), "degC");
        add("ambient_temperature_c", static_cast<int>(m[4]) - (pci ? 40 : 64), "degC");
    } else if (m[0] == 0x24) {
        add("vehicle_speed_kph", m[2], "km/h");
    } else if (m[0] == 0xe4) {
        add("engine_rpm", m[1] * 32.0, "rpm");
        add("manifold_absolute_pressure_kpa", m[2] * 0.1217 * 0.4911542 * 6.894757, "kPa");
    }
    result.disposition = DecodeDisposition::Decoded;
    return result;
}
} // namespace chrysler

// SPDX-License-Identifier: GPL-3.0-only
#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <vector>

namespace chrysler {

using Bytes = std::vector<std::uint8_t>;
inline constexpr char kNusServiceUuid[] = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
inline constexpr char kNusWriteUuid[] = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";
inline constexpr char kNusNotifyUuid[] = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E";

enum class Bus : std::uint8_t { Internal = 0, Ccd = 1, SciPcm = 2, SciTcm = 3, Pci = 4 };

struct Frame {
    Bytes raw; // Complete original wire frame, including sync/length/checksum.
    bool from_scanner = false;
    std::uint8_t bus = 0;
    std::uint8_t command = 0;
    std::uint8_t mode = 0;
    Bytes payload;
};

enum class ParseEventKind { Packet, Noise, InvalidLength, ChecksumMismatch, Truncated, TransportLoss };
struct ParseEvent {
    ParseEventKind kind = ParseEventKind::Packet;
    Frame frame; // Populated only for Packet.
    Bytes bytes; // Original rejected/pending bytes for non-Packet events.
    std::size_t lost_bytes = 0; // TransportLoss: caller-observed loss; zero means unknown.
};

// One parser per BLE connection. All callbacks are synchronous; enqueue quickly.
// BLE notifications are arbitrary chunks of one continuous byte stream.
class StreamParser {
public:
    using Sink = std::function<void(const ParseEvent&)>;
    explicit StreamParser(Sink sink, std::size_t max_packet_size = 4096);
    void feed(const std::uint8_t* bytes, std::size_t size);
    void feed(const Bytes& bytes) { feed(bytes.data(), bytes.size()); }
    void finish(); // Disconnect/stop: report partial frame, then clear it.
    void notify_loss(std::size_t lost_bytes = 0); // Never splice across a known gap.
    std::size_t pending_bytes() const { return pending_.size(); }
private:
    void drain();
    void emit(ParseEventKind kind, const Bytes& bytes);
    Sink sink_;
    std::size_t maximum_;
    Bytes pending_;
};

std::uint8_t frame_checksum(const std::uint8_t* bytes, std::size_t size);
std::optional<Frame> parse_frame(const Bytes& bytes);

enum class ReadRequest { Handshake, Status, HardwareFirmwareInfo, Timestamp, BatteryVoltage };
// Only scanner-internal reads. This library exposes no vehicle TX/flash encoder.
Bytes build_read_request(ReadRequest request);
bool is_v2_handshake(const Frame& frame);

struct ReceivedMessage {
    Bus bus = Bus::Internal;
    bool high_speed = false;
    std::uint32_t scanner_ms = 0; // Big-endian uint32 since scanner boot; wraps ~49.7 days.
    Bytes raw_bus_bytes; // ID/header and checksum/CRC are retained exactly.
};
std::optional<ReceivedMessage> decode_receive(const Frame& frame);

struct ScannerStatus {
    std::uint32_t uptime_ms = 0;
    std::uint32_t ram_used_bytes = 0;
    std::uint16_t battery_mv = 0;
    std::uint8_t ccd_settings = 0, pci_settings = 0, sci_settings = 0;
    std::uint32_t ccd_rx = 0, ccd_tx = 0, pci_rx = 0, pci_tx = 0, sci_rx = 0, sci_tx = 0;
};
std::optional<ScannerStatus> decode_status(const Frame& frame);
// Use a freshly read Status after each BLE connection. CCD/PCI only; sets enable
// bit 7 while preserving all other settings. nullopt if already enabled/unsupported.
// Wait for settings echo and read back Status before declaring the bus enabled.
std::optional<Bytes> build_receive_enable_request(Bus bus, const ScannerStatus& status);

// A profile is explicit: these upstream formulas do not certify any vehicle/year.
enum class DecoderProfile { None, UpstreamBroadcast2023 };
struct Metric {
    std::string id;
    double value = 0;
    std::string unit;
};
enum class DecodeDisposition { Decoded, ProfileDisabled, UnsupportedMessage, UnsupportedMode,
                               InvalidMessageLength, InvalidBusChecksum };
struct DecodeResult {
    DecodeDisposition disposition = DecodeDisposition::UnsupportedMessage;
    std::vector<Metric> metrics;
};
// Only passive CCD/PCI broadcasts; no SCI active-query interpretation is guessed.
DecodeResult decode_metrics(const ReceivedMessage& message, DecoderProfile profile);

} // namespace chrysler

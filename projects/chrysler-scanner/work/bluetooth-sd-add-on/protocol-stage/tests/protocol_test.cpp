// SPDX-License-Identifier: GPL-3.0-only
#include "chrysler/protocol.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>

using namespace chrysler;
namespace {
unsigned assertions = 0;
#define CHECK(value) do { ++assertions; if (!(value)) { std::cerr << __LINE__ << ": " #value "\n"; std::abort(); } } while (false)
void near(double a, double b) { CHECK(std::abs(a - b) < 0.0000001); }
Bytes framed(std::uint8_t route, std::uint8_t mode, const Bytes& payload) {
    Bytes b{0x3d, static_cast<std::uint8_t>((payload.size() + 2) >> 8),
            static_cast<std::uint8_t>(payload.size() + 2), route, mode};
    b.insert(b.end(), payload.begin(), payload.end());
    unsigned sum = 0;
    for (auto byte : b) sum += byte;
    b.push_back(static_cast<std::uint8_t>(sum));
    return b;
}
const Bytes handshake{0x3d,0,0x11,0x81,0,0x43,0x48,0x52,0x59,0x53,0x4c,0x45,0x52,0x53,0x43,0x41,0x4e,0x4e,0x45,0x52,0x45};
std::size_t count(const std::vector<ParseEvent>& events, ParseEventKind kind) {
    return static_cast<std::size_t>(std::count_if(events.begin(), events.end(), [&](const auto& e){return e.kind == kind;}));
}
ReceivedMessage message(Bus bus, Bytes bytes) { return {bus, false, 0x12345678, std::move(bytes)}; }
void metric(const DecodeResult& r, const char* id, double value, const char* unit) {
    CHECK(r.disposition == DecodeDisposition::Decoded);
    auto i = std::find_if(r.metrics.begin(), r.metrics.end(), [&](const auto& m){return m.id == id;});
    CHECK(i != r.metrics.end()); near(i->value, value); CHECK(i->unit == unit);
}
void protocol_examples() {
    CHECK(build_read_request(ReadRequest::HardwareFirmwareInfo) == Bytes({0x3d,0,2,4,1,0x44}));
    CHECK(build_read_request(ReadRequest::Handshake) == Bytes({0x3d,0,2,1,0,0x40}));
    auto h = parse_frame(handshake); CHECK(h); CHECK(is_v2_handshake(*h)); CHECK(h->raw == handshake);
    CHECK(h->payload.size() == 15);
    auto wrong = *h; wrong.from_scanner = false; CHECK(!is_v2_handshake(wrong));
    wrong = *h; wrong.payload.push_back(0); CHECK(!is_v2_handshake(wrong));
    wrong = *h; wrong.bus = 1; CHECK(!is_v2_handshake(wrong));
    auto truncated = handshake; truncated.pop_back(); CHECK(!parse_frame(truncated));
    auto extra = handshake; extra.push_back(0); CHECK(!parse_frame(extra));
    auto bad = handshake; bad.back() ^= 1; CHECK(!parse_frame(bad));
    for (auto request : {ReadRequest::Handshake, ReadRequest::Status, ReadRequest::HardwareFirmwareInfo,
                         ReadRequest::Timestamp, ReadRequest::BatteryVoltage}) {
        auto f = parse_frame(build_read_request(request)); CHECK(f);
        CHECK(!f->from_scanner && f->bus == 0 && f->command != 6 && f->command != 0xd && f->command != 0xe);
    }
}
void stream_boundaries() {
    for (std::size_t split = 0; split <= handshake.size(); ++split) {
        std::vector<ParseEvent> events;
        StreamParser p([&](const auto& e){events.push_back(e);});
        p.feed(handshake.data(), split); p.feed(handshake.data() + split, handshake.size() - split);
        CHECK(count(events, ParseEventKind::Packet) == 1); CHECK(p.pending_bytes() == 0);
        CHECK(events.back().frame.raw == handshake);
    }
    std::vector<ParseEvent> events;
    StreamParser p([&](const auto& e){events.push_back(e);});
    const auto rx = framed(0xc7, 1, {0,0,0,0x3d,0x10,0x1f,0x40,0x27,0x10,0x65,0x17});
    Bytes together = handshake; together.insert(together.end(), rx.begin(), rx.end());
    for (auto b : together) p.feed(&b, 1);
    CHECK(events.size() == 2); CHECK(events[1].frame.raw == rx);
    CHECK(decode_receive(events[1].frame)->scanner_ms == 0x3d);
}
void corruption_and_loss() {
    std::vector<ParseEvent> events;
    StreamParser p([&](const auto& e){events.push_back(e);}, 256);
    p.feed(Bytes{0xaa,0xbb,0x3d,0,0,0x3d,0xff,0xff});
    auto bad = handshake; bad.back() ^= 0x80;
    p.feed(bad); p.feed(handshake);
    CHECK(count(events, ParseEventKind::InvalidLength) == 2);
    CHECK(count(events, ParseEventKind::ChecksumMismatch) == 1);
    CHECK(count(events, ParseEventKind::Packet) == 1);
    CHECK(events.back().frame.raw == handshake);
    p.feed(handshake.data(), 8); p.finish();
    CHECK(events.back().kind == ParseEventKind::Truncated);
    CHECK(events.back().bytes == Bytes(handshake.begin(), handshake.begin() + 8));
    CHECK(p.pending_bytes() == 0);
    p.feed(handshake.data(), 8); p.notify_loss(97);
    CHECK(events.back().kind == ParseEventKind::TransportLoss && events.back().lost_bytes == 97);
    CHECK(events.back().bytes == Bytes(handshake.begin(), handshake.begin() + 8));
    p.feed(handshake.data() + 8, handshake.size() - 8);
    CHECK(count(events, ParseEventKind::Packet) == 1); // Cannot join across a reported gap.
    p.feed(handshake); CHECK(count(events, ParseEventKind::Packet) == 2);
    p.notify_loss(); CHECK(events.back().lost_bytes == 0);
    p.feed(Bytes{0x3d,0,0xfc});
    for (unsigned i = 0; i < 50000; ++i) {
        const std::uint8_t byte = 0;
        p.feed(&byte, 1); CHECK(p.pending_bytes() <= 256);
    }
    p.finish();
}
void receive_and_status() {
    auto f = parse_frame(framed(0xc7,1,{0x12,0x34,0x56,0x78,0x3d,0xff})); CHECK(f);
    auto rx = decode_receive(*f); CHECK(rx); CHECK(rx->bus == Bus::Pci);
    CHECK(rx->scanner_ms == 0x12345678); CHECK(rx->raw_bus_bytes == Bytes({0x3d,0xff})); CHECK(!rx->high_speed);
    auto changed = *f; changed.mode = 2; CHECK(!decode_receive(changed));
    changed.bus = 2; CHECK(decode_receive(changed)->high_speed);
    changed.mode = 0; CHECK(!decode_receive(changed));
    changed = *f; changed.from_scanner = false; CHECK(!decode_receive(changed));
    changed = *f; changed.bus = 5; CHECK(!decode_receive(changed));
    changed = *f; changed.payload.resize(4); CHECK(!decode_receive(changed));
    Bytes payload(45,0); payload[0]=0x12; payload[1]=0x34; payload[2]=0x56; payload[3]=0x78;
    payload[8]=0x30; payload[9]=0x39; payload[14]=0x13; payload[18]=7; payload[22]=8;
    payload[23]=0x12; payload[27]=9; payload[31]=10; payload[32]=0xe1; payload[36]=11; payload[40]=12;
    auto status_frame = parse_frame(framed(0x82,0,payload)); CHECK(status_frame);
    auto status = decode_status(*status_frame); CHECK(status);
    CHECK(status->uptime_ms == 0x12345678 && status->battery_mv == 12345);
    CHECK(status->ccd_settings == 0x13 && status->pci_settings == 0x12 && status->sci_settings == 0xe1);
    CHECK(status->ccd_rx == 7 && status->ccd_tx == 8 && status->pci_rx == 9 && status->pci_tx == 10 && status->sci_rx == 11 && status->sci_tx == 12);
    CHECK(build_receive_enable_request(Bus::Pci,*status) == Bytes({0x3d,0,3,3,6,0x92,0xdb}));
    auto ccd = parse_frame(*build_receive_enable_request(Bus::Ccd,*status)); CHECK(ccd);
    CHECK(ccd->bus == 0 && ccd->command == 3 && ccd->mode == 2 && ccd->payload == Bytes({0x93}));
    status->pci_settings |= 0x80; CHECK(!build_receive_enable_request(Bus::Pci,*status));
    CHECK(!build_receive_enable_request(Bus::SciPcm,*status)); CHECK(!build_receive_enable_request(Bus::SciTcm,*status));
    status_frame->payload.push_back(0); CHECK(!decode_status(*status_frame));
}
void selected_values() {
    // Synthetic frames exercise formulas pinned in upstream C#/Util, not captures from a vehicle.
    const auto profile = DecoderProfile::UpstreamBroadcast2023;
    auto rpm = message(Bus::Pci,{0x10,0x1f,0x40,0x27,0x10,0x65,0x17});
    auto r = decode_metrics(rpm, profile); CHECK(r.metrics.size() == 3);
    metric(r,"engine_rpm",2000,"rpm"); metric(r,"vehicle_speed_kph",78.857856,"km/h");
    metric(r,"manifold_absolute_pressure_kpa",101,"kPa");
    auto engine = message(Bus::Pci,{0xc0,0xe0,0x64,0x7d,0x50,0xdf});
    r = decode_metrics(engine,profile); CHECK(r.metrics.size() == 4);
    metric(r,"battery_voltage_v",14,"V"); metric(r,"oil_pressure_kpa",344.73785,"kPa");
    metric(r,"coolant_temperature_c",85,"degC"); metric(r,"ambient_temperature_c",40,"degC");
    auto ccd = message(Bus::Ccd,{0x0c,0x70,0x64,0x7d,0x50,0xad});
    r=decode_metrics(ccd,profile); metric(r,"battery_voltage_v",14,"V");
    metric(r,"coolant_temperature_c",61,"degC"); metric(r,"ambient_temperature_c",16,"degC");
    r=decode_metrics(message(Bus::Ccd,{0x24,0x3c,0x60,0xc0}),profile);
    metric(r,"vehicle_speed_kph",96,"km/h");
    r=decode_metrics(message(Bus::Ccd,{0xe4,0x1f,0xf0,0xf3}),profile);
    metric(r,"engine_rpm",992,"rpm");
    metric(r,"manifold_absolute_pressure_kpa",240*0.1217*0.4911542*6.894757,"kPa");
    CHECK(decode_metrics(rpm,DecoderProfile::None).disposition == DecodeDisposition::ProfileDisabled);
    rpm.raw_bus_bytes.back() ^= 1;
    CHECK(decode_metrics(rpm,profile).disposition == DecodeDisposition::InvalidBusChecksum);
    CHECK(decode_metrics(rpm,profile).metrics.empty());
    engine.raw_bus_bytes.pop_back();
    CHECK(decode_metrics(engine,profile).disposition == DecodeDisposition::InvalidMessageLength);
    CHECK(decode_metrics(message(Bus::Pci,{0x99,0}),profile).metrics.empty());
    CHECK(decode_metrics(message(Bus::SciPcm,{0xfb,1,0x1f,2,0x40}),profile).metrics.empty());
    ccd.high_speed = true; CHECK(decode_metrics(ccd,profile).disposition == DecodeDisposition::UnsupportedMode);
    ccd.high_speed = false; ccd.raw_bus_bytes[1] ^= 1;
    CHECK(decode_metrics(ccd,profile).disposition == DecodeDisposition::InvalidBusChecksum);
}
} // namespace
int main() {
    protocol_examples(); stream_boundaries(); corruption_and_loss(); receive_and_status(); selected_values();
    std::cout << "protocol/decoder tests passed: " << assertions << " assertions\n";
}

#include "capture_format.hpp"
#include "control_policy.hpp"
#include "producer_gate.hpp"
#include "scanner_state.hpp"
#include <thread>
#include <atomic>
#include "logger_core.hpp"
#include "session_storage.hpp"
#include "chrysler/protocol.hpp"
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>

namespace fs = std::filesystem;
std::string text(const fs::path& p) {
    std::ifstream f(p, std::ios::binary);
    return {std::istreambuf_iterator<char>(f), {}};
}
template <typename F> void throws(F f) {
    bool failed = false;
    try { f(); } catch (const std::exception&) { failed = true; }
    assert(failed);
}
std::uint64_t le(const std::string& s, std::size_t pos, unsigned n) {
    std::uint64_t v = 0;
    for (unsigned i=0;i<n;++i) v |= std::uint64_t(static_cast<unsigned char>(s.at(pos+i))) << (8*i);
    return v;
}
chrysler::Bytes frame(unsigned data_code, unsigned mode, chrysler::Bytes payload = {}) {
    const auto size = payload.size()+2;
    chrysler::Bytes b{0x3d,static_cast<std::uint8_t>(size>>8),static_cast<std::uint8_t>(size),
        static_cast<std::uint8_t>(data_code),static_cast<std::uint8_t>(mode)};
    b.insert(b.end(),payload.begin(),payload.end());
    b.push_back(chrysler::frame_checksum(b.data(),b.size())); return b;
}
void config_tests() {
    const std::string address="scanner_address=12:34:56:78:9a:bc\n";
    const std::string base=address+"decoder_profile=none\n";
    auto c=logger_core::parse_config(address+"decoder_profile=upstream_broadcast_2023\nselected=engine_rpm,battery_voltage_v\n");
    assert(c.upstream_profile && c.enable_pci_rx && !c.enable_ccd_rx);
    assert(logger_core::wanted(c,"engine_rpm") && !logger_core::wanted(c,"coolant_temperature_c"));
    assert(logger_core::parse_config(base+"utc_epoch_at_boot=1760000000\n").utc_epoch_at_boot==1760000000);
    for (const auto& suffix : {"transmit=true\n","flush_ms=0\n","flush_ms=10001\n",
        "auto_start=1\n","selected=guess_rpm\n","selected=engine_rpm,engine_rpm\n",
        "decoder_profile=cummins\n","utc_epoch_at_boot=-1\n","utc_epoch_at_boot=1\n"})
        throws([&]{logger_core::parse_config(base+suffix);});
    throws([&]{logger_core::parse_config(address);});
    throws([&]{logger_core::parse_config(base+"selected=engine_rpm\n");});
    throws([&]{logger_core::parse_config(base+base);});
    throws([]{logger_core::parse_config("scanner_address=00:00:00:00:00:00");});
    throws([]{logger_core::parse_config("scanner_address=12:34:56:78:9A:ZZ");});
    throws([]{logger_core::parse_config(std::string(4097,'x'));});
    assert(logger_core::csv("a,\"b")=="\"a,\"\"b\"");
}
void control_tests() {
    for (auto r : {chrysler::ReadRequest::Handshake,chrysler::ReadRequest::Status,
            chrysler::ReadRequest::HardwareFirmwareInfo,chrysler::ReadRequest::Timestamp,
            chrysler::ReadRequest::BatteryVoltage})
        assert(logger_core::safe_control_request(chrysler::build_read_request(r)));
    for (unsigned route=0;route<8;++route) for(unsigned command=0;command<16;++command)
        for(unsigned mode=0;mode<256;++mode) {
            const bool allowed=logger_core::safe_control_request(frame((route<<4)|command,mode));
            const bool expected=route==0 && ((command==1&&mode==0)||(command==2&&mode==0)||
                (command==4&&mode>=1&&mode<=3));
            assert(allowed==expected);
        }
    chrysler::ScannerStatus status; status.pci_settings=0x35;
    const auto receive=chrysler::build_receive_enable_request(chrysler::Bus::Pci,status);
    assert(receive && logger_core::safe_control_request(*receive));
    assert(chrysler::parse_frame(*receive)->payload.at(0)==0xb5);
    status.pci_settings=0xb5;
    assert(!chrysler::build_receive_enable_request(chrysler::Bus::Pci,status));
    assert(!logger_core::safe_control_request(frame(3,6,{0x35})));
    assert(!logger_core::safe_control_request(frame(3,3,{0x80})));
    assert(!logger_core::safe_control_request(frame(0x16,1,{0,1,2})));
    assert(!logger_core::safe_control_request(frame(0x81,0)));
}
void format_tests() {
    const std::uint8_t data[]{0x00,0x3d,0xff};
    auto b=capture::record(capture::Type::BleChunk,0x12345678,0x1122334455667788ull,
                          0x2233445566778899ull,9,data,3);
    const std::string s(b.begin(),b.end());
    assert(s.size()==43 && s.substr(0,4)=="CBR1" && s[4]==1 && s[5]==1);
    assert(le(s,6,2)==36 && le(s,8,4)==3 && le(s,12,4)==0x12345678);
    assert(le(s,16,8)==0x1122334455667788ull && le(s,24,8)==0x2233445566778899ull);
    assert(le(s,32,4)==9 && static_cast<unsigned char>(s[38])==0xff);
    assert(le(s,39,4)==capture::crc32(b.data(),39));
    assert(capture::crc32(reinterpret_cast<const std::uint8_t*>("123456789"),9)==0xcbf43926u);
    b[36]^=1; assert(le(s,39,4)!=capture::crc32(b.data(),39));
}
void storage_tests(const fs::path& root) {
    capture::SessionStorage store;
    store.start(root.string(),"test_configuration\n");
    const auto directory=store.directory();
    assert(!fs::exists(fs::path(directory)/"closed.ok"));
    throws([&]{store.start(root.string(),"overwrite");});
    const auto wire=frame(0x87,1,{1,2,3,4});
    store.append(capture::Type::BleChunk,123,0,2,wire.data(),wire.size());
    store.row("123,0,100,PCI,none,test,0,unit\n");
    store.flush();
    store.stop("dropped_chunks=2\n");
    assert(!store.active() && fs::exists(fs::path(directory)/"closed.ok"));
    assert(text(fs::path(directory)/"configuration.txt")=="test_configuration\n");
    const auto raw=text(fs::path(directory)/"raw_0001.bin");
    assert(raw.substr(0,8)=="CBSDRAW1" && raw.size()==8+40+wire.size());
    assert(raw.substr(44,wire.size())==std::string(wire.begin(),wire.end()));
    assert(le(raw,raw.size()-4,4)==capture::crc32(reinterpret_cast<const std::uint8_t*>(raw.data()+8),raw.size()-12));
    assert(text(fs::path(directory)/"selected_0001.csv").find("host_us,utc_us,scanner_ms") == 0);
    throws([&]{store.flush();});
    store.start(root.string(),"second");
    assert(store.directory()!=directory);
    const auto abandoned=store.directory();
    store.abandon(); assert(!fs::exists(fs::path(abandoned)/"closed.ok"));
    store.start(root.string(),"third");
    const auto failed=store.directory();
    std::ofstream(fs::path(failed)/"summary.txt")<<"preexisting";
    throws([&]{store.stop("will fail exclusive create");});
    assert(!fs::exists(fs::path(failed)/"closed.ok"));
    std::ofstream(root/"not_directory")<<"preserve me";
    throws([&]{store.start((root/"not_directory").string(),"fail");});
    assert(text(root/"not_directory")=="preserve me");
}
void integrated_parser_storage(const fs::path& root) {
    capture::SessionStorage store; store.start(root.string(),"integration");
    unsigned packets=0,errors=0;
    chrysler::StreamParser parser([&](const chrysler::ParseEvent& e){
        if(e.kind==chrysler::ParseEventKind::Packet) {
            ++packets;store.append(capture::Type::ScannerFrame,50,0,1,e.frame.raw.data(),e.frame.raw.size());
        } else {
            ++errors;store.append(capture::Type::ParserError,50,0,1,e.bytes.data(),e.bytes.size());
        }
    });
    auto a=frame(0x81,0,{'C','H','R','Y','S','L','E','R','S','C','A','N','N','E','R'});
    store.append(capture::Type::BleChunk,40,0,0,a.data(),3);parser.feed(a.data(),3);
    parser.notify_loss(20); // Must not splice the rest of this frame after a lost chunk.
    parser.feed(a.data()+3,a.size()-3); assert(packets==0);
    parser.feed(a.data(),2);parser.feed(a.data()+2,a.size()-2); assert(packets==1);
    auto bad=a;bad.back()^=1;parser.feed(bad); assert(errors>=2);
    parser.feed(a.data(),3);parser.finish(); assert(parser.pending_bytes()==0);
    store.stop("integration_complete\n");
    assert(fs::file_size(fs::path(store.directory())/"raw_0001.bin")>8+40+a.size());
}
void connection_generation_tests(const fs::path& root) {
    logger_core::ScannerState state;
    capture::SessionStorage store; store.start(root.string(), "generation_test");
    const auto old=state.begin_connection();
    auto handshake=frame(0x81,0,{'C','H','R','Y','S','L','E','R','S','C','A','N','N','E','R'});
    chrysler::Bytes payload(45,0); payload[23]=0x80;
    auto status=frame(0x82,0,payload);
    std::uint32_t feed_generation=old;
    unsigned logged=0;
    chrysler::StreamParser parser([&](const chrysler::ParseEvent& event){
        if(event.kind!=chrysler::ParseEventKind::Packet) return;
        ++logged;store.append(capture::Type::ScannerFrame,123,0,0,event.frame.raw.data(),event.frame.raw.size());
        if(chrysler::is_v2_handshake(event.frame)) state.accept_handshake(feed_generation);
        if(auto s=chrysler::decode_status(event.frame)) state.accept_status(feed_generation,*s);
    });
    const auto current=state.begin_connection();
    parser.feed(handshake);parser.feed(status);
    auto snapshot=state.snapshot();
    assert(logged==2 && !snapshot.handshake && !snapshot.status_valid && !snapshot.receive_ready);
    feed_generation=current; parser.feed(handshake);parser.feed(status);
    snapshot=state.snapshot();assert(logged==4 && snapshot.handshake && snapshot.status_valid);
    assert(snapshot.status.pci_settings==0x80);
    state.set_receive_ready(current,true);state.disconnected(old);
    assert(state.snapshot().receive_ready); // An old callback cannot clear new readiness.
    state.set_receive_ready(old,false);assert(state.snapshot().receive_ready);
    state.disconnected(current);assert(!state.snapshot().handshake && !state.snapshot().receive_ready);
    store.stop("generation_test_passed\n");
}
void producer_gate_tests() {
    logger_core::ProducerGate gate;
    { logger_core::ProducerGate::Guard late(gate); assert(!late); }
    gate.open();
    std::atomic<bool> entered{false}, release{false};
    std::thread callback([&]{
        logger_core::ProducerGate::Guard active(gate); assert(active);
        entered=true; while(!release.load()) std::this_thread::yield();
    });
    while(!entered.load()) std::this_thread::yield();
    gate.close(); assert(!gate.quiescent());
    { logger_core::ProducerGate::Guard late(gate); assert(!late); }
    release=true; callback.join(); assert(gate.quiescent());
    gate.open(); { logger_core::ProducerGate::Guard next(gate); assert(next); }
    gate.close(); assert(gate.quiescent());
}
int main() {
    char directory[]="/private/tmp/chrysler-fw-tests-XXXXXX";
    const auto p=::mkdtemp(directory); assert(p);
    const fs::path root(p);
    config_tests();control_tests();format_tests();producer_gate_tests();storage_tests(root/"storage");
    integrated_parser_storage(root/"integration");connection_generation_tests(root/"generation");
    fs::remove_all(root);
    std::cout<<"Firmware host acceptance passed: config/control allowlist/CRC/storage/recovery/parser integration\n";
}

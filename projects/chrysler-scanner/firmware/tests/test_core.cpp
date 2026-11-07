// SPDX-License-Identifier: GPL-3.0-only
#include "core.hpp"
#include "ble_transport.hpp"
#include "board.hpp"
#include "expander.hpp"
#include "rev_d_can.hpp"
#include <cassert>
#include <cstdio>
#include <vector>
using namespace scanner;

struct FakeAw {
    std::array<std::uint8_t,256> regs{};
    std::vector<Register> writes;
    int fail_at=-1, calls=0;
    FakeAw() { regs[0x10]=0x23; }
    bool read(std::uint8_t r,std::uint8_t& v) {
        if(calls++==fail_at) return false;
        v=regs[r]; return true;
    }
    bool write(std::uint8_t r,std::uint8_t v) {
        if(calls++==fail_at) return false;
        if(r==2) assert(v==0);
        if(r==3) assert(passive_p1(v));
        regs[r]=v; writes.push_back({r,v}); return true;
    }
};
void test_expander() {
    FakeAw good; assert(initialize_expander(good));
    assert(good.writes.size()==9);
    assert(good.writes[0].address==2 && good.writes[0].value==0);
    assert(good.writes[1].address==3 && good.writes[1].value==0x80);
    const auto calls=good.calls;
    for(int i=0;i<calls;++i) {
        FakeAw faulty; faulty.fail_at=i;
        assert(!initialize_expander(faulty));
    }
    for(auto reg:aw_startup) {
        FakeAw corrupt=good; corrupt.regs[reg.address]^=1;
        assert(!verify_expander(corrupt,board::p1_safe));
    }
    for(unsigned r=0;r<256;++r) {
        FakeAw io=good; io.writes.clear(); bool configured=false;
        const bool ok=select_receiver(io,r,[&]() {
            configured=true; assert(io.regs[3]==board::p1_safe); return true;
        });
        assert(ok==(r==0 || r==board::rx7 || r==board::rx15));
        assert(configured==ok);
        if(ok) {
            assert(io.writes.size()==2 && io.writes[0].value==board::p1_safe);
            assert(io.regs[3]==(board::p1_safe|r));
        }
    }
    FakeAw baud_fail=good;
    assert(!select_receiver(baud_fail,board::rx7,[](){return false;}));
    assert(baud_fail.regs[3]==board::p1_safe);
    FakeAw selection=good; selection.calls=0;
    assert(select_receiver(selection,board::rx15,[](){return true;}));
    for(int i=0;i<selection.calls;++i) {
        FakeAw failure=good; failure.calls=0; failure.fail_at=i;
        assert(!select_receiver(failure,board::rx15,[](){return true;}));
    }
}

void test_health() {
    Health h;
    assert(!h.poll(0));
    for(unsigned i=0;i<3;++i) h.vote(Worker(i),1);
    assert(!h.poll(1));
    h.vote(Worker::Storage,1); assert(h.poll(1));
    for(std::uint64_t t=10001;t<100000;t+=10000) {
        for(unsigned i=0;i<4;++i) h.vote(Worker(i),t);
        assert(h.poll(t));
    }
    // Safety task itself missed its schedule; fresh worker votes cannot re-arm.
    for(unsigned i=0;i<4;++i) h.vote(Worker(i),130001);
    assert(!h.poll(130001) && h.failed());
    assert(!h.poll(130002));
    for(unsigned missing=0;missing<4;++missing) {
        Health x;
        for(unsigned i=0;i<4;++i) x.vote(Worker(i),1);
        assert(x.poll(1));
        const auto end=Health::lease_us(Worker(missing))+10001;
        for(std::uint64_t t=10001;t<=end;t+=10000) {
            for(unsigned i=0;i<4;++i) if(i!=missing) x.vote(Worker(i),t);
            x.poll(t);
        }
        assert(x.failed());
        for(unsigned i=0;i<4;++i) x.vote(Worker(i),end+1);
        assert(!x.poll(end+1));
    }
    Health explicit_fault; explicit_fault.fail(); assert(!explicit_fault.poll(0));
}
void test_policy() {
    std::uint8_t p[8]{};
    for(unsigned route=0;route<256;++route) for(unsigned mode=0;mode<256;++mode) {
        p[3]=route; p[4]=mode;
        const auto a=classify(p,6,true,false);
        const bool allowed=(route==1 && mode==0)||(route==4 && (mode==0x7f||mode==0x80||mode==0x84));
        assert((a!=Action::Deny)==allowed);
    }
    p[3]=4; p[4]=0x81;
    for(unsigned v=0;v<256;++v) {
        p[5]=v; assert((classify(p,7,true,false)==Action::Log)==(v<=1));
        assert((classify(p,7,false,false)==Action::Log)==(v==0));
        assert((classify(p,7,true,true)==Action::Log)==(v==0));
    }
    p[4]=0x82;
    for(unsigned r=0;r<256;++r) for(unsigned b=0;b<256;++b) {
        p[5]=r; p[6]=b;
        assert((classify(p,8,true,false)==Action::Sci)==(r<=2 && b<=3));
    }
    assert(board::p0_safe==0 && board::p1_safe==0x80);
    assert(((board::rx7|board::rx15)&0xcf)==0); // No TX or bias/programming bits.
}
void test_burst_and_edges() {
    Burst burst(Bus::Ccd);
    unsigned count=0;
    auto sink=[&](const Capture& c) {
        ++count; assert(c.flags==ChecksumOk && c.size==3 && c.data[0]==1);
    };
    // A suffix can itself have a valid additive checksum: it is still not a
    // complete frame after startup, queue loss or a known UART error.
    for(unsigned recovery=0;recovery<4;++recovery) {
        burst.gap();
        burst.append(1,100); burst.append(2,100); burst.append(3,100);
        assert(burst.finish(sink)); assert(count==recovery);
        burst.append(1,200); burst.append(2,200); burst.append(3,200);
        assert(!burst.finish(sink)); assert(count==recovery+1);
    }
    for(unsigned i=0;i<max_data+1;++i) burst.append(0,300);
    assert(burst.finish(sink)); assert(count==4);
    assert(continuous_edge(10,0,20,1));
    assert(!continuous_edge(10,1,20,1));
    assert(!continuous_edge(20,0,20,1));
    assert(!continuous_edge(20,0,19,1));
    Burst sci(Bus::Sci);
    std::vector<Capture> captured;
    for(auto pin:{7,15}) {
        sci.source(pin,pin==7?1:3);
        sci.append(0xaa,100); sci.finish([&](const Capture&){assert(false);});
        sci.append(0xbb,200); sci.finish([&](const Capture& c){captured.push_back(c);});
    }
    assert(captured.size()==2);
    for(unsigned i=0;i<2;++i) {
        std::uint8_t frame[max_wire]; auto n=capture_wire(captured[i],frame);
        assert(n==13 && frame[4]==0x92 && frame[9]==(i?15:7) && frame[10]==(i?3:1));
        assert(frame[11]==0xbb);
    }
    BurstBatch batch(Bus::Ccd);
    batch.timeout(); // Establish initial boundary.
    for(auto byte:{1,2,3}) batch.append(byte,100);
    batch.timeout(); // SDK queues DATA(timeout) first.
    assert(batch.gap()==2); // Then FRAME_ERR: revoke pending completion.
    batch.publish([](const Capture&){assert(false);});
    for(auto byte:{1,2,3}) batch.append(byte,200);
    assert(batch.timeout()==1); // The first post-error suffix is quarantined.
    batch.publish([](const Capture&){assert(false);});
    for(auto byte:{1,2,3}) batch.append(byte,300);
    batch.timeout(); unsigned good=0;
    batch.publish([&](const Capture&){++good;}); assert(good==1);
    batch.gap(); // A read deficit returns immediately, ignoring suspect timeout.
    for(auto byte:{1,2,3}) batch.append(byte,400);
    assert(batch.timeout()==1);
    batch.publish([](const Capture&){assert(false);});
}
void test_parser() {
    std::uint8_t packet[max_wire];
    auto n=wire(packet,4,0x80,nullptr,0);
    assert(n==6 && packet[5]==0xc3);
    Parser p;
    unsigned received=0;
    auto sink=[&](const std::uint8_t* bytes,std::size_t size) {
        ++received; assert(size==6 && bytes[3]==4 && bytes[4]==0x80);
    };
    std::uint64_t t=0;
    for(unsigned repeat=0;repeat<100;++repeat) for(std::size_t i=0;i<n;++i) p.feed(packet[i],++t,sink);
    assert(received==100);
    const std::uint8_t bad[]{0,0xff,0x3d,0xff,0xff,0x3d,0,0,0x3d,0,2,4,0x80,0};
    for(auto b:bad) p.feed(b,++t,sink);
    for(std::size_t i=0;i<n;++i) p.feed(packet[i],++t,sink);
    assert(received==101 && p.errors>=3);
    p.feed(0x3d,++t,sink); p.feed(0,++t,sink);
    t+=100001;
    for(std::size_t i=0;i<n;++i) p.feed(packet[i],++t,sink);
    assert(received==102);
    p.feed(0x3d,++t,sink); p.feed(1,++t,sink); p.feed(0,++t,sink);
    for(std::size_t i=0;i<n;++i) p.feed(packet[i],++t,sink);
    assert(received==102);
    p.expire(t+100001,sink); assert(received==103);
    // Deterministic malformed stream exercises buffer bounds and resync.
    std::uint32_t random=123;
    for(unsigned i=0;i<100000;++i) {
        random=random*1664525+1013904223;
        p.feed(random>>24,++t,[](const std::uint8_t* b,std::size_t size){
            assert(size>=6 && size<=max_wire && sum(b,size-1)==b[size-1]);
        });
    }
}
void test_stop_completion() {
    StorageGate gate;
    gate.request(true); gate.request(false); // Stop wins before mount claim.
    assert(!gate.claim(true) && !gate.busy());
    gate.request(true); assert(gate.claim(true)); // Mount wins before stop.
    gate.request(false); assert(gate.busy() && !gate.requested());
    assert(!gate.claim(true)); // No second start while mount/close is active.
    gate.complete(); assert(!gate.busy() && !gate.claim(true));
    for(unsigned failed=0;failed<4;++failed) {
        bool busy=true; unsigned step=0;
        complete_stop([&]() { assert(busy && step++==0); return failed!=1; },
            [&](bool) { assert(busy && step++==1); return failed!=2; },
            [&]() { assert(busy && step++==2); return failed!=3; },
            [&](bool ok) { assert(busy && step++==3); assert(ok==(failed==0)); busy=false; });
        assert(!busy && step==4);
    }
}
void test_vpw() {
    const std::uint8_t data[]{0x68,0x6a,0xf1,0x01};
    assert(pci_crc(reinterpret_cast<const std::uint8_t*>("123456789"),9)==0x4b);
    std::vector<std::uint8_t> frame(data,data+4); frame.push_back(pci_crc(data,4));
    unsigned count=0;
    auto sink=[&](const Capture& c) {
        ++count; assert(c.bus==Bus::Pci && c.flags==ChecksumOk && c.size==frame.size());
        assert(std::memcmp(c.data.data(),frame.data(),frame.size())==0);
    };
    Vpw decoder;
    std::uint64_t t=1000;
    decoder.pulse(true,200,t,sink);
    bool active=false;
    for(auto byte:frame) for(unsigned bit=0;bit<8;++bit) {
        const bool one=(byte>>(7-bit))&1;
        const auto duration=(active?one:!one)?64:128;
        t+=duration; decoder.pulse(active,duration,t,sink); active=!active;
    }
    decoder.idle(t+281,t,sink); assert(count==1);
    decoder.idle(t+999,t,sink); assert(count==1);
    // Noise, incomplete octets and overlength must not become validated frames.
    decoder.pulse(true,200,t,sink); decoder.pulse(false,10,t+10,sink);
    decoder.idle(t+1000,t+10,sink); assert(count==1);
    decoder.pulse(true,200,t,sink); decoder.pulse(false,128,t+128,sink);
    decoder.idle(t+1000,t+128,sink); assert(count==1);
    decoder.reset();
    decoder.pulse(true,200,t,[](const Capture&){assert(false);});
    for(unsigned i=0;i<104;++i) decoder.pulse(i%2,64,t+i*64,[](const Capture&){assert(false);});
    decoder.idle(t+10000,t+104*64,[](const Capture&){assert(false);});
}
void test_journal() {
    assert(crc32(reinterpret_cast<const std::uint8_t*>("123456789"),9)==0xcbf43926);
    Capture c; c.bus=Bus::Ccd; c.us=123456; c.flags=ChecksumOk;
    c.size=3; c.data[0]=1; c.data[1]=2; c.data[2]=3;
    std::uint8_t frame[max_wire], record[max_wire+40];
    auto n=capture_wire(c,frame);
    assert(n==13 && frame[3]==0x97 && frame[4]==1 && frame[8]==123);
    const auto r=journal(record,2,17,c.us,4,frame,n);
    assert(r==n+40 && record[6]==36 && record[12]==17 && record[32]==4);
    const auto crc=crc32(record,r-4);
    for(unsigned i=0;i<4;++i) assert(record[r-4+i]==std::uint8_t(crc>>(8*i)));
    c.flags=Raw|Truncated; capture_wire(c,frame); assert(frame[4]==0x86);
    c.size=max_data; assert(capture_wire(c,frame)==max_capture_wire);
    c.size=max_data+1; assert(capture_wire(c,frame)==0);
}
void test_ble_command_generation() {
    std::uint32_t generation = 1;
    unsigned commands = 0;
    const auto current = [&] { return generation; };
    const auto sink = [&](const std::uint8_t*, std::size_t) { ++commands; ++generation; };
    scanner_ble::CommandStream stream(generation);
    scanner_ble::Chunk chunk{};
    chunk.generation = generation;
    const std::uint8_t start = 1;
    const auto size = wire(chunk.data, 4, 0x81, &start, 1);
    std::memcpy(chunk.data + size, chunk.data, size);
    chunk.size = 2 * size;
    stream.feed(chunk, [] { return 1000; }, current, sink);
    // A disconnect after the first command invalidates the rest of the chunk.
    assert(commands == 1);
    assert(stream.reset_if_changed(generation));
    stream.feed(chunk, [] { return 2000; }, current, sink);
    assert(commands == 1);

    // A valid frame hidden behind a false header can be recovered on parser
    // expiry, but never dispatched after its connection generation changed.
    chunk.generation = generation;
    std::memmove(chunk.data + 3, chunk.data, size);
    chunk.data[0] = 0x3d;
    chunk.data[1] = 0;
    chunk.data[2] = 30;
    chunk.size = 3 + size;
    stream.feed(chunk, [] { return 3000; }, current, sink);
    ++generation;
    stream.expire(104000, current, sink);
    assert(commands == 1);
    assert(stream.reset_if_changed(generation));
    chunk.generation = generation;
    chunk.size = wire(chunk.data, 4, 0x81, &start, 1);
    stream.feed(chunk, [] { return 105000; }, current, sink);
    assert(commands == 2);
}
void test_can_diagnostic_boundary() {
    using can_diag::supported;
    for (unsigned service=0; service<256; ++service) {
        for (unsigned pid=0; pid<256; ++pid) {
            constexpr std::array<unsigned,11> pids{0,1,4,5,0xb,0xc,0xd,0xf,0x11,0x20,0x40};
            bool allowed=(service==3 && pid==0) || (service==9 && pid==2);
            if (service==1) for (auto value:pids) allowed=allowed || pid==value;
            assert(supported(service,pid)==allowed);
        }
    }
    Capture capture{};
    capture.bus=Bus::Can;
    capture.size=6;
    capture.data[3]=0x7e;
    std::uint8_t bytes[max_wire]{};
    assert(capture_wire(capture,bytes)==16);
    assert(bytes[3]==0xd7 && bytes[4]==0xa0);
}

int main() {
    ControlLease lease;
    assert(lease.acquire(2,1));assert(!lease.acquire(1,2));
    lease.usb_stop(3);assert(lease.owner(4)==1);assert(!lease.acquire(2,5));
    lease.release(2);assert(lease.owner(6)==1);lease.release(1);assert(lease.acquire(2,7));
    assert(lease.owner(10000008)==0);assert(lease.acquire(1,10000009));
    test_ble_command_generation();
    test_can_diagnostic_boundary();
    test_expander(); test_health(); test_policy(); test_burst_and_edges(); test_parser(); test_stop_completion(); test_vpw(); test_journal();
    puts("PASS: expander faults, health latch, passive policy, UART error batches, SCI provenance, PCI gaps, stop/mount fencing, BLE epoch invalidation, framing/fuzz, VPW, journal CRC");
}

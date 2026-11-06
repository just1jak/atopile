// SPDX-License-Identifier: GPL-3.0-only
// Protocol/checksum and VPW symbol conventions derived from Laszlo Daniel's
// ChryslerScanner (c7229f288e5b3c3be8cb6123bb5958085aa0117c). See SOURCES.md.
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <atomic>

namespace scanner {
constexpr std::size_t max_data=256, max_wire=max_data+10;
enum class Bus : std::uint8_t { Internal=0, Ccd=1, Sci=2, Pci=4 };
enum Flag : std::uint8_t { ChecksumOk=1, Raw=2, Truncated=4, UartError=8 };
struct Capture {
    std::uint64_t us=0;
    std::uint32_t sequence=0;
    Bus bus=Bus::Internal;
    std::uint8_t flags=0;
    std::uint16_t size=0;
    std::uint8_t sci_pin=0, sci_speed=0;
    std::array<std::uint8_t,max_data> data{};
};
inline std::uint8_t sum(const std::uint8_t* p,std::size_t n) {
    std::uint8_t s=0; for(std::size_t i=0;i<n;++i) s+=p[i]; return s;
}
enum class Action { Deny, Handshake, Capabilities, Status, Log, Sci };
// Caller serializes request/claim/complete and status snapshots with one lock.
// Atomic reads allow the capture publisher to check admission without that lock.
class StorageGate {
    std::atomic<bool> requested_{false},busy_{false};
public:
    bool requested() const { return requested_.load(); }
    bool busy() const { return busy_.load(); }
    void request(bool value) { requested_=value; }
    void toggle() { requested_=!requested_.load(); }
    bool claim(bool eligible) {
        if(!eligible || !requested() || busy()) return false;
        busy_=true; return true;
    }
    void complete() { busy_=false; }
};
inline Action classify(const std::uint8_t* p,std::size_t size,bool ready,bool fault) {
    if(size<6) return Action::Deny;
    const auto route=p[3], mode=p[4]; const auto n=size-6;
    if(route==1 && mode==0 && n==0) return Action::Handshake;
    if(route==4 && n==0 && mode==0x7f) return Action::Capabilities;
    if(route==4 && n==0 && mode==0x80) return Action::Status;
    if(route==4 && mode==0x81 && n==1 && p[5]==0) return Action::Log; // Always permit safe stop.
    if(route!=4 || !ready || fault) return Action::Deny;
    if(mode==0x81 && n==1 && p[5]<=1) return Action::Log;
    if(mode==0x82 && n==2 && p[5]<=2 && p[6]<=3) return Action::Sci;
    return Action::Deny;
}
inline std::uint8_t pci_crc(const std::uint8_t* p,std::size_t n) {
    std::uint8_t c=0xff;
    for(std::size_t i=0;i<n;++i) {
        c^=p[i];
        for(unsigned b=0;b<8;++b) c=static_cast<std::uint8_t>((c<<1)^((c&0x80)?0x1d:0));
    }
    return c^0xff;
}
inline void be32(std::uint8_t* p,std::uint32_t v) {
    for(unsigned i=0;i<4;++i) p[i]=v>>(24-8*i);
}
inline std::size_t wire(std::uint8_t* out,std::uint8_t route,std::uint8_t mode,
                        const std::uint8_t* data,std::size_t n) {
    if(n>max_data+4) return 0;
    out[0]=0x3d; out[1]=(n+2)>>8; out[2]=n+2; out[3]=route; out[4]=mode;
    if(n) std::memcpy(out+5,data,n);
    out[n+5]=sum(out,n+5); return n+6;
}
inline std::size_t capture_wire(const Capture& c,std::uint8_t* out) {
    const bool sci=c.bus==Bus::Sci;
    if(c.size>c.data.size()-(sci?2:0)) return 0;
    std::uint8_t payload[max_data+4]; be32(payload,static_cast<std::uint32_t>(c.us/1000));
    if(sci) { payload[4]=c.sci_pin; payload[5]=c.sci_speed; }
    std::memcpy(payload+(sci?6:4),c.data.data(),c.size);
    // Only validated complete CCD/PCI frames use legacy RX mode 1. Mode 0x80+
    // is an explicit Rev C raw/error extension, never a claimed valid bus frame.
    return wire(out,0x87|(static_cast<std::uint8_t>(c.bus)<<4),
        sci?0x92:c.flags==ChecksumOk?1:static_cast<std::uint8_t>(0x80|c.flags),payload,c.size+(sci?6:4));
}

// Unknown prefixes (startup, route changes and overflow) stay quarantined until
// a real UART timeout delimiter. A checksum-valid suffix is not a whole frame.
class Burst {
    Capture c_{};
    bool discard_=true, saw_=false;
public:
    explicit Burst(Bus bus) { c_.bus=bus; }
    void gap() { c_.size=0; discard_=true; saw_=false; }
    void source(std::uint8_t pin,std::uint8_t speed) { gap(); c_.sci_pin=pin; c_.sci_speed=speed; }
    bool append(std::uint8_t byte,std::uint64_t now) {
        saw_=true;
        if(discard_) return true;
        const auto limit=max_data-(c_.bus==Bus::Sci?2:0);
        if(c_.size==limit) { c_.size=0; discard_=true; return false; }
        if(!c_.size) c_.us=now;
        c_.data[c_.size++]=byte; return true;
    }
    template<class Sink> bool finish(Sink sink) {
        const bool lost=discard_ && saw_;
        if(c_.size && !discard_) {
            c_.flags=c_.bus==Bus::Ccd && c_.size>=2 &&
                sum(c_.data.data(),c_.size-1)==c_.data[c_.size-1]?ChecksumOk:Raw;
            sink(c_);
        }
        c_.size=0; discard_=false; saw_=false;
        return lost;
    }
};

// Hold timeout-completed bursts until the entire bounded driver event batch has
// been examined. IDF can queue DATA(timeout) before its FRAME_ERR notification.
class BurstBatch {
    Burst burst_;
    std::array<Capture,16> pending_{};
    unsigned used_=0;
public:
    explicit BurstBatch(Bus bus):burst_(bus) {}
    unsigned gap() { const auto lost=used_+1; used_=0; burst_.gap(); return lost; }
    void source(std::uint8_t pin,std::uint8_t speed) { used_=0; burst_.source(pin,speed); }
    bool append(std::uint8_t byte,std::uint64_t now) { return burst_.append(byte,now); }
    unsigned timeout() {
        bool overflow=false;
        const bool lost=burst_.finish([&](const Capture& c) {
            if(used_==pending_.size()) overflow=true;
            else pending_[used_++]=c;
        });
        return overflow?gap()+1:unsigned(lost);
    }
    template<class Sink> void publish(Sink sink) {
        for(unsigned i=0;i<used_;++i) sink(pending_[i]);
        used_=0;
    }
};

inline bool continuous_edge(std::uint64_t before,std::uint8_t level,
                            std::uint64_t after,std::uint8_t next) {
    return after>before && next<=1 && level<=1 && level!=next;
}

// Bounded incremental framing. Rescan after corrupt checksum/length; discard
// incomplete input after a 100 ms inter-byte gap instead of splicing sessions.
class Parser {
    std::array<std::uint8_t,max_wire> data_{};
    std::size_t used_=0;
    std::uint64_t last_=0;
public:
    std::uint32_t errors=0;
    void clear() { used_=0; }
    template<class Sink> void expire(std::uint64_t now,Sink sink) {
        if(!used_ || now-last_<=100000) return;
        ++errors;
        // Recover complete replies/commands hidden behind a truncated false
        // head, rather than discarding an otherwise valid packet with it.
        for(std::size_t offset=1;offset+6<=used_;) {
            const auto size=(std::size_t(data_[offset+1])<<8)+data_[offset+2]+4;
            if(data_[offset]==0x3d && size>=6 && size<=max_wire && offset+size<=used_ &&
               sum(data_.data()+offset,size-1)==data_[offset+size-1]) {
                sink(data_.data()+offset,size); offset+=size;
            } else ++offset;
        }
        clear();
    }
    template<class Sink> void feed(std::uint8_t byte,std::uint64_t now,Sink sink) {
        expire(now,sink);
        last_=now;
        if(used_==data_.size()) { clear(); ++errors; }
        data_[used_++]=byte;
        for(;;) {
            while(used_ && data_[0]!=0x3d) discard();
            if(used_<3) return;
            const std::size_t size=(std::size_t(data_[1])<<8)+data_[2]+4;
            if(size<6 || size>data_.size()) { discard(); ++errors; continue; }
            if(used_<size) return;
            if(sum(data_.data(),size-1)!=data_[size-1]) { discard(); ++errors; continue; }
            sink(data_.data(),size);
            used_-=size;
            std::memmove(data_.data(),data_.data()+size,used_);
        }
    }
private:
    void discard() { --used_; std::memmove(data_.data(),data_.data()+1,used_); }
};

// Completion publication must be last, including error paths. The actual SD
// adapter uses this ordering so status cannot advertise safe removal mid-flush.
template<class Drain,class Close,class Unmount,class Done>
void complete_stop(Drain drain,Close close,Unmount unmount,Done done) {
    const bool drained=drain();
    const bool closed=close(drained);
    const bool unmounted=unmount();
    done(drained && closed && unmounted);
}

enum class Worker : unsigned { Control, Acquisition, Usb, Storage, Count };
// Caller serializes access. Faults latch until reboot, including a delayed safety
// task: it must not resume edges after the external watchdog could have expired.
class Health {
    std::array<std::uint64_t,4> seen_{};
    std::uint8_t ready_=0;
    std::uint64_t last_poll_=0;
    bool started_=false, fault_=false;
public:
    static constexpr std::uint64_t lease_us(Worker w) {
        // SD initialization, erase/program and fsync legitimately block longer
        // than a capture loop. This bounds the allowed I/O operation, not an
        // independent timer that can keep renewing a stalled worker's vote.
        return w==Worker::Storage?2000000:40000;
    }
    void vote(Worker w,std::uint64_t now) { const auto i=unsigned(w); seen_[i]=now; ready_|=1u<<i; }
    void fail() { fault_=true; }
    bool failed() const { return fault_; }
    bool poll(std::uint64_t now) {
        if(fault_) return false;
        if(ready_!=15) return false;
        if(started_ && now-last_poll_>20000) fault_=true;
        for(unsigned i=0;i<seen_.size();++i) if(now-seen_[i]>lease_us(Worker(i))) fault_=true;
        last_poll_=now; started_=true;
        return !fault_;
    }
};

// Receive-only J1850 VPW state machine. Durations describe the level that just
// ended. No TX/arbitration path. Edge loss and overlength discard until next SOF.
class Vpw {
    Capture c_{}; unsigned bits_=0; bool in_=false, ifr_=false;
public:
    void reset() { c_={}; bits_=0; in_=false; ifr_=false; }
    template<class Sink> void pulse(bool active,std::uint32_t duration,
                                   std::uint64_t end,Sink sink) {
        if(!in_) {
            if(active && duration>=164 && duration<=239) {
                reset(); in_=true; c_.bus=Bus::Pci; c_.us=end-duration;
            }
            return;
        }
        if(!active && duration>=164) {
            if(!ifr_) { finish(sink); ifr_=true; }
            return;
        }
        if(ifr_) { reset(); pulse(active,duration,end,sink); return; }
        if(duration<35 || duration>163) { reset(); return; }
        if(c_.size==12) { reset(); return; }
        const bool one=active?duration<=96:duration>=97;
        c_.data[c_.size]|=one<<(7-bits_);
        if(++bits_==8) { bits_=0; ++c_.size; }
    }
    template<class Sink> void idle(std::uint64_t now,std::uint64_t last_edge,Sink sink) {
        if(in_ && now-last_edge>=281) { if(!ifr_) finish(sink); reset(); }
    }
private:
    template<class Sink> void finish(Sink sink) {
        if(c_.size && bits_==0) {
            c_.flags=(c_.size>=2 && pci_crc(c_.data.data(),c_.size-1)==c_.data[c_.size-1])?ChecksumOk:Raw;
            sink(c_);
        }
    }
};

// CBSDRAW1/CBR1 journal envelope reused from the archived logger. Type 2 payload
// contains the exact USB scanner frame; type 4 is UTF-8 lifecycle/status text.
inline std::uint32_t crc32(const std::uint8_t* p,std::size_t n) {
    std::uint32_t c=0xffffffff;
    for(std::size_t i=0;i<n;++i) {
        c^=p[i]; for(unsigned b=0;b<8;++b) c=(c>>1)^(0xedb88320u&(0u-(c&1)));
    }
    return ~c;
}
inline void le(std::uint8_t* p,std::uint64_t x,unsigned n) { for(unsigned i=0;i<n;++i) p[i]=x>>(i*8); }
inline std::size_t journal(std::uint8_t* out,std::uint8_t type,std::uint32_t sequence,
        std::uint64_t us,std::uint32_t lost,const std::uint8_t* p,std::size_t n) {
    if(n>max_wire) return 0;
    std::memset(out,0,36); std::memcpy(out,"CBR1",4); out[4]=type; out[6]=36;
    le(out+8,n,4); le(out+12,sequence,4); le(out+16,us,8); le(out+32,lost,4);
    if(n) std::memcpy(out+36,p,n);
    le(out+36+n,crc32(out,36+n),4); return n+40;
}
}

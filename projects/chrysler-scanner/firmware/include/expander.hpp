// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "board.hpp"
#include <array>
#include <cstdint>
namespace scanner {
struct Register { std::uint8_t address, value; };
constexpr std::array<Register,9> aw_startup{{
    {2,board::p0_safe},{3,board::p1_safe},{6,0xff},{7,0xff},
    {0x12,0xff},{0x13,0xff},{0x11,0x10},{4,0},{5,0}
}};
inline bool passive_p1(std::uint8_t p1) {
    return p1==board::p1_safe || p1==(board::p1_safe|board::rx7) ||
           p1==(board::p1_safe|board::rx15);
}
template<class Io> bool verify_expander(Io& io,std::uint8_t p1) {
    if(!passive_p1(p1)) return false;
    for(auto reg:aw_startup) {
        if(reg.address==3) reg.value=p1;
        std::uint8_t actual;
        if(!io.read(reg.address,actual) || actual!=reg.value) return false;
    }
    return true;
}
template<class Io> bool initialize_expander(Io& io) {
    std::uint8_t id=0;
    if(!io.read(0x10,id) || id!=0x23) return false;
    // Latches precede mode/direction; no transient high programming/TX bits.
    for(auto reg:aw_startup) if(!io.write(reg.address,reg.value)) return false;
    return verify_expander(io,board::p1_safe);
}
template<class Io,class Configure> bool select_receiver(Io& io,std::uint8_t route,Configure configure) {
    if(route!=0 && route!=board::rx7 && route!=board::rx15) return false;
    const auto p1=static_cast<std::uint8_t>(board::p1_safe|route);
    if(!passive_p1(p1)) return false;
    // A distinct transaction completes the disconnect before baud/FIFO changes.
    return io.write(3,board::p1_safe) && configure() && io.write(3,p1) && verify_expander(io,p1);
}
}

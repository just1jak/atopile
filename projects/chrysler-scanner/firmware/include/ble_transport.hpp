// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstdint>
#include <cstddef>
namespace scanner_ble {
struct Chunk {std::uint32_t generation;std::uint16_t size;std::uint8_t data[244];};
bool initialize();
void open_pairing();
unsigned pairing_seconds();
unsigned passkey(); // USB display only; never included in BLE responses/logs.
std::uint32_t generation();
bool streaming();
bool receive(Chunk& chunk);
bool send(const std::uint8_t* bytes,std::size_t size,std::uint32_t generation);
void pump(); // Nonblocking, at most one negotiated-MTU fragment per call.
std::uint32_t lost();
}

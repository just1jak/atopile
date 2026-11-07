// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "core.hpp"
#include <cstdint>
#include <cstddef>
namespace scanner_ble {
struct Chunk {std::uint32_t generation;std::uint16_t size;std::uint8_t data[244];};

// Input arriving from NimBLE may still be queued after the link is revoked.
// Sample the current generation at each decoded command's acceptance point.
class CommandStream {
    scanner::Parser parser_;
    std::uint32_t generation_;
public:
    explicit CommandStream(std::uint32_t generation) : generation_(generation) {}
    bool reset_if_changed(std::uint32_t generation) {
        if (generation == generation_) return false;
        generation_ = generation;
        parser_.clear();
        return true;
    }
    std::uint32_t generation() const { return generation_; }
    std::uint32_t errors() const { return parser_.errors; }

    template<class Clock, class CurrentGeneration, class Sink>
    void feed(const Chunk& chunk, Clock now, CurrentGeneration current, Sink sink) {
        if (chunk.generation != generation_) return;
        for (unsigned i = 0; i < chunk.size; ++i) {
            parser_.feed(chunk.data[i], now(), guarded(current, sink));
        }
    }
    template<class CurrentGeneration, class Sink>
    void expire(std::uint64_t now, CurrentGeneration current, Sink sink) {
        parser_.expire(now, guarded(current, sink));
    }
private:
    template<class CurrentGeneration, class Sink>
    auto guarded(CurrentGeneration current, Sink sink) const {
        return [this, current, sink](const std::uint8_t* data, std::size_t size) {
            if (current() == generation_) sink(data, size);
        };
    }
};

bool initialize();
void open_pairing();
unsigned pairing_seconds();
unsigned passkey(); // USB display only; never included in BLE responses/logs.
std::uint32_t generation();
bool streaming();
bool receive(Chunk& chunk);
enum class Traffic { Capture, Reply };
void send(const std::uint8_t* bytes, std::size_t size, std::uint32_t generation, Traffic traffic);
void pump(); // Nonblocking, at most one negotiated-MTU fragment per call.
std::uint32_t lost();
}

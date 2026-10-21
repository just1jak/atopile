#pragma once
#include "chrysler/protocol.hpp"
#include <cstdint>
#include <mutex>

namespace logger_core {
// One lock governs connection generation and every readiness update. Queued
// packets from an earlier subscription remain logged but cannot authorize writes.
class ScannerState {
public:
    struct Snapshot {
        std::uint32_t generation = 0;
        bool handshake = false, status_valid = false, receive_ready = false;
        chrysler::ScannerStatus status;
    };
    std::uint32_t begin_connection() {
        std::lock_guard<std::mutex> lock(mutex_);
        const auto next = state_.generation + 1;
        state_ = {}; state_.generation = next; return next;
    }
    bool accept_handshake(std::uint32_t generation) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (generation != state_.generation) return false;
        state_.handshake = true; return true;
    }
    bool accept_status(std::uint32_t generation, const chrysler::ScannerStatus& status) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (generation != state_.generation) return false;
        state_.status = status; state_.status_valid = true; return true;
    }
    void set_receive_ready(std::uint32_t generation, bool ready) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (generation == state_.generation) state_.receive_ready = ready;
    }
    void disconnected(std::uint32_t generation) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (generation == state_.generation) {
            state_.handshake = state_.status_valid = state_.receive_ready = false;
        }
    }
    Snapshot snapshot() const {
        std::lock_guard<std::mutex> lock(mutex_); return state_;
    }
private:
    mutable std::mutex mutex_;
    Snapshot state_;
};
} // namespace logger_core

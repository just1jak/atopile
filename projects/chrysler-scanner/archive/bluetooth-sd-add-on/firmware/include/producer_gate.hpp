#pragma once
#include <atomic>

namespace logger_core {
// Close prevents new producers; quiescent means earlier producers have exited.
// The consumer closes, waits for quiescence, drains, then closes SD files.
class ProducerGate {
public:
    class Guard {
    public:
        explicit Guard(ProducerGate& gate) : gate_(gate) {
            gate_.active_.fetch_add(1);
            allowed_ = gate_.open_.load();
        }
        Guard(const Guard&) = delete;
        ~Guard() { gate_.active_.fetch_sub(1); }
        explicit operator bool() const { return allowed_; }
    private:
        ProducerGate& gate_;
        bool allowed_;
    };
    void open() { open_.store(true); }
    void close() { open_.store(false); }
    bool quiescent() const { return active_.load() == 0; }
private:
    std::atomic<bool> open_{false};
    std::atomic<unsigned> active_{0};
};
} // namespace logger_core

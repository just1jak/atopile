#pragma once
#include "capture_format.hpp"
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

namespace capture {
class SessionStorage {
public:
    SessionStorage() = default;
    SessionStorage(const SessionStorage&) = delete;
    SessionStorage& operator=(const SessionStorage&) = delete;
    ~SessionStorage() { abandon(); }
    void start(const std::string& root, const std::string& configuration) {
        if (active()) throw std::runtime_error("session already active");
        if (::mkdir(root.c_str(), 0755) && errno != EEXIST) fail("create logs directory");
        bool created = false;
        for (unsigned n = 1; n <= 999999; ++n) {
            char name[20]; std::snprintf(name, sizeof(name), "/S%06u", n);
            directory_ = root + name;
            if (::mkdir(directory_.c_str(), 0755) == 0) { created = true; break; }
            if (errno != EEXIST) fail("create session directory");
        }
        if (!created) throw std::runtime_error("session directory limit reached");
        try {
            write_file(directory_ + "/configuration.txt", configuration);
            part_ = 0; sequence_ = 0; open_part();
        } catch (...) { abandon(); throw; }
    }
    bool active() const { return raw_ >= 0 && selected_ >= 0; }
    const std::string& directory() const { return directory_; }
    void append(Type type, std::uint64_t monotonic, std::uint64_t utc,
                std::uint32_t dropped, const std::uint8_t* data, std::size_t size) {
        if (!active()) throw std::runtime_error("no active session");
        if (size > 8192) throw std::runtime_error("record payload limit exceeded");
        if (raw_bytes_ + size + 40 > 64ull * 1024 * 1024) {
            flush(); close_checked(raw_); close_checked(selected_); open_part();
        }
        const auto bytes = record(type, sequence_++, monotonic, utc, dropped, data, size);
        write_all(raw_, bytes.data(), bytes.size()); raw_bytes_ += bytes.size();
    }
    void row(const std::string& text) {
        if (!active()) throw std::runtime_error("no active session");
        write_all(selected_, reinterpret_cast<const std::uint8_t*>(text.data()), text.size());
    }
    void flush() {
        if (!active()) throw std::runtime_error("no active session");
        if (::fsync(raw_) || ::fsync(selected_)) fail("sync SD files");
    }
    void stop(const std::string& summary) {
        if (!active()) throw std::runtime_error("no active session");
        // A success marker and SAFE LED are allowed only after all data sync/close.
        flush(); close_checked(raw_); close_checked(selected_);
        write_file(directory_ + "/summary.txt", summary);
        write_file(directory_ + "/closed.ok", "clean software stop; hardware power-loss testing required\n");
    }
    void abandon() noexcept {
        if (raw_ >= 0) ::close(raw_);
        if (selected_ >= 0) ::close(selected_);
        raw_ = selected_ = -1;
    }
private:
    int raw_ = -1, selected_ = -1;
    unsigned part_ = 0;
    std::uint32_t sequence_ = 0;
    std::uint64_t raw_bytes_ = 0;
    std::string directory_;
    [[noreturn]] static void fail(const char* action) {
        throw std::runtime_error(std::string(action) + ": " + std::strerror(errno));
    }
    static void write_all(int fd, const std::uint8_t* data, std::size_t size) {
        while (size) {
            const auto n = ::write(fd, data, size);
            if (n < 0 && errno == EINTR) continue;
            if (n <= 0) fail("write SD file");
            data += n; size -= static_cast<std::size_t>(n);
        }
    }
    static void close_checked(int& fd) {
        const int old = fd; fd = -1;
        if (old >= 0 && ::close(old)) fail("close SD file");
    }
    static void write_file(const std::string& name, const std::string& value) {
        int fd = ::open(name.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0644);
        if (fd < 0) fail("create SD file");
        try {
            write_all(fd, reinterpret_cast<const std::uint8_t*>(value.data()), value.size());
            if (::fsync(fd)) fail("sync metadata");
            close_checked(fd);
        } catch (...) { if (fd >= 0) ::close(fd); throw; }
    }
    void open_part() {
        if (++part_ > 9999) throw std::runtime_error("session part limit reached");
        char name[32]; std::snprintf(name, sizeof(name), "/raw_%04u.bin", part_);
        raw_ = ::open((directory_ + name).c_str(), O_WRONLY | O_CREAT | O_EXCL, 0644);
        if (raw_ < 0) fail("create raw log");
        std::snprintf(name, sizeof(name), "/selected_%04u.csv", part_);
        selected_ = ::open((directory_ + name).c_str(), O_WRONLY | O_CREAT | O_EXCL, 0644);
        if (selected_ < 0) { abandon(); fail("create selected CSV"); }
        raw_bytes_ = 8;
        write_all(raw_, reinterpret_cast<const std::uint8_t*>(file_magic), 8);
        row("host_us,utc_us,scanner_ms,bus,profile,metric,value,unit\n");
        flush();
    }
};
} // namespace capture

#pragma once
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace logger_core {
struct Config {
    std::string scanner_address;
    bool random_address = false;
    bool auto_start = true;
    bool enable_pci_rx = true;
    bool enable_ccd_rx = false;
    bool upstream_profile = false;
    std::vector<std::string> selected;
    unsigned flush_ms = 1000;
    std::uint64_t utc_epoch_at_boot = 0;
};
inline std::string trim(std::string s) {
    const auto p = s.find_first_not_of(" \t\r\n");
    if (p == std::string::npos) return {};
    return s.substr(p, s.find_last_not_of(" \t\r\n") - p + 1);
}
inline bool boolean(const std::string& v) {
    if (v == "true") return true;
    if (v == "false") return false;
    throw std::runtime_error("expected true or false");
}
inline bool mac_address(const std::string& s) {
    if (s.size() != 17) return false;
    for (unsigned i = 0; i < 17; ++i)
        if ((i % 3 == 2) ? s[i] != ':' : !std::isxdigit(static_cast<unsigned char>(s[i])))
            return false;
    return s != "00:00:00:00:00:00" && s != "ff:ff:ff:ff:ff:ff" && s != "FF:FF:FF:FF:FF:FF";
}
inline std::uint64_t number(const std::string& s) {
    if (s.empty() || s.size() > 16) throw std::runtime_error("invalid integer");
    std::uint64_t value = 0;
    for (const char ch : s) {
        if (ch < '0' || ch > '9') throw std::runtime_error("invalid integer");
        value = value * 10 + (ch - '0');
    }
    return value;
}
inline Config parse_config(const std::string& input) {
    if (input.size() > 4096) throw std::runtime_error("logger.cfg exceeds 4096 bytes");
    Config config;
    std::map<std::string, std::string> values;
    std::size_t pos = 0;
    while (pos < input.size()) {
        auto end = input.find('\n', pos);
        if (end == std::string::npos) end = input.size();
        auto line = trim(input.substr(pos, end - pos)); pos = end + 1;
        if (line.empty() || line.front() == '#') continue;
        auto equal = line.find('=');
        if (equal == std::string::npos) throw std::runtime_error("config line requires key=value");
        auto key = trim(line.substr(0, equal)), value = trim(line.substr(equal + 1));
        if (!values.emplace(key, value).second) throw std::runtime_error("duplicate config key: " + key);
    }
    for (const auto& [key, value] : values) {
        if (key == "scanner_address") config.scanner_address = value;
        else if (key == "scanner_address_type") {
            if (value != "public" && value != "random") throw std::runtime_error("invalid address type");
            config.random_address = value == "random";
        } else if (key == "auto_start") config.auto_start = boolean(value);
        else if (key == "enable_pci_rx") config.enable_pci_rx = boolean(value);
        else if (key == "enable_ccd_rx") config.enable_ccd_rx = boolean(value);
        else if (key == "decoder_profile") {
            if (value != "none" && value != "upstream_broadcast_2023")
                throw std::runtime_error("unknown decoder profile");
            config.upstream_profile = value == "upstream_broadcast_2023";
        } else if (key == "selected") {
            std::size_t start = 0;
            while (start < value.size()) {
                auto stop = value.find(',', start); if (stop == std::string::npos) stop = value.size();
                auto metric = trim(value.substr(start, stop - start));
                if (metric.empty() || metric.size() > 48 ||
                    metric.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_") != std::string::npos)
                    throw std::runtime_error("invalid selected metric");
                const std::vector<std::string> supported{"engine_rpm", "vehicle_speed_kph",
                    "manifold_absolute_pressure_kpa", "battery_voltage_v", "oil_pressure_kpa",
                    "coolant_temperature_c", "ambient_temperature_c"};
                if (std::find(supported.begin(), supported.end(), metric) == supported.end())
                    throw std::runtime_error("unsupported selected metric: " + metric);
                if (std::find(config.selected.begin(), config.selected.end(), metric) != config.selected.end())
                    throw std::runtime_error("duplicate selected metric");
                config.selected.push_back(metric); start = stop + 1;
            }
        } else if (key == "flush_ms") {
            const auto n = number(value);
            if (n < 100 || n > 10000) throw std::runtime_error("flush_ms must be 100..10000");
            config.flush_ms = static_cast<unsigned>(n);
        } else if (key == "utc_epoch_at_boot") {
            config.utc_epoch_at_boot = number(value);
            if (config.utc_epoch_at_boot && (config.utc_epoch_at_boot < 1577836800ull ||
                config.utc_epoch_at_boot > 4102444800ull)) throw std::runtime_error("UTC anchor outside 2020..2100");
        } else throw std::runtime_error("unknown config key: " + key);
    }
    if (!mac_address(config.scanner_address)) throw std::runtime_error("set exact scanner_address in logger.cfg");
    if (!values.count("decoder_profile")) throw std::runtime_error("set explicit decoder_profile (none or upstream_broadcast_2023)");
    if (!config.upstream_profile && !config.selected.empty())
        throw std::runtime_error("selected metrics require upstream_broadcast_2023 profile");
    return config;
}
inline bool wanted(const Config& c, const std::string& metric) {
    return c.selected.empty() || std::find(c.selected.begin(), c.selected.end(), metric) != c.selected.end();
}
inline std::string csv(const std::string& s) {
    std::string out = "\"";
    for (char c : s) { if (c == '"') out += '"'; out += c; }
    return out + '"';
}
// A dropped chunk is a stream discontinuity, never a license to splice frames.
struct Counters {
    std::uint32_t notifications = 0, dropped_chunks = 0, dropped_bytes = 0;
    std::uint32_t frames = 0, parser_errors = 0, reconnects = 0;
    std::uint32_t decoded_rows = 0, unsupported = 0, invalid_bus_messages = 0;
};
} // namespace logger_core

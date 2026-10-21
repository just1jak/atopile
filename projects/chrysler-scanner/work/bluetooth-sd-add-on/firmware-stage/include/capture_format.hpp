#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

namespace capture {
// File header: 8 bytes "CBSDRAW1". Each record starts with "CBR1".
// All integers are little endian. Total record size = 40 + payload_size.
// [0:4] magic; [4] type; [5] flags (bit0 UTC valid); [6:8] header size=36;
// [8:12] payload size; [12:16] sequence; [16:24] host monotonic microseconds;
// [24:32] UTC microseconds (0 if unknown); [32:36] cumulative dropped chunks;
// [36:36+N] payload; final uint32 CRC32 over header+payload (IEEE polynomial).
// Types: 1 raw BLE chunk; 2 validated scanner frame; 3 parser error bytes;
// 4 lifecycle/status UTF-8 text. Type1 records preserve corrupt/noise bytes too.
// CRC detects incomplete/torn records; it does not guarantee SD power-loss safety.
inline constexpr char file_magic[] = "CBSDRAW1";
enum class Type : std::uint8_t { BleChunk = 1, ScannerFrame = 2, ParserError = 3, Event = 4 };
inline std::uint32_t crc32(const std::uint8_t* p, std::size_t n) {
    std::uint32_t crc = 0xffffffffu;
    for (std::size_t i = 0; i < n; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}
inline void append_le(std::vector<std::uint8_t>& v, std::uint64_t x, unsigned n) {
    for (unsigned i = 0; i < n; ++i) v.push_back(static_cast<std::uint8_t>(x >> (8 * i)));
}
inline std::vector<std::uint8_t> record(Type type, std::uint32_t sequence,
        std::uint64_t monotonic_us, std::uint64_t utc_us, std::uint32_t lost,
        const std::uint8_t* payload, std::size_t size) {
    std::vector<std::uint8_t> out{'C','B','R','1',static_cast<std::uint8_t>(type),
        static_cast<std::uint8_t>(utc_us != 0),36,0};
    out.reserve(40 + size);
    append_le(out, size, 4); append_le(out, sequence, 4);
    append_le(out, monotonic_us, 8); append_le(out, utc_us, 8); append_le(out, lost, 4);
    if (size) out.insert(out.end(), payload, payload + size);
    append_le(out, crc32(out.data(), out.size()), 4);
    return out;
}
}  // namespace capture

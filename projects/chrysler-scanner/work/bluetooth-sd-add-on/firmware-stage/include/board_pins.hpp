#pragma once

namespace logger_board {
// XIAO ESP32-S3 BASE module, external SD socket and status LED.
constexpr int sd_sck = 7;   // D8
constexpr int sd_miso = 8;  // D9
constexpr int sd_mosi = 9;  // D10
constexpr int sd_cs = 2;    // D1
constexpr int button = 1;  // D0, active low to ground
constexpr int led = 4;     // D3, active high through series resistor
static_assert(sd_sck == 7 && sd_miso == 8 && sd_mosi == 9 && sd_cs == 2);
static_assert(button == 1 && led == 4);
}  // namespace logger_board


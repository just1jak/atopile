// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstdint>
namespace board {
// ESP32-PICO-V3-02 package-specific mapping; see tools/check_board.py.
constexpr int heartbeat=13, ccd_rx=8, ccd_tx=7, sci_rx=5, sci_tx=4;
constexpr int pci_rx=14, pci_tx=27, usb_rx=3, usb_tx=1, sda=21, scl=22;
constexpr int sd_cs=15, sd_mosi=20, sd_sck=19, sd_miso=36;
constexpr int button=37, card_detect=38;
constexpr unsigned usb_baud=250000;
constexpr std::uint8_t aw_address=0x58;
// AW9523: P0[0:3] VBB, P0[4:7] VPP; P1[0:3] TX selects.
// P1[4] RX7, P1[5] RX15, P1[6] RX7 bias, P1[7] TBEN active LOW.
constexpr std::uint8_t p0_safe=0x00, p1_safe=0x80;
constexpr std::uint8_t rx7=0x10, rx15=0x20;
constexpr char pcb_sha256[]="e794b86979228ba2275eb4262df848acd16e56ef97a4ccf45402d65b119308d4";
}

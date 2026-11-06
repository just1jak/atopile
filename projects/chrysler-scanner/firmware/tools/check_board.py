#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check firmware GPIO/expander contracts against the accepted native release."""
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / "firmware"
EXPECTED_SHA = "e794b86979228ba2275eb4262df848acd16e56ef97a4ccf45402d65b119308d4"
PIN_MAP = {  # GPIO -> physical PICO-V3-02 pad, native net
    "heartbeat": (13, 20, "ACT_LED"), "ccd_rx": (8, 33, "RX1"),
    "ccd_tx": (7, 32, "TX1"), "sci_rx": (5, 34, "RX2"),
    "sci_tx": (4, 24, "TX2"), "pci_rx": (14, 17, "PCI_RX"),
    "pci_tx": (27, 16, "PCI_TX"), "usb_rx": (3, 40, "RX0"),
    "usb_tx": (1, 41, "N_R25_1"), "sda": (21, 42, "SDA"),
    "scl": (22, 39, "SCL"), "sd_cs": (15, 21, "MCU_SD_CS"),
    "sd_mosi": (20, 27, "MCU_SD_MOSI"), "sd_sck": (19, 38, "MCU_SD_SCK"),
    "sd_miso": (36, 5, "SD_MISO"), "button": (37, 6, "LOG_BUTTON"),
    "card_detect": (38, 7, "SD_DETECT"),
}
EXPANDER = {
    1: "TX6_EN", 2: "TX9_EN", 3: "TX12_EN", 4: "TX14_EN",
    5: "VBB_TO_TX6", 6: "VBB_TO_TX9", 7: "VBB_TO_TX12", 8: "VBB_TO_TX14",
    10: "VPP_TO_TX6", 11: "VPP_TO_TX9", 12: "VPP_TO_TX12", 13: "VPP_TO_TX14",
    14: "RX7_EN", 15: "RX15_EN", 16: "RX7_BIAS_EN", 17: "TBEN",
    18: "GND", 24: "GND",
}


def main():
    assert hashlib.sha256((ROOT/"current/ChryslerScanner_V240_SD.kicad_pcb").read_bytes()).hexdigest() == EXPECTED_SHA
    tree = ET.parse(ROOT/"current/reference/final-netlist.xml")
    nodes = {}
    for net in tree.findall("./nets/net"):
        for node in net.findall("node"):
            nodes[node.get("ref"), int(node.get("pin")) if node.get("pin").isdigit() else node.get("pin")] = net.get("name")
    header = (FW/"include/board.hpp").read_text()
    for name, (gpio, pad, net) in PIN_MAP.items():
        assert re.search(rf"\b{name}\s*=\s*{gpio}\b", header), name
        assert nodes["U10", pad] == net, (name, pad, net)
    for pad, net in EXPANDER.items():
        assert nodes["U19", pad] == net, (pad, net)
    source = (FW/"src/main.cpp").read_text()
    # Structural guards supplement, not replace, compiled tests and bench work.
    assert "esp_efuse_write" not in source and "nvs_set_" not in source
    writes = re.findall(r"uart_write_bytes\(([^,]+),", source)
    assert writes and all(port.strip() == "UART_NUM_0" for port in writes)
    assert "init_ble" not in source and "ledc_" not in source
    assert "format_if_mount_failed=false" in source
    assert "O_CREAT|O_EXCL|O_WRONLY" in source
    print(f"PASS: PCB hash; {len(PIN_MAP)} MCU mappings; {len(EXPANDER)} expander nets; passive source guards")


if __name__ == "__main__":
    main()

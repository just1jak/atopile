# V240 integrated SD hardware and firmware handoff

This revision adds the SD socket and controls to the **same 110 × 55 mm scanner
PCB**, using its existing U10 ESP32-PICO-V3-02. There is no XIAO, second MCU, BLE
relay, vehicle-interface reroute, or added vehicle data connection. The scanner's
existing Bluetooth feature can remain available independently. This handoff is
based on the adjacent frozen `integration.json`; original project files were not
changed by this review. Firmware is **deferred by the user**. Installing these
hardware additions does not make the existing scanner firmware log to SD.

## Final pin contract

| Function | U10 package pad | GPIO | New net / connection |
|---|---:|---:|---|
| SPI clock | 38 | 19 | `MCU_SD_SCK` → R104 33 Ω → `SD_SCK` |
| SPI MOSI | 27 | 20 | `MCU_SD_MOSI` → R105 33 Ω → `SD_MOSI` |
| SPI MISO | 5 | 36 | `SD_MISO`, input only; external pullup |
| SPI chip select | 21 | 15 | `MCU_SD_CS` → R106 33 Ω → `SD_CS`, active low |
| Logging toggle / safe stop | 6 | 37 | `LOG_BUTTON`, active low, R113 10 kΩ to MCU +3.3 V |
| Card present | 7 | 38 | `SD_DETECT`, active low, R114 10 kΩ to MCU +3.3 V |
| Logging indication | 20 | 13 | Reuse existing `ACT_LED`; existing driver unchanged |

The six newly connected package pads are NC in the original reference netlist.
GPIO36/37/38 are input only and do not provide internal pullups. The final mapping
leaves GPIO0, GPIO2 and GPIO12 and their boot/programming behavior unchanged.
GPIO15 has an existing high default strap; R112 pulls the MCU side high from its
own +3.3 V supply, so inactive CS preserves that default. Keep GPIO15 high during
reset and initial SD setup. Do not substitute a generic ESP32 development-board
pinout: package pads 35/36 are NC on this SiP, and GPIO6/11 and GPIO9/10 are used
internally for flash and PSRAM. Do not use U10's VDD_SDIO output to power the card.

GPIO20 is a real package-specific pin on ESP32-PICO-V3/V3-02. Espressif's
[SiP pin table](https://documentation.espressif.com/esp32-pico_series_datasheet_en.html)
identifies pad 27 as IO20. The official
[ESP-IDF 4.4.7](https://github.com/espressif/esp-idf/blob/v4.4.7/components/soc/esp32/gpio_periph.c#L36)
and [5.5.1](https://github.com/espressif/esp-idf/blob/v5.5.1/components/soc/esp32/gpio_periph.c#L28)
GPIO tables explicitly provide its I/O mux. Firmware must configure SPI pins
explicitly through the GPIO matrix; default VSPI/HSPI pin numbers are unsuitable.
Start with a conservative 10 MHz card clock after the usual low-speed card init;
that frequency is an engineering target, not measured signal-integrity proof.

J4 is the Hirose DM3AT-SF-PEJM5. Its contact map is: 1 DAT2, 2 CS/DAT3, 3 CMD/MOSI,
4 SD_3V3, 5 CLK, 6 GND, 7 DAT0/MISO, 8 DAT1, 9 card detect, 10 detect common GND,
and shield GND. It is SPI mode, not a four-bit SDMMC connection. Unused DAT1/DAT2
still have external pullups. R104/R105/R106 belong near their MCU source pins;
C59/C60 and the bulk capacitor belong near the socket/supply return. Backside
socket access and its final orientation/courtyard are layout-review items.

## Supply budget and limits

U20 is a **MCP1825S-3302E/DB**, a dedicated 500 mA 3.3 V LDO fed from the scanner's
main `+5V`. Pin 1 is input, pin 2 and the tab are ground, and pin 3 is SD_3V3.
It matches the SOT-223 footprint with tab connected as pad 2. This separates SD
regulation from U4's MCU/logic 3.3 V rail; it does not provide isolation or extra
upstream capacity. Both supplies share ground and the main 5 V source. The
[Microchip datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP1825-Family-Data-Sheet-DS20002056.pdf)
specifies 500 mA capability and a minimum effective 1 µF ceramic output capacitor.
The manifest provides 10 µF ceramic input/output capacitors plus local 100 nF and
100 µF bulk output capacitance. Verify DC-bias derating and placement in layout.
The selected standard `E/DB` ordering code does not itself establish automotive
qualification; Microchip lists separate automotive qualification suffixes.

The existing vehicle-powered chain is U2 LMR14010 step-down → U3 TLV76750 → +5V.
These are **1 A class** parts, with shared scanner loads. U4 TLV76733 supplies the
existing MCU/logic +3.3 V. The USB path is VBUS → U1 SY6283 → D3 LMBR130T1G → main
+5V. Therefore a main-rail connection supports either power route without a
VBUS-only logger. USB source current, cable/diode drop and protection limits must
also be checked; the USB-C CC resistors do not prove a negotiated high-current
supply. See the [TI TLV767](https://www.ti.com/product/TLV767) and
[LMR14010A](https://www.ti.com/product/LMR14010A) ratings.

Reserve a **300 mA continuous SD design budget** for initial engineering work,
then select and measure a particular card, including initialization/write peaks.
At 5.0 V input this gives approximately `(5.0 − 3.3) × 0.3 = 0.51 W` in U20;
500 mA would give 0.85 W. Those numbers are calculated losses, not demonstrated
thermal capability. U20 copper area, total +5V load, U2/U3 temperatures, supply
droop and simultaneous scanner operation remain bench gates. A 500 mA SD LDO
does not mean the shared upstream rail has 500 mA spare.

C61, Panasonic 6SVPC100M, is the 5.0 mm diameter × 5.9 mm high part, matching the
selected footprint; it is distinct from the larger 6SVP100M. See
[Panasonic's SVPC catalog](https://industrial.panasonic.com/cdbs/www-data/pdf/AAB8000/AAB8000COL88.pdf).
Its 100 µF bulk capacitance is **not a safe-shutdown energy store**. For example,
at 300 mA, an ideal 100 µF capacitor loses 0.3 V in only 0.1 ms. There is no
power-fail supervisor, hold-up circuit, RTC, battery backup or power switch in
this manifest. Safe stop will require the user to keep power applied until
future firmware confirms that recording has stopped and files are closed.

## Manifest review result

The MCU pin assignments, socket pad IDs, regulator pins, capacitor polarity,
existing-net preservation and external input pullups have no identified hard
circuit blocker in this review. This is a connection review, not routing, ERC,
DRC, assembly, thermal or electrical-performance certification.

The pullup review finding was resolved in the frozen manifest: R107/R109 now
use 10 kΩ, so CMD/MOSI and DAT0–DAT3 all have 10 kΩ card-side pullups, following the
[Espressif SD guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/sd_pullup_requirements.html).
R112 remains a separate 47 kΩ MCU-side GPIO15 strap pullup. The manifest pin map
and component values are authoritative for this handoff.

## Deferred firmware work

The target is raw capture **and** selected values for the early-2004 Cummins
automatic application. The initial selected metrics are candidates, not verified
vehicle definitions. The previously drafted standalone BLE/XIAO firmware is not
drop-in firmware for U10: its board, SDK configuration, receive source and pin map
are different. Reuse of portable framing/decoder/storage ideas requires a real
port and regression tests. Do not flash that draft or an unrelated binary here.

Integrate a bounded recording queue into the scanner's existing CCD/PCI/SCI receive
pipeline. Receive handlers must not perform SD writes. Preserve raw bus bytes,
source bus, receive timestamp, parser validity and overflow/reset counters even
when a message has no decoder. Record selected values only for explicitly chosen,
provenance-labelled profiles; do not invent SCI polling or infer Cummins support
from unrelated broadcast formulas. Logging must add no vehicle transmission,
diagnostic polling, programming-voltage changes or emulator activity by default.
Existing scanner functions remain a separate control policy.

Future firmware also needs card mount/error handling, card-present debounce,
start/stop-button debounce, regular file synchronization, clean-session markers,
overflow accounting, recovery of an incomplete power-loss tail, and ACT_LED
states tied to actual file closure. Card removal is permitted only after clean
stop, not merely because detect changed. With no RTC, record monotonic uptime;
an optional host-supplied UTC anchor must be explicitly labelled and refreshed.

The public repository contains legacy source/history, including an older Arduino
application and historical software. The inspected current
[PlatformIO scanner directory](https://github.com/laszlodaniel/ChryslerScanner/tree/master/PlatformIO/ChryslerScanner)
publishes ESP32 build binaries and CMakeLists, not the current V2 scanner source.
That does not prove no source exists elsewhere or in history; it means the
current binary cannot be assumed to be an editable, reproducible source project.
Before a port, obtain or identify a compatible scanner-source version and prove
all original interface behavior. Firmware, compilation and flashing remain
explicitly deferred for this deliverable.

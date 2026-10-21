# USB/BLE-to-microSD carrier, revision A

Open `chrysler_ble_sd.kicad_pro` in KiCad10. The native schematic and PCB are independently editable; the scanner's original files are not part of this board. `board-3d.png` shows the carrier **without the removable XIAO module or sockets fitted**. The real Hirose microSD socket is included in the native PCB and its3D view.

## Interface and assembly

Use the **base Seeed XIAO ESP32-S3**, not Sense/Plus. Fit two1x7,2.54mm socket strips on15.24mm row centres and matching male headers on the XIAO. Header hole diameter1.0mm; carrier60x50x1.6mm, two copper layers,1oz copper. USB-C faces the top edge. Four3.2mm NPTH mounting holes are at (30,3), (57,3), (3,47), (57,47)mm from the top-left origin. Use nylon M3 screws and insulating standoffs; do not rely on solder mask beneath a metal screw head. The socket/USB/enclosure height must be checked with the actual header pair before an enclosure is fabricated.

| Function | XIAO label | ESP32-S3GPIO | Carrier net |
|---|---|---|---|
| SDclock | D8 |7 | MCU_SCK through33R to SD_SCK |
| SDdataout | D10 |9 | MCU_MOSI through33R to SD_MOSI |
| SDdatain | D9 |8 | SD_MISO |
| SDchipselect | D1 |2 | MCU_CS through33R to SD_CS |
| STOP/EJECTbutton | D0 |1 | BUTTON,10k pull-up to MCU_3V3, press to GND |
| GreenstatusLED | D3 |4 | LED_GPIO, active high through1k |

Unused GPIO3/D2 is left open to avoid its boot-strap role. The SDcard's CMD and DAT0–3 have10k pull-ups to SD_3V3. CLK has no pull-up. Card-detect switch contacts9/10 are explicitly unconnected. Signal levels are3.3V. The firmware must configure chipselect high before SPI initialization and keep Wi-Fi disabled. Begin at4MHz SPI or slower; verify card operation and signal integrity before increasing clock speed.

## Power and thermal budget

Power only through XIAO USB-C from a regulated5V USB supply rated at least1A. There is **no12V input, vehicle connector, wired scanner connection, battery, or battery charger connection** on the carrier. Do not connect vehicle battery voltage to any pin. Bluetooth communication is BLE; this ESP32-S3 does not implement Classic Bluetooth SPP.

XIAO VBUS feeds MCP1825S-3302E/DB; its separate3.3V output supplies only the SDsocket. Do not bridge MCU_3V3 to SD_3V3. U2 pin1=VIN, pin2+tab=GND, pin3=VOUT. C1/C2 are10uF10V X7R; C3 is100nF10V X7R at the socket, and C4 is100uF6.3V Panasonic polymer bulk. U2's ground tab connects solidly to filled ground pours on both layers, with eight nearby0.3mm-drill thermal vias. Native DRC checks the actual filled copper, not a proposed polygon.

Design load budget: SDcard300mA continuous,500mA short peaks; module allowance300mA peak, indicator/pull-ups under5mA. Total worst planning load is about805mA from5V, so a default500mA host USB budget is insufficient. The USB supply rating does not constitute a measurement of the XIAO VBUS path or an authorization to draw this load from every host port.

At nominal5V and300mA, LDO loss is(5−3.3)*0.3=0.51W. At5.25V and minimum regulated3.2175V it is0.610W. A conservative **unverified** two-layer estimate of120°C/W gives73°C rise at the latter point and about113°C junction at40°C ambient. Microchip's62°C/W figure is for its specified four-layer test board and is **not** assumed here.500mA is the regulator's electrical capability; it is not an allowed continuous load for this carrier. Bench-check temperature and card current before use; initially limit operation to0–40°C. The selected XIAO module is a development board, not an automotive-qualified assembly, and this design is not for an engine bay.

## RF and removal

Attach the supplied external2.4GHz U.FL antenna. Route its coax clear of the microSD and USB connectors and mount the radiating antenna outside the carrier footprint and away from metal. Reserve at least20mm of clear, nonmetal space around the radiator as a conservative enclosure-design allowance; this is a project constraint, not a measured antenna certification. No RF trace or matching network is redesigned on this PCB. Keep the antenna off the carrier ground plane and do not place the antenna underneath the board. The user drawing layer marks the cable exit side; the final enclosure must provide cable strain relief.

Press STOP; wait for the firmware's solid SAFE LED before removing the card or USB. The100uF bulk capacitor is for load transients; at300mA it provides only about33microseconds per0.1V droop. It does **not** provide shutdown hold-up or guarantee a final filesystem flush. Sudden power removal can lose the active record or damage a FAT filesystem; use a quality/high-endurance card, short sync intervals, and recoverable records. No automatic power-fail circuit is present.

## Native validation and fabrication

See `verification.json`, `erc.json`, and `drc.json` for the final checks. These are KiCad10 native checks, including schematic/PCB parity, all reported track errors, filled zones, and missing connections. No DRC/ERC exclusions were added by this design; KiCad lists its standard inapplicable/disabled check categories separately in the JSON reports. `manufacturing/` contains Gerbers and separate plated/nonplated drill files for the checked board; this is a prototype fabrication package, with bench qualification still outstanding. Manufacturing assumptions: FR4,1.6mm,2layers,35um copper, green mask, white silkscreen, lead-free finish,0.20mm minimum clearance/track,0.30mm via drill,0.65mm via diameter. Review the exported Gerbers with the fabricator before ordering; nothing was ordered or uploaded.

## Primary references and provenance

- [Seeed pinout, power, module dimensions and operating limits](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/).
- [Official Seeed schematic](https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32S3/res/XIAO_ESP32S3_SCH_v1.1.pdf).
- [Seeed official KiCad library](https://github.com/Seeed-Studio/OSHW-XIAO-Series/tree/main/Seeed%20Studio%20XIAO%20Series%20Library):14-contact schematic subset and socket land pattern are derived from the base ESP32-S3 definitions. Extra underside pads/artwork and SMD castellation pads were removed; through-hole positions were preserved, holes enlarged from0.889mm to1.0mm, lands1.8mm, and overhanging USB silkscreen removed. The native module body geometry is retained. See `THIRD_PARTY.md`.
- [Microchip MCP1825S datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP1825-Family-Data-Sheet-DS20002056.pdf).
- [Hirose DM3AT-SF-PEJM5 drawing/product](https://www.hirose.com/en/product/p/CL0609-0031-0-00): the installed official KiCad footprint includes manufacturer keep-out regions; they were retained and checked by native DRC.
- [Espressif SD pull-up requirements](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/sd_pullup_requirements.html).
- [Panasonic6SVPC100M](https://industrial.panasonic.com/ww/products/pt/os-con/models/6SVPC100M):5.0mm body diameter,5.9mm high,6.3V100uF; the5x5.9mm KiCad footprint is used.

Generation scripts and the unmodified upstream Seeed files are in `source/`; rebuild into a fresh scratch directory, then repeat all native checks before replacing a manually edited design. The outputs do not show measured radio range, thermal behavior, card durability, or a completed physical assembly.

# ChryslerScanner V240 with on-board SD logging hardware

This is one **110 × 55 mm, four-layer scanner PCB**. The microSD socket, its
3.3 V regulator, card-detect circuit and LOG/STOP button are mounted on the back
of the main scanner board. The card is wired directly to the existing
ESP32-PICO-V3-02. The original Bluetooth, USB and vehicle-interface circuits remain.
This revision replaces the separate Bluetooth-to-SD carrier approach.

**Engineering revision: placed and electrically assigned, not routed or ready
for fabrication. Firmware is deferred.** The existing scanner firmware will not
gain SD logging merely by fitting these components. No fabrication Gerbers or
flashable firmware are included in this revision.

## Open the combined board

Extract the complete package into one directory and open
`ChryslerScanner_V240_SD.kicad_pro` with KiCad 10. Open its PCB or schematic from
the project manager. The PCB and all 23 schematic sheets share this project.
Keep the bundled libraries and `3dmodels` directory beside the project.

The microSD socket **J4 is on the underside** near the bottom edge. Flip the
board in KiCad's 3D viewer to see it. Its center is board-local (90, 46) mm.
Provide a card-access cutout at that edge and at least **7 mm underside
clearance**, including the 5.9 mm high bulk capacitor. The board outline,
connectors, mounting holes and all 245 original component placements remain.
Mechanical enclosure fit and actual card insertion/ejection still need testing.

`previews/board-bottom.png` and `previews/board-top.png` show the revised board.
The schematic PDF is `ChryslerScanner_V240_SD.pdf`; its final sheet contains the
new SD circuitry. Component positions and the BOM describe an unfinished
engineering layout, not approved assembly data.

## Electrical changes

There are 18 added components: J4, U20, R104–R114, C58–C61 and SW3. Six previously
unconnected ESP32 pads provide SPI, card detect and the button. All previously
assigned MCU pins and vehicle-interface nets retain their roles. Existing
ACT_LED hardware is available for future logging status. The full pin contract
and supply calculations are in `reference/integration-handoff.md`.

U20 takes power from the scanner's main +5V rail, which has vehicle and USB
power paths, and supplies a dedicated SD_3V3 rail. It does not add capacity to
the shared upstream supply. Card write peaks, USB current availability,
temperature, supply sequencing and noise remain bench checks. No battery, RTC,
power-fail supervisor or shutdown hold-up has been added. The bulk capacitor
cannot keep the logger running long enough to guarantee clean shutdown after
power removal.

Three stale no-connect markers in the older schematic reconstruction were
corrected: U3/U4/U8 pin 5 is GND, matching the corrected source netlist and PCB.
The base schematic uses passive pin types recovered from the source drawing,
so zero structural ERC alone does not certify power or driver compatibility.

## Verified state and work remaining

Native KiCad exports are compared by complete connected endpoint sets against
the PCB and expected circuit. The preservation audit checks original component
positions, rotations, sides, UUIDs and assigned nets. Reports and the original
source hashes are under `reference`.

The inherited scanner PCB is unrouted. Its baseline has 8 physical DRC errors,
2 warnings and 561 airwires reported by the native connectivity API (the DRC
report lists 499 unconnected records before reaching its reporting limit).
The combined revision has 607 airwires. Those results belong to the main scanner
and are unrelated to the earlier carrier's clean DRC report. See the current
baseline/final comparison for this revision's exact results. No DRC violations
were hidden to label the combined PCB complete.

Remaining work is to resolve physical DRC findings, route and check the complete
board, implement and test scanner firmware storage, assemble a prototype, and
verify raw capture plus selected values on the **early-2004 automatic Cummins**.
The separate XIAO/BLE firmware draft is not a drop-in replacement for this MCU.
Compatible scanner source must be identified before the port. Vehicle decoding
and actual hardware behavior are unverified. Firmware compilation and flashing
remain deferred at the user's request.

This native KiCad revision is saved separately from the original Downloads
project. The original Atopile source is unchanged; rebuilding it will not
produce these additions. Apply future changes to this revision deliberately
and check schematic/PCB parity before routing or fabrication.

## Provenance

Derived from the user's V240-USB-C-OBD reconstruction and
[laszlodaniel/ChryslerScanner](https://github.com/laszlodaniel/ChryslerScanner).
Circuit licensing is GPL-3.0; see `LICENSE`. Bundled KiCad library assets and
manufacturer models retain their respective licenses; see `licenses` and
`3dmodels/LICENSE-*`. Primary pin, SDK and regulator references are recorded in
`reference/integration.json` and `reference/architecture-review.json`.

No credentials, firmware binaries, compiler caches or user settings are needed
by this package. No hardware was purchased, flashed or connected during this
revision.

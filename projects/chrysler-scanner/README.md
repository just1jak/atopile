# Chrysler scanner with integrated microSD — revision C prototype

Open `current/ChryslerScanner_V240_SD.kicad_pro` in KiCad 10. The 24-page schematic PDF is `current/ChryslerScanner_V240_SD-Hierarchy.pdf`; page 1 retains the system block diagram with 168 native hierarchical signal ports. Input connector and protection share a sheet, and native ground symbols sit below the circuits.

The three high-priority findings are corrected: coordinated input protection and affected ratings, powered-off ADC isolation, and an external supervised health-heartbeat permit for AW9523B. Final native ERC and complete DRC are clean: zero findings, unrouted connections or schematic-parity errors. Independent native connectivity has zero uncapped airwires and all 197 ground pads in one group. The final adversarial review finds no remaining P1 within the explicit bounded prototype contract.

All 239 original electrical components and functional blocks are accounted for against the original ChryslerScanner PDF. All original placements except the user-authorized C61 top-side move, retained copper, nine zones, outline, mounting holes and rules remain exact. The 55 safety copper removals are limited to the corrected ADC/protected-supply branches; two additional unlocked C61 supply-branch segments are removed for its relocation; 380 retained locked objects and 173 retained historical protected objects are unchanged. C61 is the only accepted capacitor placement change; no experimental MCU-fanout moves were adopted. See `current/reference/original-schematic-comparison.md` and `p1-contract-audit.json` for exact exceptions, values and pin contracts.

Protection caps on page 2 are grouped and labeled by PCI and SCI channel pair. With the selected M3 socket head and no washer (checked head envelope 5.5 mm diameter × 3 mm high), H1 has 0.7504 mm centered connector clearance and 0.2504 mm after nominal screw float. The housing clears the PCB and all 16 pins align. This nominal model check leaves a small tolerance budget; verify actual screw and sample fit before production assembly. See `current/reference/rev-c-obd-mechanical-clearance.md`.

C61 (100 µF microSD supply bulk capacitor) is on the TOP side at (193,127) mm, 90 degrees, with a short 0.5 mm power route to the SD_3V3 distribution branch. Allow approximately 5.9 mm top-side component headroom. `current/reference/rev-c-c61-top-audit.json` binds this exact placement and routing exception to the frozen pre-move board. There are now 230 filled/capped/planarized processing sites, including the debug testpoint requirements. Earlier archives place C61 underneath and are superseded.

The board is 110 × 55 mm, four layers, nominal 1.6 mm, with underside microSD. Provide card access and at least 7 mm underside enclosure space, then check actual housing, screwhead and enclosure fit.

The debug-access revision adds 48 Keystone 5015 micro-miniature hook loops and four bare SPI probe pads, numbered TP1–TP52 on both board sides. Schematic page 24 and `current/reference/rev-c-testpoint-map.md` map every number to its net and position. The raw/protected supplies, programming rails, OBD lines, UART/I²C, safety controls and ADC isolation nodes are covered, with four local GND clips. RF/USB paths have no added hooks. All previous component placements and copper geometry are preserved; only three reference labels move. 19 tracks and three processed vias are added; 22 existing vias under the new solder pads are upgraded to filled/capped processing. Physical clip access and actual-speed signal integrity remain bench checks.

## Local fabrication files

- `outputs/chrysler-integrated-sd-rev-c-testpoints-fabrication.zip`: fresh Gerbers/job, separate metric PTH/NPTH drills/maps, positions, checksums and processing notes.
- `outputs/chrysler-integrated-sd-rev-c-testpoints.zip`: complete portable KiCad project, libraries/models, schematic PDF, BOM, native previews and review evidence.

Filled, copper-capped and planarized vias are required at every recorded site. Supply `current/reference/MANUFACTURING-NOTES.md` and its processing-site JSON to the fabricator, and agree the actual RF/USB stackup. Ordinary open or tented vias are not equivalent. Rev B archives and historical reports certify older boards only.

## Operation and qualification

This is a prototype fabrication package, not automotive qualification. Normal input is 9–16 V; no sustained 24 V or jump-start claim. Protected-input/VPP peaks must stay ≤28 V including overshoot within the declared pulse/energy limits. Exact generic BOM part selection, voltage/DC-bias/thermal derating, actual connector/screw fit and hardware measurements remain before assembly or vehicle use. Read `current/reference/rev-c-safety-contract.md` and `rev-c-adversarial-review.md`.

Firmware remains deferred and MUST be integrated before active operation. GPIO13/pad20 ACT_LED now belongs exclusively to the software health task: 10 ms pulses only while required tasks report healthy. The existing LED becomes a health/permit indicator. Remove old activity-LED writers, blink interrupts, PWM and DMA sources. Legacy firmware already drives ACT_LED and may accidentally retrigger the timer; it is not safe to assume it holds the expander in reset. GPIO2/pad22 remains its original no-connect. ADC calibration must include the new divider/loading and measurement point after D2. Do not bypass the hardware permit.

Current evidence is `current/reference/final-drc.json`, `final-erc.json`, `final-netlist.xml`, `p1-contract-audit.json`, `safety-bounds-audit.json` and `rev-c-adversarial-review.json`. `reference/final-status.json` binds the accepted board and ZIP hashes. Regenerate reports, PDF and fabrication files after editing; saved reports apply only to their exact hashes.

Original Atopile sources and the upstream PDF are preserved; rebuilding the old Atopile project does not recreate this native revision. Circuit licensing is GPL-3.0; bundled assets retain their notices. No manufacturing order or external upload has been performed.

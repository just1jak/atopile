# Chrysler scanner with integrated microSD — revision C prototype

Open `current/ChryslerScanner_V240_SD.kicad_pro` in KiCad 10. The 23-page schematic PDF is `current/ChryslerScanner_V240_SD-Hierarchy.pdf`; page 1 retains the system block diagram with 168 native hierarchical signal ports. Input connector and protection share a sheet, and native ground symbols sit below the circuits.

The three high-priority findings are corrected: coordinated input protection and affected ratings, powered-off ADC isolation, and an external supervised health-heartbeat permit for AW9523B. Final native ERC and complete DRC are clean: zero findings, unrouted connections or schematic-parity errors. Independent native connectivity has zero uncapped airwires and all 193 ground pads in one group. The final adversarial review finds no remaining P1 within the explicit bounded prototype contract.

All 239 original electrical components and functional blocks are accounted for against the original ChryslerScanner PDF. All original placements, retained copper, nine zones, outline, mounting holes and rules remain exact. The 55 explicitly recorded old-copper removals are limited to the corrected ADC/protected-supply branches; 380 retained locked objects and 173 retained historical protected objects are unchanged. No experimental MCU-fanout or capacitor moves were adopted. See `current/reference/original-schematic-comparison.md` and `p1-contract-audit.json` for exact exceptions, values and pin contracts.

The board is 110 × 55 mm, four layers, nominal 1.6 mm, with underside microSD. Provide card access and at least 7 mm underside enclosure space, then check actual housing, screwhead and enclosure fit.

## Local fabrication files

- `outputs/chrysler-integrated-sd-routed-rev-c-fabrication.zip`: fresh Gerbers/job, separate metric PTH/NPTH drills/maps, positions, checksums and processing notes.
- `outputs/chrysler-integrated-sd-routed-rev-c.zip`: complete portable KiCad project, libraries/models, schematic PDF, BOM, native previews and review evidence.

Filled, copper-capped and planarized vias are required at every recorded site. Supply `current/reference/MANUFACTURING-NOTES.md` and its processing-site JSON to the fabricator, and agree the actual RF/USB stackup. Ordinary open or tented vias are not equivalent. Rev B archives and historical reports certify older boards only.

## Operation and qualification

This is a prototype fabrication package, not automotive qualification. Normal input is 9–16 V; no sustained 24 V or jump-start claim. Protected-input/VPP peaks must stay ≤28 V including overshoot within the declared pulse/energy limits. Exact generic BOM part selection, voltage/DC-bias/thermal derating, actual connector/screw fit and hardware measurements remain before assembly or vehicle use. Read `current/reference/rev-c-safety-contract.md` and `rev-c-adversarial-review.md`.

Firmware remains deferred and MUST be integrated before active operation. GPIO13/pad20 ACT_LED now belongs exclusively to the software health task: 10 ms pulses only while required tasks report healthy. The existing LED becomes a health/permit indicator. Remove old activity-LED writers, blink interrupts, PWM and DMA sources. Legacy firmware already drives ACT_LED and may accidentally retrigger the timer; it is not safe to assume it holds the expander in reset. GPIO2/pad22 remains its original no-connect. ADC calibration must include the new divider/loading and measurement point after D2. Do not bypass the hardware permit.

Current evidence is `current/reference/final-drc.json`, `final-erc.json`, `final-netlist.xml`, `p1-contract-audit.json`, `safety-bounds-audit.json` and `rev-c-adversarial-review.json`. `reference/final-status.json` binds the accepted board and ZIP hashes. Regenerate reports, PDF and fabrication files after editing; saved reports apply only to their exact hashes.

Original Atopile sources and the upstream PDF are preserved; rebuilding the old Atopile project does not recreate this native revision. Circuit licensing is GPL-3.0; bundled assets retain their notices. No manufacturing order or external upload has been performed.

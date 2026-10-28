# Chrysler scanner revision C

The active project is [current/ChryslerScanner_V240_SD.kicad_pro](current/ChryslerScanner_V240_SD.kicad_pro). The requested programming-drive, recommended inductor-land and M3 clearance improvements are complete. Native ERC/full DRC/parity and all 130 combined audit checks pass; the independent review has no remaining high-priority findings.

Open `ChryslerScanner_V240_SD.kicad_pro` in KiCad 10 with this whole folder. Current hardware uses DMG6601LVT-7 for all eight programming switches, with new 8.2k R124-R127 gate resistors. L1/L2/L4/L6 use Eaton's recommended 2.50 x 3.25 mm lands. H1 moved 0.9996 mm toward the top edge: its M3 socket-head/no-washer clearance is now at least 1.25 mm after nominal screw float. Update any enclosure mounting pattern for H1.

The 24-page schematic begins with the system block diagram and retains 168 hierarchical ports. Input connector and protection share one sheet; PCI/SCI capacitors remain grouped. CCD uses TTL-input AHCT buffers at 5 V. CAN hardware remains deferred; `reference/can-upgrade.md` describes a future revision.

Use only this package's Gerbers/job, separate PTH/NPTH drills, assembly BOM, placement list and processing notes. There are 333 electrical/probe endpoints and four mounting holes: 325 PLACE parts, R23/R24 DNP, JP1/JP2 plus four bare SPI pads as PCB features. C61 remains top-side at (193,127) mm; underside microSD and 48 hook testpoints remain. Board: 110 x 55 mm, four layers, nominal 1.6 mm. **246 recorded filled, copper-capped and planarized sites are required**; ordinary open/tented vias are not equivalent. Agree RF/USB stackup and processing with the fabricator before ordering.

All-severity native ERC and full DRC/parity, native connectivity, frozen prior-release safety/procurement audit and the actual refinement delta must pass. The independent review and final combined audit are hash-bound in reference/. Earlier snapshots/reports are historical. See `reference/rev-c-refinement-review.md` for exact changes and scope.

This is a bounded prototype, not tested or automotive-qualified hardware. Normal input is 9-16 V; protected input/VPP must stay <=28 V including overshoot. No sustained 24 V/jump-start support. C14 bias/stability, regulator/inductor thermal and fault behavior, physical gate voltage/timing, protection energy, bus ESD, analog calibration and actual assembly/mechanical fit require qualification. The old 4.5 V-only MOSFET drive and undersized-inductor-land exceptions are corrected. AW9523 output drops are typical-only specifications; do not claim a formal minimum for the whole drive chain.

Firmware remains deferred. GPIO13/pad20 ACT_LED belongs exclusively to the supervised health task, pulsing every 10 ms only while required tasks vote healthy. Remove old activity/PWM/DMA writers. Configure AW9523 P0 push-pull while output latches remain low before enabling programming. Apply the safe startup/recovery contract and new ADC calibration before active operation. No manufacturing order or external upload is performed.

Allow at least the prior 7 mm underside enclosure space and card access; C61 is nominally 5.9 mm tall above the top, main coils maximum 4.35 mm. Check actual component/screw/connector/hook and enclosure tolerances with samples.

Current archives: `outputs/chrysler-integrated-sd-rev-c-drive-lands-mounting-20261028.zip` and `outputs/chrysler-integrated-sd-rev-c-drive-lands-mounting-20261028-fabrication.zip`, with SHA-256 sidecars. Earlier archives are historical. The refreshed original/current circuit comparison is `output/pdf/ChryslerScanner_Original-to-Current_Circuit_Comparison.pdf`. Exact delivery hashes and limits are in `reference/final-status.json`.

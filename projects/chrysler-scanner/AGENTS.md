# Chrysler scanner: routed revision C prototype

Read README.md, reference/final-status.json and current/reference final reports before editing. The active native KiCad project is current/ChryslerScanner_V240_SD.kicad_pro. Firmware remains deferred. Manufacturing orders require their own user request.

Accepted PCB SHA-256:
`a2cb3d5e82d57b75eb0caab103d6f82529d8543b182aa9fc80e320bfe61c2fd5`.

Native DRC/ERC/parity are clean; all 193 GND pads and all signal nets are connected. Preserve accepted original placements (C61 now on top at (193,127) mm, 90 degrees), retained copper, all nine zone/rule-area definitions, outline/holes, stackup, rules, severities and exclusions. Keep In1 as GND with no signal tracks; minimum width/clearance remain 0.15 mm. Work on a copy. Never run old setup_design.py or overwrite this native project with original Atopile output.

The exact historical baseline, 55 permitted ADC/protected-supply copper removals and 24 restored ADC objects are frozen under current/reference/pre-p1. All 380 retained locked objects and 173 retained historical protected objects are exact. All original component placements except the explicitly user-authorized C61 transform and frozen six SD assignments are preserved; no experimental C31/IO0/power/SD fanout exceptions were adopted. R112's prior accepted (172.05,121.075) mm placement remains unchanged. These are provenance exceptions, not permission to expand future changes silently.

After any edit, export fresh native XML and all-severity ERC, then full DRC with --all-track-errors --schematic-parity --severity-all --refill-zones. Run current/source/verify_safety_revision.py using KiCad 10 Python (full mode, not structural-only) and verify_safety_bounds.py. The primary audit checks 277 components, 23 value exceptions, 15 original endpoint changes, all new pin contracts, 24 recovered capacitor ratings, 23 sheets/pages, 168 hierarchy ports, complete uncapped native connectivity, body overlap, outline and preservation. Old verification scripts/reports have superseded counts and cannot certify Rev C.

GPIO13/pad20 ACT_LED is now a DEDICATED software health heartbeat and LED health indication. Only the safety task may pulse it every 10 ms after required tasks vote healthy; remove legacy activity writers, autonomous PWM/DMA and blink interrupts. Legacy firmware may accidentally retrigger the watchdog and must not be used for active operation. GPIO2/pad22 remains NC. Firmware and ADC calibration work require their own user request. Follow the safety startup/recovery contract before commands.

The declared prototype envelope is normal 9–16 V and bounded protected-input/VPP ≤28 V including overshoot. No sustained 24 V/jump-start, automotive qualification or vehicle validation is claimed. Exact generic procurement parts and bench/thermal/mechanical qualification remain. Do not weaken those limits without a new engineering review.

Filled/copper-capped/planarized processing at the recorded vias is mandatory. Preserve saved processing flags; tenting is not filling. See current/reference/MANUFACTURING-NOTES.md. After clean checks and final adversarial review, regenerate local fabrication/PDF/BOM/project archives with current/source/package_rev_c.py; it gates final hashes and never orders/uploads.

C61 top-side exception: source/verify_c61_top.py is invoked by the strict verifier. reference/pre-c61 freezes the preceding 97423163 PCB. Only C61 changes side/position/orientation; exactly two unlocked SD_3V3 branch tracks are removed and four 0.5 mm tracks plus two filled/capped vias are added. R96 reference text is repositioned. All retained copper, other footprints, nine zones and outline/holes are exact. Total processing sites: 205. The original 55 safety-removal manifest remains unchanged; the two C61 removals are separately checked. Do not add further exceptions silently.

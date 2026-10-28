# Independent refinement review

Accepted for the bounded prototype CAD delta. No remaining P1 schematic or PCB finding was identified. Layout review is complete. Primary sealed combined verification and regenerated fabrication-package reconciliation remain required before release; this review does not authorize a manufacturing order.

## Scope and evidence

This review covers the requested programming-drive, Eaton inductor-land/routing and H1 screw-clearance refinements, layered over previous independent schematic/layout and procurement reviews. Inspected actual native pin/net/land data, final programming PDF pages 16,17,20,21, front/back cropped board views and all eight detailed quadrants. Manufacturer research for the exact DMG6601 and Eaton parts was retained from the preceding review. Every passive ordering suffix and original-PDF block comparison was not repeated.

Fresh all-severity ERC/full DRC/parity reports contain zero violations. Independent native connectivity measurement found zero airwires/disconnected nets and all 197 GND pads in one group. Independent old/new copper comparison confirms every retained object's geometry, net and via properties remain exact, including 380 locked objects. All 78 cuts are unlocked; 411 new copper objects include 21 vias. Eight previous vias are removed; mandatory filled/capped processing increases from 230 to 246 sites. No retained GND via was reassigned.

## Programming control

Q8–Q11 now use DMG6601LVT-7 on the unchanged TSOT26 pin contract:1 N gate,2 P source,3 P gate,4 P drain,5 N source,6 N drain. R124–R127 each add 8.2 kΩ in series between N drain and P gate; existing 4.7 kΩ pullups remain on the P gate and 10 kΩ pulldowns remain on N gates. Native XML and pad samples show exactly these four splits; the PDF shows the intended divider topology. All eight programming switches now use the same part family.

The manufacturer specifies N RDS(max) 85 mΩ at 2.5 V and P 190 mΩ at −2.5 V, with ±30 V drains and ±12 V gates. Worst divider P-gate stress is 10.331 V at 28 V with 1% resistors; series-branch current is below 2.2 mA and resistor dissipation below 40 mW. This fixes the previous mismatch to a MOSFET specified only at 4.5 V drive.

AW9523B high/low output voltages are typical-only. Therefore this review does not claim a formally guaranteed complete-chain minimum gate voltage. P0 must be configured push-pull before programming, startup/default controls must remain low, and min-rail/temperature/output-load/shutdown behavior must be measured. No reset-enabling pullup was introduced. The existing supervised GPIO13 health contract remains unchanged.

## Inductor routing and mechanical clearance

L1/L2/L4/L6 have Eaton-recommended 2.5 × 3.25 mm rectangular pads on 6 mm centers and appropriate maximum-body envelopes. Local rerouting preserves existing locked paths; new power branches are at least 0.5 mm. The visual/native review found no body interference or new RF keepout intrusion. Ground-reference rule areas remain unchanged. Narrow courtyard-stroke bounding-box overlaps at L1/C6 and L6/C21/C22 are line-width effects; their enclosure centerlines and actual bodies remain separated.

Wider switched-node copper and rerouted adjacent sensing paths still need physical ringing/noise/thermal/stability tests. Reflow joints and 246 filled/capped/planarized sites require the specified manufacturing process. Current ratings are not a substitute for actual copper-temperature measurements.

H1 moves to y104 mm while J1 and other holes remain fixed. The nominal manufacturer-model check gives 1.75 mm centered connector clearance and 1.25 mm after 0.5 mm M3 radial float toward the connector. Screw-head clearance to the top board edge is 1.25 mm centered and 0.75 mm with float toward that edge; the updated mechanical report correctly distinguishes this from connector clearance. Both remain positive. Hardware assumption is a 5.5 mm diameter, 3 mm high M3 socket head with no washer. Connector, screw, board and enclosure tolerance/sample fit remain qualification items.

## Closeout and limitations

Primary must bind the refinement contract and finish the combined historical/procurement/refinement verifier plus export reconciliation. After repair of heterogeneous drawing-signature handling, the read-only verifier was independently re-executed with current-file hashes substituted in memory while source constants remain UNBOUND. Every technical check passes; only the intentionally pending independentReviewAccepted contract flag fails. A complete sealed combined-wrapper/package PASS is not attributed to this reviewer. Independently measured connectivity and retained-copper checks described above are additional evidence.

Existing C14 effective-capacitance/boost stability, protected-input/VPP<=28 V overshoot bound, 9–16 V normal supply, total load, thermal/ESD, firmware and vehicle-use restrictions remain. No automotive, regulatory or production qualification is claimed. CAN remains deferred.

## Exact CAD hashes

PCB SHA-256: `800c05930a0ca24fe280d5f3aace70974889129942a1b5602ce2eabfea026301`

- `01_ccd.kicad_sch`: `d787977327104e66aa4b48a5c838865b4ac6dd117d11f695b72f39c95e41f663`
- `02_pci.kicad_sch`: `9aad268904d4776394416e5b806a6e9cfcdba22089b89a352e3ea391933d08be`
- `03_sci-14-9.kicad_sch`: `31e4467933deb45bc1d08caa1ae8c8eb146c56854ac50be89443c4b9d4a04356`
- `04_sci-6-12.kicad_sch`: `3278bf66833b1123754c90a9fea45325d98025816615a87ef263d28f7dcb43dc`
- `05_sci-rx.kicad_sch`: `d4f8e54bf51bde7ae976ecb6c75d5689f5f15fada221578e30980df758073ae6`
- `06_obd-protection.kicad_sch`: `9fcbaf2fc63f41af49eea0aca353a445ffbe79f25fec2f88864f5256134dd9c8`
- `07_vehicle-input.kicad_sch`: `ef5a18f0484276ca27fa6d012aae8e72126508830782552d221c0d6a64739bfa`
- `08_power-5v.kicad_sch`: `ba2fb3f911972cecf5f81c0e76ad38a2716b1224edd5d0a9211136a6f65fadbe`
- `09_power-vpp.kicad_sch`: `ae05fbec33b02cb9f94e3cda5113b5cf677ada314431a6eeb5492517a30980d4`
- `10_power-vbb.kicad_sch`: `a49de7a51eca79de8dfd1cfadc9b40cd69cc0c355bba381476230ac8aafc7018`
- `11_power-7v5.kicad_sch`: `1fbbbb19dbe40acef668d3e4b6d34dee7bde1859f11fe83a768f5ab6b642207a`
- `12_program-6.kicad_sch`: `b41f78679450835252ead39f2e36846543a6b7e03bf027375b25ddd8e40a0b72`
- `13_program-9.kicad_sch`: `4ce78c10dfd5a40ad582a5c4c87fff640302f5cf2d653c240532c57ad56c0b18`
- `14_program-12.kicad_sch`: `d29ab5b55e4df5d61354894472aa1b9e17ccf9fe770df988754856f9db8c8df9`
- `15_program-14.kicad_sch`: `8122699d80a337b43554906c43254e2f682b912c0d573235adef2b47c886536d`
- `16_mcu.kicad_sch`: `8c686ec92dbcfdbbf292ab14fff0244d44f3589119d837b44d3ac8e4b4da7b2a`
- `17_adc.kicad_sch`: `1a7f18e6e60265873b87faeffc49bb708e7a8accad0a4421e90fd7dd94486c43`
- `18_control.kicad_sch`: `074e9cd187a142041eaa8161cc0c4342fa21b4e8003c68d7ff0f4c20aed85b6e`
- `19_usb.kicad_sch`: `de78a2fe97727f93a6ab9f572a594ccd13970d9ddca7705ea20165a9838e494f`
- `20_leds.kicad_sch`: `b04a51e07fbfdd347ec10160f9502be8f743f02977cf44073eaf5e8c237efba7`
- `22_sd-logger.kicad_sch`: `d80434fc3ba1cf1f319376d470a44078db013f89ae00d2f6a3d7cb65414e2e4e`
- `23_hardware-safety.kicad_sch`: `b8876b6a470b4e06833cac665e08abaecb462500b52d99feb2c20d4a8ea793c2`
- `24_debug-testpoints.kicad_sch`: `f47764d129360c28258037c4ab0c48c9f461094cde1cdeb30df481ed31ab0b7e`
- `ChryslerScanner_V240_SD.kicad_sch`: `7c15e34193b1047eeb3d43096ad972032ad9ea49570fb20c21b64f45cf1272ac`

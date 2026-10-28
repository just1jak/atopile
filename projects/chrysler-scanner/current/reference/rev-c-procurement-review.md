> Historical 2026-10-27 procurement review. The gate-drive, inductor-land and H1-clearance portions are superseded by [the 2026-10-28 refinement review](rev-c-refinement-review.md). Use the current combined audit and fabrication files.

# Revision C procurement closeout

Exact parts and the associated native CAD changes are reviewed for the bounded prototype. All purchasing identities are explicit; the former unselected BOM and package mismatches are superseded. This is fabrication/assembly preparation, not a claim of tested hardware, guaranteed stock, production yield or automotive qualification.

## Corrected findings

| Item | Final implementation |
| --- | --- |
| CCD logic-level margin | U17 Nexperia 74AHCT1G17GVH, U18 TI SN74AHCT1G14DBVR, both TTL-input devices on +5 V. Same pin roles and buffer placement. R98/R99 are 330 ohms, limiting an ideal 5.5 V charging step to 16.84 mA at -1% resistance. Actual gate/Miller waveforms remain a bench check. |
| Original MOSFET package mismatch | Original CJ3439KDW Q1/Q6/Q16 and HSSK8811 Q7 retain their pin roles on corrected SOT-363 lands. Q2/Q3/Q4 use DMN62D2UDM-7 on the original SOT-23-6 lands, with identical-channel physical source/gate/drain mapping and specified 1.8/2.5 V gate-drive performance. Rejected DMC2700UDM is not selected. |
| C14 | TDK C3225X7R1H226M250AC, 22 uF 50 V X7R, 1210. Manufacturer-specific 1.2 x 2.5 mm pads, 2.2 mm gap; maximum 3.6 x 2.8 x 2.8 mm body envelope. C14 moves to (157.75,116.5) mm; local power/GND branches are documented. |
| Main power coils | Eaton DR74-220-R: exact 22 uH, 1.75 Arms, 2.13 A at 30% inductance drop. Actual rectangular feet are fully covered by retained original lands. Updated maximum 7.6 mm body / 4.35 mm height and courtyard. Original coil positions and power copper remain unchanged. Lands differ from Eaton's larger suggested reflow lands; qualify actual fillets/temperature. |
| Filter coils | Bourns SRN2012-R24M and SRN2012-R47M preserve exact 240/470 nH values. Recommended 0.8 x 1.8 mm lands at +/-0.8 mm; maximum body 2.2 x 1.8 x 1.2 mm. L3 moves to (150.9,121.2) mm at -90 degrees; L5 to (162.975,139.2) mm at 0 degrees. New branches are 0.5 mm on F.Cu. No new 100 mA operating restriction is introduced. |
| Diode packages | D11/D15-D22 use PMEG4005EGWX 40 V / 0.5 A Schottkys matching SOD-123 lands and cathode pad 1. D12-D14 use SMF12A; D27-D29 use PESD3V3U1UA,115 matching SOD-323 lands. ESD diodes are not precision ADC voltage clamps. |
| Remaining BOM | Reviewed identities are in `rev-c-procurement-selections.json` and native schematic/PCB fields. Resistor families/tolerances, capacitor values/ratings, connectors, switches, LEDs, antenna, regulators and logic are specified. Exact existing MCU is retained; ESP32-PICO-V3-02 is an NRND lifecycle choice requiring stock verification. |
| Assembly ambiguity | 321 placed/purchasable parts; R23/R24 explicitly DNP; JP1/JP2 and four bare SPI pads are PCB features. The grouped assembly BOM and native position list must contain exactly the same placed references. |
| Stale SD note | The SD sheet now explicitly reserves GPIO13 for the supervised health heartbeat and prohibits SD/activity/PWM/DMA writers. Wiring is unchanged. |

## Preservation and checks

The pre-procurement CCD board is frozen at SHA-256 `6875b7628b2ace4bbad731ba96508a1c3dd032dab3aefff2669a66251b7410a1`. Its original 55-check safety audit is rerun unchanged in a temporary historical project. A separate hash-bound delta audit checks the actual current CAD, all 329 native identities/endpoints, all 333 footprint UUIDs, declared physical exceptions, exact copper changes, maximum-body collisions, outline, rules, zones, fresh all-severity native reports and full connectivity.

This delta changes 11 physical footprint implementations, adds 46 tracks and removes nine specifically recorded unlocked branch/stub objects. All retained copper, including all 380 locked and 173 historically protected objects, is exact. There are no new drills or via-processing changes. All 230 mandatory filled/capped/planarized processing sites remain. Forty no-connects, 162 named connected nets, 197 ground pads in one group, 24 schematic pages and 168 hierarchy ports remain. Electrical pin/net roles are unchanged by this procurement delta. Earlier original-PDF reconciliation accounts for all 239 original functional components/blocks; the layered audit preserves that electrical graph.

The independent procurement review combines source-device and pin/land checks with actual native sampling, independent delta-verifier execution, schematic detail inspection and cropped front/back layout inspection. It is a delta review layered over earlier reviews, not a new independent audit of every passive ordering suffix. Exact CAD hashes and remaining findings are in `rev-c-procurement-independent-review.json`. Packaging additionally gates the combined audit and checks native CAD bytes, BOM/placement agreement, portable assets, archive integrity and checksums.

## Limits that remain before operation/production

Normal input stays 9-16 V, with protected input/VPP <=28 V including overshoot within the unchanged safety contract. No sustained 24 V/jump-start or automotive qualification is claimed. C14's reference capacitance is about 8 uF at nominal 20.6 V and 5.5 uF at 28 V, before other tolerances; this is not a guaranteed minimum. Measure boost stability, ripple and transient response. Also qualify regulator/inductor temperatures and fault current, actual source/TVS energy and clamp overshoot, Schottky leakage/backfeed, powered/unpowered ADC behavior, gate timing, watchdog startup/decay and total +5 V/SD load. Q8-Q11's 3.3 V gate-drive performance remains the prior functional qualification item.

Agree filled/capped processing and the RF/USB stackup with the fabricator. Verify actual OBD housing, M3 socket head without washer, enclosure/card/hook access and component tolerances with samples. Dedicated-heartbeat firmware and ADC calibration remain deferred and are required before active operation. CAN is documented for a future hardware revision and is not added to this board. No fabrication order is placed.

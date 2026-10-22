# Revision C independent schematic review

Reviewed 2026-10-21 after final adoption of the GPIO13/ACT_LED dedicated health heartbeat, completed routing and portable-model-path correction. This independent review covers the exact schematic set, fresh native netlist/ERC/DRC and stable PCB below. **Layout review is complete for a bounded electrical prototype.** It is not automotive, production-assembly or bench qualification.

## Disposition

**No remaining P1 schematic/layout topology or absolute-rating defect was identified in the three corrective circuits under the explicitly bounded prototype contract.** The supply clamp, unpowered ADC isolation and fail-safe permit are implemented; the additional capacitor/FET rating gaps identified during the preceding review are also corrected. This is conditional bounded-prototype design acceptance, not measured transient survival, firmware approval or permission to use the board in a vehicle.

The boundary is normal 9–16 V input, protected-input/VPP peaks no greater than 28 V including overshoot for the bounded 1 ms test, controlled source/pulse energy inside the selected TVS ratings, and the declared rail-collapse/timing assumptions. It does not cover sustained 24 V, arbitrary load dump, arbitrary instantaneous rail shorts or unidentified replacement parts. Read `rev-c-safety-contract.md` with this report.

## Artifact binding

| Artifact | SHA-256 |
| --- | --- |
| Root `ChryslerScanner_V240_SD.kicad_sch` | `cddfe185bae68c4bd6b6148e21289922755a9ef2c169f8ed1c549845624a054a` |
| Final `ChryslerScanner_V240_SD.kicad_pcb` | `974231631b323828ea5a2ac47578b0f7cad72a31981915fd154d734c6b78710e` |
| Fresh `reference/final-netlist.xml` | `249456fcca8f9c3deaea80b8c109878cd1c975821f7d1cf4fe1e64f4a7d967a8` |
| `reference/rev-c-safety-contract.md` | `1288851d0f18f0b686caa8d4105eb6a8bf8d2421d54ba535def3febc26da132f` |
| Unmodified original upstream schematic PDF | `334b04164cfa96183cf502f690024a764cc719671f20583043f37604c9ed590d` |

The companion JSON binds every individual native schematic file, the native ERC export, the manifest and the exhaustive comparison results. Native ERC has zero findings. That result supports connection checking; most recovered original symbols use passive electrical pin types and ERC does not establish active-device safety.

## Corrective circuits checked

1. **Supply clamp and downstream ratings.** D1 is now exact-contract Littelfuse SMBJ16CA, whose published clamp point is 26 V at 23.1 A for the specified pulse. The 28 V system ceiling includes layout/wiring overshoot and still requires physical enforcement. R123=1 kΩ, 1 W, 1% feeds PCI_VCC; D30 cathode1 is on PCI_VCC and anode2 on GND; U9.5/C11.2 are on this clamped node. The Nexperia BZT52H-B15 standard-pad rating applies rather than its enlarged-copper rating. C14/C15 explicitly require 50 V rather than the original 35 V. [Littelfuse SMBJ](https://www.littelfuse.com/assetdocs/tvs-diodes-smbj-series-datasheet?assetguid=ba555e99-a12d-4f72-a0b6-86b06c67171e), [Nexperia BZT52H](https://assets.nexperia.com/documents/data-sheet/BZT52H_SER.pdf).

2. **Programming FET split.** Q8–Q11 are DMC3071LVT-7 with 30 V drain and ±20 V gate limits; Q12–Q15 are DMG6601LVT-7 with 30 V drain and ±12 V gate limits. Both use physical1=N gate,2=P source,3=P gate,4=P drain,5=N source,6=N drain. The latter have 4.7 kΩ/8.2 kΩ, both1%, gate dividers. Independently recalculated maximum DC |VGS| is10.332 V at28 V; minimum at nominal18.85 V VPP is6.781 V. These calculations do not guarantee fast-edge gate stress. The VBB devices' low-current3.3 V drive remains a functional qualification item because their N-channel on-resistance is specified at4.5 V, not3.3 V. It is not an established absolute-rating violation within the declared rails. [DMC3071LVT](https://www.diodes.com/datasheet/download/DMC3071LVT.pdf), [DMG6601LVT](https://www.diodes.com/datasheet/download/DMG6601LVT.pdf).

3. **ADC isolation.** U21 TMUX1511PWR maps SEL1/2/3 pins1/4/10 to LOGIC_PG, inputs2/5/9 to the pre-divider nodes, outputs3/6/8 to MCU ADC nodes, GND7 and VDD14. The unused fourth channel is tied to GND. Each22 kΩ/1.62 kΩ1% divider is upstream; each post-switch MCU node has100 kΩ1% to GND. At40 V the worst unloaded pre-node is2.795 V; the actual protected envelope is lower. Datasheet powered-off signal protection covers up to3.6 V and its2µA maximum leakage gives0.202 V through101 kΩ. U24's3.08 V threshold and reset assertion isolate the inputs before the declared slow rail-collapse budget expires. The 100 kΩ load changes nominal gain to0.06757. R49 measures protected input after D2, so old terminal-voltage calibration is not retained. [TI TMUX1511](https://www.ti.com/lit/ds/symlink/tmux1511.pdf), [TI TLV803E](https://www.ti.com/lit/ds/symlink/tlv803e.pdf).

4. **Missing-heartbeat permit.** U22 is the rising-edge retriggerable LTC6993HS6-2#TRMPBF: TRIG1=GPIO13/ACT_LED, GND2, SET3, DIV4, V+5, OUT6=HEARTBEAT_VALID. RSET100 kΩ and DIV191 kΩ/100 kΩ select positive-polarity divide code5,65.536 ms nominal. Static-high and static-low inputs both expire. U23 SN74LVC1G11DBVR has EN1, LOGIC_PG3 and HEARTBEAT_VALID6 as inputs, output4 on U19.23/RSTN, GND2 and VCC5. Its active-low output can overcome existing R88. U24 TLV803EA30DBZR uses GND1, RESET2 and VDD3; it is the3.08 V/200 ms nominal option, not another package-pin variant. [ADI LTC6993](https://www.analog.com/media/en/technical-documentation/data-sheets/LTC6993-6993-1-6993-2-6993-3-6993-4.pdf), [TI AND gate](https://www.ti.com/lit/ds/symlink/sn74lvc1g11.pdf).

The expander must not be described as generically resetting all ports to inputs. Its manufacturer specifies default GPIO outputs determined by AD1/AD0; here both pins are GND and the documented default table gives all outputs low. This supports disabled enables and programming gate drives. Verify the actual outputs during long reset, release and timeout, including load-dependent turn-off, rather than observing only RSTN. See [AWINIC product description](https://www.awinic.com/en/productDetail/AW9523BTQR) and its [manufacturer-authored V1.5 datasheet, mirrored by Waveshare](https://files.waveshare.com/upload/3/34/AW9523B-EN.pdf).

The heartbeat now uses existing U10 physical pad20/GPIO13/ACT_LED, also driving the existing Q20 LED gate. R96 and R118 are both10 kΩ, giving approximately5 kΩ total pull-down and0.66 mA high-state load at3.3 V. U22 TRIG is high impedance; no new static level/rating incompatibility was identified. GPIO2/pad22 returns to its exact original NC contract; no extra flash/boot strap is assigned. The activity LED is deliberately repurposed as a health/permit indication.

Only the software safety task may drive10 ms heartbeat pulses after required control tasks vote healthy. Remove every legacy activity writer, blink ISR, PWM and DMA source. **Unmodified legacy firmware may already toggle ACT_LED and retrigger this timer; the old assertion that it necessarily holds U19 reset is withdrawn.** Compatible firmware is mandatory before active operation. The timer detects missing edges/frozen levels, not the semantic health of unrelated software-generated pulses. Safe startup must initialize the policy, begin the dedicated heartbeat, await expander reset recovery, explicitly configure safe outputs, and only then accept active commands. Firmware remains deferred. Test the actual TRIG waveform and programming outputs on dummy loads.

The hardware permit controls the expander-driven enables; it is not a universal physical gate on every direct MCU transmit signal. Heartbeat must represent healthy required control tasks and the safety policy. Loss of an active programming/command session must cause that policy to release its active commands and stop the permit where applicable. The integrated logger is intended to operate standalone: merely having no host connection is not a fault. If firmware keeps emitting valid pulses after an active session loses its required ownership, this pulse detector cannot infer that loss. Include session-policy behavior, direct-TX idle behavior and actual programming outputs in end-to-end dummy-load tests.

## Original schematic preservation

Independent comparison against the frozen pre-P1 native XML confirms all259 baseline components remain and exactly18 safety components are added. All pre-existing endpoints agree except the15 declared changes; all23 pre-existing value changes match the remediation manifest. Every added device/pin matches that manifest. All24 recovered original capacitor rating fields remain, with only C14/C15 intentionally upgraded from35 V to50 V. The untouched original PDF hash still matches the recorded upstream source. This corroborates the detailed original-page comparison; it does not turn the recovered PDF into a hidden-pin/footprint authority.

## Completed independent layout review

Read-only native KiCad10.0.5 loading and in-memory zone refill report **zero uncapped airwires**, no disconnected net pad partitions and all193 GND pads in one connected group. Fresh all-severity native DRC has zero violations, zero unconnected items and zero schematic-parity issues; ERC remains zero. The saved PCB bytes were unchanged by the review.

All original263 footprint/pad geometries, rotations, sides and hierarchy paths are exact. All2804 retained original copper objects are exact; exactly55 declared ADC/supply objects are removed, including the three redundant ADC leaves. No C31 movement, IO0 reroute or original SD fanout exception was adopted. All nine zone/keepout definitions, board outline and project rules remain exact. No signal tracks occupy the In1 GND reference; all track widths meet0.15 mm. The unchanged RF/USB paths and antenna reserve therefore retain their earlier structural contract. These checks establish preservation and connectivity, not measured impedance/EMC performance.

The18 new safety parts and relevant C31/R106/R112 were checked against every same-side footprint using conservative native F/B.Fab-body plus pad bounding boxes:754 pairs, zero overlaps. Corresponding courtyard bounding boxes:750 pairs, zero overlaps where courtyards exist. Native front/back Fab/pad/courtyard and copper PDFs were rendered and visually inspected, using the PDF skill. The rejected C31 site that overlapped C28 is absent; C31 and C28 remain at their original locations. The broader all-part scan flags only the baseline-existing coarse J1/H1 envelope intersection, retained as an explicit mechanical qualification item below.

New analog/permit routes remain over the shared ground structure and every new ground pin is in the same native connected group. The J3 ground attachment includes a0.30 mm F.Cu track and filled/capped0.60/0.30 mm through via at(178.89,134.25) mm; all169 new vias have saved filled/capped flags. Retained original via processing flags are exact. Regenerated fabrication notes must carry all saved processing sites; ordinary tented holes are not interchangeable with the specified filled/capped process.

All277 actual model references are project-relative and their files are bundled. The original263 footprints' model paths, transforms and scales are unchanged; the18 safety model paths were made portable without any electrical/physical geometry change. Native2D review plots were produced immediately before that path-only correction; `rev-c-portable-model-paths.json` proves the geometry unchanged. The final hash was then independently reloaded, refilled and audited.

Detailed checks and via flags are in `rev-c-independent-layout-evidence.json`. The review plots are retained as work evidence under `work/p1-remediation/independent-{front,back}-{bodies,copper}.pdf`. No board, project or source PDF was saved by this review.

## Open qualification gates, separate from a demonstrated P1 design defect

- **Mechanical fit:** the unchanged coarse J1 housing/Fab envelope intersects the H1 M3 hole envelope near the connector corner. This is not proof of an actual3D collision, but connector housing, screw-head/standoff and enclosure fit must be confirmed from the exact ATTEND geometry before an assembly-fit claim. Same-side copper clearance alone cannot close that check.
- **Release BOM:** select actual C14/C15 parts giving the specified capacitance/rating in the1206 footprint after bias derating. Resolve D27–D29's generic `ESD5Z3V3` versus SOD-323 footprint with an exact compatible manufacturer part. Do not substitute a SOD-523 ordering code blindly. Specify the TVS, zener, FET and timing-resistor ordering codes/tolerances used by this contract. These are open procurement/release gates; the ADC topology no longer relies on those ESD diodes as precision clamps.
- **Bench gates:** instrument protected input, VPP, VBB and every programming FET VGS/VDS during the bounded pulse, including a command already active; verify temperature/pulse energy, ADC unpowered/ramp/brownout behavior, actual supervisor assertion and switch isolation, watchdog expiry and actual programming outputs. Qualify DMC3071 low-drive behavior on dummy loads. A28 V input/VPP bound must not be treated as proof that every internal transient is safe.
- **Prototype limitations:** safe-stop/card power-loss behavior, firmware calibration, RF/USB/SD behavior and existing thermal/VIPPO requirements remain. No arbitrary automotive transient, ECU programming, vehicle validation or production qualification claim follows from this schematic review.

The mandatory tests above measure declared assumptions; they are not evidence that another P1 failure has already been found. If any measured waveform violates the bounds, the conditional disposition expires and a new protection/drive design is required before vehicle use.


## 2026-10-22 presentation-only revalidation

Protection caps are grouped by PCI and SCI circuit. All 277 components, values, fields, footprints, sheet paths and named net endpoint sets are unchanged; see rev-c-protection-cap-grouping-audit.json. The PCB hash is unchanged. Fresh native ERC/DRC and full contract audit pass. Prior independent electrical review is retained; this is not a new independent review. Current XML SHA-256: `5f85cce75c464298ad5b482e1b51bf24356d38a2ffc3fd16dc32cd016a9b5d84`. Selected M3 socket-head/no-washer nominal fit and H1 tolerance limits are documented in rev-c-obd-mechanical-clearance.md.


## 2026-10-22 C61 top-side relocation

User authorized moving C61 to F.Cu at (193,127) mm, orientation 90 degrees. Pin 1 remains SD_3V3 and pin 2 GND. Exactly two obsolete unlocked SD_3V3 branch segments are removed; four 0.5 mm tracks and two 0.6/0.3 mm filled/capped vias are added. All retained copper and other placements are exact. R96 reference text alone is repositioned. Native all-severity ERC, full refill/track/parity DRC, body-overlap and native connectivity checks pass. See rev-c-c61-top-audit.json and source/verify_c61_top.py. This is an implementing-agent adversarial delta review; the prior independent review retains its original provenance. No new independent reviewer is claimed. C61 requires about 5.9 mm top-side component headroom; verify the actual enclosure.


## 2026-10-22 debug access addition

48 hook loops and four SPI probe pads are added on a dedicated page 24. Existing electrical components, pin assignments, placements, retained copper, zones, outline and mounting holes remain exact. 19 tracks and three processed vias are added; 22 existing via processing flags are upgraded for solder-pad overlap. The original 55 safety copper cuts and two earlier C61 cuts remain the only removals. Fresh ERC/DRC/parity, strict contract, native connectivity, body clearance and safety-bounds checks pass. This is an implementing-agent adversarial delta review, not a new independent review. See rev-c-testpoint-audit.json, rev-c-testpoint-map.md and the testPointReview record. Current PCB SHA-256: `68d206c7f3794b39c32291e626993844f60c12ea20ad78d16e5127c4ccebafd9`.

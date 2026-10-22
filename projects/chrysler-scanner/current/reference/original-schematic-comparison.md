# Original ChryslerScanner V240 schematic comparison

Compared 2026-10-21. This comparison reads the original upstream PDF and the migrated native design; it does not edit CAD. The original is a **single A2 page**, revision **2.4.0-1**, dated **2026-01-05**:

`original-atopile/reference/upstream/ChryslerScanner_V240_schematic.pdf`

Its SHA-256 is `334b04164cfa96183cf502f690024a764cc719671f20583043f37604c9ed590d`, matching the saved upstream provenance. The retained upstream commit is `4ddc6e5d1c260c87c6139f60079932ffde6e5d9a`.

## Comparison boundary and result

The original-PDF endpoint comparison uses the frozen pre-fix native netlist at commit `9399c5f9`, then reconciles the final revision C safety changes explicitly below. The final native preservation audit passes on PCB `974231631b323828ea5a2ac47578b0f7cad72a31981915fd154d734c6b78710e`. No original component or functional block is missing; revision C intentionally changes the protection circuits, ADC calibration and activity-LED role. It is not electrically identical to the original drawing.

At that baseline, **no original electrical component or functional block was found missing**. All **239 original electrical parts** in the USB-B PDF recovery remain in the 259-component native netlist. The 20 additions are the two USB-C CC resistors and the 18 integrated-SD components. The original four M3 mounting holes are retained as mechanical PCB footprints; they are not counted in those electrical-component totals.

The recovered original has 730 mapped package pins. Every original pin identifier other than the deliberately replaced J2 USB-B contact scheme exists in the native netlist. All original part values match except the intentional J1 and J2 connector replacements. The exhaustive endpoint comparison found only the documented differences listed below. This combines a visual check of the one-page PDF with a machine comparison against `original-atopile/reference/v240-usb-b-netlist.json`; it is not merely a component-count check.

## Functional blocks checked on the original page

| Original PDF area / circuit | Current native counterpart | Comparison at the frozen baseline |
| --- | --- | --- |
| A1, J1962M connector / battery input | Combined connector/protection sheet; vehicle-input sheet | J1 logical pin assignments, JP1 signal-ground link, D1/D2 and C1 retained. Connector mechanical replacement is intentional. |
| A2–A3, USB-B / power selection | USB sheet | U1 SY6283, JP2 bypass, D3, C2/C3 and power-path nets retained. USB-C contact mapping and separate CC terminations are additions. |
| A4–A6, 6 V pre-regulator and +5 V | Supply sheet | U2, L1, D4/D5, U3 and feedback/enable/output-sense nets retained. |
| A6–A7, +3.3 V | Supply sheet | U4, D6, C9/C10 retained. |
| A7–A8, PCI receiver | PCI sheet | U9 comparator, R4–R7, R18 and C11/C12 topology retained, including 3.3 V PCI_RX pullup. |
| B1–B3, VPP boost | VPP sheet | U5, L2/L3, D7 and feedback/output filtering retained. |
| B3–B5, VBB bootstrap rail | VBB sheet | U6, L4, D8 and feedback/output filtering retained. |
| B5–B7, PCI +7.5 V rail | 7.5 V sheet | U7, U8, L5/L6, D9/D10 and the two feedback networks retained. |
| B7–B8, PCI transmitter / line protection | PCI and input-protection sheets | Q1, R19–R21, D11/D12 and C25 retained. |
| C1–D3, ESP32 and RF | MCU sheet | ESP32-PICO-V3-02 identity, original supply/reset/UART/I2C/ADC/RF nets retained; six previously unused pads serve SD controls/data. AE1 and optional RF matching positions retained. |
| C3–D4, USB/UART bridge | USB sheet | Classic CP2102 pin mapping, USBLC6-2SC6, VBUS divider, reset, RTS/DTR and serial nets retained. This remains CP2102, not CP2102N. |
| C4–E8, four SCI TX / two SCI RX paths | Three SCI sheets plus input protection | All Q2–Q4 sections, U13–U15 switch channels, enables, bias and named vehicle pins retained. Shared TX2/RX2 routing and J1962 pin assignments match. |
| E1–E3, reset/boot and auto-program | USB/reset sheet | SW1/SW2, R48, C45/C46 and both Q5 transistor sections retained. |
| E3–E5, battery / VBB / VPP monitors | ADC sheet | Original three dividers, D27–D29 and C47–C49 retained. V_BA is U10 pad 13, V_BT pad 10, V_PR pad 11. |
| E5–E6, SCI selectable bias | SCI TX6/TX12/bias sheet | Q6, R75/R76 and RX7_BIAS_EN retained. |
| E6–E8, CCD termination, bias and filter/protection | CCD plus input-protection sheets | Q7, R77–R82, D13/D14 and C50/C51 retained. J1962-3 is CCD+, J1962-11 CCD−. |
| F1–G5, VBB/VPP programming switches | Four programming-driver sheets | All eight driver branches, Q8–Q15 sections, R55–R74 and D15–D22 retained. |
| F5, internal I2C connector | Control sheet | J3 +5 V, GND, SDA and SCL retained. |
| F5–F6, CCD receiver | CCD sheet | U16, R83–R85, C52/C53 and RX1 retained. |
| F6–G7, I2C expander | Control sheet | U19 AW9523B, reset pullup, grounded address straps, supply capacitors, I2C pullups and all 16 output/control nets retained. |
| F7–G8, status LEDs | LED sheet | D23–D26, Q17–Q20 and all indicator resistors/control nets retained. |
| G5–H6, CCD transmitter | CCD sheet | U17/U18, Q16, R97–R101 and C54/C55 retained, including the inverted/non-inverted TX1 paths. |
| H1–H2, mounting / assembly notes | PCB / manufacturing instructions | Four M3 holes remain. Original tooling-hole/fiducial note assigns those additions to the manufacturer; it is not an electrical circuit omitted from the native sheets. |

## Exhaustive intentional differences at the frozen baseline

1. **J1 mechanical connector:** the original generic `J1962` is the ATTEND `226A-1202`. Every original logical net/pin relationship remains, including pin 4 chassis/common GND and pin 5 through JP1. Original pins 1/8/10/13 remain unused.
2. **J2 USB-C conversion:** the original USB-B pads 1–5 are replaced with the USB4105 A/B contact scheme. A4/A9/B4/B9 carry VBUS; A6/B6 carry D+; A7/B7 carry D−; the corresponding ground contacts and shell are grounded. R102 and R103 independently terminate CC1 and CC2 to GND. USB-C does not add PD or USB-CAN functionality.
3. **TLV767 hidden/omitted ground pin correction:** U3/U4/U8 package pad 5 changed from the recovered source's NC assumption to GND. The PDF symbols do not depict pad 5; they depict GND pad 3 and exposed pad 7. The actual DRV package requires both pins 3 and 5 grounded. This is a deliberate datasheet correction, not an omitted original circuit. Original OUT/SNS/FB/EN/IN relationships remain.
4. **Integrated SD additions:** U10 package pads 5, 6, 7, 21, 27 and 38 were unused in the original. They now serve SD_MISO, LOG_BUTTON, SD_DETECT, MCU_SD_CS, MCU_SD_MOSI and MCU_SD_SCK respectively. Existing original MCU endpoints were not reassigned. U20, J4, C58–C61, R104–R114 and SW3 are additions.
5. **Presentation and physical corrections:** splitting the single page into native hierarchy, combining connector/protection, using global ground symbols, changing ground-label positions, adding checked routing, and correcting CP2102/USB footprint geometry do not create an original-circuit omission. Original PCB reference placements are not encoded by the schematic PDF; the source PDF cannot certify physical trace or enclosure equivalence.

## Original information missing from the migrated release BOM

The original PDF contains capacitor voltage labels that were lost when its values became the generic `Value` entries in `current/BOM.csv`. Those labels matter and should be carried into specified part/rating fields. They are not evidence that a real populated part already has that rating.

| Original explicit capacitor rating | References |
| --- | --- |
| 50 V | C1, C4, C13, C16, C20 |
| 100 V | C5, C17, C21 |
| 35 V | C14, C15 |
| 25 V | C6, C7, C8, C9, C10, C18, C19, C22, C23, C24 |
| 10 V | C26, C27, C35, C56 |

These 24 labels were matched to their neighboring capacitors using PDF text coordinates and visually cross-checked in the source drawing. In particular, C14/C15 are **35 V** parts on the VPP section; do not infer 25 V just because other output capacitors use 25 V. USB C2/C3 are marked **10 µF**, not “10 V”; no explicit voltage label was identified for those two in that block. Other parts without an explicit recovered rating still need a proper engineering part selection, capacitance derating and complete manufacturer part numbers.

The PDF also carries feedback accuracy, coil current and ADC calibration annotations that are absent from the generic value/footprint BOM. The battery-divider annotation uses 8.66 kΩ / 1.62 kΩ and gives 10.5 V → 1.655 V, 14.8 V → 2.332 V. Changing divider attenuation as a safety fix must update the associated voltage-conversion/calibration contract. Matching the old resistor ratio is not itself evidence of safe transient behavior.

## Safety fixes must be explicit deviations, not silently reverted

All three high-priority review concerns are already present in the original drawing: SMBJ30CA battery suppression feeding LMR14010 inputs, the raw-battery ADC divider, and the independently powered AW9523B reset pullup. Reproducing those topologies faithfully does not close the design review. The requested corrective revision should preserve the original scanner functions while documenting the exact protection/control changes, any added parts, changed signal names, calibration consequences and firmware obligations.

No CAN transceiver appears in the original PDF either. Adding a CAN block would be a new capability, not restoration of missing original content.

## Limits and repeatability

The archived editable upstream KiCad schematic is not available in this source set. The recovered original JSON is derived from this same PDF and includes inferred package pins (for example exposed pads), so it is supporting evidence rather than a completely independent upstream netlist. The visual check and complete endpoint comparison substantially reduce omission risk but cannot prove every hidden package pin from a one-page rendering alone. Device datasheets, the final native netlist/PCB parity check and footprint drawing checks remain necessary.

Working evidence is under `work/original-comparison`: source rendering, PDF text/word coordinates, a frozen pre-fix native XML, the exact baseline endpoint/value diff and the recovered capacitor-rating map. No source PDF, original project or CAD file was modified.

## Final revision C reconciliation

The final native XML has SHA-256 `249456fcca8f9c3deaea80b8c109878cd1c975821f7d1cf4fe1e64f4a7d967a8`. The checked PCB is `974231631b323828ea5a2ac47578b0f7cad72a31981915fd154d734c6b78710e`. The independent full release audit passes with `releaseGatePassed: true`: fresh native DRC has zero violations, unconnected items and parity findings; ERC is clean; every native pad partition and all ground pads are connected. These are CAD validation results, not automotive qualification.

All 259 pre-fix electrical parts remain. The candidate has 277 electrical components / 281 PCB footprints, adding exactly U21–U24, R115–R123, C62–C65 and D30. All original reference placements, mounting holes, outline, nine zone/keepout definitions, stackup and project rules are preserved. No C31, R106, R112, IO0 or SD-chip-select routing exceptions were adopted. Exactly 55 original copper objects from the explicit supply/ADC removal contract are retired; every retained original copper object's geometry, net and saved flags remains exact. All 380 retained locked objects and 173 historical protected objects pass preservation checks; the single original locked ADC removal is explicitly documented in the frozen contract.

The 23 existing-value changes are deliberate: D1 → `SMBJ16CA`; R49/R51/R53 → `22k 1%`; R50/R52/R54 → `1.62k 1%`; R64/R67/R70/R73 → `4.7k 1%`; R65/R68/R71/R74 → `8.2k 1%`; Q8–Q11 → `DMC3071LVT-7`; Q12–Q15 → `DMG6601LVT-7`. All 24 original capacitor voltage fields are explicit; C14/C15 intentionally upgrade from 35 V to **50 V minimum**, while the other 22 ratings remain unchanged.

Exactly **15 old endpoint-to-net assignments** change:

| Existing endpoint(s) | Before | Final revision C |
| --- | --- | --- |
| U9.5, C11.2 | +12V | PCI_VCC via R123/D30 supply clamp |
| R49.1 | raw J1962-16 | protected +12V after D2 |
| R49.2, R50.1, C47.1, D27.1 | V_BA | V_BA_PRE |
| R51.2, R52.1, C48.1, D28.1 | V_BT | V_BT_PRE |
| R53.2, R54.1, C49.1, D29.1 | V_PR | V_PR_PRE |

Every other original endpoint and the frozen SD mapping remain exact. U21 isolates the three ADC post-nets, which R120–R122 pull down. U19.23 remains N_R88_2 and now receives U23's hardware permit. The final circuit has 162 connected nets, 40 no-connect pins, 22 child sheets / 23 pages and 168 native hierarchical ports. Explicit junctions restore the existing ground contracts at J2 shell, J3.4 and J4.10 after wire normalization.

The final heartbeat uses **GPIO13 / U10 pad20, ACT_LED**, with U22.1 and R118.1 added to that existing net. GPIO2 / U10 pad22 remains its exact original no-connect. This is an intentional semantic change: the LED now indicates dedicated software health/permit heartbeat, not arbitrary activity. Only the safety-control task may service the 10 ms heartbeat after required tasks report healthy. Remove all legacy activity writers and autonomous PWM/DMA/blinking sources. Legacy firmware already drives ACT_LED and can accidentally retrigger the timer; it must not be claimed to hold the expander safely in reset or to be compatible with active Rev C operation. Hardware detects missing edges and frozen levels, not whether software pulses truly represent health. Compatible firmware remains deferred.

ADC calibration also changes. The effective lower leg is approximately `1.62k || 100k = 1.594k`, giving nominal gain **0.06757** with a 22k upper leg. Include switch resistance/leakage, tolerances and ADC characterization. Battery measurement is after D2, so connector-voltage reporting includes a current/temperature-dependent diode-drop correction.

Earlier initial-candidate XML evidence used a GPIO2 heartbeat and 16 endpoint changes; it is superseded by the exact final binding above. Its hashes and scratch reports are historical, not final release evidence.

## Bounded prototype limits

No unexpected original-circuit omission was found. This establishes reconstruction and controlled revision, not electrical qualification. Normal input is 9–16 V; sustained 24 V and jump-start operation are unsupported. Protected input/VPP must remain ≤28 V including overshoot within the specified bounded pulse, energy, ambient and supervisor-fall assumptions. Hardware measurements must validate TVS/fuse coordination, PCI clamp temperature, ADC powered/unpowered faults, watchdog timing, programming switch behavior and thermal margins. Q8–Q11 gate drive at 3.0–3.3 V is a qualification item because on-resistance is guaranteed at 4.5 V. Exact generic BOM selection and capacitor bias/thermal derating remain incomplete. See the final safety contract and final independent adversarial review for accepted bounds and outstanding bench tests.

Final portability-only metadata correction: the 18 added safety footprints now use bundled `${KIPRJMOD}/3dmodels/standard` model paths. Original models, electrical endpoints and all geometry remain unchanged. `rev-c-portable-model-paths.json` records the correction; fresh full native DRC and strict release audit pass on the final PCB hash above.


## 2026-10-22 presentation-only revalidation

Protection caps are grouped by PCI and SCI circuit. All 277 components, values, fields, footprints, sheet paths and named net endpoint sets are unchanged; see rev-c-protection-cap-grouping-audit.json. The PCB hash is unchanged. Fresh native ERC/DRC and full contract audit pass. Prior independent electrical review is retained; this is not a new independent review. Current XML SHA-256: `5f85cce75c464298ad5b482e1b51bf24356d38a2ffc3fd16dc32cd016a9b5d84`. Selected M3 socket-head/no-washer nominal fit and H1 tolerance limits are documented in rev-c-obd-mechanical-clearance.md.


## 2026-10-22 C61 top-side relocation

User authorized moving C61 to F.Cu at (193,127) mm, orientation 90 degrees. Pin 1 remains SD_3V3 and pin 2 GND. Exactly two obsolete unlocked SD_3V3 branch segments are removed; four 0.5 mm tracks and two 0.6/0.3 mm filled/capped vias are added. All retained copper and other placements are exact. R96 reference text alone is repositioned. Native all-severity ERC, full refill/track/parity DRC, body-overlap and native connectivity checks pass. See rev-c-c61-top-audit.json and source/verify_c61_top.py. This is an implementing-agent adversarial delta review; the prior independent review retains its original provenance. No new independent reviewer is claimed. C61 requires about 5.9 mm top-side component headroom; verify the actual enclosure.

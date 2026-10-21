# Adversarial schematic and layout review

Reviewed 2026-10-21 against the native integrated-SD project in `current`. No CAD was changed by this review. PCB SHA-256: `85011cefd33c4d6a623440d91eeb9876282d39dc7fc6a37eb90d50e2a278c36a`.

**Verdict: connectivity is clean, but the design should remain a prototype rather than an electrically qualified vehicle product.** Two protection-coordination gaps and an active-mode fail-safe gap need resolution before an unrestricted vehicle-use claim. A fabrication package exists; that is different from electrical sign-off. The review did not establish that the board will fail in ordinary 12–14 V receive-only operation.

P1 below means resolve before vehicle electrical release. P2 means close before a production/assembly release or before claiming the affected capability. A rating gap is not a claim of observed damage. Measurement gates are explicitly separated from schematic defects.

## Actionable findings

### P1 — Input TVS does not establish a safe clamp below the buck-regulator limit

**Evidence:** `final-netlist.xml` connects D1 `SMBJ30CA` directly between raw `J1962-16` and GND. D2 `SS56` then feeds `+12V`. U2.5 and U7.5 (`LMR14010`) connect to `+12V`; there is no intervening surge-stopper or regulated input clamp. C1 and C4/C13/C20 also see that rail. The nominal 12 V name is not a voltage limiter.

The [TI LMR14010A specification](https://www.ti.com/lit/ds/symlink/lmr14010a.pdf) permits 40 V operation and 45 V maximum input/transient stress. A representative [Littelfuse SMBJ30CA](https://www.littelfuse.com/~/media/electronics/datasheets/tvs_diodes/littelfuse_tvs_diode_smbj_datasheet.pdf.pdf) is specified to clamp at 48.4 V at its rated 12.4 A pulse point. A forward series diode does not provide a guaranteed several-volt reduction. Consequently, this combination does not guarantee the downstream input stays below 45 V during its rated TVS pulse condition.

**Consequence:** a sufficiently energetic positive transient can overstress the buck inputs even while the TVS is operating according to its specification. This does not prove that a particular vehicle waveform reaches that condition. The generic BOM does not lock D1's manufacturer or U2/U7's complete ordering code, so those must be fixed before the final coordination calculation.

**Required action:** define the allowed input, jump-start and surge waveforms plus source impedance/upstream fuse; select exact protection and regulator parts; calculate worst-case clamp including tolerance, temperature and wiring inductance. Change the protection architecture or voltage ratings where necessary. Verify the protected rail with controlled transient tests before vehicle use. Do not treat a 600 W, 10/1000 µs TVS rating alone as a load-dump qualification.

### P1 — Raw-battery ADC divider reaches the MCU input range before the TVS can clamp it safely

**Evidence:** raw `J1962-16` feeds R49 `8.66 kΩ`; its other end is `V_BA`, connected to R50 `1.62 kΩ` to GND, C47, D27 `ESD5Z3V3`, and **U10 pad 13**. This is separate from `V_BT` on U10 pad 10. The unloaded DC divider is:

`V_BA = Vbattery × 1.62 / (8.66 + 1.62) = 0.15759 × Vbattery`.

It produces about 3.782 V at 24 V input, and reaches 3.6 V at about 22.84 V. The [ESP32-PICO electrical specification](https://documentation.espressif.com/esp32-pico_series_datasheet_en.html) gives the input high-voltage range only through its respective VDD + 0.3 V. The intended 3.3 V domain therefore does not establish a 3.78 V input allowance.

The name `ESD5Z3V3` is insufficient protection evidence. For example, the exact-name [Diotec ESD5Z3V3](https://diotec.com/en/product/ESD5Z3V3.html) has 3.3 V **stand-off**, 5 V minimum breakdown at 1 mA, and 8.4 V clamping at 5 A. It does not guarantee a 3.3/3.6 V clamp. The actual manufacturer is unspecified, so this example must not be mistaken for an identified installed part.

**Consequence:** 24 V jump-start or larger positive input events can exceed the published input range; turning the MCU off makes the allowed powered-domain relationship more restrictive. R49 limits current, so observed damage is not proven. Relying on an undocumented internal MCU clamp/injection allowance is still an unclosed protection design.

**Required action:** define the maximum raw input and powered/unpowered states; redesign attenuation and/or add a specified input clamp/buffer with guaranteed leakage and injection-current limits. Preserve measurement accuracy and ADC settling. Verify the other monitoring channels `V_BT` and `V_PR` against their own maximum rails and failure states as well. Demonstrate pin voltage and injection behavior under the chosen transients, rather than relying on the TVS voltage label.

### P1 — MCU reset does not guarantee release of latched bus/programming enables

**Evidence:** U19.23 `RSTN` is on `N_R88_2`, connected only to R88 `4.7 kΩ` up to `+3.3V`. The MCU's `EN` reset net is separate. U19 controls the `VPP_TO_TX6/9/12/14`, `VBB_TO_TX6/9/12/14`, transmit enables and receive/bias controls. The [AW9523B datasheet](https://doc.awinic.com/doc/202403/deffbf3b-7e7b-4ff6-8e91-fd85e2d845d5.pdf) describes power-on, hardware-pin and software resets; a reset of another chip does not clear its output registers while U19 stays powered.

**Consequence:** if a programming/bus output has been asserted and U10 is reset, hangs or loses command ownership, the corresponding expander output can remain asserted. Passive pulldowns establish a default for an undriven signal but cannot defeat an actively driven high output. Cold power-on defaults being low do not solve a powered MCU-only reset. This finding applies to active/programming operation; it does not claim that receive-only bench operation spontaneously generates programming voltage.

**Required action:** specify a safe state and maximum release time for every bus/programming output under external reset, watchdog reset, firmware hang and communication loss. Implement an independent hardware permit/interlock or watchdog-backed disable path that actually removes the programming/bus drive. Coordinating external reset pins alone is insufficient for internal watchdog resets that do not change CHIP_EN. Prove the result with dummy loads and forced failures before ECU connection. Software startup writes can be part of recovery but do not provide an independent fail-safe during the reset/hang interval.

### P2 — Assembly BOM is not sufficiently specified to validate protection, capacitance or package fit

**Evidence:** `current/BOM.csv` supplies value, footprint and quantity but leaves many datasheet/description fields empty and has no manufacturer/MPN/rating columns. `v240-netlist.json` explicitly labels several parts Generic and includes outstanding package-choice verification notes. C1 is only `100µF`; the C4/C13/C20 group is only `10µF`. D27–D29 are `ESD5Z3V3` on `D_SOD-323` footprints, while the Diotec exact-name example above is SOD-523. D12–D14 likewise have a generic diode value with a package-choice note.

**Consequence:** a purchaser can select an electrically or mechanically incompatible part while satisfying the visible BOM value. In particular, 10/22 µF nominal MLCC values do not establish effective capacitance under DC bias, temperature and tolerance; an unspecified C1 voltage rating cannot establish transient survival. The Diotec example is a **conditional** footprint mismatch, not proof that an already-selected vendor part is wrong.

**Required action:** lock manufacturer/orderable part, package drawing, voltage rating, dielectric, tolerance, temperature and qualification requirements for the release BOM. Recheck every recovered footprint against the chosen drawing, especially protection diodes and power parts. Record DNP and assembly options unambiguously. Obtain an assembly DFM review using that BOM and the actual footprint geometry.

### P2 — Added SD load has no demonstrated system-current or thermal margin

**Evidence:** U20 is `MCP1825S-3302E/DB`, a 500 mA 3.3 V LDO fed from main `+5V`. The same +5 V supplies U4 and existing scanner loads. Vehicle power passes through U2 and U3, both 1 A-class devices. USB uses J2 → U1 → D3 → the same rail. R102/R103 are passive 5.1 kΩ CC terminations; no CC-current measurement/controller appears in the netlist. A 500 mA SD regulator is not evidence of 500 mA spare upstream capacity or USB-source permission.

At 300 mA SD load U20 dissipates approximately 0.51 W; at 500 mA, 0.85 W. Its physical tab is GND on the underside at approximately (186.85, 128) mm, in a populated four-layer layout. The [Microchip datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP1825-Family-Data-Sheet-DS20002056.pdf) makes thermal capability board-dependent. The saved geometry and DC continuity do not establish the needed junction temperature. The other LDOs also dissipate heat concurrently.

**Required action:** produce a worst-case whole-board current budget for each power source and operating mode, including SD initialization/write peaks, radio operation and active interfaces. Measure rail droop and U2/U3/U4/U20 temperature with the selected card and intended enclosure/ambient. Confirm USB descriptors/current behavior against the actual source. Set firmware limits or revise power conversion/copper if the measured margin is insufficient. This is an unqualified capability, not a demonstrated overload.

### P2 — SD interface and separate 3.3 V domains need waveform and power-sequence qualification

**Layout evidence:** native track sums give `SD_MISO` 62.062 mm of copper, five vias and three signal layers. `MCU_SD_SCK` is 6.014 mm before R104, followed by 32.849 mm on `SD_SCK`. `MCU_SD_CS` is 16.754 mm before R106 despite R106 being physically close to U10; its routed source-side length, not center-to-center distance alone, determines the undamped interconnect. These sums include all branches and are not a timing simulation.

**Electrical evidence:** U20's `SD_3V3` is separate from U4's logic `+3.3V`. SD signals connect directly or through 33 Ω resistors; pullups exist on both domains. There is no isolation/bus switch establishing safe arbitrary rail ordering. No accessible-socket ESD array is listed on J4's SPI contacts.

**Consequence:** DC connectivity and a 4 MHz initial target do not prove edge quality, setup/hold margin, hot-plug robustness or safe behavior when either rail collapses first. These are risks requiring measurements; this review does **not** prove that the present routing fails or that it must be rerouted.

**Required action:** scope clock/MOSI/CS/MISO at source and socket using realistic edge rates and representative cards; verify errors under simultaneous recording/radio traffic. Measure rail ordering, backfeed and pin voltage at cold start, brownout and unplug. Define allowable hot-plug/ESD handling and add appropriate protection or sequencing if required. Choose a validated clock ceiling from results.

## Manufacturing and remaining qualification gates

- Native design calls for resin-filled, copper-capped, planarized vias at 35 recorded sites. Drill intersections with fine-pitch SMT apertures cannot be handled by substituting ordinary tented/open vias. Obtain explicit fabricator and assembler acceptance of the VIPPO list, stencil/reflow plan, finished mask openings and exposed-pad processing. This requirement is already documented; it remains a real purchase condition rather than a new DRC defect.
- A nominal stackup **is** saved: four 35 µm copper layers, 0.18 mm outer dielectrics and a 1.08 mm center dielectric. The actual fabrication stackup, RF matching and USB return paths still need review/measurement. `LNA_IN` and antenna-feed copper are 0.3 mm wide on the top layer. USB net sums across the ESD device are approximately 28.55 mm for D+ plus D+P and 30.91 mm for D− plus D−P, with two vias on each connector-side net. These sums alone are not an eye diagram, impedance proof or a reason to demand equal-length routing on a full-speed link.
- Verify cold-start, brownout and host-command safety of the SCI/programming stages with dummy loads before connecting an ECU. There are real VBB/VPP drivers; a software error can be materially different from a passive receive error. The AW9523B address straps are grounded and its documented default outputs are low, which is reassuring, but does not replace end-to-end enable-state testing.
- Continuous recording has no power-loss hold-up/shutdown guarantee. Select the card and file/journal strategy, test interrupted writes and recovery, and state the maximum loss window. Existing safe-stop controls are not protection against a sudden cable/battery loss.

## Checks that did not become findings

The fresh cross-check in `reference/adversarial-review-evidence.json` records the reviewed PCB hash, relevant net endpoints, route metrics and ignored checks. The current final reports show zero native DRC violations, zero missing connections, zero schematic parity findings and zero ERC findings. The independent audit reports all 175 GND pads connected and preserves the original 174 protected copper objects, placements, nine zones and rules. This reviewer inspected the native board through KiCad's Python API and the endpoint netlist, plus top rendering and manufacturing notes. I did not manufacture or energize hardware, perform an EMC/ESD test, run a field solver, or measure a physical prototype.

Recovered functional symbols largely use passive pin types. ERC therefore cannot independently validate IC supply pin assignments, output contention, logic voltage compatibility or transient ratings. New native ground power symbols improve presentation but do not change this limitation. The DRC report also retains documented disabled checks, including missing courtyard and holes-inside-courtyard checks; clean DRC is not an enclosure/assembly fit certificate.

I specifically checked several tempting false positives: RX1 and PCI_RX have 3.3 V pullups rather than 5 V/12 V pullups; U12's VDD/REGIN tied to external 3.3 V matches the CP2102 bypass arrangement in the [Silicon Labs datasheet](https://www.silabs.com/documents/public/data-sheets/CP2102-9.pdf); U3/U4/U8's DRV ground/sense mapping agrees with the [TI TLV767 pin table](https://www.ti.com/lit/ds/symlink/tlv767.pdf). No new pinout error was established in these checks. Nexperia's [74LVC1G14 transfer thresholds](https://assets.nexperia.com/documents/data-sheet/74LVC1G14.pdf) also do not justify treating the 3.3 V MCU → 5 V Schmitt-input path as an ordinary 0.7×VCC CMOS mismatch.

The lack of CAN hardware and deferred logging firmware are existing scope limits, not newly discovered schematic defects. No fixes have been applied as part of this report.

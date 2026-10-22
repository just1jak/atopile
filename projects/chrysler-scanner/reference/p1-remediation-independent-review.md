# Independent targeted review of the P1 corrective schematic

Historical design evolution. Final revision C acceptance and adopted GPIO13 health-heartbeat contract are in `current/reference/rev-c-adversarial-review.md`; earlier GPIO2 proposals were not adopted.

> Final decision: see "Adopted GPIO13 health-heartbeat implementation" at the end. Earlier candidate issues and GPIO2 routing discussions are retained as audit history and are superseded where stated.

Reviewed 2026-10-21. Scope: `work/p1-remediation/candidate`, exported `work/p1-remediation/netlist-initial.xml`, construction manifest, native schematic definitions, and `reference/original-schematic-comparison.md` / its candidate endpoint diff. PCB routing was ongoing; this report does not approve final routing or fabrication outputs.

## Disposition

The three proposed corrective topologies are present and their new IC physical pin assignments match the exact selected package datasheets. No unintended original-circuit omission is evident in the endpoint comparison. One additional component-rating issue requires resolution before the 40 V protected-rail envelope is accepted: C14/C15 remain specified 35 V on a boost output that can pass the protected input through. Final PCB verification, release BOM selection, firmware integration and bench qualification remain separate requirements.

## Blocking rating issue: VPP capacitors versus the new transient envelope

C14.1 is on `N_R8_1`, shared with D7.1 and L3.1; C15.1 is on VPP after L3. The upstream path is +12V → L2 → D7 → C14/L3 → C15/VPP. This passive boost-output path exists regardless of stopping boost switching. The candidate permits a protected input transient approaching 40 V, while the restored original capacitor fields specify C14/C15 as 35 V. Therefore a 40 V input bound does not establish a <=35 V capacitor-voltage bound. Raise both capacitor voltage ratings to at least 50 V with package/capacitance derating and suitable parts, or prove a lower VPP clamp under the declared waveform. This is a release-rating gap, not a claim that an assembled board has already failed. The original comparison correctly preserved the historical 35 V labels; this corrective revision must intentionally supersede them.

## Verified corrective connections

| Device | Verified physical pin contract |
| --- | --- |
| U21 TMUX1511PWR, TSSOP-14 | SEL1/2/3 pins1/4/10 = LOGIC_PG; S1/2/3 pins2/5/9 = V_BA_PRE/V_BT_PRE/V_PR_PRE; D1/2/3 pins3/6/8 = MCU V_BA/V_BT/V_PR; GND7, VDD14. Unused fourth channel pins11/12/13 tied GND. |
| U22 LTC6993HS6-2#TRMPBF, TSOT-23-6 | TRIG1 = SAFETY_HEARTBEAT; GND2; SET3 = R115; DIV4 = R116/R117; V+5 = +3.3V; OUT6 = HEARTBEAT_VALID. Correct rising-edge retriggerable -2 variant. |
| U23 SN74LVC1G11DBVR, SOT-23-6 | Inputs1/3/6 = EN/LOGIC_PG/HEARTBEAT_VALID; GND2; output4 = U19.23 RSTN / N_R88_2; VCC5 = +3.3V. |
| U24 TLV803EA30DBZR, SOT-23-3 | GND1; open-drain RESET2 = LOGIC_PG with R119 pull-up; VDD3 = +3.3V. Exact part encodes 3.08 V threshold / 200 ms nominal release delay. |
| D30 / R123 | D30 cathode1 PCI_VCC, anode2 GND; R123 +12V → PCI_VCC; U9.5 and C11.2 moved to PCI_VCC. |

Primary pin/function sources: [TI TMUX1511](https://www.ti.com/lit/ds/symlink/tmux1511.pdf), [ADI LTC6993](https://www.analog.com/media/en/technical-documentation/data-sheets/LTC6993-6993-1-6993-2-6993-3-6993-4.pdf), [TI SN74LVC1G11](https://www.ti.com/lit/ds/symlink/sn74lvc1g11.pdf), [TI TLV803E](https://www.ti.com/lit/ds/symlink/tlv803e.pdf).

The resulting RSTN permit is EN AND LOGIC_PG AND HEARTBEAT_VALID. R88 remains a pull-up but cannot defeat U23 actively driving low. R115=100k, R116=191k, R117=100k select positive-polarity DIVCODE5 and 65.536 ms nominal timeout. Absence of edges, including a frozen high input, expires the permit. This is a bounded timeout; it is not instantaneous response to an internal MCU reset.

U10 physical pad22 is **GPIO2**, connected only to R118 10k pull-down and U22.TRIG. GPIO4 is pad24 and already TX2. GPIO2 must stay low through reset and the >=1 ms strap interval after CHIP_PU rises; application-controlled pulses may follow. Its low strap supports UART download with GPIO0 low. Verify real reset/download behavior. [Espressif package and boot configuration](https://documentation.espressif.com/esp32-pico_series_datasheet_en.html).

## Bounds, calibration and qualification

R49/R51/R53 are 22k; R50/R52/R54 remain1.62k. Worst 1% ratio gives <=2.795 V at a 40 V nonnegative source, including when the switch is open. Powered-off U21 signal protection is specified to3.6 V; its maximum2µA leakage through a worst-case101k post-pull-down contributes about0.202 V. Enabled100k post-pull-downs reduce the effective lower leg to approximately1.594k: nominal reconstruction multiplier is approximately14.800, with switch resistance/leakage and actual calibration added. R49 now measures protected +12V after D2, not raw connector battery voltage. Do not reuse the original calibration.

The supervisor/isolation combination still requires the declared <=5mV/µs normal rail-collapse qualification; arbitrary hard shorts are excluded. Test ADC pins during startup, brownout, unplug, rail faults and restart. The 40 V bound on all measured source rails also needs to be enforced by the operating/transient contract, not inferred from ADC attenuation.

D30 standard-footprint thermal rating is375mW at25°C, not830mW without1cm² cathode copper. At continuous24 V, approximate0.13 W dissipation gives43°C rise on the specified330K/W reference mounting. An85°C ambient target has plausible margin;125°C ambient does not. R123 and D30 pulse/thermal behavior must cover the selected transient duty. Normal U9 headroom is adequate at>=9 V connector input under the conservative supply-drop calculation in the design recommendations. [Nexperia BZT52H](https://assets.nexperia.com/documents/data-sheet/BZT52H_SER.pdf).

Required integration: software heartbeat serviced by the scanner control logic, every10ms, after boot; no independent PWM/DMA heartbeat. Firmware without that change holds U19 reset. On timeout recovery, release reset via heartbeat before waiting for I2C ACK, then reinitialize all U19 outputs and directions safely before active commands. Test actual programming outputs on dummy loads, not only RSTN.

## Original preservation and remaining release gates

The candidate diff retains259 baseline electrical components and adds18. Original deviations are explicit: D1 TVS value, three divider values, protected battery measurement source, three inserted ADC switch paths, comparator supply clamp and GPIO2-driven watchdog/reset path. The earlier USB-C/SD additions and regulator hidden-ground correction remain documented in the original comparison. No CAN capability has been added.

This review found no additional pin-map blocker among the new ICs. It does not certify final PCB geometry: rerun native ERC/DRC/refill/parity, independent connectivity including all GND pads, reference-placement and retained-copper preservation checks after routing. Regenerate the release BOM, PDFs, hashes and fabrication archive from that exact final candidate. Specify exact capacitor/resistor/zener parts and ratings, including the conditional D27–D29 package ambiguity described in the earlier adversarial report. Existing VIPPO fabrication, RF/USB/SD signal integrity, regulator/card thermal loading, and vehicle transient/dummy-load qualification remain applicable. Most recovered legacy symbol pins are passive, so zero ERC alone cannot establish electrical correctness.

## Subsequent downstream check and lower-envelope option

The proposed 40 V survival envelope must also cover Q12–Q15, not just capacitors and the ADC switch. Their source pins2 connect VPP; the switching topology leaves off-state transistor terminals facing the vehicle-side path. The precise HSW4602 manufacturer datasheet must be archived and checked: manufacturer-distributor tables identify approximately30 V drain-source limits, which would invalidate40 V survival independently of C14/C15. Treat this as an unresolved procurement/rating blocker until the primary document confirms the actual fitted part; no exact-source specification is inferred from a generic package name.

Even lowering the rail bound to28 V requires checking the active P-channel gate stress. The actual gate divider is4.7k source-to-gate and1.1k gate-to-N-channel-drain. When the N-channel device pulls low, nominal |VGS| = VPP*4.7/(4.7+1.1) =0.8103*VPP, approximately22.69 V at28 V. If the exact part's gate limit is±20 V, this exceeds it. Prohibiting initiation of programming above16 V does not address an input transient during an already active programming command. A candidate correction is R65/R68/R71/R74 from1.1k to2.7k: the fraction becomes0.6351, giving17.78 V at28 V and approximately12 V at18.85 V normal VPP. Check resistor tolerance, gate transient/overshoot, actual pin mapping and current before accepting that correction.

A lower main TVS such as exact Littelfuse SMBJ16CA, with declared9–16 V normal input and no24 V jump-start/steady-input claim, is a practical architecture direction. Its specified clamp and the measured PCB overshoot must establish a protected rail below the transistor rating, e.g. a28 V maximum target. This requires explicit bounded source current, pulse duration/energy, repetition and source fusing; an arbitrary automotive transient claim remains unsupported. Retain the independent15 V U9 clamp and higher capacitor ratings for margin. This paragraph records a proposed alternative, not an implemented or qualified final revision.

## Exact-part alternative and numerical gate-divider check

HSW4602 manufacturer PDF retrieval remained unsuccessful: the cached archive could not be opened and the distributor download linked an expired signed URL. Consequently the original HSW ratings remain unverified here; this report does not close them by citing a reseller summary.

A primary-backed substitution option is **Diodes DMG6601LVT-7**, TSOT26, [official datasheet](https://www.diodes.com/datasheet/download/DMG6601LVT.pdf). It has +/-30 V drain limits, +/-12 V gate limits, and specified on-resistance at2.5 V for both channels. Its pin map is1=N gate,2=P source,3=P gate,4=P drain,5=N source,6=N drain. For Q12–Q15, use8.2k rather than2.7k for R65/R68/R71/R74. At28 V with1% divider tolerance, maximum |VGS| is10.332 V. At nominal18.85 V VPP, minimum ratio gives6.781 V, exceeding the4.5 V gate condition used for the P-channel on-resistance specification. With RSET devices replaced, preserve actual package land-pattern compatibility and check drive/waveforms on dummy loads.

**Do not apply this substitution blindly to Q8–Q11.** Their existing VBB circuit differs: Q8.3 P-gate and Q8.6 N-drain are directly joined on N_R56_2, and R56=4.7k is only the pull-up to VBB. The nominal12.85 V rail already exceeds DMG6601's12 V gate maximum when enabled. Replacing these four devices requires adding an actual series gate-divider resistor or clamp, or selecting another fully verified part. No1.1k lower divider exists there to edit. This observation supersedes any suggestion that all eight devices are automatically interchangeable.

DMC3071LVT-7 has an accessible [official30 V / +/-20 V datasheet](https://www.diodes.com/datasheet/download/DMC3071LVT.pdf) and the same pin map, but specifies N-channel on-resistance only at4.5 V and10 V. It does not meet the requested2.5 V guaranteed-drive criterion merely because the actual N-channel load is a few milliamps. No alternative satisfying every requested criterion was verified during this check.

## Final patched schematic disposition (supersedes earlier candidate blockers)

Independently exported `work/p1-remediation/netlist-independent-final.xml`, SHA-256 `00e9bb8a67969a74d55affd615e9e92c67ac89589860bb2d4d80701c44e4d65a`. It confirms D1=SMBJ16CA; Q8–Q11=DMC3071LVT-7; Q12–Q15=DMG6601LVT-7; R65/R68/R71/R74=8.2k1%. Native C14/C15 fields now specify50 V. Read the final `candidate/reference/rev-c-safety-contract.md` alongside this disposition.

**Result: the identified P1 absolute-rating/topology gaps are addressed for the explicitly bounded electrical prototype.** This is conditional on enforcing the declared9–16 V input and <=28 V protected-input/VPP envelope, with the stated bounded1 ms pulse, and does not establish measured transient survival or vehicle readiness. The earlier40 V /35 V-capacitor and unverified HSW substitutions are no longer the selected candidate. No additional P1 pin-map defect was found in this final schematic review.

Q8–Q11 use +/-20 V gate-rated parts, so their direct pull-down topology is consistent with the nominal12.85 V regulated VBB. Their low-current N-channel drive at3.0–3.3 V still lacks a datasheet on-resistance guarantee. This remains a mandatory functional bench gate before programming: measure N-drain low voltage, P-gate drive, switching/turn-off and actual programming output under dummy load across voltage and temperature. Do not present threshold voltage or typical curves as a guaranteed3.3 V on-resistance. A failure of this drive assumption principally loses programming function; it does not itself establish an absolute-rating violation within the declared rail bounds.

Both selected parts share the verified physical mapping1=N gate,2=P source,3=P gate,4=P drain,5=N source,6=N drain. Their official TSOT26 outlines use0.95 mm pitch,2.8 mm outer lead span and0.30–0.45 mm lead width. The retained footprint has0.95 mm pitch,0.6 mm pad width and pads extending radially0.475–1.8 mm from center. These pads contain the specified lead landing regions. They are longer and0.1 mm narrower than the manufacturer's suggested1.0 by0.7 mm lands; this is compatible package geometry, not exact duplication of the manufacturer's solder-process recommendation. Confirm stencil/assembly process with the fabricator.

For Q12–Q15,8.2k lower legs with4.7k upper legs give10.332 V maximum gate stress at28 V when both resistor tolerances are1%, and6.781 V minimum at nominal18.85 V VPP. Explicitly specify the upper resistors R64/R67/R70/R73 as1% too; the generic4.7k value alone does not encode that assumption. Mandatory transient qualification must measure actual P-channel VGS and VDS, including fast pulse overshoot and active programming during an input transient; a DC divider calculation does not bound every capacitive transient. Remediate any observed overshoot with a suitable gate clamp or adjusted slew/envelope before vehicle use.

The final safety contract correctly separates prototype design bounds, firmware obligations, functional qualifications and physical tests. Final PCB routing/parity/connectivity, production BOM choices and regeneration of fabrication exports remain pending outside this schematic-only sign-off.

## Adopted GPIO13 health-heartbeat implementation (final routing decision)

This section supersedes the earlier GPIO2/GPIO12 routing proposals and their placement/copper exceptions. The accepted architecture reuses **U10 physical pad20 / GPIO13 / ACT_LED** as a dedicated safety-task heartbeat and Q20 health indicator. It does not infer safety from arbitrary activity. All original scanner and SD component placements, all original CS assignments and all original copper remain intact; none of the proposed C31/R106/R112 moves or IO0/power/ACT_LED fanout cuts were promoted.

The health route was applied to the work candidate as PCB SHA-256 `04256ce7512689c5bcf3ae3d95eb279544777ec71a68451bb84759298a098739`, before the parent's remaining J3 thermal and ADC-stub cleanup. U10 pad22 is restored to its own no-connect net. U22.TRIG, R118 and their new routing join the existing ACT_LED network. The existing Q20 MOS gate and R96 pull-down are compatible loads; adding R118 gives approximately5k effective pull-down, about0.66mA at3.3V. Native routing introduced27 copper objects and moved no footprints. New safety-part model paths were made project-relative; original footprint model paths were preserved. Evidence: `work/p1-remediation/health-led-heartbeat-proof.json`.

**Compatibility correction:** legacy firmware already writes ACT_LED and may generate edges that retrigger U22. It is incorrect to claim that legacy firmware necessarily holds the expander in reset. Compatible firmware must exclusively assign GPIO13 to the safety control task, remove legacy activity/status writers, avoid autonomous PWM/DMA, and stop heartbeat when required safety checks fail. A frozen high or low pin still times out. LED appearance is now a health/heartbeat indication rather than arbitrary bus activity. Firmware implementation and actual bench tests remain mandatory before operation.

The temporary-board native DRC after cleanup had zero unconnected items and no new heartbeat clearance/courtyard errors. Remaining items were the known J3 thermal, one exposed legacy ADC stub requiring parent resolution, and library lookup warnings caused by the temporary board living outside its bundled project folder. This is routing evidence, not the final project-native DRC/parity result. The parent must run the final checks from the candidate project after completing those remaining items.

No additional P1 electrical topology/rating defect was identified in the adopted heartbeat architecture under the declared prototype supply bounds. The existing qualification gates remain: bounded surge and source energy, transistor gate/drain overshoot during active programming, Q8–Q11 drive across temperature, ADC power sequencing, watchdog timeout and reset recovery on dummy loads, final fabrication/process checks, and firmware ownership of GPIO13. This conditional prototype review does not establish automotive qualification or certify arbitrary input faults.


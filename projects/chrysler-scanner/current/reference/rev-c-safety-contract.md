# Revision C hardware safety contract

This is a prototype design contract, not automotive transient or thermal qualification.

## Input and programming rails

Normal input: 9–16 V on a nominal 12 V vehicle. No sustained 24 V input or jump-start claim. D1 must be Littelfuse SMBJ16CA (16 V stand-off, 26 V maximum clamp at the datasheet pulse current). The protected input and VPP must remain at or below 28 V including wiring/layout overshoot, for the bounded 1 ms transient test. Source current and pulse energy must remain inside the selected TVS ratings; this is not a generic load-dump guarantee. Validate fuse coordination, surge waveform, temperature and repetitive pulse energy on hardware.

U9 supply is separately limited by R123 (1 kΩ, 1 W, 1%) and D30 (Nexperia BZT52H-B15,115). D30 standard-pad thermal rating applies; do not assume the enhanced 1 cm² cathode-copper power rating. Qualify at an ambient temperature no higher than 85 °C. PCI operation is specified from 9 V input; cranking below that is not guaranteed.

C14/C15 require at least 50 V ratings, upgraded from the original PDF's 35 V. Select exact capacitor parts with effective capacitance at operating bias and physical fit confirmed.

Q8-Q11 now use Diodes DMG6601LVT-7, matching Q12-Q15: 30 V drains and +/-12 V gates, with N-channel on-resistance specified at 2.5 V gate drive. R124-R127 (8.2 kohm, 1%) separate each N drain from its P gate; R56/R58/R60/R62 remain 4.7 kohm, 1% from VBB to P gate. This divider limits worst-case P gate stress to 10.332 V at the bounded 28 V rail. No enabling pullups were added to the N gates; original 10 kohm pulldowns remain. Both N/P channels have specified 2.5 V drive points. The original 4.5 V-only N-channel selection is superseded.

AW9523 P0_0-P0_3 default to open-drain. Firmware must explicitly select push-pull mode while output latches remain low before accepting programming commands. The AW9523 datasheet gives typical output drops, without a guaranteed worst-case VOH table entry; validate gate voltage and startup/shutdown timing across temperature. This is an expander/physical qualification limit, not a claim that the whole drive chain has a guaranteed 2.5 V minimum under every brownout. The supply fall-rate and supervision assumptions below remain controlling.

Q12–Q15 use Diodes DMG6601LVT-7 (30 V drains, ±12 V gates), with R65/R68/R71/R74 changed to 8.2 kΩ, 1%. Upper R64/R67/R70/R73 are explicitly 4.7 kΩ, 1% and produce at most about 10.33 V gate stress at the 28 V envelope with 1% tolerances; the nominal programming rail provides sufficient P-channel gate drive. All eight devices retain physical pin mapping 1=N gate, 2=P source, 3=P gate, 4=P drain, 5=N source, 6=N drain. Verify exact ordering codes and footprint land patterns in procurement.

## ADC isolation and calibration

R49/R51/R53 are 22 kΩ, 1%; lower legs are explicitly 1.62 kΩ, 1%. U21 TMUX1511PWR disconnects all three ADC channels while LOGIC_PG is low or power is absent. R120/R121/R122 (100 kΩ) pull the MCU-side nodes down. At 40 V the unloaded divider worst case is below 2.80 V; the defined protected-input envelope is lower still. The 100 kΩ load changes the nominal gain to approximately 0.06757. Use actual switch resistance, resistor tolerances and ADC characterization in calibration. Battery ADC now measures the protected input after D2, so terminal-voltage reporting needs diode-drop correction. Generic D27–D29 are secondary ESD protection, not precision voltage clamps.

U24 TLV803EA30DBZR has a 3.08 V threshold and 200 ms nominal release delay. Qualification must include the assumed normal rail fall rate (≤5 mV/µs) and maximum assertion delay. Arbitrary instantaneous rail shorts are not covered by a timing calculation alone.

## Hardware permit and required firmware integration

AW9523B reset is driven by U23 SN74LVC1G11DBVR:

`AW_RESET_N = MCU_EN AND LOGIC_PG AND HEARTBEAT_VALID`

U22 must be the retriggerable rising-edge LTC6993HS6-2#TRMPBF, not the non-retriggerable -1 variant. R115=100 kΩ, 0.1%, 25 ppm; R116=191 kΩ and R117=100 kΩ select divide code 5. Nominal timeout is 65.536 ms; verify release within the defined 70 ms budget over tolerance, voltage and temperature. Default output is low until a trigger. Frozen-high and frozen-low heartbeat both time out.

Heartbeat is the existing ACT_LED net, U10 physical pad 20 / GPIO13. This signal is explicitly repurposed as a dedicated software health heartbeat and drives the existing LED as a health/permit indicator. The LED is no longer an independently controlled traffic/activity indication. U22 TRIG is high impedance. Existing R96=10 kΩ and added R118=10 kΩ provide approximately 5 kΩ total pull-down, about 0.66 mA at 3.3 V. GPIO2 / physical pad 22 returns to its exact original no-connect; no extra boot-strap assignment is introduced.

Firmware integration is mandatory before active operation. Only the safety control task may issue a 10 ms software pulse train after all required tasks report healthy; stop pulses on a failed safety vote. Remove every old activity-LED writer, independent blink interrupt, autonomous PWM and DMA source. Existing legacy firmware already drives ACT_LED and may accidentally retrigger the timer, so this hardware does NOT guarantee that legacy firmware leaves AW9523B in reset. Do not operate active interfaces with an unmodified legacy image. The external timer detects missing edges and frozen-high/low; it cannot infer whether unrelated software-generated edges represent healthy control logic.

Safe startup sequence: initialize MCU and safe command policy; begin the dedicated health heartbeat; wait for AW9523B reset recovery; explicitly write safe expander configuration; then accept interface/programming commands. Stop heartbeat on failed safety checks. Loss of a required active programming/control session must enter its safe state; standalone logging without a host is not itself a fault. Do not attempt programming outside the normal input range. Firmware implementation remains deferred under the repository instructions.

## Bench release gates

Measure protected-input and VPP overshoot, TVS/fuse energy, PCI zener temperature and supply minimum, ADC powered/off/unpowered faults, supervisor fall timing, watchdog release and programming switch drive across voltage and temperature. Native DRC/ERC and schematic review do not establish these physical properties. Filled/capped/planarized via-in-pad processing remains required wherever present.

# P1 remediation design recommendations

Historical design evolution. Final revision C acceptance and adopted GPIO13 health-heartbeat contract are in `current/reference/rev-c-adversarial-review.md`; earlier GPIO2 proposals were not adopted.

2026-10-21. Independent review of candidate solutions, before CAD implementation. This document proposes a hardware architecture and acceptance conditions; it does not claim that an unbuilt circuit has passed surge, brownout or ECU tests. No CAD changes were made by this reviewer.

## Recommended architecture

Use a coordinated input TVS with an explicit input envelope; rescale and isolate the three monitoring inputs; generate a hardware heartbeat permit that resets U19 when software stops making progress. Share a 3.3 V power-good signal between ADC isolation and the U19 permit gate.

### 1. Input protection: account for all loads, not just the bucks

D1 replacement candidates must also protect **U9 TS391C**, whose supply is directly `+12V`, as well as U2/U7 and input capacitors. The [ST TS391 specification](https://www.st.com/resource/en/datasheet/cd00001660.pdf) permits a 36 V supply. Therefore **SMBJ24CA's 38.9 V specified clamp remains too high for U9**, even though it fits the LMR14010A's 45 V stress limit. Do not claim this substitution closes the entire input-protection finding without separately protecting or changing U9.

For the smallest change, an exact manufacturer-selected **Littelfuse SMBJ18CA** on the existing DO-214AA footprint is a credible candidate: nominal 18 V stand-off and 29.2 V maximum clamp at the specified approximately 20.5 A, 10/1000 µs pulse condition. Verify against the actual revision of the [Littelfuse SMBJ datasheet](https://www.littelfuse.com/~/media/electronics/datasheets/tvs_diodes/littelfuse_tvs_diode_smbj_datasheet.pdf.pdf). Its 29.2 V clamp leaves materially more margin to U9 and the 40 V operating bucks. This is not 24 V jump-start capability.

The minimum defensible documented envelope is a **12 V system, e.g. 9–16 V continuous**, fused externally, with positive transients constrained by the selected TVS's current, pulse-duration, repetition and temperature derating. Preserve reverse-battery protection and verify negative-pulse paths. Record a maximum downstream voltage including wiring inductance and overshoot rather than equating the TVS table number with the voltage at every IC. No claim of arbitrary unsuppressed load-dump or 24 V jump-start survival follows from this small substitution.

If 24 V jump-start/long load-dump survival is required, use an input overvoltage disconnect/surge-stopper architecture or separately protect the 36 V comparator supply; do not quietly narrow the use case while calling it fully automotive qualified. U5's manufacturer [Legend-Si product page](https://www.legend-si.com/productinfo/1318196.html) describes LGS6302 as a 60 V boost family; lock its exact SOT-23-5 ordering code and datasheet before assembly.

### 2. Monitoring inputs: use powered-off isolation, not only a nominal 3.3 V TVS

**TI TMUX1511PWR**, TSSOP-14, is a practical four-channel SPST isolator for the three ADC channels. Its [datasheet](https://www.ti.com/lit/ds/symlink/tmux1511.pdf) explicitly supports signal-path powered-off protection through 3.6 V at VDD = 0. Its control inputs also have fail-safe behavior. This addresses a property that a generic 74LVC analog switch or a TL431 shunt alone does not provide.

Connect each divider/filter node to a source input; connect its drain to the existing U10 ADC pin, keeping the existing MCU-side net names `V_BA`, `V_BT`, `V_PR`. Tie the three channel selects to a defined 3.3 V power-good signal. Give the MCU side a pulldown sized from the specified maximum off leakage, not just typical leakage. Disable and terminate the unused fourth channel. Decouple locally.

All source-side divider nodes must remain below the isolator's powered-off 3.6 V limit under the bounded input/rail fault envelope. One simple common scaling is **22 kΩ top / 1.62 kΩ bottom, both 1%** for R49/R51/R53 and R50/R52/R54 respectively: the largest divider output at 40 V, including resistor tolerance, is approximately **2.795 V**. If preserving the existing VBB/VPP dividers, explicitly prove their worst-case rail limits first; nominal setpoints alone do not cover a pass-through/shorted-switch event. The expected normal setpoints are about 18.85 V VPP and 12.85 V VBB, subject to the actual feedback resistors and IC tolerances.

The change alters measurement calibration. Account for any MCU-side pulldown loading, isolator leakage and ON resistance, ADC sampling requirements and RC settling. Do not carry over old conversion constants. At normal battery voltage a smaller ADC swing is acceptable only if the resulting accuracy/resolution meets the intended measurements.

**Power-good candidate:** **TLV803EA30DBZR**, SOT-23-3, open-drain active-low reset, 3.08 V nominal threshold, nominal 200 ms release delay. Its exact pinout is GND 1, RESET 2, VDD 3 for this no-extra-pinout-letter suffix. Use a pullup to the MCU's 3.3 V rail; a low power-good opens the ADC switches and disables U19. Check the [TI supervisor datasheet](https://www.ti.com/lit/ds/symlink/tlv803e.pdf), including threshold tolerance and its **50 µs maximum assertion delay** at the stated overdrive.

A supervisor is not instantaneous protection against an arbitrarily fast hard short of the 3.3 V rail. With 3.08 V −2% = 3.0184 V minimum trip and a 2.795 V maximum ADC source, the MCU rail must remain above approximately 2.495 V until isolation opens. The nominal margin is 0.523 V over 50 µs, approximately 10.46 mV/µs before additional delays. A conservative test bound is **no faster than 5 mV/µs falling at 3.3 V**, or demonstrate more precise margin using selected component specifications. If the real rail collapses faster, add hold-up, a faster cutoff path or specified pin-clamp circuitry; do not claim powered-off isolation alone covers the entire ramp. Test cold start, normal unplug, regulator collapse, brownout, and return to power with voltage probes on both sides of the isolator.

### 3. U19 fail-safe: retriggerable default-low permit

**ADI LTC6993HS6-2#TRMPBF**, TSOT-23-6, is the preferred minimal heartbeat timer. Use **-2**, the rising-edge retriggerable variant; -1 is not equivalent. With positive output polarity, its output starts low, remains low after startup until a trigger edge, and returns low when retriggering stops. Use **SN74LVC1G11DBVR**, a three-input AND in SOT-23-6, to implement:

`U19_RSTN = HEARTBEAT_PERMIT AND MCU_EN AND POWER_GOOD`.

Retain a defined pullup on U19 RSTN, but drive it with the gate; do not short a push-pull output directly to an unrelated reset output. Check low-level drive against the pullup and U19 reset threshold, reset minimum pulse width and recovery time. Gate supply and timer supply are the same MCU 3.3 V domain. Add local bypass capacitors and defined logic levels, especially a **10 kΩ TRIG pulldown** so an input/high-impedance MCU pin cannot arm the permit.

Candidate timing: **Ndiv = 32768, RSET = 100 kΩ** gives **65.536 ms** nominal. Choose DIVCODE 5, positive polarity; its midpoint is VDIV/V+ = 0.34375. A **191 kΩ upper / 100 kΩ lower** divider gives about 0.34364. Use precise low-tempco RSET and do not add a large capacitor to DIV. Budget **70 ms maximum loss-of-heartbeat release** only after including all timer, resistor, temperature and propagation tolerances. A **10 ms software heartbeat** leaves practical scheduling margin. Verify these details against the [LTC6993 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/LTC6993-6993-1-6993-2-6993-3-6993-4.pdf) and [TI AND-gate datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g11.pdf).

Use **U10 physical pad 22 / GPIO2** for a dedicated software heartbeat, with an external 10 kΩ pull-down. Correction: physical pad 22 is GPIO2; GPIO4 is pad 24 and already assigned TX2. GPIO2 is a boot strapping pin. Its pull-down matches the default strap and permits UART download when GPIO0 is held low. Keep GPIO2 low throughout reset and for at least 1 ms after CHIP_PU rises, as required by the official strap timing; start heartbeat pulses only after normal application initialization. The timer TRIG is a high-impedance input and must have no pull-up or other active driver that could defeat the strap. Verify cold boot, external reset, software/internal watchdog reset, and serial-download entry with a scope and actual firmware. Use an explicitly driven software heartbeat, not free-running PWM/DMA that can continue after the control task hangs. The H-grade timer supports −40 to +125 °C; claiming automotive qualification additionally requires its documented `#W` automotive ordering option and the same scrutiny for the rest of the BOM.

The logic must remain disabled before the first heartbeat, during MCU_EN low, during undervoltage, and after a heartbeat stops at either logic level. A resumed heartbeat releases U19 into reset defaults, so firmware must reinitialize its registers before accepting active commands.

## Firmware compatibility consequence

Existing firmware without the new heartbeat will hold U19 in reset and will not enable its controlled scanner/programming paths. This is a deliberate fail-safe behavior, not backward compatibility. Document it prominently; do not fit an undocumented bypass that restores the original unsafe behavior.

Safe startup order is: initialize MCU pins/I²C and command policy; start the heartbeat to release U19's default-off reset state; wait the documented reset-recovery interval; explicitly initialize all U19 output values, directions and modes to safe states; only then permit active commands. Waiting for an AW9523B I²C acknowledgement before the first heartbeat would deadlock because the expander is still held in reset. Repeat this recovery sequence after a watchdog timeout.

## Required implementation review and tests

1. Check exact symbol/footprint pin maps, all changed net endpoints, component ratings and fitted orderable parts independently of the old source netlist.
2. Check no heartbeat, frozen high, frozen low, delayed heartbeat, external reset, internal watchdog reset, undervoltage and restart. Measure RSTN and representative programming output voltages on dummy loads; a logical gate trace is not the complete propagation path.
3. Check ADC voltage/current with the MCU supply on, off and ramping, at maximum bounded input and rail voltages. Include leakage and component tolerances.
4. Run full native ERC/DRC/parity/refill plus uncapped connectivity, and review high-current return paths and added placement/courtyard constraints.
5. Revisit any operational envelope excluded by this minimal revision. CAD checks and calculations can close identified topology/rating errors; they do not replace measured qualification.

## Amendment: 24 V candidate with a separately protected comparator supply

The later candidate SMBJ24CA plus a separate U9 supply clamp resolves the specific reason the earlier section rejected a 24 V TVS: U9 no longer sees the main protected rail directly. Use exact Littelfuse SMBJ24CA, a source-fused and explicitly bounded maximum 40 V protected rail, and document the allowed pulse waveform/current. A nominal TVS clamping value does not establish immunity to arbitrary automotive load dump.

Candidate R123 = 1 kΩ / 1 W / 2512, +12V to PCI_VCC; D30 = Nexperia BZT52H-B15,115, cathode PCI_VCC and anode GND; U9.5 and C11.2 on PCI_VCC. At 24 V steady state the nominal zener dissipation is approximately 0.13 W and R123 dissipation 0.081 W. At 40 V, nominal instantaneous dissipation is approximately 0.375 W in D30 and 0.625 W in R123. Those 40 V values require an explicitly short pulse, the selected resistor pulse/derating data, and appropriate repetitive-duty limits.

Do not use the headline 830 mW zener rating for a standard SOD123F footprint. The Nexperia datasheet specifies 830 mW only with a 1 cm² cathode pad; a standard footprint is 375 mW at 25°C and 330 K/W junction-to-ambient. Approximately 0.13 W raises the junction about 43°C on that reference mounting. Consequently this is reasonable at <=85°C ambient but cannot claim 125°C ambient operation at continuous 24 V without thermal improvements and verification. The 150°C junction maximum remains controlling. Select an explicit system ambient envelope and verify the actual board thermal behavior.

Normal comparator headroom is adequate for a 9 V minimum connector voltage: allowing 0.7 V in D2 and conservatively 1.25 mA U9 supply current gives PCI_VCC >=7.05 V. The full-temperature common-mode ceiling VCC−2 V then exceeds the nominal 3.507 V reference by 1.54 V. Cranking down to 6 V is outside that argument; specify a minimum input voltage for PCI decoding and test transitions rather than claiming uninterrupted crank operation.

Moving the battery measurement source from raw J1962-16 to protected +12V after D2 avoids a negative battery input at the analog mux. It intentionally measures the protected rail; calibration and the user-visible definition must account for the diode drop. With an enabled mux and a 100 kΩ output pull-down, the effective lower divider resistor is 1.62 kΩ || 100 kΩ = 1.594 kΩ. Update firmware scaling for that load as well as the new 22 kΩ top resistors.

Sources: [Nexperia BZT52H series datasheet](https://assets.nexperia.com/documents/data-sheet/BZT52H_SER.pdf), [ST TS391 product and datasheet](https://www.st.com/en/amplifiers-and-comparators/ts391.html). These are engineering acceptance conditions for reviewing the pending candidate, not evidence that its routing, assembly or physical qualification has passed.


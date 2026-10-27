# Independent procurement delta review

No remaining P1 schematic or PCB finding was identified in this bounded prototype delta. Layout delta review is complete. Final fresh ERC/native XML/full DRC-parity, reviewed catalog and every technical delta verifier check now pass. Primary combined-wrapper and exported fabrication-package reconciliation remain release closeout gates. This is not a bench-qualified or automotive-qualified design approval.

## Review scope and evidence

This independent review covers the actual procurement/copper delta, layered over earlier independent schematic/layout reviews and the frozen checked CCD checkpoint. It combines manufacturer-source research, native footprint/pad/net samples, inspection of the preservation verifier and its independent execution without file writes, schematic previews, and high-resolution cropped front/back board views and all eight quarter-board detail views. It does not repeat every passive ordering suffix audit or independently reconstruct the original-PDF comparison.

Technical delta checks passed:329 native identities and electrical endpoints,333 footprint UUIDs,24 schematic structures, pin numbers/nets/hierarchy,40 no-connects,197 ground pads in one group, unchanged rules/outline/zones, all retained copper/via properties,9 unlocked cuts,46 declared new tracks, and no new drills. Final independent execution passes all checks, including report freshness and reviewed catalog state. Existing historical-audit evidence is preserved; its earlier all-pass result is evidence for the frozen baseline, not a fresh report for this candidate.

## High-risk delta findings

- Q1/Q6/Q16 CJ3439KDW and Q7 HSSK8811 now use correct SOT-363 lands, with physical pin roles retained. Q2/Q3/Q4 use DMN62D2UDM-7 on the original SOT-23-6 geometry; the identical-channel mapping and low-voltage gate-drive specification are compatible with the level-shifter circuits. Do not use rejected DMC2700UDM with its insufficient gate-voltage rating.
- R98/R99 are330 ohms. A full5.5 V ideal charging step is limited to16.84 mA with1% tolerance before driver impedance, below the AHCT 25 mA absolute output-current rating. RC delay for120 pF is approximately87 ns 10–90%; this is an estimate, not a guaranteed Miller-plateau waveform. No significant CCD-bit-time penalty is expected, and measurement remains required.
- DR74-220-R main coils have appropriate normal-operation current margin and actual rectangular terminal coverage on existing1.5 × 2.2 mm pads. The maximum body/courtyard/model envelope is updated. Those lands are smaller than Eaton's recommended reflow lands: assembly/fillet qualification remains necessary. Fault/current-limit and hot saturation are bench gates.
- SRN2012-R24M/R47M preserve exact240/470 nH values, exceed required normal filter current capability, and use manufacturer-recommended0.8 × 1.8 mm lands at±0.8 mm. Their small relocations and0.5 mm F.Cu branches fit within preserved surrounding copper and maximum envelopes. No new 100 mA programming restriction is introduced.
- C14 uses TDK C3225X7R1H226M250AC 1210 lands,1.2 × 2.5 mm pads at±1.7 mm. Native GND return branches and full ground connectivity remain intact. This is a physical-fit correction, not proof of boost-loop stability.
- PMEG4005EGWX matches the larger diode lands and cathode-pad1 roles. SMF12A and PESD3V3U1UA polarity and package roles agree with bus/ADC protection. Reverse leakage, real clamp overshoot and precision ADC behavior require operating tests.
- Dedicated GPIO13 health wiring is unchanged. The stale SD status annotation is resolved: no SD/activity, autonomous blink, PWM or DMA writer is permitted.

## Prototype qualification gates

C14's 22 uF nameplate is not its operating capacitance: the reviewed TDK curve is approximately 8 uF at 20.6 V and 5.5 uF at 28 V before tolerance, temperature and aging. Boost stability/ripple/transients must be measured. No reduced-capacitance stability guarantee is claimed. Thermal/current-limit behavior, switching noise, total +5 V/SD supply load, diode leakage and ESD/clamp overshoot remain bench requirements.

Retain 9–16 V normal operation, bounded protected input/VPP <=28 V including overshoot, the 230 filled/capped/planarized vias and accepted stackup. OBD housing and M3 socket-head screw/no-washer sample fit, dedicated-heartbeat firmware and safe startup/decay tests remain required. CAN remains deferred by user decision. No vehicle-use, automotive-transient, production or regulatory qualification is established.

## Hash binding

The JSON contains exact PCB and 24 schematic SHA-256 hashes, scope, limitations, review state and primary sources. Any CAD edit after this snapshot requires hash refresh and applicable rechecks.

PCB SHA-256: `83ac625f2283aa789455802fa4367dbc786c7a2f0ae6c87ffc91c8959a40ac15`

- `01_ccd.kicad_sch`: `d787977327104e66aa4b48a5c838865b4ac6dd117d11f695b72f39c95e41f663`
- `02_pci.kicad_sch`: `9aad268904d4776394416e5b806a6e9cfcdba22089b89a352e3ea391933d08be`
- `03_sci-14-9.kicad_sch`: `31e4467933deb45bc1d08caa1ae8c8eb146c56854ac50be89443c4b9d4a04356`
- `04_sci-6-12.kicad_sch`: `3278bf66833b1123754c90a9fea45325d98025816615a87ef263d28f7dcb43dc`
- `05_sci-rx.kicad_sch`: `d4f8e54bf51bde7ae976ecb6c75d5689f5f15fada221578e30980df758073ae6`
- `06_obd-protection.kicad_sch`: `9fcbaf2fc63f41af49eea0aca353a445ffbe79f25fec2f88864f5256134dd9c8`
- `07_vehicle-input.kicad_sch`: `ef5a18f0484276ca27fa6d012aae8e72126508830782552d221c0d6a64739bfa`
- `08_power-5v.kicad_sch`: `7890de9a16d8707a4bcaf9bda022c597cbecb30ba43923f2c87583c1c2991992`
- `09_power-vpp.kicad_sch`: `4c0399831bcf5aae2fd8b2e71366ce38b37f841a571f11e8f20b85328ed7d822`
- `10_power-vbb.kicad_sch`: `26b12a3f36d094a698c9869ae96741fbda4ad60238a903e20cec0965b32f51d1`
- `11_power-7v5.kicad_sch`: `08bf05c9a5d37346ef8afd396654f0cd6e8d8c002771d0f7e93af6d2694f1a1c`
- `12_program-6.kicad_sch`: `de784bb3d1b7aa19d61791202e63600e47e7efece975e80853fe9d8912c5528d`
- `13_program-9.kicad_sch`: `c87a774dc7b7a282fe5b664e0562cdfdc5120ccac8d43b228759e3a20d97c652`
- `14_program-12.kicad_sch`: `b25492e1eb75c46146314b62567b12e83ad6ea7ecbfa11d79ad6972cbd63a3ef`
- `15_program-14.kicad_sch`: `c21859b7b0f5a168212df9b398345c413b23023592f5ce06f91bb8fc97f948ae`
- `16_mcu.kicad_sch`: `8c686ec92dbcfdbbf292ab14fff0244d44f3589119d837b44d3ac8e4b4da7b2a`
- `17_adc.kicad_sch`: `1a7f18e6e60265873b87faeffc49bb708e7a8accad0a4421e90fd7dd94486c43`
- `18_control.kicad_sch`: `074e9cd187a142041eaa8161cc0c4342fa21b4e8003c68d7ff0f4c20aed85b6e`
- `19_usb.kicad_sch`: `de78a2fe97727f93a6ab9f572a594ccd13970d9ddca7705ea20165a9838e494f`
- `20_leds.kicad_sch`: `b04a51e07fbfdd347ec10160f9502be8f743f02977cf44073eaf5e8c237efba7`
- `22_sd-logger.kicad_sch`: `d80434fc3ba1cf1f319376d470a44078db013f89ae00d2f6a3d7cb65414e2e4e`
- `23_hardware-safety.kicad_sch`: `b8876b6a470b4e06833cac665e08abaecb462500b52d99feb2c20d4a8ea793c2`
- `24_debug-testpoints.kicad_sch`: `f47764d129360c28258037c4ab0c48c9f461094cde1cdeb30df481ed31ab0b7e`
- `ChryslerScanner_V240_SD.kicad_sch`: `7c15e34193b1047eeb3d43096ad972032ad9ea49570fb20c21b64f45cf1272ac`

Metadata/whitespace refresh: prior CAD byte copies were not retained, so a direct old-to-new byte diff is not claimed. Original review hashes remain in JSON. Final native semantic/preservation/geometry/procurement verifier independently rerun without report writes: PASS. The exact health annotation uses the same parser grammar without relaxing its intended text.

# C14 release change review — 2026-11-06

Primary adversarial change review, carrying forward the frozen earlier independent reviews. No new independent reviewer or physical qualification is claimed.

C14 changes from the unavailable 1210 TDK part to CGA9P3X7R1H226MT0Y0N (JLC C49297044; supplier/distributor alias CGA9P3X7R1H226M250KB). Nominal 22 µF, 50 V, X7R, ±20% remain. TDK CGA series dimensions: 5.7±0.4 by 5.0±0.4 by 2.5±0.3 mm. New conservative prototype lands are 1.4 by 5.4 mm at ±2.8 mm, with 7.5 by 5.9 mm courtyard; enlarged Fab and STEP envelope represent maximum body dimensions. The previous candidate retained the small STEP scale: corrected before release.

C14 stays top side at (158.75,114.3) mm, −90°. C13 moves +0.4 mm in X; TP25 moves to (164.2,118.25) mm and rotates to 90°. C13 and C46 silk references are hidden to avoid collisions, with Fab references retained; TP25 board text moves. J1, mounting holes, C61, every other component placement and every zone/rule-area definition remain unchanged.

Three existing signal vias move on V_BA_PRE, EN and +3.3V. Exactly 15 old copper signatures change or disappear and 27 reviewed copper signatures are added/modified. Only seven local nets change copper. No locked copper changes, no via is added/removed, and all 486 vias retain drilling/tenting/filled/capped flags; 246 filled/capped/planarized processing sites remain. The moved V_BA_PRE bridge uses In2, preserving In1 as a signal-free ground plane. New +12V branches remain 0.5 mm wide. TP25 gains a 1.4204 mm branch; the debug map is updated.

Adversarial checks considered wrong voltage/dielectric, land/body mismatch, misleading model size, altered safety connectivity, disconnected power branches/planes, hidden processing flag changes, courtyard/copper/silk interference, manufacturing-file and BOM/CPL disagreement, and stale historical acceptance reports. All-severity native ERC/full DRC/parity are zero; complete uncapped native connectivity is zero, all 197 ground pads connect. The unchanged prior 130-check gate reruns from a SHA-bound ZIP in a temporary project, followed by 31 current-delta checks. Safety-bounds arithmetic passes separately.

No high-priority CAD finding remains for this bounded prototype change. DC-bias capacitance, regulator stability/ripple, thermal/transient behavior, assembly quality, PCB-flex/MLCC cracking and physical enclosure/clip access still require prototype measurements. These are existing prototype qualification limits, not demonstrated by DRC.

Only C14's stock substitution is incorporated into this CAD release. Other JLC alternate selections remain quote/procurement work and must not be silently substituted from the quote screen into this release BOM. Q2–Q4 procurement and the delivered fully assembled quote remain open. The exact original J1 footprint is preserved.

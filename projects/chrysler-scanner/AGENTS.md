# Chrysler scanner: completed routed prototype

Read `README.md`, `reference/final-status.json` and `current/reference` final
validation reports before editing. Firmware remains deferred. The active PCB
is the single integrated-SD scanner board under `current`.

Accepted PCB SHA-256:
`85011cefd33c4d6a623440d91eeb9876282d39dc7fc6a37eb90d50e2a278c36a`.

Native DRC and ERC are clean; all 175 GND pads and every signal net are connected.
Preserve all original scanner placements, 174 accepted protected copper objects,
the outline and mounting holes, all nine zone/keepout definitions and existing
rules, severities and exclusions. Keep In1 as the GND reference with no signal
tracks. Minimum track width/clearance remain 0.15 mm.

The sole added-part placement adjustment is R112, from (172,121) to
(172.05,121.075) mm. Its exact recorded exception and original accepted input
are under `current/reference`. Do not treat historical incomplete routing
prototypes as accepted boards. Work on a copy and rerun complete native DRC with
zone refill, all severities, track checks and schematic parity, plus independent
uncapped connectivity and preservation checks after any edit.

Filled/capped/planarized via-in-pad processing and saved tenting flags are part
of this board's manufacturing requirements. See MANUFACTURING-NOTES.md.
Never run old setup_design.py over this project or overwrite it with the
original Atopile layout. Manufacturing orders and firmware work require their
own user request. No order or external upload has been performed.

J1 and protection now share `06_obd-protection.kicad_sch`. The PCB hash above
includes the J1 sheet-path metadata correction only; physical routing is unchanged.
Run `current/source/verify_system_hierarchy.py` after new native ERC/netlist/DRC
exports to check the 156 ports and all 194 original named net endpoint sets.

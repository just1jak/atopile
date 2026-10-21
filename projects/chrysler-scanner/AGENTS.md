# Chrysler scanner engineering checkpoint

Read this project's `README.md`, `reference/checkpoint-status.json` and the
`work/chrysler-routed-sd/handoff` notes before editing. Paths beginning `work/`
in archived notes are relative to this project directory, not the Git root.

The active request is to finish routing and clear all native KiCad DRC findings
on the **single integrated-SD main board**. Firmware remains deferred. The
archived Bluetooth/XIAO add-on is superseded and does not run this MCU.

Start native editing from `current/ChryslerScanner_V240_SD.kicad_pro`. The best
accepted PCB is SHA-256
`f5b42ba76001f790c445533dfcd8567136b5b018127ac8982a2b04650661a2d1`.
It has three actual gaps: RX15_EN at U19.15, TX_LED at U10.15 and PCI_RX at
U10.17. Fresh DRC: four edge errors, seven dangling warnings, three unconnected
items, zero schematic parity issues. All 175 GND pads are connected.

Preserve all original scanner placements, the outline and mounting holes, all
122 protected copper objects, all nine approved zones/keepouts, and existing
rules, severities and exclusions. Keep In1 as the unbroken GND reference; use
native layer constants. Do not reduce the 0.15 mm minimum trace/clearance or
hide findings. The only placement exception considered is the **new** SD
resistor R112, a proposed +0.075 mm Y shift from (172,121) mm. That idea remains
unvalidated; it has not been applied to the accepted board. Validate and record
any accepted adjustment narrowly rather than weakening the audits globally.

The latest paired RX and direct TX_LED/R112 prototypes are under `handoff`.
They are not accepted replacement PCBs. Respect their exact input hashes and
temporary displaced-net lists. Preserve all filled/capped/tented via flags;
ordinary open vias do not replace reviewed via-in-pad fabrication requirements.

Use the precise native wiring DSN exporter before fresh router import. Normalize
only originally unlocked USER_FIXED copper; keep SYSTEM_FIXED anchors fixed and
initialize positive costs. Raw router contact counts can include false N_C3_1
and VBB gaps that are connected natively. Perform routing locally; the bundled
engine is not an extension-integrated autorouter. Import SES copper only with
the matching native seed and unchanged placements.

Completion requires fresh native KiCad DRC with all severities, all track
errors, refilled zones and schematic parity: **zero errors, zero warnings,
zero unconnected items, zero parity issues**. Also require uncapped native
airwires zero and every net's pad partitions connected. The preservation and
electrical audits must pass against the exact final PCB hash. Do not label a
route plan, router-core contact count or electrical-parity pass as completion.

Do not run old `setup_design.py` over the latest project. Preserve the bundled
original CAD references and historical evidence bytes; use
`prepare_reference_manifest.py` to restore reference-copy times after cloning.
Final packaging helpers intentionally reject unfinished routing. Firmware
compilation/flashing and manufacturing orders are outside this checkpoint.

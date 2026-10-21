# Chrysler scanner with integrated SD hardware

**Unfinished engineering checkpoint. Routing is incomplete; do not manufacture
this revision. Firmware is deferred.** The microSD socket and logging hardware
are on the original 110 × 55 mm, four-layer main scanner board, using its
ESP32-PICO-V3-02. The earlier separate Bluetooth carrier is archived only.

Open `current/ChryslerScanner_V240_SD.kicad_pro` in KiCad 10 and open its PCB or
schematic from the project manager. All required project files, 23 schematic
sheets, symbols, footprints, model files and asset notices are bundled.
Flip the 3D view to see microSD socket J4 on the underside. The intended case
requires card access and at least 7 mm underside clearance.

## Accepted checkpoint and unfinished work

The PCB in `current` is the accepted full-ground candidate, byte-identical to
`work/chrysler-routed-sd/ground-final-stage/combined/ChryslerScanner_V240_SD.kicad_pcb`.
Its SHA-256 is
`f5b42ba76001f790c445533dfcd8567136b5b018127ac8982a2b04650661a2d1`.
The design work folder still contains an earlier pre-route board; start with
`current` for native editing, not that earlier `design` PCB.

The accepted candidate has 263 footprints: 245 original scanner/mechanical
parts and 18 added SD parts. Original placements and 122 protected copper
objects are preserved. All 175 GND pads share one native connected group.
Three signal gaps remain: `RX15_EN`, `TX_LED`, `PCI_RX`. Fresh KiCad DRC reports
four edge-clearance errors, seven dangling-copper warnings, three unconnected
items and zero schematic-parity issues. The native checkpoint report
in `current/reference/checkpoint-drc.json` is the fresh report for this copy;
other reports are historical and apply only to their named input/hash.

The latest paired RX escape and R112/TX_LED alternatives under
`work/chrysler-routed-sd/handoff` are **unvalidated prototypes**. They may create
temporary gaps in other nets and must not silently replace the accepted board.
Only the newly added R112 has been considered for a small placement adjustment;
the accepted board retains its original location. Do not move original scanner
parts or relax clearances to force a passing result.

Use native KiCad DRC with all severities, schematic parity and zone refill.
Independently inspect uncapped native airwires and all per-net pad partitions.
The completion gate is zero errors, zero warnings, zero unconnected items and
zero parity issues. `work/chrysler-routed-sd/package_routed_revision.py` refuses
to make a routed release until its final reports and board hashes pass.

## Resume tooling

The routing work folder includes Python and Java helper sources, exact DSN/SES
inputs and saved route states, the offline FreeRouting JAR and guard audits.
See its `handoff` notes before continuing. The offline router runs with network
access denied on the original Mac; use an equivalent local restriction on the
next machine. FreeRouting is not evidence of final native KiCad connectivity.

The precise native wiring exporter avoids coordinate-rounding gaps. For a
fresh imported router core, only originally unlocked `USER_FIXED` copper may
be normalized to `UNFIXED`; reviewed `SYSTEM_FIXED` anchors stay fixed. Initialize
positive search costs. Preserve the unbroken In1 GND plane, all fixed routes,
zone definitions and the 0.15 mm minimum clearance. Final native verification
is mandatory after importing any route session.

Some historical scripts and reports use absolute paths from the first Mac.
These are retained for provenance and need path review before reuse. The
"repository root" in older `work/...` examples means this project directory,
`projects/chrysler-scanner`, within the combined extension repository. The
original input manifest includes exact file times; Git does not preserve
modification times. `prepare_reference_manifest.py` verifies the bundled
original bytes, restores those reference-copy times, and writes a local
manifest suitable for `verify_revision.py --source-manifest`.

The board includes filled and capped/planarized via-in-pad locations. They
require an appropriate fabrication process, not ordinary open drilled vias.
Final manufacturing notes must be generated from the eventual clean board.
Prototype power, USB capacity, SD write peaks, RF/USB signal integrity,
temperature and enclosure fit still require physical validation.

## Firmware and provenance

Firmware remains deferred. There is no working SD logging firmware for this
integrated MCU in this checkpoint. The archived XIAO/Bluetooth firmware draft
is not a drop-in replacement. The intended vehicle is an early-2004 automatic
Cummins, logging both raw traffic and selected values. No RTC, battery,
power-fail supervisor or shutdown hold-up has been added.

This is a native KiCad revision; rebuilding the original Atopile project will
not regenerate its integrated SD changes. The original Downloads project is
unchanged. Its exact original 25 CAD reference inputs are in
`reference/original-source`, with the original SHA/size/time manifest beside it.
The separate `original-atopile` folder preserves the original circuit code,
part assets, configuration and helpers. Its original absolute layout path
needs adjustment on another computer; do not point a rebuild at `current` or
overwrite the integrated SD board with the earlier circuit.

Derived from [laszlodaniel/ChryslerScanner](https://github.com/laszlodaniel/ChryslerScanner)
and the user's V240 reconstruction. The circuit is GPL-3.0; see `current/LICENSE`.
Library assets and manufacturer CAD retain their own terms and notices under
`current/licenses` and `current/3dmodels`. In particular the ATTEND model has
manufacturer rights notices; the entire asset collection is not relicensed as
GPL by this repository's root license.

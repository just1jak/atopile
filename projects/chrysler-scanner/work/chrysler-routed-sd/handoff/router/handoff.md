# Local router continuation

Routing is paused for the cross-computer checkpoint. This is an unfinished board;
firmware remains deferred. No router executable, Java classes, serialized FRB,
Python environment, credentials, or local application state is bundled here.
`verification.json` records source compilation, read-only input parsing and 32
guard/unit checks; no resumed routing was run during handoff preparation.

## Verified restart input

`inputs/native2-fullground/ChryslerScanner_V240_SD.kicad_pcb` is the immutable
fallback native board, SHA256
`f5b42ba76001f790c445533dfcd8567136b5b018127ac8982a2b04650661a2d1`.
It has 263 footprints, all 175 GND pads connected, and three native airwires:
RX15_EN/U19.15, TX_LED/U10.15, and PCI_RX/U10.17. The original 122 protected
copper objects, footprint geometry and antenna keepouts passed preservation audit.
The matching project settings and preservation report are included.

`inputs/atopile-sd-native2-fullground-precise.dsn`, SHA256
`9877d490b21aaf1b64820abaf4e7b78892dba2b3a068099904d2bb8c4debe4d2`,
was derived from that exact board. Wiring retains native nanometre coordinates
as fractional micrometres. Its export proof is alongside it.

This is a restart fallback, not a replacement for a newer project or prototype
saved elsewhere in the main handoff. Paired RX7/RX15 escapes and a proposed small
R112 movement were being investigated separately. Their proof reports must be
checked before combining changes. The historical hint-blocker JSON describes
an earlier signal layout and is diagnostic evidence only.

## Critical fresh-import fixes

`DsnToCore.java` applies two corrections, without changing board geometry:

1. FreeRouting 1.9 reads KiCad unlocked `(type route)` tracks/vias as USER_FIXED.
   For this native-export pipeline only, normalize those to UNFIXED. Explicit
   native `(type fix)` copper is SYSTEM_FIXED and remains protected. Do not apply
   this conversion blindly to an unrelated FRB containing intentional user locks.
2. Minimal DSN autoroute settings can parse as zero trace/via costs. Initialize
   positive search costs: preferred/other direction 1/2.5, via 50, plane via 5.

Before the fixed-state correction, PCI_RX frozen/victim retries could not move
any generic copper. Those failures do not prove routing infeasibility. The
corrected normalized core was not routed before the user paused work.

Expected raw core accounting for this fallback is five non-GND gaps: the three
real native gaps plus N_C3_1 and VBB, which were connected in native KiCad but
appear disconnected in this core representation. Keep that distinction explicit.
The core reported 299 baseline clearance approximations; that is not a native
KiCad DRC result and must not be treated as permission for new physical errors.

## Rebuild and inspect

Use JDK 17 and the pinned FreeRouting 1.9.0 JAR from its official release:
https://github.com/freerouting/freerouting/releases/download/v1.9.0/freerouting-1.9.0.jar

Required JAR SHA256:
`9084a4888937a7f31f857ecc12aa7a37407f51160e4d2892dff9c9bb47ae3102`.
The external engine is GPL-3.0; its binary is intentionally excluded.

From `source/router-tools`, put the verified JAR beside the source and use:

```sh
mkdir -p ../../scratch/classes
javac -cp freerouting-1.9.0.jar -d ../../scratch/classes *.java
CP="freerouting-1.9.0.jar:../../scratch/classes"
java -XX:-UsePerfData -Xmx192m -Djava.awt.headless=true -cp "$CP" DsnToCore \
  ../../inputs/atopile-sd-native2-fullground-precise.dsn ../../scratch/native.core.frb
java -Xmx192m -Djava.awt.headless=true -cp "$CP" InspectRules ../../scratch/native.core.frb PCI_RX
java -Xmx192m -Djava.awt.headless=true -cp "$CP" TargetedRouteGuardTest ../../scratch/native.core.frb
java -Djava.awt.headless=true -cp "$CP" GroundFanoutCoverageTest
java -Djava.awt.headless=true -cp "$CP" RouteOnlyExportStateTest
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_specctra_tools
```

These are POSIX commands; Windows Java uses `;` as the classpath separator.
Python preservation-audit tests additionally require `sexpdata`.
`CHECKPOINTS.md` documents older GUI checkpoint handling; its historical captured
FRB fixtures are not part of this portable source bundle.

## Resume after reviewing the latest native project

Regenerate a complete raw DSN from the chosen latest board with native
`pcbnew.ExportSpecctraDSN`, preserving its actual lock states. Do not use the old
`pcb_route_io.py export` mode for this step: it deliberately locks every route.
Apply reviewed layer/clearance configuration while retaining the native RF,
USB, Power and default classes. The supplied DSN is already configured.
`specctra_tools.configure_dsn` handles only a single-default-class input and
intentionally refuses this newer custom-class board.

Then use `source/export_precise_native_wiring.py` with KiCad 10's Python/pcbnew
to replace only the rounded wiring scope. Always start with a fresh raw export
of that same board; a changed R112 placement also changes library/placement data.
Load the result with `DsnToCore` and inspect its accounting before routing.

PCI_RX's known local B.Cu cut is
`(172.2872,121.0216) -> (170.05,121.0216)` mm near the C26 GND stitch.
`RouteOnly` can reserve existing PCI_RX copper and attempt a strict victim pass:

```sh
java -XX:-UsePerfData -Xmx192m -Djava.awt.headless=true \
  -Datopile.route.preserveTargetCopper=true -cp "$CP" RouteOnly \
  ../../scratch/native.core.frb PCI_RX ../../scratch/pci-rx.ses \
  ../../inputs/atopile-sd-native2-fullground-precise.dsn 90 victim-pass
```

Run routing with OS-level network denial. `offline.sb` provides the macOS
`sandbox-exec` profile; other systems need an equivalent process/container rule.
Do not run multiple high-memory jobs on a nearly full disk.

RouteOnly requires all displaced net counts to return exactly to baseline.
It restores original fixed states in its export clone and also emits target
copper JSON. That JSON lists the whole target net: derive an explicit geometric
delta before merging it with another prototype's fanout. Do not replace a newer
PCI_RX fanout with an older whole-net list.

## Import and completion gates

- Remove the entire SES placement scope with `specctra_tools.py sanitize-ses`.
  Import only into a work copy of its matching native seed.
- SES omits fixed copper. Newly introduced fixed anchors absent from the native
  seed need an explicit manifest or `ExportAnchoredSes`'s export-only unfixing.
  Never unlock original protected copper to work around this omission.
- SES does not preserve all via fabrication flags. The verified V_BT via at
  `(170.9425,117.1125)` mm is 0.60/0.30 mm, filled/capped and tented on both sides;
  preserve that and the other native VIPPO declarations after import and reload.
- Keep F/In2/B as signal-routing layers and In1 as the continuous GND reference.
  Preserve RF/USB fixed geometry and widths. Native minimum track/clearance is
  0.15 mm; through vias remain 0.60/0.30 mm. Power trunks remain 0.50 mm, with only
  the separately reviewed short 0.20 mm chip breakouts allowed.
- Audit every assigned pad net, original 245 scanner placements, protected
  copper, keepouts and plane intent. Any intentional new-part R112 translation
  requires its exact separate allowlist, not a weakened general placement test.
- Refill zones and run native KiCad DRC, unconnected checks and schematic parity.
  All must pass on the saved/reloaded final board. Engine scores and successful
  SES export do not establish completion or manufacturing readiness.

`SHA256SUMS` covers every source/input file in this bundle. Originals were copied
read-only and remain at their original paths. Two copied-source adjustments are
recorded here: the guard test accepts an explicit core fixture path, and RouteOnly
can export newly created victim traces as unlocked while refusing ambiguous new
extensions of protected copper. The latter case was found during handoff review;
no new routing result was generated to exercise it.

# Continue the Chrysler scanner project

The integrated-SD PCB is fully routed and packaged for prototype fabrication
as of 2026-10-21. Firmware remains deferred.

Open `projects/chrysler-scanner/current/ChryslerScanner_V240_SD.kicad_pro` in
KiCad 10. Read `projects/chrysler-scanner/README.md` and `reference/final-status.json`
under that project for current evidence and package locations.

Final native checks show zero DRC errors, warnings, unconnected items and
schematic-parity issues; ERC is clean. Independent connectivity confirms all
175 ground pads and every signal net connected. Fabrication requires the
recorded filled/capped/planarized vias and manufacturer stackup review.

The complete KiCad archive and fabrication-only ZIP are under
`projects/chrysler-scanner/outputs`. Original placements, protected copper,
zones and rules are preserved; only added R112 moved +0.050 mm X/+0.075 mm Y.

Prior unfinished checkpoints and experimental scripts are retained as history.
Use the current final reports, not earlier partial-route diagnostics. The
original Atopile source cannot regenerate the integrated native PCB changes.

For the Atopile Local extension, runtime setup remains in the repository
README and source recovery information in extension-handoff.md. Runtime caches
and AI login sessions are machine-specific. Bench/vehicle validation, firmware
and manufacturing orders have not been performed.

The first schematic page exposes 177 hierarchical signal ports. J1 and input
protection share a sheet. The latest 22-page PDF is
`projects/chrysler-scanner/current/ChryslerScanner_V240_SD-Hierarchy.pdf`.

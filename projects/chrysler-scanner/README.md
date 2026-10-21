# Chrysler scanner with integrated microSD

The native KiCad PCB is fully routed and packaged for prototype fabrication.
Open `current/ChryslerScanner_V240_SD.kicad_pro` in KiCad 10.
Page 1 is a clickable system block diagram. The updated PDF is
`current/ChryslerScanner_V240_SD-Hierarchy.pdf`.

Final checks: zero DRC errors, warnings, unconnected items and schematic-parity
issues; zero ERC findings. Independent native connectivity reports zero uncapped
airwires and all 175 ground pads connected. All original scanner placements,
174 accepted protected copper objects, nine zones, outline, mounting holes,
rules and exclusions are preserved. Only added resistor R112 moved, +0.050 mm X
and +0.075 mm Y. See `current/reference/placement-exception.json`.

The board is 110 x 55 mm, four layers, 1.6 mm thick, with microSD socket J4 on
the underside. Provide card access and at least 7 mm underside enclosure space.

## Fabrication files

- `outputs/chrysler-integrated-sd-rev-b-fabrication.zip`: Gerbers, separate metric
  PTH/NPTH drills, Gerber job, drill maps, checksums and manufacturing notes.
- `outputs/chrysler-integrated-sd-routed-rev-b.zip`: complete portable KiCad project,
  22 schematic sheets, libraries, models, BOM, renders, reports and fabrication set.

Filled, capped and planarized via processing is required at the recorded sites.
Send `current/reference/MANUFACTURING-NOTES.md` with the fabrication files; ordinary
open vias are not equivalent. Agree the actual RF/USB stackup with the fabricator.

Final evidence is in `current/reference/final-drc.json`, `final-erc.json`,
`final-routing-audit.json` and `native-circuit-audit.json`. The board SHA-256 and
package status are in `reference/final-status.json`. Earlier checkpoint reports
and routing trials remain historical; use the final reports for this revision.

Firmware is still deferred. Bench, thermal, supply, enclosure and vehicle tests
remain prototype work; no manufacturing order or external upload was made.
The intended logging target remains raw traffic plus selected values for an
early-2004 automatic Cummins. The archived Bluetooth/XIAO firmware is not a
replacement for integrated-board firmware.

The original CAD references and original Atopile sources remain preserved.
Rebuilding the original Atopile circuit will not regenerate this native layout.
The circuit is GPL-3.0; bundled assets retain their own notices and licenses.

# ChryslerScanner V240 atopile migration

This project recreates the **V240 schematic, revision 2.4.0-1 (2026-01-05)** in
atopile, with a local **V240-USB-C-OBD** connector revision. It creates an editable
four-layer KiCad PCB using the original V140 Gerbers for mechanical geometry
and matching component locations. The upstream schematic PDF remains unchanged.

The current board is **110 x 55 mm**, enlarged from the original **100 x 50 mm**
at the user's request. It retains R2 corners and four 4 mm mounting drills.
The right holes move 10 mm right and the bottom holes move 5 mm down, giving
approximately 100 x 45 mm mounting-hole spacing. J1 now uses the ATTEND
manufacturer drill pattern; USB-C and CP2102 move 10 mm right. Other sections spread into
the extra area while critical pin-distance pairs retain their local geometry.
This changes enclosure fit and the LED/header locations. Current dimensions
and recovered-component translations are in `reference/board-mechanics.json`;
the original placement and region plan remain in the two
`reference/v240-100x50-*.json` snapshots.

**Status: electrically connected, placed, unrouted engineering layout. It is
not ready to order or assemble.** No updated manufacturing Gerbers are supplied.
The original V140 Gerbers remain unchanged in `gerbers/`.

Open `elec/layout/v240/v240.kicad_pcb` in KiCad 9 or later. Read the circuit in
`elec/src/main.ato`; physical parts and pads are defined in `elec/src/parts.ato`.
The local compiler is pinned to **atopile 0.15.9**, the classic local CLI syntax.
This is not a project for the different atopile 0.16 cloud editor syntax.

The source has 241 circuit parts, 142 connected nets and 746 numbered package
terminals. Multi-unit transistor and switch symbols share one footprint.
Four 4 mm mounting holes are additional mechanical footprints.

## First placement pass

The current PCB contains the first placement refinement: **199 footprints
repositioned**, with the connectors, mounting holes, ESP32, antenna, status
LEDs, buttons and the complete C1 body clearance retained. Components stay
in their functional regions; C16 retains its VPP circuit role but is placed
in the VBB region near U6's input. The RF matching network is closer to the
ESP32's LNA input. USB power-switch capacitors, regulator feedback resistors,
LED driver passives and ADC filter parts have shorter local connections.

The local signal half-perimeter sum falls from **1286.47 to 944.53 mm (26.58%)**.
This is a placement proxy, not a measured routed length or performance result.
All 41 earlier distance limits still pass, and 29 achieved additional targets
are now checked, for **70 physical proximity checks**. Native silkscreen
references retain the same size and clearance policy. Package pads, paste
apertures, part selections, model assignments, electrical source and BOM are
unchanged. No tracks or vias were added.

`reference/placement-pass-1-verification.json` records the preservation audit,
before/after measurements and 14 further power-placement targets. The before
positions, package signatures and candidate are retained beside it. The
comparison is `renders/V240-placement-pass-1-review.png`. Run
`scripts/refine_placement.py` to produce a candidate, inspect it, then use
`--apply` followed by the finish/validation helpers to install it.

One electrical review finding remains: U3/U4/U8 pin 5 is NC in the current
netlist, while the [TI TLV767 datasheet](https://www.ti.com/lit/ds/symlink/tlv767.pdf)
identifies DRV WSON-6 pin 5 as GND. This placement-only pass preserves the
existing circuit; correct/review that hidden-pin mapping before routing.

## Editable schematic visualization

Open `elec/schematic/ChryslerScanner_V240.kicad_pro` or its adjacent
`ChryslerScanner_V240.kicad_sch`. The overview links to 21 functional sheets:
power supplies, bus interfaces, programming drivers, ESP32/RF, voltage
monitoring, I/O control, USB/reset, LEDs and the OBD connector. The 22-page
PDF in `renders/ChryslerScanner_V240_schematic.pdf` has clickable sheet links.

For a portable viewing copy, extract `ChryslerScanner_V240_schematic.zip`
and open `ChryslerScanner_V240.kicad_pro` in the extracted folder. Its 22
schematic files, symbol library, footprints and 3D models are bundled with
relative paths. Native KiCad 10.0.7 exported the relocated bundle and its
connection comparison passed; see `reference/schematic-bundle-validation.json`.

The cleaned pages use standard A4/A3 paper, a 50 mil connection grid,
larger component graphics and consistent reference/value text. Connected
circuit blocks move together; captions and named ports are spaced around
the graphics. Redundant ports and unused wire tails are removed. The
I2C connector is drawn as a readable two-bank symbol with unchanged pin nets.
Duplicated PDF pin-number outlines are removed from U17/U18's native symbols.
The
overview and regulator pages visibly flag the existing U3/U4/U8 pin-5
ground issue, and the RF sheet shows R23/R24's DNP assembly option.
This cleanup preserves the atopile source, BOM, packages and PCB placement.
The final native checks report no off-grid or dangling-wire warnings.
See `reference/schematic-cleanup.json` and the rendered page contact sheet
in `renders/V240-schematic-contact.png`.

`elec/schematic/footprints.pretty` contains a native viewing copy of the
PCB packages. Its arc fields use the order required by KiCad's library
parser, and its model paths resolve from the schematic project directory.
All geometry, pads and model transform parameters are preserved; the
authoritative atopile package files remain unchanged. See
`reference/schematic-library-preparation.json` and
`reference/schematic-bundle-libraries.json`.

This is a native editable KiCad reconstruction from the current atopile
netlist, using vector component artwork and local circuit layout recovered
from the upstream V240 PDF. It includes USB-C, both 5.1 kohm CC resistors
and the selected ATTEND OBD-II connector.
Additional symbol units expose package-only supply, exposed-pad and NC pins.
Standard passive pin numbers are hidden; FET/IC/connector pin numbers remain
visible. Anonymous internal `N_*` nets remain ordinary wired connections
when all endpoints are on one sheet; KiCad assigns its own local names to
these nets. The validation report maps those names back to the compiler
names by their exact endpoint sets. Named ports connect matching signals
across sheets.

The native KiCad-exported netlist is compared against all 241 component
references, 142 connected nets, 746 numbered package terminals, 49 NC pins,
values, footprint assignments and the two DNP flags. The report is
`reference/schematic-validation.json`. Pin electrical types are passive
visualization types; this does not independently validate the original PDF
extraction or certify ERC/circuit performance. Atopile remains the electrical
source of truth: apply circuit edits there and regenerate this view.
The native CLI ERC report has zero errors and zero warnings.
`fp-lib-table` and every assigned footprint are included; package names and
pin sets are checked independently by the native netlist comparison.
The passive visualization pin types do not check driver/power compatibility.

The upstream repository tree, rechecked 2026-10-13 at commit
`4ddc6e5d1c260c87c6139f60079932ffde6e5d9a`, contains the V240 color/B&W PDFs
and no editable `.kicad_sch` or `.sch` files. The original PDF remains in
`reference/upstream/ChryslerScanner_V240_schematic.pdf`.

Regenerate and verify:

```sh
.venv/bin/python scripts/generate_kicad_schematic.py
kicad-cli sch export netlist --format kicadxml --output reference/ChryslerScanner_V240_generated.xml elec/schematic/ChryslerScanner_V240.kicad_sch
.venv/bin/python scripts/validate_kicad_schematic.py
kicad-cli sch export pdf --output renders/ChryslerScanner_V240_schematic.pdf elec/schematic/ChryslerScanner_V240.kicad_sch
.venv/bin/python scripts/package_schematic.py
```

The viewing ZIP can be checked after extraction with native
`kicad-cli sch export netlist` / `sch erc`, followed by
`scripts/validate_kicad_schematic.py --native-export <xml> --schematic-dir <extracted-folder> --output <report>`.
Run `scripts/verify_schematic_bundle.py <extracted-folder>` using KiCad's
bundled Python to check every footprint's native pin set and relative model
paths. `scripts/measure_schematic_text.py`, also run with KiCad's Python,
refreshes the stroke-font metrics used by the page layout.

## Selected OBD-II connector

**ATTEND 226A-1202** is a documented Type-A male, 16-pin, right-angle PCB
connector. The [manufacturer page](https://www.attend.com.tw/en/product.php?act=view&id=11)
provides a dimensional drawing and STEP CAD archive. It also has an
[ordering listing](https://www.ozdisan.com/p/pcb-konnektorler-310/attend-226a-1202-607756).
No connector has been purchased.

The drawing specifies 4 mm pitch along the rows, 3.0 mm between PCB tail
rows, 1.35 mm drills and 2.35 mm pads. The Gerber-derived J1 instead has
approximately 3.29946 mm between rows and 1.2 mm drills. The main board now
uses the manufacturer pattern, preserving all 16 electrical terminal assignments.
J1 is at board-local (3.00, 25.00) mm, mating left, with pin 1 at the top of
the near-edge row. Its tails are at x=1.50/4.50 mm and y=11,15,...,39 mm.
The selected position is 0.15 mm inward from the recommended board-edge
relation, increasing nominal pad copper clearance from 0.175 to 0.325 mm.

`elec/src/footprints/OBDII_ATTEND_226A-1202.kicad_mod` and
`elec/src/3dmodels/ATTEND_226A-1202.step` are the active footprint and aligned
manufacturer model. FreeCAD confirms all 16 tails fit their nominal drills,
with zero intersections with the 1.6 mm PCB and four 7 mm mounting hardware
envelopes. The report is `reference/obd-cad-validation.json`. The courtyard
covers the inboard solder-tail assembly clearance; F.Fab and the CAD show
the complete housing projecting beyond the left edge. A physical sample,
tolerance stack, insertion-load support and enclosure fit remain unverified.
Manufacturer CAD rights remain with ATTEND. Source URLs, hashes and dimensions
are in `reference/obd-connector-selection.json`.

The original manufacturer CAD and earlier recommended-edge candidate preview
remain in `reference/connector-candidates/` as references. The main board,
current 3D renders, BOM, atopile source and editable schematic use the selected
connector. `scripts/apply_obd_layout.py` reinstalls this package and location
after an intentional layout regeneration; ordinary rebuilds preserve them.

## USB-C revision

J2 is a **GCT USB4105-GF-A** USB-C receptacle with 16 contacts and standard
0.95 mm shell stakes. Its KiCad footprint and matching local STEP model were
checked against the [GCT package drawing](https://gct.co/files/drawings/usb4105.pdf).
The mating face is on the right board edge, centered at y=29 mm, preserving
the prior USB-B port centerline. The socket is lower and narrower than USB-B;
an existing enclosure opening may need an insert or revised cutout.

The existing CP2102 remains the USB 2.0 full-speed device. A6/B6 connect to D+,
A7/B7 to D-, all four VBUS contacts to the existing VBUS net, and all four
ground contacts plus shell stakes to GND. SBU1/SBU2 are NC. R102 and R103 are
independent 5.1 kohm, 1% CC1/CC2 pulldowns, respectively, using
[Yageo RC0603FR-075K1L](https://www.yageogroup.com/component-documentation/download/specsheet/RC0603FR-075K1L).
This implements a 5 V sink without USB-PD or SuperSpeed. The two pulldowns
follow [ST's sink-termination guidance](https://www.st.com/resource/en/technical_article/dm00496853-overview-of-usb-type-c-and-power-delivery-technologies-stmicroelectronics.pdf).

U11, the existing USBLC6 data ESD protector, now sits beside the USB-C contact
row. Its D+/D- input pads and both CC resistor input pads are each within
2.5 mm of their respective connector contacts. USB-C SMT pads use 0.025 mm
mask expansion per side, leaving a 0.15 mm bridge at the 0.5 mm-pitch contact
row for the planned black solder mask. The new connector's two 0.65 mm NPTH
alignment holes and four plated shell slots are part of its footprint.

`reference/hardware-overrides.json` records this local revision and is applied
by the source generator. `reference/v240-usb-b-netlist.json` retains the prior
electrical circuit for comparison. All 238 retained component pin maps remain
identical; only J2's package/terminal mapping and the two added CC resistors
change the circuit. J2, U11 and the two CC resistors receive local placement
changes. The later board enlargement changes placement and mounting-hole
spacing, preserving component pad and paste geometry. The board still needs routing,
USB current-budget/protection review and physical cable testing.

## 3D components

All 241 circuit footprints have local 3D models, including the two DNP
resistors (R23/R24). The four mounting holes remain bare holes without invented
fasteners. Open the board and choose **View → 3D Viewer** in KiCad (Option+3 on
macOS). `renders/V240-3D-isometric.png` and `renders/V240-3D-top.png` show the
assembled appearance. The STEP assembly in `renders/V240-assembly.step`
excludes the two DNP resistors.

Models are bundled in `elec/src/3dmodels/`; model paths are relative to the
PCB project, so an external KiCad model library is unnecessary. Generic KiCad
package models cover standard components. Dimension-based representative
models cover the ESP32 SiP, SY6283, antenna and selected inductors;
the USB-C socket uses the matching KiCad GCT model.
the LEDs have the schematic's red, yellow, green and blue colors. Solder
jumpers show their intended solder states.

**J1 uses ATTEND's actual manufacturer CAD.** Capacitor height, inductor choice
and LED/switch details still need
confirmation against orderable parts. These models support visualization and
layout review; they do not certify enclosure fit. Every model's source,
license, dimensions/assumptions and assignment are recorded in
`reference/3d-models.json`. The copied KiCad models retain their library license
and exception in `elec/src/3dmodels/LICENSE-KiCad.md`; generated geometry uses
the project's GPL-3.0-or-later license. ATTEND CAD rights are recorded separately
in `elec/src/3dmodels/LICENSE-ATTEND.md`.

## Functional placement and four layers

The board is regrouped into 21 circuit regions. CCD, PCI and SCI front ends
sit toward the OBD edge. Each switching supply has its own regulator,
inductor, catch diode, bootstrap capacitor, feedback and output components.
VBB/VPP programming drivers are arranged in repeated channel groups. ESP32
bypass capacitors sit beside their supply pins, and the ADC, I/O expander,
USB and LED circuits have separate local groups.

The expanded outline and mounting holes, J1/J3 connector coordinates, CP2102
and LED positions are fixed at their current planned locations. J2 is locked
to its USB-C board-edge location at x=110 mm, y=29 mm.
The grouping and physical pin-distance constraints
are recorded in `reference/layout-plan.json`; the fixed coordinates are in
`reference/mechanical-anchors.json`. Placement choices remain preliminary:
short pad-center distances are not a substitute for reviewing the routed loops.

| Copper layer | Intended use |
| --- | --- |
| F.Cu / L1 | Components, critical signals and local switching loops |
| In1.Cu / L2 | GND reference plane, with no signal routing |
| In2.Cu / L3 | Power distribution, with GND beneath the RF feed |
| B.Cu / L4 | Remaining signal routing |

The PCB contains an outline-wide L2 GND zone definition, a local L3 GND
definition beneath the RF feed and an antenna keepout on all four copper
layers. These zones are **not filled or electrically verified**. They must be
refilled in KiCad against the eventual tracks, vias and holes; power islands
and ground/thermal stitching vias are part of the routing stage.

The nominal 1.6 mm stackup uses 35 um copper, 0.18 mm outer dielectrics and a
1.08 mm core. These are provisional planning dimensions. Confirm the actual
fabricator stackup before calculating USB/RF trace widths or ordering boards.

## Hardware source

- [Upstream ChryslerScanner](https://github.com/laszlodaniel/ChryslerScanner)
- [Pinned V240 schematic](https://github.com/laszlodaniel/ChryslerScanner/blob/4ddc6e5d1c260c87c6139f60079932ffde6e5d9a/PCB/V240/ChryslerScanner_V240/schematic/ChryslerScanner_V240_schematic.pdf)
- Upstream commit: `4ddc6e5d1c260c87c6139f60079932ffde6e5d9a`, checked 2026-10-12.
- The original upstream PDF and supporting manufacturer documents are in
  `reference/upstream/`. The upstream repository supplied PDF schematics rather
  than an editable schematic/netlist for this revision.

The new circuit includes ESP32-PICO-V3-02, PCI/J1850, CCD and SCI interfaces,
AW9523B control and the V240 programming-voltage supplies. The upstream USB-B
interface is adapted locally to USB-C. The V240 circuit replaces
the V140 ATmega design and its old transceiver/power circuits. Old copper was
not imported into the new circuit because those connections changed.

## What the Gerbers contributed

The original Gerbers establish the 100 x 50 mm outline, R2 corners and four
4 mm mounting holes. The current 110 x 55 mm board expands the right/bottom
edges and corresponding holes. The original OBD drill positions served as
a placement reference and are superseded by ATTEND's documented pattern.
CP2102 and the four 1206 status LEDs retain their recovered pad
geometry, with component translations recorded in `reference/board-mechanics.json`.
New reference designators differ:
old D1/D2/D3/D4 become new D23/D24/D25/D26, respectively (RX/TX/PWR/ACT).

The USBLC6-2SC6 pad geometry is recovered from the old Gerber, and its placement
is now beside USB-C at (99.1, 28.75) mm. Its original V140 center was
(92.328982, 24.999941) mm from the upper-left board corner. USB-C, CC resistor,
reset and boot switch positions are recorded in `migration.csv`. CP2102 rotation
was inferred from the old silkscreen. J1 pin numbering now follows ATTEND's
recommended top-view drawing and retains the original electrical assignments.
Physical connector/board fit remains a fabrication review item.

`reference/v140-layout-reference.json` retains the raw Gerber coordinates.
The conversion is `board_x = gerber_x - 9.254`,
`board_y = 59.254 - gerber_y`, in millimeters. The KiCad upper-left board corner
is at (100, 100) mm. All positions in `migration.csv` are board-local.

## Build and inspect

The installed `.venv` can build immediately:

```sh
.venv/bin/ato build --target update-pcb
.venv/bin/python scripts/finish_board.py
.venv/bin/python scripts/validate_board.py
.venv/bin/python scripts/render_board.py
```

For a fresh environment, install Python 3.14 and the pinned dependencies in
`requirements.txt`. The footprint library is local and needs no cloud part
picker. `BOM.csv` is the useful BOM: atopile's automatic picked-parts BOM is
empty because these are explicitly defined atomic parts.

Routine `ato build` updates connectivity and preserves the layout. The local
compiler hides designators and omits footprint lock tokens when saving, so run
`scripts/finish_board.py` afterward. It restores all 245 real reference fields
on F.SilkS, adds F.Fab identifiers and restores the mechanical locks. Labels use
1.0 mm text height, compact 0.65 mm font width and 0.15 mm strokes, using
[JLCPCB's standard capability minimum](https://jlcpcb.com/capabilities/pcb-capabilities/).
References keep at least 0.15 mm clearance from physical bodies and pad/mask
openings, with 0.15 mm between label ink bounds and clearance for mounting
hardware. Bounds are measured with KiCad's actual stroke font, rather than
estimated from character count. Labels can use otherwise empty assembly
courtyard space. The helper preserves footprint coordinates, nets and
routing. It also restores bundled 3D assignments and native `(attr smd dnp)`
flags for R23/R24. The earlier unsupported footprint-level `(dnp yes)` syntax
has been removed from the generator. KiCad 10.0.7 natively loaded, rendered
and exported the updated board. `scripts/lock_mechanical.py` also invokes it
for compatibility. Do not run
`scripts/place_board.py` on a manually refined board: it deliberately resets
placement to the functional layout plan. To regenerate the migration from its sources:

```sh
.venv/bin/python scripts/extract_gerber_reference.py
.venv/bin/python scripts/extract_v240.py
.venv/bin/python scripts/generate_atopile.py --keep-footprints
.venv/bin/python scripts/normalize_footprints.py
.venv/bin/python scripts/apply_usb_c_layout.py --prepare-connector
.venv/bin/ato build --target update-pcb
.venv/bin/python scripts/place_board.py
.venv/bin/python scripts/apply_usb_c_layout.py
.venv/bin/python scripts/expand_board.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 scripts/measure_reference_text.py
.venv/bin/python scripts/finish_board.py
.venv/bin/python scripts/validate_board.py
.venv/bin/python scripts/render_board.py
```

The included 3D assets need no regeneration. To regenerate their geometry on
this Mac, use FreeCAD's bundled Python:

```sh
/Applications/FreeCAD.app/Contents/Resources/bin/python scripts/generate_3d_models.py
.venv/bin/python scripts/attach_models.py
```

`scripts/verify_native_kicad.py` runs with KiCad's bundled Python and checks the
native PCB parser, actual reference ink bounds and dimensions, resolved model
files, DNP flags and exported STEP references.
`reference/3d-cad-validation.json` records the separate solid-geometry check.

`reference/silkscreen-text-metrics.json` records the text policy and measured
glyph bounds. To change that policy, edit and run
`scripts/measure_reference_text.py` with KiCad's Python, then run the finish and
validation helpers. The main JLCPCB capability table lists 1.0 mm minimum
height; its [silkscreen blog](https://jlcpcb.com/blog/pcb-silkscreen) separately
quotes 0.8 mm. This board uses the main capability table's standard limit.

## Required work before fabrication

1. Review the recovered PDF netlist against the schematic. Extraction uses
   vector wires, explicit junctions, numeric pad labels and NC marks; it is
   auditable in `reference/upstream/v240-extracted.json`. A compiler pass alone
   does not independently establish that the PDF extraction is correct.
2. Finalize orderable part numbers, passive packages, ratings and assembly
   options. Most passive packages are not specified by the schematic; new
   passives use 0603/0805 with selected 1206 power/interface parts to fit the
   board area. These are migration choices. Inductor/ferrite packages,
   the 100 uF capacitor, diode
   suffixes, switches and exact connector fit need review. Preserve schematic
   capacitor-voltage/current/tolerance notes when selecting parts. R23/R24 are
   explicitly DNP, not zero-ohm links.
3. Review the grouped placement while routing switching-power loops,
   comparator reference/sense paths and interface protection. The checks
   enforce courtyard clearance and 70 pin-distance constraints; this remains
   an engineering layout, with further adjustment possible during routing.
4. Route the entire board; fill and verify ground zones, design power islands,
   supply widths, thermal vias,
   USB differential routing and a 50-ohm antenna feed for the chosen stackup.
   The antenna pad dimensions and initial keepout are provisional and require
   the manufacturer's RF layout review. The PICO and AW9523B exposed pads are
   connected in the netlist, but their thermal-via design remains open.
5. Run KiCad DRC and independent electrical review, confirm connector
   orientation and enclosure clearance, then generate new manufacturing files.
   No KiCad DRC or physical prototype testing has been completed here.

`reference/validation.json` records the reproducible checks that were run.
Those checks cover source/PCB connectivity, pad completeness, mechanical
geometry, actual courtyard geometry, functional regions, pin distances,
four-layer stackup, visible reference fields and fixed connector positions.
The C1 check independently reads its actual 8 mm circular body and verifies
the complete 8.5 mm courtyard, outline containment and neighboring-component
and mounting-hardware clearance. An ordinary atopile rebuild
preserves these changes. They do not constitute fabrication approval.

## Recovered hidden package connections

The source plot omits some physical pads. U13/U14/U15 pads 4/8 are GND/3.3 V;
U12 exposed pad 29 is GND; U19 exposed pad 25 is GND. ESP32-PICO-V3-02 pads
4/43/46 are additional 3.3 V supply pads per Espressif's datasheet. All package
NC pads are included and left unconnected. See each pin's `origin` in
`reference/v240-netlist.json` for the additions to the visible PDF pin graph.

Derived circuit/source: upstream GPL-3.0; see `LICENSE`. Vendored KiCad
footprints: CC-BY-SA-4.0 with KiCad library exception; see
`reference/upstream/footprint-provenance.json`. Footprint syntax was normalized
for the local compiler without changing pad positions.

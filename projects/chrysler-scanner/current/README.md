# ChryslerScanner V240 with integrated SD hardware — routed revision

Open `ChryslerScanner_V240_SD.kicad_pro` in KiCad 10, then open its PCB or schematic.
Keep the complete folder together: all 22 schematic sheets, footprints, symbols
and 3D models are bundled. The microSD socket J4 is on the underside near the
bottom edge. Flip the board in the 3D viewer to see it.

The single main board is 110 × 55 mm, four layers, 1.6 mm thick. It uses the
existing ESP32-PICO-V3-02 directly for SD storage; no separate Bluetooth carrier
or second microcontroller is required. The 18 added SD components, LOG button,
card-detect circuit and regulator remain on this main PCB. Provide a card-access
opening and at least 7 mm underside clearance. Check the intended enclosure
against the actual connector and capacitor dimensions before manufacturing.

## System overview

Page 1 restores the original functional block-diagram layout, with vehicle
interfaces on the left, the controller in the middle, USB/SD on the right, and
power/programming below. It has 156 native hierarchical signal ports
across 21 circuit sheets. Named signal stubs connect matching nets across blocks.
J1 and its line-protection components now share the input sheet. GND uses
native ground power symbols below each circuit, with the common net shared
globally instead of repeated ground hierarchy ports. Every original
net endpoint is preserved; only J1's PCB sheet-path metadata changed.

Use `ChryslerScanner_V240_SD-Hierarchy.pdf` for the updated 22-page PDF.
Older PDF previews were open in another application and remain unchanged locally.
The portable ZIP uses the updated PDF under its conventional project filename.
`source/verify_system_hierarchy.py` checks ports, endpoints and the exact permitted
PCB metadata change; `reference/system-diagram-validation.json` records the result.

## Final routing changes

RX15_EN, TX_LED and PCI_RX are complete. The four board-edge findings and
redundant dangling branches are cleared. A filled/capped GND stitch at C56
keeps all 175 GND pads in one native connected group. Only added resistor
R112 moved: (172,121) to (172.05,121.075) mm. All original scanner parts,
all 174 accepted protected copper objects, nine zones and existing rules are
preserved. The original accepted input and explicit geometry exception are
retained under `reference`.

`checkpoint-*` and `pre-route-*` reports are historical. Use `final-drc.json`,
`final-erc.json`, `final-routing-audit.json` and `native-circuit-audit.json`
for this PCB. Fabrication requires the filled/capped processing sites listed
in `reference/MANUFACTURING-NOTES.md`.

## CAD validation

The final native KiCad DRC reports zero violations, zero unconnected items and
zero schematic-parity issues. Native connectivity is checked independently,
including every ground pad. The schematic has 259 electrical components and
154 connected nets; all 40 declared no-connect terminals remain isolated.
The PCB has 263 footprints including the four mechanical holes. Reports and
file checksums are under `reference` and `SHA256SUMS.txt`.

The original scanner placements and outline are preserved. CP2102 and USB-C
land-pattern corrections, protected RF/USB/power routing, ground stitching and
antenna clearances are recorded in the verification reports. Existing DRC
minimums and exclusions were not relaxed to achieve the result. Existing
disabled checks remain documented by the native reports.

Unused outer-layer copper provides ground fills; surface-mount ground pads use
solid connections and through-hole pads use thermal reliefs. Assembly must use
an appropriate reflow profile. See the grounding report for any exposed-pad
via-in-pad locations that require filled and copper-capped/planarized vias;
ordinary open drilled vias are not an equivalent assembly process.

`previews` contains native KiCad routing plots and any available 3D renders.
`fabrication` contains the native Gerber and drill exports of this checked CAD
revision. The schematic PDF and BOM are beside the project. These are local
review artifacts; no manufacturing order or external upload has been made.

## Firmware and prototype work

Firmware remains deferred at the user's request. Fitting the SD circuitry does
not make the existing scanner firmware log data. Raw traffic plus selected
values for the early-2004 automatic Cummins remain the intended firmware target;
decoder compatibility and vehicle behavior have not been demonstrated.

KiCad checks establish geometry and connectivity, not physical operation.
Prototype power, SD write-current peaks, USB supply capacity, regulator
temperature, enclosure fit and signal integrity still need hardware validation.
The shared upstream supply was not enlarged. There is no RTC, battery, power-fail
supervisor or shutdown hold-up, so a clean file close after sudden power removal
is not guaranteed. The RF/USB geometry still needs the chosen fabricator's
stackup/impedance review. The recovered base schematic uses passive pin types;
zero ERC is not an independent active-device electrical-design review.

The original Downloads project and Atopile sources are unchanged. Rebuilding
the original Atopile project will not regenerate this native KiCad revision.
Make future edits in this project deliberately and rerun native DRC and parity.

## Licensing and provenance

Derived from the user's V240-USB-C-OBD reconstruction and
https://github.com/laszlodaniel/ChryslerScanner. Circuit licensing is GPL-3.0;
see `LICENSE`. Bundled library and manufacturer assets retain their respective
licenses in `licenses` and `3dmodels`. Circuit and source references are under
`reference/integration.json` and `reference/architecture-review.json`.

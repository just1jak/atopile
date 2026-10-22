# Chrysler V240 SD: inherited physical DRC corrections

This is the unrouted combined scanner PCB, with the inherited footprint errors corrected. It is an input to routing, not a manufacturing release. Work was performed exclusively in this new stage; the previous engineering PCB and original scanner project were not changed.

## Native verification

KiCad10.0.7 full DRC, including all track errors and zone refill, reports **zero physical errors and zero warnings**. `drc-corrected.json` records the full result. Missing connections remain and must be routed. The CLI caps its missing-item list; the independent native connectivity counts are recorded in `drc-remediation-proof.json`.

No design-rule thresholds, rule severities, exclusions, component positions, connector mating positions, locks, footprint UUIDs, existing pad UUIDs, schematic instance paths, model assignments, net names, or electrical net membership were changed. Board outline, all keepout polygons, and both GND-plane definitions remain exact. All263footprints are retained.

## Corrections and basis

### U12: classic CP2102 QFN28

[Silicon Labs CP2102/9 Rev1.8](https://www.silabs.com/documents/public/data-sheets/CP2102-9.pdf), Figure4/Table11, specifies a0.50mm pitch and4.80mm spacing between opposing pad rows. Recommended perimeter lands are0.20–0.30mm wide and0.85–0.95mm long; the exposed land is3.20–3.30mm square.

The imported perimeter lands were1.518666×0.318770mm at5.00mm row spacing, causing four0.1149mm corner clearances against the unchanged0.15mm rule. They are now nominal0.90×0.25mm at4.80mm row spacing. Pad29 is3.30mm square. Each land has the specified minimum0.06mm NSMD expansion. Its center uses nine paste-only0.90mm apertures on1.10mm pitch, following the manufacturer's stencil recommendation (approximately67%coverage). Existing pad29 retains its ground assignment and UUID; the nine new paste apertures contain no copper and no electrical net.

This is the classic CP2102 land pattern, not a substitution with CP2102N.

### J2: GCT USB4105

[GCT USB4105 RevB4 drawing](https://gct.co/files/drawings/usb4105.pdf), sheet1, was inspected directly. The recommended0.60×1.15mm ground-land envelope,0.65mm locating holes,5.78mm locating-hole spacing, and all contact centers remain unchanged.

The four shared ground pads A1/B12/A12/B1 had0.15mm corner radii, leaving only0.1944mm to the locating holes against the unchanged0.20mm rule. Their radius is now0.25mm, removing only the unnecessary corner copper nearest each hole while retaining the nominal rectangular envelope and solder-tail coverage. This rounded-corner adaptation is an engineering clearance correction; it does not change the manufacturer's hole or land-envelope dimensions. Native full DRC verifies the resulting clearance. All connector mechanical positions remain exact.

The corrected local footprint is synchronized with the embedded PCB geometry, resolving the previous library mismatch. The native GCT3D model assignment remains unchanged.

### GND reference planes and jumper library

Both existing GND planes are retained. One0.60mm diameter/0.30mm drill through-via at absolute(178.5,113.5)mm joins In1.Cu and the local In2.Cu plane, clearing the isolated-copper warning without removing the RF ground reference. It lies outside the antenna keepout and passes native clearance DRC. Its deterministic UUID is recorded in the proof. Further ground routing is still required.

The local bridged-jumper footprint did not contain JP1's already-existing net-tie metadata and F.Fab reference text. The library is now synchronized with the unchanged embedded jumper. No JP1 copper, net assignment, location, or UUID changed.

## Handoff

Use `ChryslerScanner_V240_SD.kicad_pcb` and its unchanged matching `.kicad_pro`. Merge these three corrected local footprint files into the portable package:

- `footprints.pretty/CP2102_V140_Reference.kicad_mod`
- `footprints.pretty/USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal.kicad_mod`
- `footprints.pretty/SolderJumper-2_P1.3mm_Bridged_Pad1.0x1.5mm.kicad_mod`

`footprint-correction-proof.json` records each changed pad and preservation assertions. `drc-remediation-proof.json` records the exact baseline/final comparison. The stage's `libraries` and `3dmodels` links are for local validation only; the parent portable package already contains those assets. No Gerbers or other manufacturing outputs were generated.

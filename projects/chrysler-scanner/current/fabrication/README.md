# Chrysler integrated-SD scanner: prototype fabrication files

Original fabrication-export source PCB SHA-256: `f4a5945538dd61389ef7a3937fe1406f76e9dfba2382e11e35fac4b787a8e12a`

Four layers, 1.6 mm, ENIG; outline centerlines are 110 x 55 mm. The native
Gerber job bounding box is 110.05 x 55.05 mm because it includes the 0.05 mm
outline stroke. Fabricate to the Edge.Cuts centerline; do not rescale the files.
Layer order is F.Cu, In1.Cu (GND), In2.Cu, B.Cu. Minimum track width and copper
clearance are 0.15 mm. Through vias are 0.60 mm copper / 0.30 mm drill.

**Filled, capped and planarized via-in-pad processing is required.** The exact
35 saved processing sites, coordinates and tenting flags are listed in
MANUFACTURING-NOTES.md. Ordinary open drilled vias are not equivalent.
Supply those notes to the fabricator along with the Gerbers and drills.

Gerbers are native KiCad X2 exports. PTH and NPTH drill files are separate,
metric, and use absolute coordinates. SVG drill maps are inspection aids.
Paste files are for optional stencil preparation. The Gerber job records the
stackup; agree the actual RF/USB stackup and process with the fabricator.

Native DRC: zero errors, warnings, unconnected items and schematic-parity issues.
Independent native connectivity: zero uncapped airwires; all 175 GND pads joined.
ERC: zero findings. Rules, exclusions and original scanner placements preserved.
Only new pull-up R112 moved, +0.050 mm X and +0.075 mm Y.

This is a routed prototype revision. Firmware, bench/vehicle validation and
manufacturing orders remain deferred. The SD socket is underneath the board;
provide card access and at least 7 mm underside enclosure clearance.

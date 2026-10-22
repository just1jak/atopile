# Rev C prototype fabrication

Four layers, 110 × 55 mm, nominal 1.6 mm. Confirm actual RF/USB stackup and impedance with fabricator. Use separate PTH/NPTH drill files. Assembly positions are millimetres, both sides, absolute board coordinates. Filled/copper-capped/planarized vias listed in filled-capped-via-sites.json are mandatory; saved drill flags do not themselves specify a fabricator process. Confirm underside microSD/enclosure clearance. This is a local export, not a fabrication order or qualified automotive design.

C61 is TOP-side at (193,127) mm; nominal body height 5.9 mm above PCB. Two new vias bring the filled/capped/planarized processing count to 205. Use this package only; earlier Gerbers place C61 underneath.

Mounting: M3 socket head, NO washer; checked envelope 5.5 mm diameter by 3 mm high. H1 clearance is 0.7504 mm centered, 0.2504 mm after nominal screw float. Actual tolerance/sample fit remains to be qualified before production assembly. See rev-c-obd-mechanical-clearance.md.

Checked PCB SHA-256: `a2cb3d5e82d57b75eb0caab103d6f82529d8543b182aa9fc80e320bfe61c2fd5`. Processing-site count: 205. See rev-c-filled-capped-via-sites.json for exact coordinates, UUIDs, drill sizes and saved flags.

# Rev C prototype fabrication

Four layers, 110 × 55 mm, nominal 1.6 mm. Confirm actual RF/USB stackup and impedance with fabricator. Use separate PTH/NPTH drill files. Assembly positions are millimetres, both sides, absolute board coordinates. Filled/copper-capped/planarized vias listed in filled-capped-via-sites.json are mandatory; saved drill flags do not themselves specify a fabricator process. Confirm underside microSD/enclosure clearance. This is a local export, not a fabrication order or qualified automotive design.

C61 is TOP-side at (193,127) mm; nominal body height 5.9 mm above PCB. Current testpoint revision requires 246 filled/capped/planarized processing sites. Use this package only; earlier Gerbers place C61 underneath.

Assemble 48 Keystone 5015 SMT hook loops (both board sides). TP45-TP48 are bare copper SPI probe pads: no components to purchase/place. Read rev-c-testpoint-map.md and the processing-upgrades JSON. This revision has 333 electrical/probe footprints plus four mounting holes, 24 schematic pages and 246 mandatory processing sites.

Mounting: M3 socket head, NO washer; checked envelope 5.5 mm diameter by 3 mm high. H1 is at (105.00048,104.0) mm. Connector clearance is 1.75 mm centered, at least 1.25 mm after nominal screw float; the head-to-board-edge margin is at least 0.75 mm after float. Update enclosure mounting pattern for H1. Actual tolerance/sample fit remains to be qualified before production assembly. See rev-c-obd-mechanical-clearance.md.

Checked PCB SHA-256: `800c05930a0ca24fe280d5f3aace70974889129942a1b5602ce2eabfea026301`. Processing-site count: 246. See rev-c-filled-capped-via-sites.json for exact coordinates, UUIDs, drill sizes and saved flags.

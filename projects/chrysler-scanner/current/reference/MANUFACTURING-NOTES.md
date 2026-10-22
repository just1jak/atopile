# Rev C prototype fabrication

Four layers, 110 × 55 mm, nominal 1.6 mm. Confirm actual RF/USB stackup and impedance with fabricator. Use separate PTH/NPTH drill files. Assembly positions are millimetres, both sides, absolute board coordinates. Filled/copper-capped/planarized vias listed in filled-capped-via-sites.json are mandatory; saved drill flags do not themselves specify a fabricator process. Confirm underside microSD/enclosure clearance. This is a local export, not a fabrication order or qualified automotive design.

C61 is TOP-side at (193,127) mm; nominal body height 5.9 mm above PCB. Current testpoint revision requires 230 filled/capped/planarized processing sites. Use this package only; earlier Gerbers place C61 underneath.

Assemble 48 Keystone 5015 SMT hook loops (both board sides). TP45-TP48 are bare copper SPI probe pads: no components to purchase/place. Read rev-c-testpoint-map.md and the processing-upgrades JSON. This revision has 329 electrical/probe footprints plus four mounting holes, 24 schematic pages and 230 mandatory processing sites.

Mounting: M3 socket head, NO washer; checked envelope 5.5 mm diameter by 3 mm high. H1 clearance is 0.7504 mm centered, 0.2504 mm after nominal screw float. Actual tolerance/sample fit remains to be qualified before production assembly. See rev-c-obd-mechanical-clearance.md.

Checked PCB SHA-256: `68d206c7f3794b39c32291e626993844f60c12ea20ad78d16e5127c4ccebafd9`. Processing-site count: 230. See rev-c-filled-capped-via-sites.json for exact coordinates, UUIDs, drill sizes and saved flags.

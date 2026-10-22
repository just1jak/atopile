# OBD connector and M3 screw clearance — 2026-10-22

Selected hardware: **M3 socket head, no washer**. Checked a conservative cylindrical head envelope **5.5 mm diameter × 3 mm high**, seated directly on the PCB top. Confirm the actual screw does not exceed that envelope.

| Check | Result |
|---|---|
| ATTEND 226A-1202 housing vs PCB with its 16 drilled holes | No solid intersection; all 16 solder tails enter their correct holes |
| Housing overhang past left PCB edge | 18.8 mm, intentional connector mating overhang |
| Nearest connector pad copper to board edge | 0.325 mm; native 0.30 mm rule passes |
| H1 centered screw-head to connector | 0.7504 mm |
| H1 screw shifted 0.5 mm toward connector | 0.2504 mm, no intersection |
| H2 centered screw-head to connector | 4.3225 mm |
| H3 / H4 centered screw-head to connector | More than 97 mm |

All four mounting holes are 4 mm diameter. A nominal 3 mm screw can move 0.5 mm radially. By the distance bound, any such translation leaves at least 0.2504 mm at H1; the worst-direction translated solid was also checked directly. The washer-free head fits nominal CAD. **This is not a full tolerance qualification:** 0.25 mm is the remaining budget before connector/PCB/hole/fastener tolerances. Verify the actual screw and sample assembly before production assembly. If their combined adverse tolerance exceeds that budget, locate the screw positively or revise the mechanical clearance before ordering production quantities.

Do not substitute a washer or above-board standoff based on this result: a 7 mm tall envelope has only 0.0004 mm nominal H1 clearance, and an 8 mm above-board envelope intersects the housing. Enclosure fit and support for connector insertion loads remain separate mechanical checks. PCB placements, holes, copper and outline are unchanged.

Geometry: bundled manufacturer STEP, FreeCAD 1.0 solid distances/booleans, native KiCad coordinates. [Manufacturer drawing](https://www.attend.com.tw/data/download/file/226A-1202.pdf). Exact PCB/model hashes and raw measurements are in rev-c-obd-mechanical-clearance.json. Older zero-intersection checks alone did not establish an adequate clearance margin.

C61 top-side revision: exact layout delta preserves J1, mounting holes and outline. OBD/screw measurements remain applicable to PCB `a2cb3d5e82d57b75eb0caab103d6f82529d8543b182aa9fc80e320bfe61c2fd5`; C61 is outside the connector housing envelope.

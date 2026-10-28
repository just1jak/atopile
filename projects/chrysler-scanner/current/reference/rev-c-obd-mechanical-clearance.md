# OBD connector and M3 screw clearance - 2026-10-28

H1 is now (105.00048,104.0) mm, moved 0.9996 mm toward the top edge. H2/H3/H4, J1, all 16 connector tail holes and the board outline are unchanged. The selected hardware remains M3 socket head, no washer, bounded by a 5.5 mm diameter x 3 mm high cylinder seated on top of the PCB.

FreeCAD 1.0 manufacturer-STEP distance checks give H1 connector clearance **1.75 mm centered / at least 1.25 mm after any nominal 0.5 mm radial screw float**. This improves the previous 0.2504 mm worst-float result by about 1 mm. There is no nominal head/housing intersection. The centered head-to-board-edge margin is 1.25 mm, or at least 0.75 mm after float; the 4 mm hole leaves a 2 mm fixed edge web. The other holes have larger connector clearances.

Exact CAD/model evidence is in `rev-c-refinement-mechanical.json`. The original nominal housing/tail alignment check remains applicable because J1/outline/tail drills are unchanged. Actual screw, molding, drilling and board-edge tolerances, insertion loads, tool/enclosure fit and sample assembly remain to be qualified. Any pre-existing enclosure mounting pattern must be updated for H1. No washer or above-board standoff is included in this acceptance.

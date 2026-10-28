# Revision C prototype manufacturing requirements

This file supersedes the pre-Rev-C 35-site notes and old acceptance hash. Routing is still in progress: no final fabrication-site count or release hash is claimed here. The gated package_rev_c.py exporter will regenerate this document and rev-c-filled-capped-via-sites.json directly from the final checked native PCB, binding every recorded filled/capped via UUID, coordinate, drill/diameter and count to its SHA-256. Require reference/p1-contract-audit.json releaseGatePassed=true for that same hash.

Four copper layers, 110 × 55 mm, nominal 1.6 mm. Agree final RF/USB stackup and impedance with the fabricator. All recorded filled/copper-capped/planarized vias require that process; ordinary open or tented drills are not equivalent. Inspect all via-in-pad locations. Use separate PTH/NPTH drill exports and verify assembly-position coordinates and bottom-side orientation. Confirm connector overhang, enclosure and underside microSD clearance.

Exact generic BOM selections remain incomplete. Confirm capacitor voltage/DC-bias capacitance and case fit, inductor current, resistor power/tolerance and exact FET ordering/pinout before assembly. C14/C15 require ≥50 V; see BOM and safety contract. Native clean DRC/ERC is not automotive, transient, thermal or vehicle qualification. No manufacturing order or external upload has been made.

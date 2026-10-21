# Ground stitching fabrication handoff

This is a routing-stage fabrication requirement, not a board-order release. Native KiCad DRC does not validate whether a manufacturer supports this process.

Eight vias overlap assembly lands and require filled, copper-capped, planarized via-in-pad fabrication (VIPPO). Each uses a 0.30 mm finished drill and a 0.60 mm annular land. Do not substitute ordinary open barrels or tenting alone. The PCB stores explicit `filling yes` and `capping yes` on each via. The original component footprint and soldermask land definitions were preserved.

| Ground location | Absolute PCB position (mm) | Front mask | Back mask | Via UUID |
|---|---|---|---|---|
| U10.49 | 173.6875, 115.3625 | Open within exposed-pad window | Tented | 87918af0-1294-525b-97f0-f493c22293c6 |
| U10.49 | 172.7875, 115.3625 | Open within exposed-pad window | Tented | 3369aeaf-d4a1-5472-b28b-5c869e8d0f87 |
| U10.49 | 174.5875, 115.3625 | Open within exposed-pad window | Tented | acb91d58-5ff1-55fc-9627-1e082d19c8f0 |
| U19.18,U19.22,U19.24,U19.25,U19.9 | 168, 137.85 | Open within exposed-pad window | Tented | 3f620289-6eae-5796-977d-602df49c9a9f |
| U12.29,U12.3 | 203.979982, 114.440018 | Open within exposed-pad window | Tented | 054fe1b1-22f7-5290-b500-a7f213f7380a |
| R59.2 | 152.075, 147.75 | Tented | Tented | 0bcb79aa-808e-548b-b188-6a060d332568 |
| U11.2 | 200.050099, 128.75 | Tented | Tented | 9a887a6b-218d-5083-812e-b6f3faba1440 |
| U13.4 | 123.8125, 141.4875 | Tented | Tented | 48f683c4-3dd7-526b-8754-f7ab5cfa5510 |

The three U10 vias join its exposed ground pad to the continuous In1.Cu reference. U12 and U19 vias also join their peripheral ground-pin clusters through the existing outer ground copper. R59, U11 and U13 use both-side via tenting so their original component-pad openings define the solderable surface; filling and capping are still required below those openings.

All other newly added ground vias are outside assembly-pad apertures and are tented on both surfaces. Added tracks, widths and lengths are enumerated in `ground-stitch-proof.json`. All pre-existing copper, component/pad geometry, hierarchy paths and approved zone definitions were preserved.

The parent final-board assembly must retain these via fabrication attributes when merging routes or importing router sessions.

# Independent routed-board audit

`audit_routed_board.py` loads the frozen `route-pass-3/seed.kicad_pcb` and a routed candidate using KiCad 10's native Python. It never saves either board or project. Native zone filling occurs only in memory. Run it with KiCad's bundled Python, with `--output` pointing into this audit directory.

For final acceptance, use **`--run-drc --require-complete`**. This runs a fresh full native DRC with zone refill and all-track errors, then requires zero errors, zero warnings, zero uncapped native airwires and a single connected ground-pad group. Without `--require-complete`, the helper intentionally permits an incomplete seed while still checking preservation and geometry.

When the approved outer GND pours are included, also pass `--zone-baseline` pointing to the frozen `ground-pour-stage/check3/outer-ground-experiment.kicad_pcb`. This allows exactly those three reviewed additional zone definitions. Every original seed zone must still match, and every approved added zone must match the final candidate; arbitrary added or altered keepouts remain a failure. Keep the copper/footprint seed as `route-pass-3/seed.kicad_pcb`, so legitimate corrections to unprotected autorouter tracks are allowed while all 122 protected objects remain exact.

Checks include:

- Every footprint's complete serialized block and native pad geometry/net assignments, by UUID.
- All 122 protected seed copper objects, including exact native attributes and serialized track/via/arc blocks.
- Every zone's boundary, holes, canonical layers, net, antenna prohibitions, thermal and fill settings. Filled polygons can change to clear new copper; zone definitions cannot.
- Board setup, layer definitions, board drawings, project design settings, severities and exclusions.
- One exact drawing-only replacement from `SD LOGGER - NEW CIRCUIT UNROUTED / FIRMWARE DEFERRED` to `SD LOGGER - ROUTED / FIRMWARE DEFERRED` is allowed only when the independent native connectivity check is complete. Its UUID, layer, location and typography must remain identical; no other drawing change is allowed.
- No route on a non-copper layer and no track narrower than 0.15 mm.
- Canonical route-layer counts, with a separate failure at final acceptance if signal tracks interrupt the In1.Cu ground reference.
- Actual native pad-connectivity partitions for every named net, an explicit ground-pad audit, filled plane areas, and rail track-length distributions by width.
- Seed/candidate/project file bytes and modification times remain unchanged during the audit.

`--self-test` independently changes temporary in-memory objects to prove footprint movement, pad movement, protected-track width changes and keepout-rule changes are detected. The seed-only test passes preservation but correctly reports incomplete connectivity.

`input-power-proposal.json` and `input-power-preflight.kicad_pcb` contain the separate native-DRC-clean vehicle input/TVS plan. It was tested against the frozen seed and still requires a collision check against the final autorouted copper before merging. It does not replace or modify the frozen seed.

`native-netclass-proposal.json` and `class-validation.kicad_pro` demonstrate persistent native routing preferences. Native reloading confirmed Power, RF and USB assignments. These defaults do not enforce current capacity or a per-net minimum width. Native DSN export still emits an overly small global SMD-to-SMD clearance; retain the main routing pipeline's strict DSN correction for future autorouter runs.

KiCad's native netclass format is documented by the [upstream NET_SETTINGS implementation](https://gitlab.com/kicad/code/kicad/-/blob/a53a6395237858bfe3770a27d10d04666f84d4b8/common/project/net_settings.cpp). This audit establishes native CAD geometry and connectivity; hardware, thermal, EMC, stackup and vehicle qualification remain separate.

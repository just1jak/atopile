# R112 / TX_LED routing handoff

Work stopped for the requested transfer to another computer. **Routing is incomplete.** The newest R112 / TX_LED proposal below is an unvalidated draft; no candidate PCB was saved from it. It must not be described as DRC-clean or connected.

All paths below are relative to the repository root, so this handoff survives a different checkout location. Do not use absolute `/private/tmp` paths as the resumed source of truth.

## Frozen input and current evidence

- Draft input: `work/chrysler-routed-sd/mcu-final-escape-stage/input/ChryslerScanner_V240_SD.kicad_pcb`, SHA256 `0902c778c8f56598a5c9c79f36f420d5f87bf48f2c6ba173834abb14c671b795` (2,855,866 bytes). The matching `.kicad_pro` is beside it.
- This is the retained raw copy of the previous RX7-shift snapshot. Its provenance proof was copied to `handoff/frozen-source-rx7-shift-proof.json`. Later sibling RX15/RX7/power restoration work may be newer: integrate geometry-matched changes, never replace a newer board with this complete old snapshot.
- `handoff/r112-txled-draft-recipe.json` records exact coordinates, widths, old copper UUIDs, constraints and unsolved sections.
- `handoff/prototype_direct.INCOMPLETE.py` preserves the exact 3,517-byte interrupted draft. **Do not run it as a complete implementation.** It ends after adding the proposed B.Cu power arch; it lacks both remaining route searches, validation, proof and a save. The original remains in `mcu-final-escape-stage/prototype_direct.py`.
- `mcu-final-escape-stage/{inspect_candidates.py,candidate-blockers.json,inspect_direct_txled.py,direct-txled-blockers.json}` contain actual native collision diagnostics. Their older via positions differ from the refined proposal below; they do not prove that the refined route works.

## Approved narrow exception and latest proposal

Only **R112**, our newly added SD pull-up, may move. Its UUID is `02c8eb1a-24b2-5552-8d67-a69e0ca939ec`, on B.Cu at -90 degrees. Proposed rigid translation: footprint center **(172.000, 121.000) -> (172.000, 121.075) mm**. Pad 1 (+3.3V) becomes (172.000,120.250); pad 2 (MCU_SD_CS) becomes (172.000,121.900). These old values were read natively; the proposed movement has not been validated. Keep all 245 original scanner footprints and the other 17 added footprints unchanged. Parent intended a new strictly reviewed placement seed after successful validation, not a general placement exception.

1. TX_LED: a locked 0.15 mm F.Cu escape from U10.15 (171.9375,118.7275) to a 0.60/0.30 mm via at **(171.9000,119.3750)**. Explicit filled/capped and both-side tenting flags are required because this is close to pad apertures. This refinement intends to leave PCI_TX and PCI_RX unchanged.
2. RX_LED: replace only the two named unlocked F.Cu breakout tracks with the same 0.20 mm path: (171.4375,118.7275) -> (171.3375,119.0675) -> (171.3375,119.6138) -> existing via (171.0591,119.9922). Lock this reviewed replacement after it passes native validation.
3. +3.3V: replace only five named generic B.Cu tracks with a **0.50 mm** arch (170.7787,118.3271) -> (173.9139,118.3271) -> existing via (173.9139,119.5484). Preserve the west and upper rail continuations. This shape still needs a native clearance check.
4. R112 feed: a new locked, filled/capped, tented 0.60/0.30 mm +3.3V via at (171.9000,120.2000), then a **short 0.15 mm F.Cu feed** to C26.1 (170.4500,121.1750). A narrow channel near (171.2545,120.5086) is only a search hint, not accepted geometry. Parent approved a narrow local feed for this 47k pull-up (~70 microamp); all main +3.3V trunks remain 0.50 mm.
5. PWR_LED: reroute only the named unbranched middle chain on In2.Cu at its existing **0.20 mm** width around the new vias. Degree-one endpoints must be exactly (170299901,120195201) and (172279799,122175099) in native nanometres. Retain the outer chain. New route points are not solved.

The longer paired TX_LED / PCI_TX escape alternative is retained in `router-tools/signals-stage/alternate-pin-escape-hints-v2.json` and `handoff/historical-pin-hint-blockers.json`. Prefer testing the simpler R112 exception first. Do not silently rip up protected RF/USB/power copper to make either proposal fit.

## Resume and acceptance

1. Verify `required-inputs.sha256.json` in this directory and choose the latest accepted integrated board with the parent/sibling handoff. Keep the frozen input immutable. Work on a new candidate only.
2. Restore KiCad 10 native Python and CLI. On this Mac the Python was `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9` and CLI `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`. Those executable paths are machine-specific. No extra firmware toolchain is needed.
3. Complete the two unsolved local routes, using source-geometry/UUID guards. The reusable native-shape Grid/A* is in `ground-detour-stage/apply_detours.py`. Its original defaults were conservative; use the actual board minima, and validate all new geometry natively. A route plan or collision scan alone is insufficient.
4. Compare the new board against its true input: all 175 GND pads stay one connected group; no non-target pad partition worsens; all original 122 protected copper items and all nine zone definitions remain unchanged; all pads/nets and all footprints except the explicitly rigid-translated R112 remain exact. The saved candidate must retain explicit via fabrication flags.
5. Put the complete 23-sheet schematic and library context from `work/chrysler-routed-sd/design` beside an **own output copy** before parity checking. Run KiCad `pcb drc --format json --all-track-errors --schematic-parity --severity-all --refill-zones --save-board --output <own-report> <own-board>`. Never save through a frozen symlink or run `--save-board` on the source.
6. Record a geometry-matched delta for the approved changes. Lock the reviewed new pin escapes before fresh core routing so the router cannot undo one escape and cycle missing nets. Parent handles final old edge/stub cleanup and release gates.

Final completion still requires native **zero physical violations, zero schematic parity violations and zero unconnected items** on the actual final board. The earlier inherited edge/stub findings and unfinished logic routes are not waived. DRC also does not establish electrical/thermal/vehicle bench readiness.

## Earlier accepted work and archived diagnostics

The accepted all-ground repair is retained at `ground-final-stage/combined/ChryslerScanner_V240_SD.kicad_pcb` (SHA256 `f5b42ba76001f790c445533dfcd8567136b5b018127ac8982a2b04650661a2d1`), with `apply_ground_repair_delta.py`, `ground-repair-delta.json`, `delta-validation.json` and native proofs in that stage. It had all 175 GND pads in one native group; it was still an intermediate routing snapshot. Guarded delta replay must use matching source geometry, not an arbitrary later board. `ground-final-stage/verify_ground_delta.py` is a historical diagnostic expecting a removed duplicate self-test PCB; the actual guard-test results are in `delta-validation.json`.

`handoff/archived-tmp-diagnostics/` contains the small earlier scripts that otherwise existed only in `/private/tmp` (C23/C26 anchor, failed short GND searches and failed PCI_RX local searches). `archived-tmp-manifest.json` lists original paths and verified copied hashes. They are historical diagnostics, contain old machine-specific paths and are **not** passing final routing recipes.

Three immutable temporary duplicate PCBs were replaced with symlinks to retained raw work copies after SHA256 checks. `work/disk-cleanup-stage/frozen-pcb-duplicates.json` records the targets. Transfer the retained raw repository files, not those external symlink paths. No original Downloads board was modified. No commit, push, firmware build or firmware-cache cleanup was performed by this handoff task.

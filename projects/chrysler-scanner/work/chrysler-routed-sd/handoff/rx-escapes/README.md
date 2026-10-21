# Paused RX pin-escape work

These are native KiCad work copies, not completed routing or fabrication files. The original scanner project was not changed. `SHA256-manifest.json` records exact saved bytes and the original local paths.

| Saved board | Proven state |
| --- | --- |
| `boards/rx7-shift/` | RX7 relocated to (171.025, 138.25) mm; native DRC introduced no physical errors. All 175 GND pads remain one group; the same three signal gaps remain. |
| `boards/paired-rx-escapes/` | Reviewed paired RX7/RX15 escape prototype. Both new signal paths and vias are locked. Native DRC introduced no physical errors, and all 175 GND pads remain one group. Eight airwires remain after displacing generic signal and power branches. |
| `boards/paired-rx-power-restored/` | Same paired escape prototype, with C57 restored using 0.50 mm F.Cu copper. Native connectivity reports seven airwires and all 175 GND pads in one group. A fresh full native DRC has **not** been run after this restoration. |

The matching `.kicad_pro` and available proof/DRC reports accompany each board. For a fresh schematic-parity check, copy the saved board and project settings into a new directory with the complete 23-sheet schematic and local libraries from the project design. Existing reports describe the exact checkpoint they were generated from; the C57-restored board still needs a fresh DRC.

## Next work

1. Preserve the full-ground source (`ground-final-stage/combined`, PCB SHA `f5b42ba76001f790c445533dfcd8567136b5b018127ac8982a2b04650661a2d1`) and these prototypes.
2. Run fresh native KiCad DRC on a disposable copy of the C57-restored board before accepting its restored power path.
3. Restore the remaining R87.1 power branch without narrowing the main 0.50 mm +3.3 V trunks or the restored C57 path. R87 is a 4.7 kΩ SCL pull-up, bounding its branch current to 0.702 mA at 3.3 V. A short 0.20 mm branch is authorized; 0.15 mm is the unchanged native minimum if necessary. This branch has **not** been built or checked.
4. An untested candidate is a 0.20 mm F.Cu neck from R87.1 at (171.5, 139.075) mm to an ordinary 0.60/0.30 mm via near (171.8, 139.7) mm, then a 0.20 mm B.Cu or In2.Cu branch to the connected +3.3 V via at (173.883, 140.1463) mm. Check actual copper and drill clearances; do not infer safety from these coordinates.
5. Restore displaced SDA, SCL, and LOG_BUTTON copper, then complete RX15_EN, TX_LED, and PCI_RX. Preserve all 263 footprints, original 122 protected copper objects, native board rules, ground planes, and all 175 GND connections.

The paired anchors are RX7 via (172.5, 138.0) mm and RX15 via (173.4, 138.425) mm, both 0.60/0.30 mm, ordinary tented through-vias outside pad apertures. Full geometry and exact displaced objects are recorded in `paired-rx-proof.json`. Keep both reviewed signal escapes locked during core rerouting so the router cannot restore the old RX7 choke point.

Any drill overlapping an SMD solder-mask aperture requires native filled-and-capped flags plus recorded fabrication requirements. Keep the existing filled/capped ground and V_BT vias intact. Final acceptance requires native zero physical violations/warnings, zero schematic-parity issues, zero airwires, and exact source net/NC accounting.

## Scripts and environment

`scripts/` contains the exact paused helper sources. They contain historical absolute source/output paths and destination-exists guards; review and reroot them before using another computer. Do not run them against the original scanner or overwrite saved prototypes. `find_pin_escapes.py` currently searches 0.15 mm logic necks; the proposed configurable 0.20 mm width change was not applied.

Verified native environment: KiCad 10.0.7, using its bundled Python 3.9 `pcbnew` module and `kicad-cli`. No router or CAD dependency binaries, credentials, account state, or firmware toolchain are included here. Firmware remains deferred.

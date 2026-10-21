# Continue on another computer

This branch preserves the Atopile Local extension source and the Chrysler
scanner engineering work as of 2026-10-20. **The PCB is not fully routed or ready
for fabrication. Firmware remains deferred.**

```sh
git clone --branch feature/chrysler-sd-checkpoint https://github.com/just1jak/atopile.git
cd atopile
```

Open `projects/chrysler-scanner/current/ChryslerScanner_V240_SD.kicad_pro` in
KiCad 10. Keep the complete folder together; its symbols, footprints, all 23
schematic sheets and 3D models are included. J4, the microSD socket, is on the
underside of the same scanner board. There is no separate board in this design.

For the editor and local agent, follow the runtime setup in `README.md` and the
source recovery notes in `extension-handoff.md`. Runtime environments and
compiler caches must be installed on the new computer. They are not portable
between machines. Sign in to the desired AI provider on that computer; no
credentials or existing login sessions are included in this checkpoint.

## Where to resume

- `projects/chrysler-scanner/README.md`: accepted PCB status, opening and checks.
- `projects/chrysler-scanner/current`: the complete project with the best
  accepted native board, not an experimental pin-escape prototype.
- `projects/chrysler-scanner/work/chrysler-routed-sd`: routing history, exact
  seeds, scripts, reports, offline router and final completion gates.
- `projects/chrysler-scanner/work/chrysler-routed-sd/handoff`: temporary scripts
  and native inputs preserved for the next session, including unvalidated
  R112/TX_LED and paired RX escape ideas.
- `projects/chrysler-scanner/reference/original-source`: the 25 immutable
  original CAD inputs used by the preservation audits.
- `projects/chrysler-scanner/original-atopile`: the original `.ato` circuit,
  part libraries, configuration and project helpers. Read its transfer notes
  before rebuilding; its original layout path belongs to the first Mac.
- `projects/chrysler-scanner/archive/bluetooth-sd-add-on`: superseded carrier
  hardware and firmware drafts. Its firmware does not run the integrated PCB.

The best accepted PCB still has three signal gaps: `RX15_EN`, `TX_LED` and
`PCI_RX`. All 175 GND pads were connected in the native connectivity audit.
Fresh KiCad checks report four edge-clearance errors, seven dangling-copper
warnings, three unconnected items and zero schematic-parity issues. The proposed
small move of added resistor R112 has **not** been validated or applied to the
accepted board. All original scanner placements are preserved.

Finish the signal routes, resolve remaining physical/dangling findings, then
run native KiCad DRC with schematic parity and an independent uncapped
connectivity audit. Completion requires zero violations, zero warnings, zero
unconnected items and zero parity issues without weakening the existing rules.
The final packaging scripts deliberately refuse an incomplete PCB.

Historical reports contain paths from the first Mac. These are provenance,
not usable paths on the new computer. Use the relative project paths above;
review older experimental scripts before running them. Never run
`setup_design.py` over the latest project because it predates metadata fixes.
When the archived routing notes say "repository root" for a `work/...` path,
use `projects/chrysler-scanner` as that root in this combined repository.

Firmware compilation/flashing, manufacturing orders and vehicle testing were
not performed as part of this checkpoint. The requested future logging target
is raw traffic plus selected values for an early-2004 automatic Cummins.

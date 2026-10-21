# Original pre-SD Atopile source archive

This directory preserves the original Chrysler V240 Atopile source and migration helpers. It is **historical source**, not the active integrated SD revision. Open `../current/ChryslerScanner_V240_SD.kicad_pro` to continue the integrated design. Do not run these old generators against that project.

`ato.yaml`, `.ato` files, helper scripts and the original README files are unchanged. The configuration still names the original absolute Downloads PCB path; change that only in a separate legacy working copy before building. The matching original native PCB, project and schematic inputs are preserved separately in `../reference/original-source/`; restore their `elec/layout` and `elec/schematic` trees to that legacy working copy when needed.

`source-archive-manifest.json` records every copied source SHA-256, size, original modification time, exclusions and portability limitations. All copied bytes were rehashed and original size/modification times rechecked. No source scripts, compiler, routing, firmware or packaging processes were run during this archival copy.

The legacy scripts retain machine-specific KiCad/Python paths and may need external KiCad libraries, CADQuery or historical generated reports. Optional upstream datasheets, fit-preview boards and old routing outputs are omitted. No source ZIP is required: the ZIP named by `verify_schematic_bundle.py` is a generated output. Historical READMEs and validation reports apply to the old project and do not establish readiness of the current integrated design.

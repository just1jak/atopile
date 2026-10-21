"""Portable KiCad schematic-only bundle, with local libraries and a PDF.

Unpack the archive and open the project directly in its root directory.
Only model/library path expressions differ from the full project's files.
No user KiCad preferences or authoritative circuit files are modified.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--staging-dir', type=Path, default=Path('/private/tmp/chrysler-kicad-schematic-bundle'))
args = parser.parse_args()
stage = args.staging_dir
stage.mkdir(parents=True, exist_ok=True)
report = json.loads((ROOT/'reference/schematic-validation.json').read_text())
assert report['status'] == 'PASS'
assert report['source_netlist_sha256'] == hashlib.sha256((ROOT/'reference/v240-netlist.json').read_bytes()).hexdigest()
if report.get('pdf_sha256'):
    assert report['pdf_sha256'] == hashlib.sha256((ROOT/'renders/ChryslerScanner_V240_schematic.pdf').read_bytes()).hexdigest()
for path, digest in report['schematic_sha256'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest, path
for p in (ROOT/'elec/schematic').iterdir():
    if p.suffix in ('.kicad_sch', '.kicad_sym', '.kicad_pro') or p.name == 'sym-lib-table':
        shutil.copy2(p, stage/p.name)
(stage/'fp-lib-table').write_text((ROOT/'elec/schematic/fp-lib-table').read_text())
(stage/'footprints.pretty').mkdir(exist_ok=True)
for p in (ROOT/'elec/schematic/footprints.pretty').iterdir():
    if p.is_file():
        if p.suffix == '.kicad_mod':
            data = p.read_text().replace('${KIPRJMOD}/../src/3dmodels/', '${KIPRJMOD}/3dmodels/')
            (stage/'footprints.pretty'/p.name).write_text(data)
        else:
            shutil.copy2(p, stage/'footprints.pretty'/p.name)
shutil.copytree(ROOT/'elec/src/3dmodels', stage/'3dmodels', dirs_exist_ok=True)
for filename in ['LICENSE', 'renders/ChryslerScanner_V240_schematic.pdf']:
    shutil.copy2(ROOT/filename, stage/Path(filename).name)
(stage/'README.txt').write_text('''ChryslerScanner V240 - editable KiCad schematic view

1. Extract the complete ZIP into one folder.
2. Open ChryslerScanner_V240.kicad_pro in KiCad, then open Schematic Editor.
   You can also open ChryslerScanner_V240.kicad_sch directly.
3. Open the functional sheets from the overview or Hierarchy Navigator.

All 22 schematic files must stay together. Symbol, footprint and 3D libraries
are bundled; no online parts service is needed to view the circuit.
Native export and rendering were checked with KiCad 10.0.7.

This view includes USB-C, both independent 5.1 kohm CC pull-downs and the
ATTEND 226A-1202 OBD-II connector. Connectivity matches the current atopile
source: 241 components, 142 connected nets, 746 numbered package terminals,
including 46 NC terminals. R23 and R24 retain their DNP flags.

Circuit changes belong in the authoritative atopile project. Editing this
view alone does not update the PCB or atopile source. The full project is
available separately as ChryslerScanner_V240_atopile.zip.

Electrical correction: U3, U4 and U8 TLV767 DRV pin 5 now connects to GND
in atopile, the PCB and the schematic, per the TI datasheet Table 5-1.
Pin electrical types are passive visualization types; native connectivity
validation is not independent circuit/ERC certification. Native KiCad ERC
reports zero structural violations. Assigned packages and terminal sets are
also compared with the authoritative source. The viewing footprint library
normalizes arc syntax and relative model paths while preserving geometry.

Circuit/source license: GPL-3.0; see LICENSE. Library and manufacturer CAD
licenses are included beside the corresponding assets. ATTEND CAD is not
covered by the circuit's GPL license.
''')
files = sorted(p for p in stage.rglob('*') if p.is_file() and not p.name.endswith(('.kicad_prl', '.lck')) and p.name != '.DS_Store')
target = ROOT/'ChryslerScanner_V240_schematic.zip'
temporary = target.with_suffix('.zip.tmp')
with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, p.relative_to(stage).as_posix())
with zipfile.ZipFile(temporary) as z:
    assert z.testzip() is None
    for p in files:
        assert z.read(p.relative_to(stage).as_posix()) == p.read_bytes()
temporary.replace(target)
print(f'{target.name}: {len(files)} files, {target.stat().st_size/1024/1024:.2f} MiB; verified complete ZIP contents')

"""Prepare the single-board routing work copy without touching earlier revisions."""
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'chrysler-integrated-sd/package'
OUT = HERE / 'design'
OUT.mkdir(exist_ok=True)
for source in BASE.iterdir():
    if source.is_file() and (source.suffix in ('.kicad_sch', '.kicad_sym') or source.name in ('sym-lib-table', 'fp-lib-table', 'LICENSE')):
        (OUT / source.name).write_bytes(source.read_bytes())
for name in ['3dmodels', 'libraries']:
    link = OUT / name
    if not link.exists():
        link.symlink_to(BASE / name, target_is_directory=True)
footprints = OUT / 'footprints.pretty'
if footprints.is_symlink():
    footprints.unlink()
footprints.mkdir(exist_ok=True)
for source in (BASE / 'footprints.pretty').glob('*.kicad_mod'):
    (footprints / source.name).write_bytes(source.read_bytes())
(OUT / 'reference').mkdir(exist_ok=True)
for name in ['integration.json', 'v240-netlist.json', 'native-nc-net-names.json', 'symbol-paths.json']:
    (OUT / 'reference' / name).write_bytes((BASE / 'reference' / name).read_bytes())
print(json.dumps({'destination': str(OUT), 'schematic_pages': len(list(OUT.glob('*.kicad_sch')))}))

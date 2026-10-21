"""Assemble the checked native CAD revision; no original-project writes."""
from pathlib import Path
import hashlib
import json
import re
import shutil

HERE = Path(__file__).resolve().parent
DEST = HERE / 'package'
NAME = 'ChryslerScanner_V240_SD'


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


sch = HERE / 'schematic-stage'
pcb = HERE / 'pcb-stage'
for path in sch.iterdir():
    if path.suffix in ('.kicad_sch', '.kicad_sym') or path.name == 'sym-lib-table':
        copy(path, DEST / path.name)
for path in (sch / 'reference').iterdir():
    if path.is_file():
        copy(path, DEST / 'reference' / path.name)
for suffix in ('.kicad_pcb', '.kicad_pro'):
    copy(pcb / (NAME + suffix), DEST / (NAME + suffix))
for path in pcb.iterdir():
    if path.is_file() and path.suffix == '.json':
        copy(path, DEST / 'reference' / path.name)
for path in (HERE / 'handoff-stage').iterdir():
    if path.is_file():
        copy(path, DEST / 'reference' / path.name)
handoff = DEST / 'reference/integration-handoff.md'
handoff.write_text(handoff.read_text().replace('conservative 10 MHz card clock', 'conservative 4 MHz card clock'))
copy(HERE / 'README-integrated.md', DEST / 'README.md')
for source in [HERE / 'verify_revision.py', HERE / 'verify_preservation_geometry.py',
               pcb / 'build_integrated_pcb.py', pcb / 'check_drc.py',
               *(sch / 'source').glob('*.py')]:
    if source.is_file():
        copy(source, DEST / 'source' / source.name)
pdf = sch / (NAME + '.pdf')
if not pdf.is_file():
    pdf = sch / 'reference' / (NAME + '.pdf')
if pdf.is_file():
    copy(pdf, DEST / pdf.name)

# Every embedded model must resolve inside the bundle. Only pathnames change;
# model origin, rotation, scale and all copper geometry remain untouched.
path = DEST / (NAME + '.kicad_pcb')
data = path.read_text()
data = re.sub(r'\$\{KIPRJMOD\}/(?:\.\./)+(?:src/)?3dmodels/', '${KIPRJMOD}/3dmodels/', data)
data = data.replace('${KICAD10_3DMODEL_DIR}/', '${KIPRJMOD}/3dmodels/standard/')
data = data.replace('${KICAD9_3DMODEL_DIR}/', '${KIPRJMOD}/3dmodels/standard/')
for model in re.findall(r'\(model\s+"([^"]+)"', data):
    resolved = Path(model.replace('${KIPRJMOD}', str(DEST.resolve())))
    if not resolved.is_file():
        raise FileNotFoundError('Missing embedded model: ' + model)
path.write_text(data)

baseline = json.loads((HERE / 'original-source-manifest.json').read_text())
source_root = Path(baseline['source_root'])
preserved = []
for relative, expected in baseline['files'].items():
    source = source_root / relative
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != expected['sha256'] or source.stat().st_mtime_ns != expected['mtime_ns']:
        raise AssertionError('Original source changed: ' + relative)
    preserved.append(relative)
(DEST / 'reference/original-preservation.json').write_text(json.dumps({
    'status': 'PASS', 'all_original_source_files_unchanged_by_hash_and_mtime': True,
    'files_checked': len(preserved), 'files': preserved,
}, indent=2) + '\n')
print(json.dumps({'schematic_sheets': len(list(DEST.glob('*.kicad_sch'))),
                  'all_original_source_files_preserved': len(preserved),
                  'portable_model_references': len(re.findall(r'\(model\s+', data))}))

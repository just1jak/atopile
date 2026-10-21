"""Copy only CAD libraries and their licenses, using bytes without cloud metadata."""
from pathlib import Path
import json
import re

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/justinkobely/Downloads/ChryslerCCDSCIScanner_V140')
DEST = HERE / 'package'
KICAD = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport')


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def fix_models(data):
    return re.sub(r'\$\{KIPRJMOD\}/(?:\.\./)+(?:src/)?3dmodels/', '${KIPRJMOD}/3dmodels/', data)


for source in (BASE / 'elec/schematic/footprints.pretty').glob('*.kicad_mod'):
    write(DEST / 'footprints.pretty' / source.name, fix_models(source.read_text()).encode())
for source in (BASE / 'elec/src/3dmodels').iterdir():
    if source.is_file():
        write(DEST / '3dmodels' / source.name, source.read_bytes())
write(DEST / 'LICENSE', (BASE / 'LICENSE').read_bytes())
write(DEST / 'licenses/KiCad-footprints-LICENSE.md', (BASE / 'reference/upstream/KiCad-footprints-LICENSE.md').read_bytes())

manifest = json.loads((HERE / 'integration.json').read_text())
libraries = {'footprints': '${KIPRJMOD}/footprints.pretty'}
models = []
for part in manifest['parts']:
    lib, name = part['footprint'].split(':', 1)
    if lib == 'footprints':
        continue
    source = KICAD / 'footprints' / (lib + '.pretty') / (name + '.kicad_mod')
    data = source.read_text()
    for model in re.findall(r'\(model\s+"([^"]+)"', data):
        if model.startswith('${KICAD10_3DMODEL_DIR}/'):
            relative = model.split('/', 1)[1]
            model_source = KICAD / '3dmodels' / relative
            if not model_source.is_file():
                raise FileNotFoundError(model_source)
            write(DEST / '3dmodels/standard' / relative, model_source.read_bytes())
            data = data.replace(model, '${KIPRJMOD}/3dmodels/standard/' + relative)
            models.append(relative)
    write(DEST / 'libraries' / (lib + '.pretty') / source.name, data.encode())
    libraries[lib] = '${KIPRJMOD}/libraries/' + lib + '.pretty'
table = '(fp_lib_table (version 7)\n' + ''.join(
    '  (lib (name ' + json.dumps(name) + ') (type "KiCad") (uri ' + json.dumps(path)
    + ') (options "") (descr "Bundled project footprints"))\n'
    for name, path in libraries.items()
) + ')\n'
write(DEST / 'fp-lib-table', table.encode())
write(DEST / 'reference/integration.json', (HERE / 'integration.json').read_bytes())
write(DEST / 'reference/original-source-manifest.json', (HERE / 'original-source-manifest.json').read_bytes())
print(json.dumps({'library_assets': len(list(DEST.rglob('*'))), 'standard_model_references': len(models)}))

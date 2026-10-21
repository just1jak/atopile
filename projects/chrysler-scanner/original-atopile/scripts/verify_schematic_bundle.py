"""Verify an extracted viewing bundle with KiCad's native footprint loader.

Run with KiCad's bundled Python after package_schematic.py and ZIP extraction.
Every assigned package pin set is compared with the atopile source; library
models must resolve locally and match the original model bytes.
"""
from pathlib import Path
import argparse
import hashlib
import json
import pcbnew

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('bundle_dir', type=Path)
parser.add_argument('--output', type=Path, default=ROOT/'reference/schematic-bundle-libraries.json')
args = parser.parse_args()
bundle = args.bundle_dir.resolve()
source = json.loads((ROOT/'reference/v240-netlist.json').read_text())
loaded = {}
models = set()
for path in sorted((bundle/'footprints.pretty').glob('*.kicad_mod')):
    fp = pcbnew.FootprintLoad(str(path.parent), path.stem)
    assert fp, path
    loaded[path.stem] = fp
    for model in fp.Models():
        path = Path(model.m_Filename.replace('${KIPRJMOD}', str(bundle)))
        assert path.is_file(), (fp.GetFPID().GetLibItemName(), str(path))
        assert path.read_bytes() == (ROOT/'elec/src/3dmodels'/path.name).read_bytes(), path
        models.add(path.name)
for ref, part in source['parts'].items():
    fp = loaded[part['footprint']]
    pins = {p.GetNumber() for p in fp.Pads() if p.GetNumber()}
    assert pins == set(part['pins']), (ref, pins, set(part['pins']))
archive = ROOT/'ChryslerScanner_V240_schematic.zip'
report = {'status':'PASS', 'native_kicad_version':pcbnew.GetBuildVersion(),
          'bundle':archive.name, 'bundle_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
          'relocated_native_footprint_libraries_loaded':len(loaded),
          'component_package_pin_sets_checked':len(source['parts']),
          'model_files_resolved_with_relative_paths':len(models),
          'all_bundled_footprint_model_geometry_matches_source':True}
args.output.write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))

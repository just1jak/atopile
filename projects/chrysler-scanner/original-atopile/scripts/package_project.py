"""Package source, editable PCB and reference assets; exclude local build tools."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
validation=json.loads((ROOT/'reference/validation.json').read_text())
assert validation['status']=='PASS', 'Validate the current PCB before packaging'
verification=json.loads((ROOT/'reference/build-verification.json').read_text())
assert verification['pcb_sha256']==hashlib.sha256((ROOT/'elec/layout/v240/v240.kicad_pcb').read_bytes()).hexdigest(), 'Rebuild and refresh the build verification before packaging'
native=json.loads((ROOT/'reference/native-kicad-verification.json').read_text())
assert native['status']=='PASS' and native['pcb_sha256']==verification['pcb_sha256'], 'Verify this board with native KiCad before packaging'
schematic_path=ROOT/'reference/schematic-validation.json'
if schematic_path.exists():
 schematic=json.loads(schematic_path.read_text())
 assert schematic['status']=='PASS','Validate the generated schematic before packaging'
 assert schematic['source_netlist_sha256']==hashlib.sha256((ROOT/'reference/v240-netlist.json').read_bytes()).hexdigest(),'Schematic source netlist changed after verification'
 for path,digest in schematic['schematic_sha256'].items():
  assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,f'Schematic changed after native validation: {path}'
 assert (ROOT/'renders/ChryslerScanner_V240_schematic.pdf').is_file(),'Schematic PDF is missing'
 if schematic.get('pdf_sha256'):
  assert schematic['pdf_sha256']==hashlib.sha256((ROOT/'renders/ChryslerScanner_V240_schematic.pdf').read_bytes()).hexdigest(),'Schematic PDF changed after verification'
hardware=json.loads((ROOT/'reference/hardware-overrides.json').read_text())
if 'J1' in hardware['parts']:
 placement_path=ROOT/'reference/placement-pass-1-verification.json'
 connector_phase='placement-pass-1-verification.json' if placement_path.exists() else 'obd-update-verification.json'
 for filename in [connector_phase,'obd-cad-validation.json']:
  check=json.loads((ROOT/'reference'/filename).read_text())
  assert check['status']=='PASS' and check['pcb_sha256']==verification['pcb_sha256'],f'OBD verification is stale: {filename}'
 if placement_path.exists():
  assert check['status']=='PASS'
  placement=json.loads(placement_path.read_text())
  assert placement['all_package_pad_paste_and_connection_signatures_preserved'] and 'J1' in placement['protected_footprints'],'Placement pass changed the connector or pad geometry'
 selection=json.loads((ROOT/'reference/obd-connector-selection.json').read_text())
 assert selection['current_board_modified'],'Selected OBD connector has not been installed'
 assert native['obd_connector']['native_pin_positions_and_connections_checked']==16,'Native OBD pins were not checked'
provenance=json.loads((ROOT/'reference/provenance.json').read_text())
for path,digest in provenance['sha256'].items():
 assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest, f'Reference changed: {path}'
paths=[ROOT/f for f in ['README.md','README!.txt','LICENSE','ato.yaml','requirements.txt','BOM.csv','migration.csv','.gitignore']]
for folder in ['elec','gerbers','infos','reference','scripts','renders']:
 paths.extend(q for q in (ROOT/folder).rglob('*') if q.is_file() and '__pycache__' not in q.parts and q.name!='.DS_Store' and not q.name.endswith(('.lck','.kicad_prl')))
target=ROOT/'ChryslerScanner_V240_atopile.zip';temporary=target.with_suffix('.zip.tmp')
with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(set(paths)):z.write(p,p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(temporary) as z:
 assert z.testzip() is None,'ZIP integrity check failed'
 assert 'elec/layout/v240/v240.kicad_pcb' in z.namelist()
 manifest=json.loads((ROOT/'reference/3d-models.json').read_text())
 assert all('elec/src/3dmodels/'+fn in z.namelist() for fn in manifest['models']), 'Bundled 3D models are missing from the archive'
 count=len(z.namelist())
temporary.replace(target)
print(f'{target.name}: {count} files, {target.stat().st_size/1024/1024:.2f} MiB; original reference hashes and ZIP integrity verified')

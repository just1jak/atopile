"""Publish a local CAD package after validation, with a verified ZIP copy."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

HERE = Path(__file__).resolve().parent
STAGE = HERE / 'package'
OUT = HERE.parents[1] / 'outputs/chrysler-integrated-sd'
ZIP = OUT.parent / 'chrysler-integrated-sd-engineering-rev-a.zip'

for filename in ['native-pcb-schematic-audit.json', 'geometry-preservation.json', 'original-preservation.json']:
    report = json.loads((STAGE / 'reference' / filename).read_text())
    assert report['status'] == 'PASS', filename
comparison = json.loads((STAGE / 'reference/drc-comparison.json').read_text())
assert not comparison['introducedViolations']
assert not comparison['newPhysicalErrors']

files = sorted(p for p in STAGE.rglob('*') if p.is_file())
assert all(not p.is_symlink() for p in files)
assert not any(p.name.endswith(('.lck', '.kicad_prl')) for p in files)
patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
            rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{40,}',
            rb'AKIA[A-Z0-9]{16}']
findings = []
for path in files:
    data = path.read_bytes()
    for index, pattern in enumerate(patterns):
        if re.search(pattern, data):
            findings.append({'file': str(path.relative_to(STAGE)), 'pattern': index})
assert not findings, findings
scan = {'status': 'PASS', 'files_scanned': len(files), 'credential_pattern_findings': findings,
        'external_upload_performed': False, 'scope': 'This integrated CAD package only; not account or Git history audit'}
(STAGE / 'reference/package-secret-scan.json').write_text(json.dumps(scan, indent=2) + '\n')
files = sorted(p for p in STAGE.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt')
checksums = ''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(STAGE).as_posix() + '\n' for p in files)
(STAGE / 'SHA256SUMS.txt').write_text(checksums)
files = sorted(p for p in STAGE.rglob('*') if p.is_file())
assert not OUT.exists(), 'Output directory already exists; inspect before replacing'
OUT.mkdir(parents=True)
for source in files:
    target = OUT / source.relative_to(STAGE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())

with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED) as archive:
    for source in files:
        archive.writestr('ChryslerScanner_V240_SD/' + source.relative_to(STAGE).as_posix(), source.read_bytes())
with zipfile.ZipFile(ZIP) as archive:
    assert archive.testzip() is None
    for source in files:
        relative = source.relative_to(STAGE)
        want = source.read_bytes()
        assert archive.read('ChryslerScanner_V240_SD/' + relative.as_posix()) == want
        assert (OUT / relative).read_bytes() == want
report = {'project': str(OUT), 'archive': str(ZIP), 'files': len(files), 'zip_bytes': ZIP.stat().st_size,
          'zip_sha256': hashlib.sha256(ZIP.read_bytes()).hexdigest(), 'contents_verified': True}
print(json.dumps(report, indent=2))

"""Create a portable local delivery only after the native CAD checks pass."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
DESIGN = HERE / 'design'
OUT = HERE.parents[1] / 'outputs/chrysler-routed-sd'
ARCHIVE = OUT.parent / 'chrysler-integrated-sd-routed-rev-b.zip'
NAME = 'ChryslerScanner_V240_SD'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    drc = json.loads((DESIGN / 'reference/final-drc.json').read_text())
    assert not drc['violations'], 'Native DRC is not clean'
    assert not drc['unconnected_items'], 'Unrouted connections remain'
    assert not drc['schematic_parity'], 'Schematic and PCB disagree'
    circuit = json.loads((DESIGN / 'reference/native-circuit-audit.json').read_text())
    assert circuit['status'] == 'PASS', 'Circuit audit failed'
    assert circuit['routing_complete'] is True, 'Circuit audit has not verified complete routing'
    routing = json.loads((DESIGN / 'reference/final-routing-audit.json').read_text())
    assert routing['auditPassed'] is True and routing['completeConnectivityPassed'] is True, 'Routing preservation audit failed'
    assert routing['groundReferenceLayerUnbrokenBySignalTracks'] is True
    assert routing['candidateSha256'] == circuit['pcbSha256'] == sha(DESIGN / (NAME + '.kicad_pcb')), 'Reports refer to another PCB'
    erc = json.loads((DESIGN / 'reference/final-erc.json').read_text())
    # KiCad versions use either a flat violations list or per-sheet violations.
    erc_items = erc.get('violations', []) + [v for s in erc.get('sheets', []) for v in s.get('violations', [])]
    assert not erc_items, 'Schematic ERC is not clean'
    assert not OUT.exists(), 'Inspect the existing delivery before replacing it'
    assert not ARCHIVE.exists(), 'Inspect the existing archive before replacing it'
    (DESIGN / 'README.md').write_text('''# ChryslerScanner V240 with integrated SD hardware — routed revision

Open `ChryslerScanner_V240_SD.kicad_pro` in KiCad 10, then open its PCB or schematic.
Keep the complete folder together: all 23 schematic sheets, footprints, symbols
and 3D models are bundled. The microSD socket J4 is on the underside near the
bottom edge. Flip the board in the 3D viewer to see it.

The single main board is 110 × 55 mm, four layers, 1.6 mm thick. It uses the
existing ESP32-PICO-V3-02 directly for SD storage; no separate Bluetooth carrier
or second microcontroller is required. The 18 added SD components, LOG button,
card-detect circuit and regulator remain on this main PCB. Provide a card-access
opening and at least 7 mm underside clearance. Check the intended enclosure
against the actual connector and capacitor dimensions before manufacturing.

## CAD validation

The final native KiCad DRC reports zero violations, zero unconnected items and
zero schematic-parity issues. Native connectivity is checked independently,
including every ground pad. The schematic has 259 electrical components and
154 connected nets; all 40 declared no-connect terminals remain isolated.
The PCB has 263 footprints including the four mechanical holes. Reports and
file checksums are under `reference` and `SHA256SUMS.txt`.

The original scanner placements and outline are preserved. CP2102 and USB-C
land-pattern corrections, protected RF/USB/power routing, ground stitching and
antenna clearances are recorded in the verification reports. Existing DRC
minimums and exclusions were not relaxed to achieve the result. Existing
disabled checks remain documented by the native reports.

Unused outer-layer copper provides ground fills; surface-mount ground pads use
solid connections and through-hole pads use thermal reliefs. Assembly must use
an appropriate reflow profile. See the grounding report for any exposed-pad
via-in-pad locations that require filled and copper-capped/planarized vias;
ordinary open drilled vias are not an equivalent assembly process.

`previews` contains native KiCad routing plots and any available 3D renders.
`fabrication` contains the native Gerber and drill exports of this checked CAD
revision. The schematic PDF and BOM are beside the project. These are local
review artifacts; no manufacturing order or external upload has been made.

## Firmware and prototype work

Firmware remains deferred at the user's request. Fitting the SD circuitry does
not make the existing scanner firmware log data. Raw traffic plus selected
values for the early-2004 automatic Cummins remain the intended firmware target;
decoder compatibility and vehicle behavior have not been demonstrated.

KiCad checks establish geometry and connectivity, not physical operation.
Prototype power, SD write-current peaks, USB supply capacity, regulator
temperature, enclosure fit and signal integrity still need hardware validation.
The shared upstream supply was not enlarged. There is no RTC, battery, power-fail
supervisor or shutdown hold-up, so a clean file close after sudden power removal
is not guaranteed. The RF/USB geometry still needs the chosen fabricator's
stackup/impedance review. The recovered base schematic uses passive pin types;
zero ERC is not an independent active-device electrical-design review.

The original Downloads project and Atopile sources are unchanged. Rebuilding
the original Atopile project will not regenerate this native KiCad revision.
Make future edits in this project deliberately and rerun native DRC and parity.

## Licensing and provenance

Derived from the user's V240-USB-C-OBD reconstruction and
https://github.com/laszlodaniel/ChryslerScanner. Circuit licensing is GPL-3.0;
see `LICENSE`. Bundled library and manufacturer assets retain their respective
licenses in `licenses` and `3dmodels`. Circuit and source references are under
`reference/integration.json` and `reference/architecture-review.json`.
''')
    # Dereference the bundled models and standard footprint libraries so the
    # archive does not depend on another working directory on this computer.
    shutil.copytree(DESIGN, OUT, symlinks=False,
                    ignore=shutil.ignore_patterns('*.lck', '*.kicad_prl', '*-backups', '.DS_Store'))
    files = sorted(p for p in OUT.rglob('*') if p.is_file())
    assert all(not p.is_symlink() for p in OUT.rglob('*'))
    patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
                rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{40,}',
                rb'AKIA[A-Z0-9]{16}']
    findings = []
    for path in files:
        data = path.read_bytes()
        for i, pattern in enumerate(patterns):
            if re.search(pattern, data):
                findings.append({'file': str(path.relative_to(OUT)), 'pattern': i})
    assert not findings, 'Credential-like content found; do not archive'
    (OUT / 'reference/package-secret-scan.json').write_text(json.dumps({
        'status': 'PASS', 'files_scanned': len(files), 'credential_pattern_findings': findings,
        'external_upload_performed': False, 'scope': 'This CAD package only'}, indent=2) + '\n')
    files = sorted(p for p in OUT.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt')
    (OUT / 'SHA256SUMS.txt').write_text(''.join(sha(p) + '  ' + p.relative_to(OUT).as_posix() + '\n' for p in files))
    files = sorted(p for p in OUT.rglob('*') if p.is_file())
    with zipfile.ZipFile(ARCHIVE, 'x', zipfile.ZIP_DEFLATED) as z:
        for path in files:
            z.write(path, NAME + '/' + path.relative_to(OUT).as_posix())
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        for path in files:
            assert z.read(NAME + '/' + path.relative_to(OUT).as_posix()) == path.read_bytes()
    print(json.dumps({'project': str(OUT), 'archive': str(ARCHIVE), 'files': len(files),
                      'zip_bytes': ARCHIVE.stat().st_size, 'zip_sha256': sha(ARCHIVE),
                      'pcb_sha256': sha(OUT / (NAME + '.kicad_pcb')),
                      'contents_verified': True}, indent=2))


if __name__ == '__main__':
    main()

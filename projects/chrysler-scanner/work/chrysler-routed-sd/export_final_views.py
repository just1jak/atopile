"""Export KiCad's native manufacturing plots and views after a clean DRC."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import subprocess
import time

HERE = Path(__file__).resolve().parent
DESIGN = HERE / 'design'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
NAME = 'ChryslerScanner_V240_SD'
BOARD = DESIGN / (NAME + '.kicad_pcb')


def main():
    drc = json.loads((DESIGN / 'reference/final-drc.json').read_text())
    assert not any(drc[k] for k in ('violations', 'unconnected_items', 'schematic_parity'))
    before = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    (DESIGN / 'previews').mkdir(exist_ok=True)
    (DESIGN / 'fabrication').mkdir(exist_ok=True)
    tasks = {
        'gerbers': ['pcb', 'export', 'gerbers', '--layers', 'F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.SilkS,B.SilkS,Edge.Cuts',
                    '--subtract-soldermask', '--output', 'fabrication/', str(BOARD)],
        'drills': ['pcb', 'export', 'drill', '--format', 'excellon', '--excellon-separate-th',
                   '--generate-map', '--map-format', 'pdf', '--generate-report',
                   '--report-path', 'fabrication/drill-report.txt', '--output', 'fabrication/', str(BOARD)],
        'top-copper': ['pcb', 'export', 'svg', '--layers', 'F.Cu,F.SilkS,Edge.Cuts',
                       '--mode-single', '--fit-page-to-board', '--exclude-drawing-sheet',
                       '--output', 'previews/routing-top.svg', str(BOARD)],
        'bottom-copper': ['pcb', 'export', 'svg', '--layers', 'B.Cu,B.SilkS,Edge.Cuts',
                          '--mirror', '--mode-single', '--fit-page-to-board', '--exclude-drawing-sheet',
                          '--output', 'previews/routing-bottom.svg', str(BOARD)],
    }
    results = []

    def run(item):
        label, args = item
        start = time.monotonic()
        proc = subprocess.run([CLI, *args], cwd=DESIGN, capture_output=True, text=True, timeout=120)
        (DESIGN / 'reference' / ('export-' + label + '.log')).write_text(proc.stdout + proc.stderr)
        return {'export': label, 'returncode': proc.returncode, 'seconds': round(time.monotonic() - start, 2),
                'command': [CLI, *args]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(run, tasks.items()):
            results.append(result)
            assert result['returncode'] == 0, result
    # Render sequentially to limit graphics memory on a nearly full machine.
    for side in ('top', 'bottom'):
        result = run(('3d-' + side, ['pcb', 'render', '--width', '1400', '--height', '900',
                      '--side', side, '--background', 'opaque', '--quality', 'basic',
                      '--output', 'previews/board-' + side + '.png', str(BOARD)]))
        results.append(result)
        # Routing plots remain available if graphics services are unavailable.
    assert hashlib.sha256(BOARD.read_bytes()).hexdigest() == before, 'Export changed the checked board'
    report = {'pcb_sha256': before, 'exports': results,
              'native_plot_exports_passed': all(r['returncode'] == 0 for r in results if not r['export'].startswith('3d-')),
              'native_3d_renders_passed': all(r['returncode'] == 0 for r in results if r['export'].startswith('3d-'))}
    (DESIGN / 'reference/native-exports.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

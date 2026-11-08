"""Package validated Rev D assembly quote inputs without changing Gerbers.

Run with KiCad Python, passing the same fresh export paths as verify.py.
The original hardened bench fabrication ZIP must remain byte-identical.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from verify import HERE, PROJECT, sha, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('netlist', 'erc', 'drc', 'positions', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Choose a new output path'
    result = verify(args.netlist, args.erc, args.drc, args.positions)
    saved = json.loads((HERE / 'checks.json').read_text())
    assert saved == result, 'Refresh checks.json from these exports first'
    original = PROJECT / 'outputs/ChryslerScanner-RevD-hardened-bench-fabrication.zip'
    assert sha(original) == 'c1663b4b48c9ed3a417d6e2abbae966029568083a504ff6e5e4dc472fdc33b68'
    files = {}
    with ZipFile(original) as source:
        assert source.testzip() is None
        for name in source.namelist():
            files[name] = source.read(name)
    for name in ['README.md', 'BOM.csv', 'JLC-BOM.csv', 'JLC-CPL.csv', 'selections.json', 'checks.json', 'quote-status.md', 'verify.py', 'package.py']:
        files['assembly/' + name] = (HERE / name).read_bytes()
    for path in (args.netlist, args.erc, args.drc, args.positions):
        files['evidence/' + path.name] = path.read_bytes()
    files['README-ASSEMBLY-QUOTE.md'] = (
        '# Rev D assembly quote inputs\n\n'
        'Bench prototype only. Use the assembly BOM/CPL together with the included unchanged Rev D Gerbers.\n'
        'See assembly/README.md for the Omron compatibility decision, assembly exclusions and qualifications.\n'
        'See assembly/quote-status.md for current quote limitations. No order or stock reservation is included.\n'
        'PCB: 110 x 96 mm, four layers, 1.6 mm, both-side assembly; 254 mandatory filled/capped/planarized sites.\n'
        'JLC adds temporary assembly rails. Review actual stackup, process and part placement before ordering.\n'
        'The original manufacturing notes and historical KiCad reports remain unchanged; fresh reports are in evidence/.\n'
    ).encode()
    files['ASSEMBLY-SHA256SUMS.txt'] = ''.join(
        hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in sorted(files.items())
    ).encode()
    with ZipFile(args.output, 'x', ZIP_DEFLATED) as target:
        for name, data in sorted(files.items()):
            target.writestr(name, data)
    with ZipFile(args.output) as target:
        assert target.testzip() is None
        assert set(target.namelist()) == files.keys()
        assert all(target.read(name) == data for name, data in files.items())
        with ZipFile(original) as source:
            assert all(source.read(name) == target.read(name) for name in source.namelist())
    args.output.with_suffix('.zip.sha256').write_text(sha(args.output) + '  ' + args.output.name + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(output=str(args.output), sha256=sha(args.output), files=len(files), unchangedOriginalGerbers=True)))


if __name__ == '__main__':
    main()

"""Replace rounded DSN wiring with the board's exact native coordinates.

KiCad's native DSN wiring export rounds points to integer micrometres, while
placement/pad centres retain fractional micrometres. A routing engine requiring
exact endpoint contacts can then report hundreds of artificial missing joins.
This helper exports existing copper only; it never edits the PCB or any other
DSN scope. Apply reviewed rule/layer/metadata configuration separately.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import sys
import pcbnew as p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('dsn', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists() and args.output.resolve() != args.dsn.resolve()
    raw, stamp = args.board.read_bytes(), args.board.stat().st_mtime_ns
    spec = importlib.util.spec_from_file_location('specctra', Path(__file__).parent / 'router-tools/specctra_tools.py')
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    board = p.LoadBoard(str(args.board.resolve()))
    text = args.dsn.read_text()
    root = m.parse(text)
    assert m.atom(m.one(root, 'unit')) == 'um'
    wiring = m.one(root, 'wiring')
    via_id = m.atom(m.one(m.one(root, 'structure'), 'via'))
    assert via_id == 'Via[0-3]_600:300_um'

    def unit(value):
        # Integer nm -> exact fractional um, without scientific notation.
        return f'{value / 1000:.3f}'.rstrip('0').rstrip('.') if value else '0'

    def point(q):
        return unit(q.x) + ' ' + unit(-q.y)

    lines, segments, vias = ['(wiring'], 0, 0
    for obj in board.GetTracks():
        net = m.quoted(obj.GetNetname())
        fixed = 'fix' if obj.IsLocked() else 'route'
        if obj.GetClass() == 'PCB_VIA':
            assert obj.GetWidth(p.F_Cu) == p.FromMM(.6) and obj.GetDrillValue() == p.FromMM(.3)
            assert obj.TopLayer() == p.F_Cu and obj.BottomLayer() == p.B_Cu
            lines.append('    (via ' + m.quoted(via_id) + ' ' + point(obj.GetPosition()) +
                ' (net ' + net + ')(type ' + fixed + '))')
            vias += 1
        else:
            assert obj.GetClass() == 'PCB_TRACK', 'Arcs require a separate exact exporter'
            lines.append('    (wire (path ' + m.quoted(board.GetLayerName(obj.GetLayer())) +
                ' ' + unit(obj.GetWidth()) + ' ' + point(obj.GetStart()) + ' ' + point(obj.GetEnd()) +
                ')(net ' + net + ')(type ' + fixed + '))')
            segments += 1
    lines.append('  )')
    result = m.patch(text, [(wiring.start, wiring.end, '\n'.join(lines))])
    after = m.parse(result)
    for head in ('structure', 'placement', 'library', 'network'):
        before_scope, after_scope = m.one(root, head), m.one(after, head)
        assert text[before_scope.start:before_scope.end] == result[after_scope.start:after_scope.end]
    assert len(m.one(after, 'wiring').children('wire')) == segments
    assert len(m.one(after, 'wiring').children('via')) == vias
    assert args.board.read_bytes() == raw and args.board.stat().st_mtime_ns == stamp
    args.output.write_text(result)
    report = dict(nativeBoardSha256=hashlib.sha256(raw).hexdigest(),
        inputDsnSha256=hashlib.sha256(args.dsn.read_bytes()).hexdigest(),
        outputDsnSha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        nativeSegments=segments, nativeVias=vias, coordinatePrecision='nm expressed as fractional um',
        structurePlacementLibraryNetworkUnchanged=True, sourceBytesAndMtimeUnchanged=True,
        requiresRouterAndNativeVerification=True)
    args.proof.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

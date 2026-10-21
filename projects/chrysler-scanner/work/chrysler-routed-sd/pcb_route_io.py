"""Native KiCad DSN/SES bridge with exact placement and net preservation gates.

Run with KiCad 10's bundled Python. Work-copy paths only.
"""
from pathlib import Path
import argparse
import hashlib
import json
import pcbnew as p

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=['export', 'import', 'audit'])
parser.add_argument('board', type=Path)
parser.add_argument('--dsn', type=Path)
parser.add_argument('--session', type=Path)
parser.add_argument('--output', type=Path)
parser.add_argument('--report', type=Path)
args = parser.parse_args()
if args.output:
    assert args.output.resolve() != args.board.resolve(), 'Output must be a new work copy'


def snap(board):
    result = {}
    for fp in board.GetFootprints():
        pads = {}
        for pad in fp.Pads():
            pads[pad.m_Uuid.AsString()] = {
                'number': pad.GetNumber(), 'xy': [pad.GetPosition().x, pad.GetPosition().y],
                'size': [pad.GetSize().x, pad.GetSize().y],
                'drill': [pad.GetDrillSize().x, pad.GetDrillSize().y],
                'angle': pad.GetOrientationDegrees(), 'shape': int(pad.GetShape()),
                'layers': pad.GetLayerSet().FmtHex(), 'net': pad.GetNetname(),
            }
        result[fp.GetReference()] = {
            'uuid': fp.m_Uuid.AsString(), 'xy': [fp.GetPosition().x, fp.GetPosition().y],
            'angle': fp.GetOrientationDegrees(), 'layer': int(fp.GetLayer()),
            'fpid': str(fp.GetFPID().GetLibNickname()) + ':' + str(fp.GetFPID().GetLibItemName()),
            'value': fp.GetValue(), 'pads': pads,
        }
    return result


def stats(board):
    board.BuildConnectivity()
    tracks = list(board.GetTracks())
    return {
        'footprints': len(list(board.GetFootprints())),
        'track_segments': sum(not isinstance(x, p.PCB_VIA) for x in tracks),
        'vias': sum(isinstance(x, p.PCB_VIA) for x in tracks),
        'zones': len(list(board.Zones())),
        'airwires_before_zone_refill': board.GetConnectivity().GetUnconnectedCount(False),
        'thin_tracks': [x.m_Uuid.AsString() for x in tracks if not isinstance(x, p.PCB_VIA) and x.GetWidth() < p.FromMM(.15)],
        'non_copper_route_layers': sorted({int(x.GetLayer()) for x in tracks if not isinstance(x, p.PCB_VIA)} - {p.F_Cu, p.In1_Cu, p.In2_Cu, p.B_Cu}),
    }


def copper_snap(track):
    if isinstance(track, p.PCB_VIA):
        q = track.GetPosition()
        return ('via', track.GetNetname(), q.x, q.y, track.GetWidth(p.F_Cu), track.GetDrillValue(),
                track.TopLayer(), track.BottomLayer(), bool(track.IsLocked()))
    a, b = track.GetStart(), track.GetEnd()
    return (type(track).__name__, track.GetNetname(), int(track.GetLayer()), track.GetWidth(),
            a.x, a.y, b.x, b.y, bool(track.IsLocked()))


raw = args.board.read_bytes()
board = p.LoadBoard(str(args.board.resolve()))
before = snap(board)
result = {'input': str(args.board), 'input_sha256': hashlib.sha256(raw).hexdigest(), 'before': stats(board)}
assert len(before) == 263, 'Wrong input board'
if args.mode == 'export':
    assert args.dsn and args.output
    # Existing traces are reviewed critical routes and may not be moved by the
    # generic router. This also preserves them through native SES import.
    for track in board.GetTracks():
        track.SetLocked(True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    p.SaveBoard(str(args.output.resolve()), board)
    assert p.ExportSpecctraDSN(board, str(args.dsn.resolve()))
    assert snap(board) == before
    result.update({'seed_board': str(args.output), 'dsn': str(args.dsn),
                   'seed_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                   'dsn_sha256': hashlib.sha256(args.dsn.read_bytes()).hexdigest()})
elif args.mode == 'import':
    assert args.session and args.output
    protected = {x.m_Uuid.AsString(): copper_snap(x) for x in board.GetTracks() if x.IsLocked()}
    assert p.ImportSpecctraSES(board, str(args.session.resolve())), 'Native session import failed'
    assert snap(board) == before, 'Session changed a component, pad or net assignment'
    imported = {x.m_Uuid.AsString(): copper_snap(x) for x in board.GetTracks()}
    assert all(imported.get(uid) == shape for uid, shape in protected.items()), 'Session changed protected copper'
    # A retained protected segment can also be present in the session. Remove
    # only exact duplicate copper, preferring the original protected object.
    seen = {}
    removed = []
    ordered = sorted(board.GetTracks(), key=lambda x: (x.m_Uuid.AsString() not in protected, not x.IsLocked()))
    for track in ordered:
        assert not isinstance(track, p.PCB_ARC), 'Arc import requires a separate geometry-aware audit'
        if isinstance(track, p.PCB_VIA):
            point = track.GetPosition()
            key = ('via', track.GetNetname(), point.x, point.y, track.GetWidth(p.F_Cu),
                   track.GetDrillValue(), track.TopLayer(), track.BottomLayer())
        else:
            a, b = track.GetStart(), track.GetEnd()
            key = ('track', track.GetNetname(), int(track.GetLayer()), track.GetWidth(),
                   tuple(sorted(((a.x, a.y), (b.x, b.y)))))
        if key in seen:
            assert track.m_Uuid.AsString() not in protected, 'Refusing to delete original protected copper'
            removed.append(track.m_Uuid.AsString())
            board.Remove(track)
        else:
            seen[key] = track
    after = stats(board)
    assert not after['thin_tracks'], 'Router introduced tracks below native minimum width'
    assert not after['non_copper_route_layers'], 'Router introduced an invalid copper layer'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    p.SaveBoard(str(args.output.resolve()), board)
    saved = p.LoadBoard(str(args.output.resolve()))
    assert snap(saved) == before
    saved_copper = {x.m_Uuid.AsString(): copper_snap(x) for x in saved.GetTracks()}
    assert all(saved_copper.get(uid) == shape for uid, shape in protected.items())
    result.update({'session_sha256': hashlib.sha256(args.session.read_bytes()).hexdigest(),
                   'output': str(args.output), 'output_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                   'component_pad_and_net_assignments_preserved': True,
                   'original_protected_copper_preserved': len(protected),
                   'exact_duplicate_copper_removed': len(removed), 'after': after})
else:
    result['after'] = stats(board)
if args.report:
    args.report.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))

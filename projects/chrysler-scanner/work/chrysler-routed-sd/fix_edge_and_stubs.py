"""Repair a checked edge detour and remove proven redundant SES stubs."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import pcbnew as p

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('board', type=Path)
parser.add_argument('drc', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
assert args.board.resolve() != args.output.resolve()
assert not args.output.exists(), 'Output must be a new board'
board = p.LoadBoard(str(args.board.resolve()))
drc = json.loads(args.drc.read_text())
assert drc.get('source') == args.board.name, 'DRC names another source board'
tracks = {x.m_Uuid.AsString(): x for x in board.GetTracks()}
spec = importlib.util.spec_from_file_location('routing_audit', Path(__file__).parent / 'audit-stage/audit_routed_board.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def net_pad_groups():
    # Counts alone do not prove connectivity, so native DRC is rerun separately.
    board.BuildConnectivity()
    return board.GetConnectivity().GetUnconnectedCount(False)

before_connections = audit.connectivity(board)
before_airwires = net_pad_groups()
assert before_airwires == 0 and not before_connections['disconnectedNetGroups'], \
    'Final cleanup requires completely connected nets first'
mapping = {
    (p.FromMM(209.4829), p.FromMM(113.85)): (p.FromMM(209.35), p.FromMM(113.85)),
    (p.FromMM(209.4829), p.FromMM(115.1444)): (p.FromMM(209.35), p.FromMM(115.2773)),
}
moved = []
for obj in board.GetTracks():
    if obj.GetNetname() != '+3.3V':
        continue
    changed = False
    if isinstance(obj, p.PCB_VIA):
        q = obj.GetPosition()
        if (q.x, q.y) in mapping:
            assert not obj.IsLocked(), 'Refusing to move protected copper'
            obj.SetPosition(p.VECTOR2I(*mapping[(q.x, q.y)]))
            changed = True
    else:
        for get, set_ in ((obj.GetStart, obj.SetStart), (obj.GetEnd, obj.SetEnd)):
            q = get()
            if (q.x, q.y) in mapping:
                assert not obj.IsLocked(), 'Refusing to move protected copper'
                set_(p.VECTOR2I(*mapping[(q.x, q.y)]))
                changed = True
    if changed:
        moved.append(obj.m_Uuid.AsString())
assert len(moved) == 4, ('Unexpected edge-detour objects', moved)

removed = []
allowed_nets = {'VPP', 'N_C17_2', 'N_C5_2', 'TX_LED'}
for issue in drc['violations']:
    if issue['type'] not in ('track_dangling', 'via_dangling'):
        continue
    assert len(issue['items']) == 1
    uid = issue['items'][0]['uuid']
    obj = tracks[uid]
    assert not obj.IsLocked() and obj.GetNetname() in allowed_nets
    board.Remove(obj)
    removed.append(uid)
assert 3 <= len(removed) <= 4, ('Unexpected dangling copper', removed)
after_connections = audit.connectivity(board)
assert after_connections['disconnectedNetGroups'] == before_connections['disconnectedNetGroups'], 'Repair changed a net pad-connectivity partition'
assert net_pad_groups() == before_airwires, 'Repair changed native connectivity count'
args.output.parent.mkdir(parents=True, exist_ok=True)
p.SaveBoard(str(args.output.resolve()), board)
print(json.dumps({'input_sha256': hashlib.sha256(args.board.read_bytes()).hexdigest(),
                  'output_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                  'edge_copper_objects_moved': moved, 'redundant_stubs_removed': removed,
                  'uncapped_airwire_count_unchanged': before_airwires,
                  'all_net_pad_connectivity_partitions_unchanged': True,
                  'requires_fresh_native_drc': True}, indent=2))

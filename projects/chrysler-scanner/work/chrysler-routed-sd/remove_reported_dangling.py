"""Prune native-reported dangling copper from a new board copy only.

Every pad-connectivity partition and the uncapped native airwire count must
remain identical. Rerun native DRC after each pass: a redundant branch can
contain several segments. This helper does not suppress any rule or warning.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import pcbnew as p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('drc', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    assert args.board.resolve() != args.output.resolve() and not args.output.exists()
    raw = args.board.read_bytes()
    stamp = args.board.stat().st_mtime_ns
    d = json.loads(args.drc.read_text())
    assert d.get('source') == args.board.name
    issues = d['violations']
    assert issues and all(v['type'] in ('track_dangling', 'via_dangling') for v in issues)
    spec = importlib.util.spec_from_file_location('audit', Path(__file__).parent / 'audit-stage/audit_routed_board.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    b = p.LoadBoard(str(args.board.resolve()))
    before = audit.connectivity(b)
    assert before['fullNativeAirwires'] == 0 and not before['disconnectedNetGroups'], \
        'Finish actual routing first; a dangling partial route can still be useful while nets are open'
    copper = {audit.uid(t): audit.copper(t) for t in b.GetTracks()}
    tracks = {audit.uid(t): t for t in b.GetTracks()}
    removed = []
    for issue in issues:
        assert len(issue['items']) == 1
        key = issue['items'][0]['uuid']
        assert key not in removed
        obj = tracks[key]
        assert not obj.IsLocked(), 'Refusing protected copper removal'
        b.Remove(obj)
        removed.append(key)
    after = audit.connectivity(b)
    for key in ('disconnectedNetGroups', 'fullNativeAirwires', 'ground'):
        assert before[key] == after[key], ('Connectivity changed', key)
    current = {audit.uid(t): audit.copper(t) for t in b.GetTracks()}
    assert current == {k: v for k, v in copper.items() if k not in removed}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    p.SaveBoard(str(args.output.resolve()), b)
    assert audit.blocks(raw, 'footprint') == audit.blocks(args.output.read_bytes(), 'footprint')
    assert args.board.read_bytes() == raw and args.board.stat().st_mtime_ns == stamp
    report = dict(source=str(args.board), output=str(args.output),
        sourceSha256=hashlib.sha256(raw).hexdigest(),
        outputSha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        removedCopper={k: copper[k] for k in removed},
        everyNativePadPartitionUnchanged=True, fullNativeAirwires=after['fullNativeAirwires'],
        allUnrelatedCopperUnchanged=True, footprintBlocksUnchanged=True,
        sourceBytesAndMtimeUnchanged=True, requiresFreshNativeDrc=True)
    args.proof.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(removed=len(removed), fullNativeAirwires=after['fullNativeAirwires'])))


if __name__ == '__main__':
    main()

"""Read-only preservation audit of a routed native board against its exact seed.

Run with a Python containing sexpdata. Does not call a writer, refill a zone,
change a board, or invoke a router. Native KiCad DRC remains a separate gate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import sexpdata


def key(value):
    return str(value[0]) if isinstance(value, list) and value else ''


def first(value, name):
    return next((v for v in value if key(v) == name), None)


def identity(value):
    item = first(value, 'uuid')
    if item is None:
        raise ValueError(f'Native {key(value)} lacks UUID')
    return str(item[1])


def footprints(board):
    result = {}
    for fp in board:
        if key(fp) != 'footprint':
            continue
        ref = next(v[2] for v in fp if key(v) == 'property' and v[1] == 'Reference')
        if ref in result:
            raise ValueError(f'Duplicate reference {ref}')
        result[ref] = fp
    return result


def physical_pads(fps):
    result = {}
    for ref, fp in fps.items():
        for pad in fp:
            if key(pad) == 'pad':
                pad_id = identity(pad)
                if pad_id in result:
                    raise ValueError('Duplicate physical pad UUID')
                net = first(pad, 'net')
                result[pad_id] = {'reference': ref, 'number': str(pad[1]),
                                  'net': str(net[-1]) if net is not None else '', 'node': pad}
    return result


def copper(board):
    return {identity(n): n for n in board if key(n) in ('segment', 'arc', 'via')}


def audit(seed_path, candidate_path, expected_path=None, drc_path=None):
    seed_bytes, candidate_bytes = seed_path.read_bytes(), candidate_path.read_bytes()
    seed, candidate = map(sexpdata.loads, [seed_bytes.decode(), candidate_bytes.decode()])
    if key(seed) != 'kicad_pcb' or key(candidate) != 'kicad_pcb':
        raise ValueError('Expected native kicad_pcb roots')
    source_fps, target_fps = footprints(seed), footprints(candidate)
    source_pads, target_pads = physical_pads(source_fps), physical_pads(target_fps)
    source_copper, target_copper = copper(seed), copper(candidate)
    locked = {uid: node for uid, node in source_copper.items()
              if first(node, 'locked') is not None and str(first(node, 'locked')[1]) == 'yes'}
    errors = []
    if set(source_fps) != set(target_fps):
        errors.append({'footprint_set_changed': True})
    changed_fps = sorted(ref for ref, fp in source_fps.items() if target_fps.get(ref) != fp)
    if changed_fps:
        errors.append({'footprints_changed': changed_fps})
    # Full footprint subtree equality includes UUID/XY/rotation/side and every
    # pad polygon, offset, layer, dimension, drill, net, and text/model property.
    changed_pads = [uid for uid, pad in source_pads.items() if target_pads.get(uid) != pad]
    if set(source_pads) != set(target_pads) or changed_pads:
        errors.append({'physical_pad_set_or_fields_changed': changed_pads})
    changed_locked = [uid for uid, node in locked.items() if target_copper.get(uid) != node]
    if changed_locked:
        errors.append({'locked_critical_copper_changed_or_missing': changed_locked})

    circuit_errors = []
    if expected_path is not None:
        expected = json.loads(expected_path.read_text())
        by_pin = {}
        for pad in target_pads.values():
            if pad['number']:
                by_pin.setdefault((pad['reference'], pad['number']), set()).add(pad['net'])
        for ref, part in expected['parts'].items():
            for number, pin in part['pins'].items():
                actual = by_pin.get((ref, number), set())
                wanted = pin['net'] if pin['net'] is not None else f'unconnected-({ref}-Pad{number})'
                if actual != {wanted}:
                    circuit_errors.append({'reference': ref, 'pin': number, 'expected': wanted, 'actual': sorted(actual)})
        if circuit_errors:
            errors.append({'expected_circuit_mismatches': circuit_errors})

    native = None
    if drc_path is not None:
        drc = json.loads(drc_path.read_text())
        required = {'violations', 'unconnected_items', 'schematic_parity'}
        if not required.issubset(drc) or not all(isinstance(drc[k], list) for k in required):
            raise ValueError('Native DRC report lacks required result lists')
        native = {field: len(drc.get(field, [])) for field in ['violations', 'unconnected_items', 'schematic_parity']}
        native['violation_types'] = dict(Counter(v['type'] for v in drc.get('violations', [])))
        native['ignored_checks'] = drc.get('ignored_checks', [])
        native['source'] = drc.get('source')
        native['kicad_version'] = drc.get('kicad_version')
        if isinstance(drc.get('source'), str) and Path(drc['source']).name != candidate_path.name:
            errors.append({'drc_source_filename_differs': drc['source']})
        if any(native[f] for f in ['violations', 'unconnected_items', 'schematic_parity']):
            errors.append({'native_drc_or_connectivity_or_parity_not_clear': native})

    return {'preservation_passed': not errors, 'seed_sha256': hashlib.sha256(seed_bytes).hexdigest(),
            'candidate_sha256': hashlib.sha256(candidate_bytes).hexdigest(),
            'footprints': len(target_fps), 'physical_pads': len(target_pads),
            'numbered_physical_pads': sum(bool(p['number']) for p in target_pads.values()),
            'all_footprint_subtrees_identical': not changed_fps and set(source_fps) == set(target_fps),
            'locked_seed_copper': len(locked), 'locked_seed_copper_unchanged': not changed_locked,
            'candidate_copper': dict(Counter(key(n) for n in target_copper.values())),
            'expected_circuit_checked': expected_path is not None, 'native_drc_report': native,
            'errors': errors,
            'scope': 'Exact native-file circuit/placement/pad/locked-copper preservation. '
                     'A clear supplied KiCad DRC report is required separately; no electrical bench validation is claimed.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seed', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--expected', type=Path)
    parser.add_argument('--drc', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = audit(args.seed, args.candidate, args.expected, args.drc)
    rendered = json.dumps(result, indent=2) + '\n'
    if args.report:
        with args.report.open('x') as output:
            output.write(rendered)
    print(rendered)
    raise SystemExit(0 if result['preservation_passed'] else 1)

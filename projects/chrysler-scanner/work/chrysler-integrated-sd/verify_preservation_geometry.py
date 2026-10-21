"""Verify preservation from the actual serialized native PCB files, read-only."""
import argparse
import json
from pathlib import Path
import sexpdata as sx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('original', type=Path)
parser.add_argument('revision', type=Path)
parser.add_argument('--nc-map', type=Path)
args = parser.parse_args()


def key(x):
    return str(x[0]) if isinstance(x, list) and x else ''


def one(x, k):
    return next((n for n in x if key(n) == k), None)


def identity(x):
    u = one(x, 'uuid') or one(x, 'tstamp')
    return str(u[1]) if u else None


def ref(x):
    return next(n[2] for n in x if key(n) == 'property' and n[1] == 'Reference')


base = sx.loads(args.original.read_text())
new = sx.loads(args.revision.read_text())
errors = []
counts = {}
# Compare full zone/keepout and drawing representations, including polygon
# vertices, clearances, layers, fills, text, thickness and all mechanical arcs.
for kind in ['zone', 'gr_line', 'gr_arc', 'gr_rect', 'gr_poly', 'gr_circle', 'gr_text', 'dimension']:
    old_items = {identity(x): x for x in base if key(x) == kind}
    new_items = {identity(x): x for x in new if key(x) == kind}
    for uid, item in old_items.items():
        if new_items.get(uid) != item:
            errors.append(kind + ': original serialized geometry/properties changed: ' + str(uid))
    counts[kind] = len(old_items)

old_fps = {ref(x): x for x in base if key(x) == 'footprint'}
new_fps = {ref(x): x for x in new if key(x) == 'footprint'}
nc_map = json.loads(args.nc_map.read_text()) if args.nc_map else {}
expected = json.loads((args.nc_map.parent / 'v240-netlist.json').read_text()) if args.nc_map else {'parts': {}}
base_net_members = {}
new_net_members = {}
for collection, target in [(old_fps, base_net_members), (new_fps, new_net_members)]:
    for name, fp in collection.items():
        for pad in fp:
            if key(pad) != 'pad':
                continue
            net = one(pad, 'net')
            if net:
                target.setdefault(str(net[-1]), set()).add((name, str(pad[1])))
for token, want in nc_map.items():
    name, pin = token.split('.', 1)
    if expected['parts'][name]['pins'][pin].get('net'):
        errors.append(token + ': NC metadata allowlist contains connected terminal')
    pad = next(p for p in old_fps[name] if key(p) == 'pad' and str(p[1]) == pin)
    old_net = one(pad, 'net')
    if old_net and base_net_members.get(str(old_net[-1])) != {(name, pin)}:
        errors.append(token + ': original NC metadata net has another endpoint')
    if new_net_members.get(want) != {(name, pin)}:
        errors.append(token + ': canonical NC metadata net is not isolated')
pad_count = 0
for name, fp in old_fps.items():
    current = new_fps.get(name)
    if current is None:
        errors.append('Missing original footprint: ' + name)
        continue
    old_pads = {identity(x): x for x in fp if key(x) == 'pad'}
    new_pads = {identity(x): x for x in current if key(x) == 'pad'}
    if set(old_pads) != set(new_pads):
        errors.append(name + ': original pad UUID set changed')
    for uid, pad in old_pads.items():
        # The six authorized U10 pads have new net assignments. Compare every
        # other pad property verbatim rather than relying on bounding boxes.
        strip_net = ((name == 'U10' and str(pad[1]) in {'5', '6', '7', '21', '27', '38'})
                     or name + '.' + str(pad[1]) in nc_map)
        clean = lambda x: [n for n in x if not (strip_net and key(n) == 'net')]
        if uid not in new_pads or clean(pad) != clean(new_pads[uid]):
            errors.append(name + '.' + str(pad[1]) + ': serialized pad geometry or properties changed')
        pad_count += 1

result = {'status': 'PASS' if not errors else 'FAIL', 'original_footprints': len(old_fps),
          'original_pads_checked': pad_count, 'original_drawing_zone_counts': counts,
          'isolated_nc_name_metadata_entries_verified': len(nc_map),
          'complete_serialized_pad_geometry_preserved': not errors,
          'complete_original_outline_drawing_zone_properties_preserved': not errors,
          'errors': errors}
print(json.dumps(result, indent=2))
raise SystemExit(bool(errors))

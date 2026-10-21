"""Independently compare the integrated KiCad PCB with its exported schematic.

Run using KiCad's bundled Python (pcbnew). Only reads CAD inputs.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pcbnew

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('project', type=Path)
parser.add_argument('--original', type=Path)
args = parser.parse_args()
project = args.project
name = 'ChryslerScanner_V240_SD'
manifest = json.loads((project / 'reference/integration.json').read_text())
xml = ET.parse(project / 'reference' / (name + '.xml')).getroot()
board = pcbnew.LoadBoard(str(project / (name + '.kicad_pcb')))
errors = []
components = {node.attrib['ref']: node for node in xml.findall('components/comp')}
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
if len(fps) != len(list(board.GetFootprints())):
    errors.append('Duplicate PCB references')
if set(components) != set(fps) - {'H1', 'H2', 'H3', 'H4'}:
    errors.append('Schematic/PCB component reference set differs')
for ref, component in components.items():
    fp = fps.get(ref)
    if fp is None:
        continue
    if fp.GetValue() != component.findtext('value'):
        errors.append(ref + ': native schematic/PCB value differs')
    fp_id = str(fp.GetFPID().GetLibNickname()) + ':' + str(fp.GetFPID().GetLibItemName())
    if fp_id != component.findtext('footprint'):
        errors.append(ref + ': native schematic/PCB footprint assignment differs')

sch_nets = {}
for net in xml.findall('nets/net'):
    endpoints = frozenset((n.attrib['ref'], n.attrib['pin']) for n in net.findall('node'))
    # Each NC is exported as a single-node net. Only compare connected sets here.
    if len(endpoints) > 1:
        sch_nets[endpoints] = net.attrib['name']
pcb_nets = defaultdict(set)
pad_nets = {}
for ref, fp in fps.items():
    for pad in fp.Pads():
        pin = pad.GetNumber()
        if not pin:
            continue
        net = pad.GetNetname()
        key = (ref, pin)
        if key in pad_nets and pad_nets[key] != net:
            errors.append('Duplicate physical pad number has differing nets: ' + str(key))
        pad_nets[key] = net
        if net:
            pcb_nets[net].add(key)
pcb_sets = {frozenset(v): k for k, v in pcb_nets.items() if len(v) > 1}
missing_pcb = set(sch_nets) - set(pcb_sets)
extra_pcb = set(pcb_sets) - set(sch_nets)
if missing_pcb or extra_pcb:
    errors.append('Native schematic/PCB connected endpoint sets differ')
expected = json.loads((project / 'reference/v240-netlist.json').read_text())
nc_names_path = project / 'reference/native-nc-net-names.json'
nc_names = json.loads(nc_names_path.read_text()) if nc_names_path.exists() else {}
expected_nc = {(r, pin) for r, part in expected['parts'].items()
               for pin, mapping in part['pins'].items() if not mapping.get('net')}
nc_count = 0
for ref, part in expected['parts'].items():
    actual_pins = {pin for r, pin in pad_nets if r == ref}
    if actual_pins != set(part['pins']):
        errors.append(ref + ': physical pad number set differs from expected source')
    for pin, mapping in part['pins'].items():
        if not mapping.get('net'):
            nc_count += 1
            net = pad_nets.get((ref, pin))
            if len(pcb_nets.get(net, set())) > 1:
                errors.append(ref + '.' + pin + ': expected no-connect joined to another terminal')

critical = []
for pin, mapping in manifest['mcu_additions'].items():
    expected = mapping['net']
    actual = pad_nets.get(('U10', pin))
    critical.append({'ref': 'U10', 'pin': pin, 'gpio': mapping['gpio'], 'expected': expected, 'actual': actual})
    if actual != expected:
        errors.append('Incorrect new U10 connection: ' + pin)
for part in manifest['parts']:
    ref = part['ref']
    if fp := fps.get(ref):
        if fp.GetLayer() != pcbnew.B_Cu:
            errors.append(ref + ' expected on back side')
        if fp.GetValue() != part['value']:
            errors.append(ref + ' value differs from integration manifest')
    else:
        errors.append('Missing new footprint ' + ref)
    for pin, net in part['nets'].items():
        if pad_nets.get((ref, pin)) != net:
            errors.append('Incorrect new connection: ' + ref + '.' + pin)
for ref in ('U3', 'U4', 'U8'):
    if pad_nets.get((ref, '5')) != 'GND':
        errors.append('TLV767 pin5 ground correction lost: ' + ref)

preservation = {}
if args.original:
    base = pcbnew.LoadBoard(str(args.original))
    originals = {fp.GetReference(): fp for fp in base.GetFootprints()}
    authorized = {('U10', pin) for pin in manifest['mcu_additions']}
    base_net_members = defaultdict(set)
    for fp in base.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname():
                base_net_members[pad.GetNetname()].add((fp.GetReference(), pad.GetNumber()))
    changed = []
    for ref, fp in originals.items():
        new = fps.get(ref)
        if new is None:
            changed.append(ref + ': missing')
            continue
        for label, a, b in [
            ('uuid', str(fp.m_Uuid), str(new.m_Uuid)),
            ('position', (fp.GetPosition().x, fp.GetPosition().y), (new.GetPosition().x, new.GetPosition().y)),
            ('orientation', fp.GetOrientationDegrees(), new.GetOrientationDegrees()),
            ('side', fp.GetLayer(), new.GetLayer()),
            ('value', fp.GetValue(), new.GetValue()),
        ]:
            if a != b:
                changed.append(ref + ': ' + label)
        old_pads = {(p.GetNumber(), p.GetPosition().x, p.GetPosition().y): p for p in fp.Pads()}
        new_pads = {(p.GetNumber(), p.GetPosition().x, p.GetPosition().y): p for p in new.Pads()}
        if set(old_pads) != set(new_pads):
            changed.append(ref + ': pad positions')
        for key, pad in old_pads.items():
            replacement = new_pads.get(key)
            nc_rename_ok = (replacement is not None and (ref, key[0]) in expected_nc
                            and len(base_net_members[pad.GetNetname()]) <= 1
                            and replacement.GetNetname() == nc_names.get(ref + '.' + key[0])
                            and len(pcb_nets[replacement.GetNetname()]) <= 1)
            if replacement and (ref, key[0]) not in authorized and not nc_rename_ok and pad.GetNetname() != replacement.GetNetname():
                changed.append(ref + '.' + key[0] + ': net')
            if (ref, key[0]) in authorized and len(base_net_members[pad.GetNetname()]) > 1:
                changed.append(ref + '.' + key[0] + ': formerly assigned pin reused')
    if changed:
        errors.extend(changed)
    preservation = {'original_footprints': len(originals), 'position_rotation_side_uuid_values_and_assigned_nets_preserved': not changed,
                    'isolated_nc_name_metadata_allowlist': len(nc_names), 'differences': changed}

result = {
    'status': 'PASS' if not errors else 'FAIL',
    'native_kicad_version': pcbnew.GetBuildVersion(),
    'components': len(components),
    'pcb_footprints_including_mounting_holes': len(fps),
    'schematic_connected_nets': len(sch_nets),
    'pcb_connected_nets': len(pcb_sets),
    'connected_endpoint_sets_match': not missing_pcb and not extra_pcb,
    'expected_no_connect_terminals_checked': nc_count,
    'new_components': len(manifest['parts']),
    'critical_mcu_pins': critical,
    'preservation': preservation,
    'pcb_sha256': hashlib.sha256((project / (name + '.kicad_pcb')).read_bytes()).hexdigest(),
    'routing_complete': False,
    'firmware': 'deferred_by_user',
    'errors': errors,
}
print(json.dumps(result, indent=2))
raise SystemExit(bool(errors))

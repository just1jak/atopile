"""Compare KiCad's native export with the independently preserved circuit JSON."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def validate(root: Path) -> dict:
    expected_path = root / 'reference/v240-netlist.json'
    native_path = root / 'reference/ChryslerScanner_V240_SD.xml'
    expected = json.loads(expected_path.read_text())
    native = ET.parse(native_path)
    parts = {p.attrib['ref']: p for p in native.findall('./components/comp')}
    errors = []
    if set(parts) != set(expected['parts']):
        errors.append({'component_set': {
            'missing': sorted(set(expected['parts']) - set(parts)),
            'extra': sorted(set(parts) - set(expected['parts']))}})
    for ref, part in expected['parts'].items():
        if ref not in parts:
            continue
        actual = parts[ref]
        footprint = part['footprint']
        if ':' not in footprint:
            footprint = 'footprints:' + footprint
        checks = {
            'value': (part['value'], actual.findtext('value')),
            'footprint': (footprint, actual.findtext('footprint')),
            'dnp': (bool(part.get('dnp')), any(p.attrib['name'] == 'dnp' for p in actual.findall('property'))),
            'pins': (set(part['pins']), {p.attrib['num'] for p in actual.findall('./units/unit/pins/pin')}),
        }
        for name, (want, got) in checks.items():
            if want != got:
                errors.append({'reference': ref, 'field': name, 'expected': sorted(want) if isinstance(want, set) else want,
                               'native': sorted(got) if isinstance(got, set) else got})

    native_nets = {}
    native_nc = set()
    for net in native.findall('./nets/net'):
        endpoints = frozenset((p.attrib['ref'], p.attrib['pin']) for p in net.findall('node'))
        if net.attrib['name'].startswith('unconnected-'):
            native_nc.update(endpoints)
            if len(endpoints) != 1 or not all('no_connect' in p.attrib.get('pintype', '') for p in net.findall('node')):
                errors.append({'not_explicit_nc': net.attrib['name']})
        else:
            native_nets[net.attrib['name']] = endpoints
    expected_nets = {n: frozenset(map(tuple, pins)) for n, pins in expected['nets'].items()}
    aliases = {}
    unmatched = dict(native_nets)
    for name, pins in expected_nets.items():
        actual_name = name if unmatched.get(name) == pins else next((n for n, p in unmatched.items() if p == pins), None)
        if actual_name is None:
            errors.append({'net_endpoint_mismatch': name, 'expected': sorted(pins),
                           'native': sorted(native_nets.get(name, []))})
            continue
        del unmatched[actual_name]
        if name != actual_name:
            if not name.startswith('N_'):
                errors.append({'unexpected_named_net_alias': [name, actual_name]})
            aliases[name] = actual_name
    if unmatched:
        errors.append({'extra_connected_nets': sorted(unmatched)})
    expected_nc = {(r, n) for r, p in expected['parts'].items() for n, pin in p['pins'].items()
                   if pin.get('no_connect') and pin['net'] is None}
    if expected_nc != native_nc:
        errors.append({'nc_mismatch': {'missing': sorted(expected_nc - native_nc), 'extra': sorted(native_nc - expected_nc)}})

    report = {
        'passed': not errors,
        'native_tool': 'KiCad CLI 10.0.7 sch export netlist --format kicadxml',
        'electrical_components': len(parts),
        'connected_nets': len(native_nets),
        'explicit_nc_pins': len(native_nc),
        'pages': len(native.findall('./design/sheet')),
        'preserved_dnp_references': sorted(r for r, p in expected['parts'].items() if p.get('dnp')),
        'anonymous_net_aliases': aliases,
        'errors': errors,
        'expected_sha256': hashlib.sha256(expected_path.read_bytes()).hexdigest(),
        'native_xml_sha256': hashlib.sha256(native_path.read_bytes()).hexdigest(),
        'scope': 'Values, footprint IDs, DNP, complete pin sets, connected endpoint sets, and explicit NC pins. '
                 'No hardware, firmware, power-budget, or manufacturing validation is claimed.',
    }
    if report['pages'] != 23:
        errors.append({'page_count': report['pages']})
        report['passed'] = False
    (root / 'reference/native-connectivity-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    generation_path = root / 'reference/schematic-generation.json'
    if generation_path.exists():
        generation = json.loads(generation_path.read_text())
        generation['native_connectivity_validation_pending'] = not report['passed']
        generation['native_connectivity_validation_report'] = 'reference/native-connectivity-validation.json'
        generation_path.write_text(json.dumps(generation, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = validate(args.root.resolve())
    print(json.dumps({k: v for k, v in report.items() if k != 'anonymous_net_aliases'}, indent=2))
    raise SystemExit(0 if report['passed'] else 1)

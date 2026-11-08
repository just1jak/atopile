"""Verify the Omron procurement change against fresh KiCad exports.

Run with KiCad Python. This does not change CAD or accept JLC substitutions.
"""
import argparse
import copy
import csv
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
REV = HERE.parent
PROJECT = REV.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(name):
    with (HERE / name).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def verify(netlist, erc_file, drc_file, native_positions):
    selection = json.loads((HERE / 'selections.json').read_text())
    old_file = (HERE / selection['inheritedSelection']).resolve()
    assert sha(old_file) == selection['inheritedSelectionSha256']
    for name, digest in selection['unchangedFiles'].items():
        assert sha(PROJECT / name) == digest, ('Release file changed', name)
    parts = copy.deepcopy(json.loads(old_file.read_text())['parts'])
    components = {c.attrib['ref']: c for c in ET.parse(netlist).findall('.//components/comp')}
    assert len(components) == 393
    for group in selection['newPartGroups']:
        part = (copy.deepcopy(parts[group['inheritReference']]) if 'inheritReference' in group
                else {k: v for k, v in group.items() if k != 'references'})
        for ref in group['references']:
            assert ref not in parts
            parts[ref] = dict(part, assembly='PLACE', footprint=components[ref].findtext('footprint'))
    assert parts.keys() == components.keys()
    expected = {r for r, p in parts.items() if p['assembly'] == 'PLACE'}
    assert len(expected) == 385
    detailed = rows('BOM.csv')
    assert len(detailed) == len(parts)
    assert {r['Reference'] for r in detailed} == parts.keys()
    for row in detailed:
        ref = row['Reference']
        part, comp = parts[ref], components[ref]
        assert row['Value'] == comp.findtext('value'), ref
        assert row['Footprint'] == comp.findtext('footprint') == part['footprint'], ref
        for column, key in [('Manufacturer', 'manufacturer'), ('MPN', 'mpn'), ('Assembly', 'assembly'), ('Source', 'source')]:
            assert row[column] == part[key], (ref, column)
        assert row['LCSC Part #'] == selection['supplierIds'].get(part['mpn'], ''), ref
    bom = rows('JLC-BOM.csv')
    seen = set()
    by_ref = {r['Reference']: r for r in detailed}
    for row in bom:
        refs = [r.strip() for r in row['Designator'].split(',')]
        assert refs and not seen.intersection(refs)
        seen.update(refs)
        for ref in refs:
            part = by_ref[ref]
            assert row['Comment'] == row['Manufacturer Part'] == part['MPN']
            assert row['Manufacturer'] == part['Manufacturer']
            assert row['LCSC Part #'] == part['LCSC Part #']
            assert row['Footprint'] == part['Footprint'].split(':')[-1]
    assert seen == expected
    with native_positions.open(encoding='utf-8-sig', newline='') as handle:
        native = list(csv.DictReader(handle))
    cpl = rows('JLC-CPL.csv')
    assert len(cpl) == len(native) == 385
    assert {r['Designator'] for r in cpl} == {r['Ref'] for r in native} == expected
    native_map = {r['Ref']: r for r in native}
    for row in cpl:
        native_row = native_map[row['Designator']]
        for a, b in [('Mid X', 'PosX'), ('Mid Y', 'PosY'), ('Rotation', 'Rot'), ('Layer', 'Side')]:
            assert row[a] == native_row[b], (row['Designator'], a)
    board = pcbnew.LoadBoard(str(REV / 'ChryslerScanner_RevD.kicad_pcb'))
    assert len(list(board.GetFootprints())) == 397
    relay_pads = {
        '1': (-3.5, -3.8), '2': (-3.5, -0.6), '3': (-3.5, 1.6), '4': (-3.5, 3.8),
        '5': (3.5, 3.8), '6': (3.5, 1.6), '7': (3.5, -0.6), '8': (3.5, -3.8),
    }
    relays = {f.GetReference(): f for f in board.GetFootprints() if f.GetReference() in ('K1', 'K2', 'K3', 'K4')}
    assert len(relays) == 4
    for ref, relay in relays.items():
        assert by_ref[ref]['MPN'] == 'G6K-2F-Y-TR DC5 BY OMR/C'
        assert by_ref[ref]['LCSC Part #'] == 'C231390'
        pads = {pad.GetNumber(): pad for pad in relay.Pads()}
        assert pads.keys() == relay_pads.keys()
        for number, pad in pads.items():
            local = pad.GetFPRelativePosition()
            actual = tuple(round(pcbnew.ToMM(v), 4) for v in (local.x, local.y))
            size = tuple(round(pcbnew.ToMM(v), 4) for v in (pad.GetSize().x, pad.GetSize().y))
            assert actual == relay_pads[number] and size == (1.8, 0.8), (ref, number)
        assert pads['1'].GetNetname() == '+5V'
        assert pads['2'].GetNetname().startswith('unconnected-')
        assert pads['7'].GetNetname().startswith('unconnected-')
    processed = [v for v in board.GetTracks() if v.GetClass() == 'PCB_VIA' and (v.GetPrimaryDrillFilledFlag() or v.GetPrimaryDrillCappedFlag())]
    assert len(processed) == 254
    assert all(v.GetPrimaryDrillFilledFlag() and v.GetPrimaryDrillCappedFlag() for v in processed)
    drc, erc = json.loads(drc_file.read_text()), json.loads(erc_file.read_text())
    assert not drc['violations'] and not drc['unconnected_items'] and not drc['schematic_parity']
    assert all(not sheet['violations'] for sheet in erc['sheets'])
    subprocess.run([sys.executable, str(REV / 'check_netlist.py'), str(netlist)], check=True)
    report = dict(
        status='PASS', qualification='Bounded bench prototype; procurement compatibility only',
        pcbSha256=selection['pcbSha256'], unchangedReleaseFiles=len(selection['unchangedFiles']),
        schematicComponents=393, placedParts=385, purchasingLines=len(bom), filledCappedSites=254,
        exactOmronRelays=list(sorted(relays)), relayLandPattern='1.8 x 0.8 mm pads, 7.0 mm row spacing, 3.2/2.2/2.2 mm column intervals',
        retainedFunctions=['CCD', 'PCI', 'SCI', 'Legacy pin selection', 'passive CAN default', 'active CAN diagnostics', 'hardware TX permit and timer', 'two series NO relays per branch', '48 hook testpoints'],
        ercViolations=0, drcViolations=0, unconnectedItems=0, schematicParityIssues=0,
        isolationAndTxCheck='PASS: unchanged check_netlist.py; 80 conductor/contact cases and 128 TX permit cases',
        ruleSettings='Unchanged baseline severities and exclusions; not a new qualification of ignored rules',
        evidenceSha256={p.name: sha(p) for p in [netlist, erc_file, drc_file, native_positions]},
        bomSha256={n: sha(HERE / n) for n in ['selections.json', 'BOM.csv', 'JLC-BOM.csv', 'JLC-CPL.csv']},
    )
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netlist', type=Path, required=True)
    parser.add_argument('--erc', type=Path, required=True)
    parser.add_argument('--drc', type=Path, required=True)
    parser.add_argument('--positions', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.netlist, args.erc, args.drc, args.positions)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))

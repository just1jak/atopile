"""Check native sheet ports and the pre-reorganization electrical endpoint map.

Run after refreshing reference/final-netlist.xml, final-erc.json and final-drc.json
with KiCad CLI. Does not modify CAD files.
"""
from pathlib import Path
import hashlib, importlib.util, json, sys, xml.etree.ElementTree as ET

D = Path(__file__).resolve().parent.parent
N = 'ChryslerScanner_V240_SD'
spec = importlib.util.spec_from_file_location('hierarchy_sexp', D/'source/specctra_tools.py')
s = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s
spec.loader.exec_module(s)
root = s.parse((D/(N+'.kicad_sch')).read_text())
change = json.loads((D/'reference/hierarchy-change.json').read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
check = {}
total = 0
for sheet in root.children('sheet'):
    filename = next(p.items[2].value for p in sheet.children('property') if p.items[1].value == 'Sheetfile')
    child = s.parse((D/filename).read_text())
    pins = [p.items[1].value for p in sheet.children('pin')]
    labels = [p.items[1].value for p in child.children('hierarchical_label')]
    check[filename] = sorted(pins) == sorted(labels) == change['ports'][filename]
    total += len(pins)
xml = ET.parse(D/'reference/final-netlist.xml')
nets = {n.attrib['name']: sorted([v.attrib['ref'], v.attrib['pin']] for v in n.findall('node'))
        for n in xml.findall('.//nets/net')}
check['all194NamedEndpointSetsPreserved'] = nets == json.loads((D/'reference/net-endpoints-before-hierarchy.json').read_text())
check['all259ComponentsPreserved'] = len(xml.findall('.//components/comp')) == 259
check['connectorAndProtectionSameSheet'] = all(
    xml.find(f'.//components/comp[@ref="{ref}"]/sheetpath').attrib['tstamps'] == '/'+change['connectorMovedTo']+'/'
    for ref in ['J1', 'D11', 'D12', 'D13', 'D14', 'C42', 'C25', 'C36', 'C37', 'C39', 'C40', 'C44'])
paths = {c.attrib['ref']: c.find('sheetpath').attrib['tstamps'] for c in xml.findall('.//components/comp')}
expected_paths = dict(change['componentPathsBefore'])
expected_paths['J1'] = '/'+change['connectorMovedTo']+'/'
check['onlyJ1ComponentPathChanged'] = paths == expected_paths
board = (D/(N+'.kicad_pcb')).read_text()
normalized = board.replace('/'+change['connectorMovedTo']+'/'+change['connectorSymbolUuid'],
                           '/'+change['connectorMovedFrom']+'/'+change['connectorSymbolUuid'])
check['pcbOnlyJ1PathMetadataChanged'] = hashlib.sha256(normalized.encode()).hexdigest() == change['normalizedBoardBeforeSha256']
erc = json.loads((D/'reference/final-erc.json').read_text())
drc = json.loads((D/'reference/final-drc.json').read_text())
check['nativeErcClean'] = not any(sh['violations'] for sh in erc['sheets'])
check['nativeDrcAndParityClean'] = not drc['violations'] and not drc['unconnected_items'] and not drc.get('schematic_parity', [])
check['twentyOneCircuitSheets'] = len(root.children('sheet')) == 21
ground_change_path = D/'reference/ground-symbol-change.json'
if ground_change_path.exists():
    ground_change = json.loads(ground_change_path.read_text())
    ground_labels = []
    for filename in [N+'.kicad_sch', *change['ports']]:
        circuit = s.parse((D/filename).read_text())
        ground_labels.extend(n for kind in ('global_label', 'hierarchical_label')
                             for n in circuit.children(kind) if n.items[1].value == 'GND')
    check['groundLabelsReplacedByPowerSymbols'] = not ground_labels
    check['groundHierarchyUsesGlobalPowerNet'] = all('GND' not in names for names in change['ports'].values())
    check['groundsBelowCircuitBodies'] = all(c['bodyBottom'] is None or c['new'][1] >= c['bodyBottom']
                                           for c in ground_change['changes'])
result = dict(status='PASS' if all(check.values()) else 'FAIL', checks=check,
              hierarchicalPorts=total, totalPages=22,
              pcbSha256=sha(D/(N+'.kicad_pcb')), rootSchematicSha256=sha(D/(N+'.kicad_sch')),
              pcbChange='J1 sheet path metadata only; geometry and copper unchanged',
              hierarchyChange='J1 moved to protection sheet; its symbol UUID preserved')
(D/'reference/system-diagram-validation.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
assert result['status'] == 'PASS'

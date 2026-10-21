"""Verify the isolated preroute seed, never writing its source or original project."""
from pathlib import Path
import hashlib
import json
import math
import re
import pcbnew as p

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'physical-fix-stage/ChryslerScanner_V240_SD.kicad_pcb'
OUTPUT = HERE / 'critical-power-candidate.kicad_pcb'
source_bytes = SOURCE.read_bytes()
output_bytes = OUTPUT.read_bytes()
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(source_bytes) == 'f2b5c36611bb8ea9b47a6f21de91bd04ad656ecaa4f75047ede9a9424269604e'
assert sha(output_bytes) == '82c75bbcafb8474820fe86ec497f9660b5a900f2315c6744f6cd3a8a79019ea4'

def blocks(data, kind):
    return re.findall(r'(?ms)^\t\(' + kind + r'\b.*?^\t\)\n', data.decode())

assert len(blocks(source_bytes, 'footprint')) == 263
assert blocks(source_bytes, 'footprint') == blocks(output_bytes, 'footprint')
for kind in ('setup', 'gr_line', 'gr_arc', 'gr_rect', 'gr_poly', 'gr_text', 'via', 'segment', 'zone'):
    old = blocks(source_bytes, kind)
    new = blocks(output_bytes, kind)
    assert all(item in new for item in old), kind

base = p.LoadBoard(str(SOURCE))
board = p.LoadBoard(str(OUTPUT))
base_uuids = {item.m_Uuid.AsString() for item in base.GetTracks()}
added = [item for item in board.GetTracks() if item.m_Uuid.AsString() not in base_uuids]
assert added and all(item.IsLocked() for item in added)
assert len([z for z in board.Zones() if z.GetIsRuleArea()]) == 4

required = {
    'LNA_IN': ['U10.2', 'R22.2', 'R24.1'],
    'N_R23_1': ['R22.1', 'R23.1', 'AE1.1'],
    'D+': ['J2.A6', 'J2.B6', 'U11.1'],
    'D-': ['J2.A7', 'J2.B7', 'U11.3'],
    'D+P': ['U11.6', 'U12.4'],
    'D-P': ['U11.4', 'U12.5'],
    'N_C5_2': ['U2.6', 'D4.1', 'L1.1', 'C5.2'],
    'N_C5_1': ['U2.1', 'C5.1'],
    'N_D7_2': ['U5.1', 'D7.2', 'L2.2'],
    'N_C17_2': ['U6.6', 'D8.1', 'L4.1', 'C17.2'],
    'N_C17_1': ['U6.1', 'C17.1'],
    'N_C21_2': ['U7.6', 'D9.1', 'L6.1', 'C21.2'],
    'N_C21_1': ['U7.1', 'C21.1'],
    'N_R2_1': ['L1.2', 'C6.1'],
    'N_R8_1': ['D7.1', 'C14.1', 'L3.1'],
    'VPP': ['L3.2', 'C15.1'],
    'N_R11_1': ['L4.2', 'C18.1', 'L5.1'],
    'VBB': ['L5.2', 'C19.1'],
    'N_R14_1': ['L6.2', 'C22.1'],
    'VBUS': ['U1.2', 'U1.3', 'C2.1'],
    'N_C3_1': ['U1.4', 'C3.1'],
}
pad_names = {q.m_Uuid.AsString(): f.GetReference()+'.'+q.GetNumber()
             for f in board.GetFootprints() for q in f.Pads()}
pads = {pad_names[q.m_Uuid.AsString()]: q
        for f in board.GetFootprints() for q in f.Pads()}
board.BuildConnectivity()
c = board.GetConnectivity()
results = {}
for net, expected in required.items():
    connected = {pad_names[item.m_Uuid.AsString()]
                 for item in c.GetConnectedItems(pads[expected[0]])
                 if item.m_Uuid.AsString() in pad_names}
    assert set(expected) <= connected, (net, expected, connected)
    assert all(pads[name].GetNetname() == net for name in expected), net
    if net in ('LNA_IN', 'N_R23_1', 'D+', 'D-', 'D+P', 'D-P'):
        assert connected == set(expected), (net, connected)
    results[net] = {'requiredConnectedPads': expected, 'passed': True}

p.ZONE_FILLER(board).Fill(board.Zones())
board.BuildConnectivity()
c = board.GetConnectivity()
ground_names = {pad_names[item.m_Uuid.AsString()]
                for item in c.GetConnectedItems(pads['R23.2'])
                if item.m_Uuid.AsString() in pad_names}
assert {'R23.2', 'R24.2', 'U2.2', 'D4.2', 'U5.2', 'U6.2', 'D8.2', 'U7.2', 'D9.2'} <= ground_names
drc = json.loads((HERE/'critical-power-drc.json').read_text())
assert drc['violations'] == []
assert SOURCE.read_bytes() == source_bytes and OUTPUT.read_bytes() == output_bytes

route_plans = [json.loads((HERE/name).read_text())
               for name in ('critical-routes.json', 'critical-power-routes.json')]
lengths = {}
for plan in route_plans:
    for route in plan['tracks']:
        length = sum(math.hypot(b[0]-a[0], b[1]-a[1])
                     for a,b in zip(route['points'], route['points'][1:]))
        lengths.setdefault(route['net'], 0.0)
        lengths[route['net']] += length

proof = {
    'sourceSha256': sha(source_bytes), 'outputSha256': sha(output_bytes),
    'sourceUnchanged': True, 'all263FootprintBlocksByteIdentical': True,
    'allExistingCopperZonesAndDrawingsPreserved': True,
    'nativeDrcErrors': 0, 'nativeDrcWarnings': 0,
    'nativeZoneRefillUsed': True, 'drcExclusionsAdded': False,
    'footprintsMoved': False,
    'addedLockedTracks': sum(item.GetClass() == 'PCB_TRACK' for item in added),
    'addedLockedVias': sum(item.GetClass() == 'PCB_VIA' for item in added),
    'addedTrackKeepouts': 3,
    'connectedGroups': results,
    'antennaGroundShuntsAndPowerGroundReturnsJoinedToGround': True,
    'remainingFullBoardAirwiresAfterNativeZoneFill': c.GetUnconnectedCount(False),
    'routingComplete': False,
    'addedTrackLengthByNetMm': {net: round(mm, 5) for net, mm in lengths.items()},
    'impedanceOrHardwareQualificationPerformed': False,
}
(HERE/'critical-route-proof.json').write_text(json.dumps(proof, indent=2)+'\n')
print(json.dumps(proof, indent=2))

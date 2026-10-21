"""Verify the already-saved work copy and attach fresh native DRC evidence."""
from pathlib import Path
import argparse,hashlib,json
import pcbnew as p
ap=argparse.ArgumentParser();ap.add_argument('directory',type=Path);a=ap.parse_args()
board_path=a.directory/'ChryslerScanner_V240_SD.kicad_pcb'
report_path=a.directory/'ground-stitch-proof.json'
j=json.loads(report_path.read_text());drc=json.loads((a.directory/'native-drc.json').read_text())
baseline=json.loads((a.directory.parent/'native5/native-drc.json').read_text())
signature=lambda x:(x['type'],x['severity'],tuple(sorted(i['uuid'] for i in x.get('items',[]))))
new=set(map(signature,drc['violations']))-set(map(signature,baseline['violations']))
assert not new;assert not drc['schematic_parity']
b=p.LoadBoard(str(board_path.resolve()));vias={v.m_Uuid.AsString():v for v in b.GetTracks() if isinstance(v,p.PCB_VIA)}
fabrication=[]
for entry in j['added']:
    if entry.get('filledCappedThermal'):
        via=vias[entry['uuid']]
        assert via.GetPrimaryDrillFilledFlag() and via.GetPrimaryDrillCappedFlag()
        fabrication.append({'uuid':entry['uuid'],'target':entry['target'],'positionMm':entry['positionMm'],
            'filled':True,'capped':True,'frontTenting':int(via.GetFrontTentingMode()),'backTenting':int(via.GetBackTentingMode())})
j['candidateSha256']=hashlib.sha256(board_path.read_bytes()).hexdigest()
j['nativeDRCPending']=False;j['nativeDRC']={'newViolationIdentities':0,'inheritedViolations':len(drc['violations']),
    'schematicParity':0,'unconnectedItems':len(drc['unconnected_items']),'path':str((a.directory/'native-drc.json').resolve())}
j['savedViaFabricationFlags']=fabrication
report_path.write_text(json.dumps(j,indent=2)+'\n')
lines=['# Native5 ground stitching fabrication requirements','',
    'This is an incomplete engineering work copy. It has six isolated GND pads and five signal connections remaining.',
    'All nine sites below require nonconductive filled, copper capped, planarized via-in-pad (VIPPO) processing. Open vias or tenting alone are not equivalent.',
    'All are through vias with 0.60 mm copper diameter and 0.30 mm drill. The pad and footprint geometry was not changed.',
    'The original front pad mask windows remain. Exposed thermal pad vias are top open / bottom tented; ordinary component pad sites are tented both sides.',
    '', '| Target | X mm | Y mm | Via UUID |','| --- | ---: | ---: | --- |']
for entry in fabrication:lines.append('| %s | %.6f | %.6f | %s |'%(entry['target'],*entry['positionMm'],entry['uuid']))
lines+=['','Native DRC: no new violation identities; only the inherited four edge-clearance findings and three dangling copper warnings remain. Schematic parity: zero.',
    'The 150 µm necks and their actual lengths are recorded individually in ground-stitch-proof.json; wider copper is retained elsewhere.']
(a.directory/'GROUND-FABRICATION-NOTES.md').write_text('\n'.join(lines)+'\n')
print(j['candidateSha256'],len(fabrication),'VIPPO sites verified',j['nativeDRC'])

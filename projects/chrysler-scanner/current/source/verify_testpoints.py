"""Read-only, exact additive debug-access contract against the frozen C61 board."""
from pathlib import Path
import sys,json,hashlib,pcbnew as p
sys.path.insert(0,str(Path(__file__).parent))
import audit_routed_board as a
D=Path(__file__).resolve().parent.parent;N='ChryslerScanner_V240_SD.kicad_pcb'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
oldpath=D/'reference/pre-testpoints'/N
assert sha(oldpath)=='a2cb3d5e82d57b75eb0caab103d6f82529d8543b182aa9fc80e320bfe61c2fd5'
planpath=D/'reference/rev-c-testpoint-plan.json';copperpath=D/'reference/rev-c-testpoint-copper-contract.json'
assert sha(planpath)=='05c3880f299f439f8e773cccb1c1cfe6db9bf3c29d8160cd6d36419ddaa613f5'
assert sha(copperpath)=='d5a71569a4fe24dc82291152b71206450167e068d413b1a6f539bc33c3b2a836'
plan=json.loads(planpath.read_text())['testpoints'];contract=json.loads(copperpath.read_text())
old=p.LoadBoard(str(oldpath));b=p.LoadBoard(str(D/N));original=a.native_footprints(old);now=a.native_footprints(b)
# Two explicit later value exceptions; every pad, placement and copper object
# remains subject to the original exact additive testpoint contract.
for item in original.values():
    if item['reference'] in ('U17','U18'):
        item['value']={'U17':'74AHCT1G17GV','U18':'SN74AHCT1G14'}[item['reference']]
refs={'TP'+str(i) for i in range(1,53)};fps={f.GetReference():f for f in b.GetFootprints()}
checks={'all277PreviousPartsAndFourHolesExactExceptTwoDeclaredCcdValues':all(now.get(k)==v for k,v in original.items()),'exact52AdditionalFootprints':len(now)==len(original)+52 and {f['reference'] for k,f in now.items() if k not in original}==refs}
o={a.uid(t):a.copper(t) for t in old.GetTracks()};n={a.uid(t):a.copper(t) for t in b.GetTracks()}
checks['everyPreviousCopperObjectRetainedExactly']=all(n.get(k)==v for k,v in o.items())
checks['exact19TracksAnd3ViasAdded']={k:v for k,v in n.items() if k not in o}==contract and len(contract)==22 and sum(v['kind']=='PCB_VIA' for v in contract.values())==3
checks['noRfOrUsbTestBranches']=all(t['net'] not in ['LNA_IN','D+','D-','D+P','D-P'] for t in contract.values())
checks['all3NewViasFilledCapped']=all(t.GetPrimaryDrillFilledFlag() and t.GetPrimaryDrillCappedFlag() and t.GetDrillValue()==300000 for t in b.GetTracks() if a.uid(t) in contract and t.GetClass()=='PCB_VIA')
checks['exactPointPositionsNetsAndStyles']=all(v['ref'] in fps and abs(p.ToMM(fps[v['ref']].GetPosition().x)-v['xMm'])<.00001 and abs(p.ToMM(fps[v['ref']].GetPosition().y)-v['yMm'])<.00001 and fps[v['ref']].GetLayer()==(p.F_Cu if v['side']=='top' else p.B_Cu) and {q.GetNumber():q.GetNetname() for q in fps[v['ref']].Pads()}=={'1':v['net']} and fps[v['ref']].GetField('MPN').GetText()==('5015' if v['hook'] else 'COPPER_PAD_NO_COMPONENT') for v in plan)
processing=D/'reference/rev-c-testpoint-processing-upgrades.json'
assert sha(processing)=='0d04ef671bc2f879f0546d53292870b63a8223326edd5052e29732762198e5bc'
fill_ids={v['uuid'] for v in json.loads(processing.read_text())['sites']}
oldvias={a.uid(t):t for t in old.GetTracks() if t.GetClass()=='PCB_VIA'}
newvias={a.uid(t):t for t in b.GetTracks() if t.GetClass()=='PCB_VIA'}
checks['only22ExistingViaProcessingUpgrades']=len(fill_ids)==22 and all((newvias[k].GetPrimaryDrillFilledFlag(),newvias[k].GetPrimaryDrillCappedFlag())==((True,True) if k in fill_ids else (t.GetPrimaryDrillFilledFlag(),t.GetPrimaryDrillCappedFlag())) for k,t in oldvias.items())
checks['exactNineZoneDefinitions']={a.uid(z):a.zone_signature(z) for z in old.Zones()}=={a.uid(z):a.zone_signature(z) for z in b.Zones()}
# Original electrical pins, values, model paths and sheet UUIDs are additionally
# checked by verify_safety_revision.py, which invokes this verifier.
result=dict(status='PASS' if all(checks.values()) else 'FAIL',pcbSha256=sha(D/N),baselinePcbSha256=sha(oldpath),checks=checks,hookLoops=48,bareSpiPads=4,addedTracks=19,addedFilledCappedVias=3,originalCopperRemovals=0,planSha256=sha(planpath),copperContractSha256=sha(copperpath))
(D/'reference/rev-c-testpoint-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));assert all(checks.values())

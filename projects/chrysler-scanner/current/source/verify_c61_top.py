"""Exact user-authorized C61-only physical delta, measured against accepted pre-move CAD."""
from pathlib import Path
import pcbnew as p,json,hashlib,sys
sys.path.insert(0,str(Path(__file__).parent))
import audit_routed_board as a
D=Path(__file__).resolve().parent.parent;N='ChryslerScanner_V240_SD.kicad_pcb';oldpath=D/'reference/pre-c61'/N
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
assert sha(oldpath)=='974231631b323828ea5a2ac47578b0f7cad72a31981915fd154d734c6b78710e'
old=p.LoadBoard(str(oldpath));b=p.LoadBoard(str(D/N));f=old.FindFootprintByReference('C61');f.Flip(f.GetPosition(),False);f.SetOrientationDegrees(90);f.SetPosition(p.VECTOR2I(193000000,127000000))
checks={'onlyC61FootprintTransform':a.native_footprints(old)==a.native_footprints(b)}
o={a.uid(t):a.copper(t) for t in old.GetTracks()};n={a.uid(t):a.copper(t) for t in b.GetTracks()};cut={'b2e77e8c-5db9-4c4b-b5df-6fa86e1b60ba','ba39bf73-e299-4de0-a91a-89bb4415e8a3'}
checks['exactTwoUnlockedC61BranchRemovals']=o.keys()-n.keys()==cut and all(o[k]['net']=='SD_3V3' and not o[k]['locked'] for k in cut)
checks['everyRetainedCopperObjectExact']=all(o[k]==n[k] for k in o.keys()&n.keys())
added=[t for t in b.GetTracks() if a.uid(t) not in o]
def sig(t):return (t.GetClass(),t.GetNetname(),t.GetLayer(),tuple(a.xy(t.GetStart())),tuple(a.xy(t.GetEnd())),t.GetWidth(p.F_Cu) if t.GetClass()=='PCB_VIA' else t.GetWidth())
def mm(x,y):return (round(x*1e6),round(y*1e6))
expected=[('PCB_TRACK','SD_3V3',p.F_Cu,mm(193,129.2),mm(194,129.2),500000),('PCB_TRACK','SD_3V3',p.B_Cu,mm(194,129.2),mm(194.1,129.3),500000),('PCB_TRACK','SD_3V3',p.B_Cu,mm(194.1,129.3),mm(194.1,131.25),500000),('PCB_TRACK','GND',p.F_Cu,mm(193,124.8),mm(191.5,124.8),500000),('PCB_VIA','SD_3V3',p.F_Cu,mm(194,129.2),mm(194,129.2),600000),('PCB_VIA','GND',p.F_Cu,mm(191.5,124.8),mm(191.5,124.8),600000)]
# KiCad's flip/save conversion can round coordinates by one nanometre.
def close(s,t):return s[:3]==t[:3] and all(abs(x-y)<=1 for q,r in zip(s[3:5],t[3:5]) for x,y in zip(q,r)) and s[5]==t[5]
checks['exactFourTracksAndTwoVias']=len(added)==6 and all(sum(close(sig(t),e) for t in added)==1 for e in expected)
checks['bothNewViasFilledCapped']=all(t.GetDrillValue()==300000 and t.GetPrimaryDrillFilledFlag() and t.GetPrimaryDrillCappedFlag() for t in added if t.GetClass()=='PCB_VIA')
checks['nineZoneDefinitionsExact']={a.uid(z):a.zone_signature(z) for z in old.Zones()}=={a.uid(z):a.zone_signature(z) for z in b.Zones()}
r=b.FindFootprintByReference('R96').Reference();checks['r96LabelAtDeclaredPosition']=a.xy(r.GetPosition())==[191500000, 132000000]
result=dict(status='PASS' if all(checks.values()) else 'FAIL',pcbSha256=sha(D/N),previousPcbSha256=sha(oldpath),checks=checks,addedCopper=[dict(uuid=a.uid(t),signature=a.copper(t)) for t in added],removedCopper=sorted(cut),placement=dict(reference='C61',side='F.Cu',xMm=193,yMm=127,orientationDegrees=90),qualification='CAD checks only; actual enclosure/thermal/assembly fit remains to be verified.')
(D/'reference/rev-c-c61-top-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=result['status'],checks=checks),indent=2));assert all(checks.values())

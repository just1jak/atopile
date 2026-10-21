"""Add four explicitly filled/capped U10 thermal-ground vias to a new copy."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,sys,uuid
import pcbnew as p
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SOURCE=ROOT/'route-pass-3/seed.kicad_pcb'
DEST=HERE/'U10-thermal-ground.kicad_pcb'
raw=SOURCE.read_bytes();mtime=SOURCE.stat().st_mtime_ns
s=importlib.util.spec_from_file_location('route_audit',ROOT/'audit-stage/audit_routed_board.py')
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
b=p.LoadBoard(str(SOURCE));before_fp=m.native_footprints(b)
before_copper={m.uid(t):m.copper(t) for t in b.GetTracks()}
before_zones={m.uid(z):m.zone_signature(z) for z in b.Zones()}
target=next(q for f in b.GetFootprints() for q in f.Pads() if f.GetReference()=='U10' and q.GetNumber()=='49')
assert target.GetNetname()=='GND' and target.GetSize().x==4500000 and target.GetSize().y==4500000
cx,cy=target.GetPosition().x,target.GetPosition().y
vias=[]
for dx,dy in [(-900000,-900000),(900000,-900000),(-900000,900000),(900000,900000)]:
    v=p.PCB_VIA(b);v.SetPosition(p.VECTOR2I(cx+dx,cy+dy));v.SetWidth(600000);v.SetDrill(300000)
    v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNet(target.GetNet())
    v.SetPrimaryDrillFilledFlag(True);v.SetPrimaryDrillCappedFlag(True)
    v.SetBackTentingMode(p.TENTING_MODE_TENTED)
    v.SetFrontTentingMode(p.TENTING_MODE_NOT_TENTED)
    v.SetLocked(True)
    v.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/u10-thermal/%s/%s'%(dx,dy)))))
    b.Add(v);vias.append(v)
assert m.native_footprints(b)==before_fp
assert {m.uid(z):m.zone_signature(z) for z in b.Zones()}==before_zones
assert all({m.uid(t):m.copper(t) for t in b.GetTracks()}.get(u)==g for u,g in before_copper.items())
shutil.copyfile(SOURCE.with_suffix('.kicad_pro'),DEST.with_suffix('.kicad_pro'))
for name in ('fp-lib-table',):shutil.copyfile(ROOT/'design'/name,HERE/name)
for name in ('footprints.pretty','libraries','3dmodels'):
    path=HERE/name
    if not path.exists():path.symlink_to(ROOT/'design'/name,target_is_directory=True)
p.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()
connected={m.uid(item) for item in b.GetConnectivity().GetConnectedItems(target)}
assert all(m.uid(v) in connected for v in vias)
ground_plane_ids=[m.uid(z) for z in b.Zones() if z.GetNetname()=='GND' and z.IsOnLayer(p.In1_Cu)]
assert any(z in connected for z in ground_plane_ids),'U10 thermal array did not join actual In1GNDplane'
p.SaveBoard(str(DEST),b)
again=p.LoadBoard(str(DEST));again_copper={m.uid(t):m.copper(t) for t in again.GetTracks()}
assert m.native_footprints(again)==before_fp
assert all(again_copper.get(u)==g for u,g in before_copper.items())
assert {m.uid(z):m.zone_signature(z) for z in again.Zones()}==before_zones
saved={m.uid(t):t for t in again.GetTracks()}
details=[]
for v in vias:
    q=saved[m.uid(v)]
    assert q.GetPrimaryDrillFilled() and q.GetPrimaryDrillCapped()
    assert q.GetBackTentingMode()==p.TENTING_MODE_TENTED
    details.append({'uuid':m.uid(q),'xyMM':[p.ToMM(q.GetPosition().x),p.ToMM(q.GetPosition().y)],
                    'diameterMM':.6,'drillMM':.3,'filled':True,'capped':True,
                    'bottomTenting':'tented','topTenting':'not_tented','locked':True})
assert SOURCE.read_bytes()==raw and SOURCE.stat().st_mtime_ns==mtime
report={'source':str(SOURCE),'sourceSha256':hashlib.sha256(raw).hexdigest(),
        'candidate':str(DEST),'candidateSha256':hashlib.sha256(DEST.read_bytes()).hexdigest(),
        'array':'2x2,1.8mm pitch centered in4.5mm exposed groundpad',
        'vias':details,'originalCopperPreserved':len(before_copper),
        'allOriginalFootprintsPadsNetsAndPlaneDefinitionsExact':True,
        'nativeConnectionToIn1GroundPlaneVerified':True,'nativeDRCPending':True,
        'fabricationRequirement':'Four0.30mm drill vias IN U10 thermal pad must be FILLED and COPPER-CAPPED/PLANARIZED; bottom soldermask tenting also specified. Ordinary open/tented vias are not an equivalent substitution.',
        'routingComplete':False}
(HERE/'U10-thermal-ground-proof.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

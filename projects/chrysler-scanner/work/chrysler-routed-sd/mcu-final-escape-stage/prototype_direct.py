from pathlib import Path
from collections import defaultdict,Counter
import hashlib,heapq,importlib.util,json,math,time,uuid
import pcbnew as p
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
SOURCE=HERE/'input/ChryslerScanner_V240_SD.kicad_pcb';raw=SOURCE.read_bytes();source_mtime=SOURCE.stat().st_mtime_ns
assert hashlib.sha256(raw).hexdigest()=='0902c778c8f56598a5c9c79f36f420d5f87bf48f2c6ba173834abb14c671b795'
spec=importlib.util.spec_from_file_location('audit',ROOT/'audit-stage/audit_routed_board.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
b=p.LoadBoard(str(SOURCE));before=audit.connectivity(b)
old_copper={audit.uid(t):audit.copper(t) for t in b.GetTracks()};old_zones={audit.uid(z):audit.zone_signature(z) for z in b.Zones()};old_fp=audit.native_footprints(b)
mm=lambda n:round(n*1e6)
vec=lambda q:p.VECTOR2I(mm(q[0]),mm(q[1]))
to_mm=lambda q:[p.ToMM(q.x),p.ToMM(q.y)]
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)
fp=next(f for f in b.GetFootprints() if f.GetReference()=='R112');fpkey=audit.uid(fp);fpold=fp.GetPosition();fpnew=p.VECTOR2I(fpold.x,fpold.y+mm(.075));fp.SetPosition(fpnew)
remove_ids=['5bb6c0de-9712-4580-bc99-d912eda3678c','c2ab3c1c-7f88-4c1d-9b06-21efb75e64ab',
 '2441b0e2-60dc-472b-acd4-b558b8574f7f','35e4541a-a0cb-4806-b498-4b06bccbae80','5d665197-29d8-4aaf-b18a-a5a422586114','5b8eee42-cb11-4164-bf52-564d28eb289d','ef2bb34a-eae7-4b4d-aa1a-4e524be01772']
chunk=[]
for t in b.GetTracks():
 if t.GetClass()!='PCB_TRACK' or t.GetNetname()!='PWR_LED' or t.GetLayer()!=p.In2_Cu:continue
 points=[to_mm(t.GetStart()),to_mm(t.GetEnd())]
 if all(170.29<=x<=172.29 and 119.30<=y<=122.18 for x,y in points):chunk.append(t)
ends=Counter((q.x,q.y) for t in chunk for q in (t.GetStart(),t.GetEnd()))
assert {q for q,n in ends.items() if n==1}=={(170299901,120195201),(172279799,122175099)} and all(n in (1,2) for n in ends.values())
remove_ids += [audit.uid(t) for t in chunk]
tracks={audit.uid(t):t for t in b.GetTracks()}
for key in remove_ids:
 t=tracks[key];assert not t.IsLocked();b.Remove(t)
new=[]
def add_tracks(points,layer,width,net,label,locked=True):
 for a,z in zip(points,points[1:]):
  if a==z:continue
  t=p.PCB_TRACK(b);t.SetStart(a);t.SetEnd(z);t.SetWidth(mm(width));t.SetLayer(layer);t.SetNet(b.FindNet(net));t.SetLocked(locked)
  t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler/final-direct/%s/%d/%d/%d/%d/%d'%(label,layer,a.x,a.y,z.x,z.y)))));b.Add(t);new.append(t)
def add_via(net,xy,label,filled):
 q=p.PCB_VIA(b);q.SetPosition(vec(xy));q.SetWidth(mm(.6));q.SetDrill(mm(.3));q.SetLayerPair(p.F_Cu,p.B_Cu);q.SetViaType(p.VIATYPE_THROUGH);q.SetNet(b.FindNet(net));q.SetLocked(True)
 q.SetFrontTentingMode(p.TENTING_MODE_TENTED);q.SetBackTentingMode(p.TENTING_MODE_TENTED);q.SetPrimaryDrillFilledFlag(filled);q.SetPrimaryDrillCappedFlag(filled)
 q.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler/final-direct-via/'+label))));b.Add(q);new.append(q)
add_via('TX_LED',[171.9,119.375],'TX_LED',True)
add_tracks([vec(q) for q in [[171.9375,118.7275],[171.9,119.375]]],p.F_Cu,.15,'TX_LED','TX_LED-inline')
add_via('+3.3V',[171.9,120.2],'R112-power',True)
add_tracks([vec(q) for q in [[171.4375,118.7275],[171.3375,119.0675],[171.3375,119.6138],[171.0591,119.9922]]],p.F_Cu,.2,'RX_LED','RX_LED-shift')
# Keep the main rail at 0.50 mm, arching above the new escape instead of between vias.
add_tracks([vec(q) for q in [[170.7787,118.3271],[173.9139,118.3271],[173.9139,119.5484]]],p.B_Cu,.5,'+3.3V','main-rail-arch',False)

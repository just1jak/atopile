"""Review a submillimeter generic RX15_EN via shift in an isolated native copy."""
from pathlib import Path
from collections import defaultdict
import hashlib,importlib.util,json,math,shutil,uuid
import pcbnew as p
root=Path(__file__).resolve().parent.parent
source=Path('/private/tmp/atopile-sd-native3logic-pin-escapes/ChryslerScanner_V240_SD.kicad_pcb')
dest=Path('/private/tmp/atopile-sd-rx15-escape-shift/ChryslerScanner_V240_SD.kicad_pcb')
assert not dest.exists()
s=importlib.util.spec_from_file_location('audit_rx15',root/'audit-stage/audit_routed_board.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
b=p.LoadBoard(str(source));before=m.connectivity(b);fp_before=m.native_footprints(b)
raw=source.read_bytes();before_cu={m.uid(t):m.copper(t) for t in b.GetTracks()}
via=next(t for t in b.GetTracks() if m.uid(t)=='aa041d82-52ee-48ff-8ce4-85efba70a8e8')
assert isinstance(via,p.PCB_VIA) and not via.IsLocked() and via.GetNetname()=='RX15_EN'
old=via.GetPosition();mm=lambda n:round(n*1e6);vec=lambda x,y:p.VECTOR2I(round(x),round(y))
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu);hit=lambda x,y,c:p.SHAPE.Collide(x,y,c)
class Grid:
 def __init__(self):self.items=[];self.cells=defaultdict(set)
 def keys(self,box):return [(x,y) for x in range(math.floor(box.GetLeft()/2e6),math.floor(box.GetRight()/2e6)+1) for y in range(math.floor(box.GetTop()/2e6),math.floor(box.GetBottom()/2e6)+1)]
 def add(self,name,layer,shape):
  i=len(self.items);self.items.append((name,layer,shape))
  for k in self.keys(shape.BBox(mm(.7))):self.cells[k].add(i)
 def candidates(self,shape):
  ids=set()
  for k in self.keys(shape.BBox(mm(.7))):ids.update(self.cells.get(k,()))
  return (self.items[i] for i in ids)
cu=Grid();holes=Grid();apertures=Grid()
for f in b.GetFootprints():
 for q in f.Pads():
  if q.HasDrilledHole():holes.add(m.uid(q),q.GetNetname(),q.GetEffectiveHoleShape())
  for l in layers:
   if q.IsOnLayer(l):
    sh=q.GetEffectiveShape(l)
    if q.GetNetname()!='RX15_EN':cu.add(m.uid(q),l,sh)
    if q.GetAttribute()==p.PAD_ATTRIB_SMD:apertures.add(m.uid(q),l,sh)
for t in b.GetTracks():
 if t==via:continue
 if isinstance(t,p.PCB_VIA):holes.add(m.uid(t),t.GetNetname(),t.GetEffectiveHoleShape())
 if t.GetNetname()!='RX15_EN':
  for l in layers:
   if t.IsOnLayer(l):cu.add(m.uid(t),l,t.GetEffectiveShape(l))
def clear(point):
 circle=p.SHAPE_CIRCLE(point,mm(.3));drill=p.SHAPE_CIRCLE(point,mm(.15))
 if any(hit(circle,s,mm(.1505)) for _,_,s in cu.candidates(circle)):return False
 if any(hit(drill,s,mm(.2505)) or (net!='RX15_EN' and hit(circle,s,mm(.2005))) for _,net,s in holes.candidates(circle)):return False
 if any(hit(circle,s,mm(.0605)) for _,_,s in apertures.candidates(circle)):return False
 for l in (p.F_Cu,p.In2_Cu):
  sh=p.SHAPE_SEGMENT(old,point,mm(.15))
  if any(layer==l and hit(sh,s,mm(.1505)) for _,layer,s in cu.candidates(sh)):return False
  if any(net!='RX15_EN' and hit(sh,s,mm(.2005)) for _,net,s in holes.candidates(sh)):return False
 return True
offsets=[(dx,dy) for dy in range(6,25) for dx in range(-12,13)]
offsets.sort(key=lambda d:math.hypot(d[0],d[1]))
legal=[]
for dx,dy in offsets:
 point=vec(old.x+mm(dx*.025),old.y+mm(dy*.025))
 if clear(point):legal.append(point)
print('Legal submillimeter shifts',len(legal),flush=True)
if not legal:raise SystemExit(2)
# Prefer an outward shift of at least .2mm, preserving the existing lower-left
# In2 escape and leaving both old connected endpoints as bridge anchors.
point=min(legal,key=lambda q:abs(q.y-old.y-mm(.25))+abs(q.x-old.x))
via.SetPosition(point);via.SetLocked(True);added=[]
for l in (p.F_Cu,p.In2_Cu):
 t=p.PCB_TRACK(b);t.SetStart(old);t.SetEnd(point);t.SetWidth(mm(.15));t.SetLayer(l);t.SetNet(via.GetNet());t.SetLocked(True)
 t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/rx15-via-shift/%s/%s/%s'%(l,point.x,point.y)))))
 b.Add(t);added.append(m.uid(t))
after=m.connectivity(b);assert before['disconnectedNetGroups']==after['disconnectedNetGroups']
assert fp_before==m.native_footprints(b)
now={m.uid(t):m.copper(t) for t in b.GetTracks()};key=m.uid(via)
assert all(now.get(k)==v for k,v in before_cu.items() if k!=key)
dest.parent.mkdir(parents=True,exist_ok=True);p.SaveBoard(str(dest),b)
assert m.blocks(raw,'footprint')==m.blocks(dest.read_bytes(),'footprint') and source.read_bytes()==raw
for f in source.parent.iterdir():
 if f.suffix=='.kicad_pro':shutil.copyfile(f,dest.parent/f.name)
 elif f.suffix in ('.kicad_sch','.kicad_sym') or f.name.endswith('lib-table') or f.name in ('libraries','3dmodels','reference','footprints.pretty'):
  (dest.parent/f.name).symlink_to(f.resolve(),target_is_directory=f.is_dir())
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'outputSha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'movedGenericVia':key,'oldMm':[old.x/1e6,old.y/1e6],'newMm':[point.x/1e6,point.y/1e6],'added150umBridges':added,'allPadPartitionsUnchanged':True,'originalCopperPreservedExceptReviewedGenericViaShift':True,'connectivity':after}
(dest.parent/'rx15-shift-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))

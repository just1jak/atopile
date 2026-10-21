"""Native-reviewed RX7 breakout shift, preserving pad partitions and protected Cu."""
from pathlib import Path
from collections import defaultdict
import hashlib,heapq,importlib.util,json,math,shutil,time,uuid
import pcbnew as p
root=Path(__file__).resolve().parent.parent
source=root/'ground-final-stage/combined/ChryslerScanner_V240_SD.kicad_pcb'
dest=Path('/private/tmp/atopile-sd-rx7-escape-shift/ChryslerScanner_V240_SD.kicad_pcb');assert not dest.exists()
s=importlib.util.spec_from_file_location('audit_rx7',root/'audit-stage/audit_routed_board.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
b=p.LoadBoard(str(source));before=m.connectivity(b);fp_before=m.native_footprints(b);raw=source.read_bytes()
cu_before={m.uid(t):m.copper(t) for t in b.GetTracks()};zones_before={m.uid(z):m.zone_signature(z) for z in b.Zones()}
via=next(t for t in b.GetTracks() if m.uid(t)=='92559ee8-fd35-41a6-9b11-cc155f43f096')
assert isinstance(via,p.PCB_VIA) and not via.IsLocked() and via.GetNetname()=='RX7_BIAS_EN'
remove_ids={'29af10c1-f9ab-45e3-a039-e45499efe4ed','d9fdeb72-192e-4d50-86c9-3d4c3cc2fcaf','f8657eb5-bc57-4b8e-9014-e79fc2aff7ef'}
removed=[t for t in b.GetTracks() if m.uid(t) in remove_ids];assert len(removed)==3
assert all(not t.IsLocked() and t.GetNetname()=='RX7_BIAS_EN' and t.GetLayer()==p.F_Cu and t.GetWidth()==150000 for t in removed)
power_ids={'c719d16e-1e81-44de-9cc3-2cac617efd43','e42a15df-6938-426d-b053-c3658b3e390f'}
power_removed=[t for t in b.GetTracks() if m.uid(t) in power_ids];assert len(power_removed)==2
assert all(not t.IsLocked() and t.GetNetname()=='+3.3V' and t.GetLayer()==p.B_Cu and t.GetWidth()==500000 for t in power_removed)
old=via.GetPosition();pin=p.VECTOR2I(169900000,138000000);mm=lambda n:round(n*1e6);vec=lambda x,y:p.VECTOR2I(round(x),round(y))
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
    if q.GetNetname()!='RX7_BIAS_EN':cu.add(m.uid(q),l,sh)
    if q.GetAttribute()==p.PAD_ATTRIB_SMD:apertures.add(m.uid(q),l,sh)
for t in b.GetTracks():
 if t==via or m.uid(t) in power_ids:continue
 if isinstance(t,p.PCB_VIA):holes.add(m.uid(t),t.GetNetname(),t.GetEffectiveHoleShape())
 if t.GetNetname()!='RX7_BIAS_EN':
  for l in layers:
   if t.IsOnLayer(l):cu.add(m.uid(t),l,t.GetEffectiveShape(l))
def clear(point):
 circle=p.SHAPE_CIRCLE(point,mm(.3));drill=p.SHAPE_CIRCLE(point,mm(.15))
 if any(hit(circle,s,mm(.1505)) for _,_,s in cu.candidates(circle)):return False
 if any(hit(drill,s,mm(.2505)) or (net!='RX7_BIAS_EN' and hit(circle,s,mm(.2005))) for _,net,s in holes.candidates(circle)):return False
 if any(hit(circle,s,mm(.0605)) for _,_,s in apertures.candidates(circle)):return False
 for l,start in ((p.F_Cu,pin),(p.In2_Cu,old)):
  sh=p.SHAPE_SEGMENT(start,point,mm(.15))
  if any(layer==l and hit(sh,s,mm(.1505)) for _,layer,s in cu.candidates(sh)):return False
  if any(net!='RX7_BIAS_EN' and hit(sh,s,mm(.2005)) for _,net,s in holes.candidates(sh)):return False
 return True
candidates=[vec(mm(171.4+x*.025),mm(138.4+y*.025)) for x in range(-16,25) for y in range(-8,13)]
candidates.sort(key=lambda q:(q.x-mm(171.4))**2+(q.y-mm(138.4))**2)
legal=[point for point in candidates if clear(point)];print('Legal RX7staggeredvia sites:',len(legal),flush=True)
if not legal:
 point=vec(mm(171.4),mm(138));circle=p.SHAPE_CIRCLE(point,mm(.3))
 diag={'proposedMm':[171.4,138],'viaCopperBlockers':[(key,layer) for key,layer,s in cu.candidates(circle) if hit(circle,s,mm(.1505))],
   'bridges':[]}
 for layer,start in ((p.F_Cu,pin),(p.In2_Cu,old)):
  sh=p.SHAPE_SEGMENT(start,point,mm(.15))
  diag['bridges'].append({'layer':layer,'blockingCu':[key for key,l,s in cu.candidates(sh) if l==layer and hit(sh,s,mm(.1505))]})
 allids={key for key,_ in diag['viaCopperBlockers']}|{k for bridge in diag['bridges'] for k in bridge['blockingCu']}
 diag['blockingGeometry']={key:cu_before.get(key) for key in allids};print(json.dumps(diag,indent=2),flush=True)
 raise SystemExit(2)
point=legal[0]
for t in removed+power_removed:b.Remove(t)
via.SetPosition(point);via.SetLocked(True);via.SetFrontTentingMode(p.TENTING_MODE_TENTED);via.SetBackTentingMode(p.TENTING_MODE_TENTED)
added=[]
for l,start in ((p.F_Cu,pin),(p.In2_Cu,old)):
 t=p.PCB_TRACK(b);t.SetStart(start);t.SetEnd(point);t.SetWidth(mm(.15));t.SetLayer(l);t.SetNet(via.GetNet());t.SetLocked(True)
 t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/rx7-via-shift/%s/%s/%s'%(l,point.x,point.y)))))
 b.Add(t);added.append(m.uid(t))
# Keep the .5mm power width. Only these two reviewed generic B segments
# change; native geometry gates include the reserved next RX15 via site.
power_cu=Grid();power_holes=Grid()
for f in b.GetFootprints():
 for q in f.Pads():
  if q.IsOnLayer(p.B_Cu) and q.GetNetname()!='+3.3V':power_cu.add(m.uid(q),p.B_Cu,q.GetEffectiveShape(p.B_Cu))
  if q.HasDrilledHole():power_holes.add(m.uid(q),q.GetNetname(),q.GetEffectiveHoleShape())
for t in b.GetTracks():
 if t.IsOnLayer(p.B_Cu) and t.GetNetname()!='+3.3V':power_cu.add(m.uid(t),p.B_Cu,t.GetEffectiveShape(p.B_Cu))
 if isinstance(t,p.PCB_VIA):power_holes.add(m.uid(t),t.GetNetname(),t.GetEffectiveHoleShape())
power_cu.add('reserved RX15 .6mm via',p.B_Cu,p.SHAPE_CIRCLE(vec(170656200,139200000),300000))
def power_clear(start,end):
 sh=p.SHAPE_SEGMENT(start,end,500000)
 if any(hit(sh,other,150500) for _,_,other in power_cu.candidates(sh)):return False
 if any(net!='+3.3V' and hit(sh,other,200500) for _,net,other in power_holes.candidates(sh)):return False
 return True
start=vec(167516500,134184400);end=vec(174835000,138390900)
step=50000;queue=[(math.hypot(end.x-start.x,end.y-start.y),0.,0,0)];dist={(0,0):0.};prev={};began=time.monotonic();goal=None;expanded=0
while queue and expanded<100000 and time.monotonic()-began<20:
 _,cost,ix,iy=heapq.heappop(queue);node=(ix,iy)
 if dist[node]!=cost:continue
 expanded+=1;pt=vec(start.x+ix*step,start.y+iy*step)
 if math.hypot(pt.x-end.x,pt.y-end.y)<step*1.5 and power_clear(pt,end):goal=node;break
 for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
  nxt=(ix+dx,iy+dy);new=cost+step*math.hypot(dx,dy)
  if new>mm(16) or new>=dist.get(nxt,float('inf')):continue
  q=vec(start.x+nxt[0]*step,start.y+nxt[1]*step)
  if power_clear(pt,q):dist[nxt]=new;prev[nxt]=node;heapq.heappush(queue,(new+math.hypot(q.x-end.x,q.y-end.y),new,*nxt))
print('Power detour search',expanded,'nodes',time.monotonic()-began,'seconds',flush=True)
if goal is None:raise SystemExit(3)
nodes=[goal]
while nodes[-1]!=(0,0):nodes.append(prev[nodes[-1]])
nodes.reverse();simple=[nodes[0]]
for i in range(1,len(nodes)-1):
 n0,n1,n2=nodes[i-1:i+2]
 if (n1[0]-n0[0],n1[1]-n0[1])!=(n2[0]-n1[0],n2[1]-n1[1]):simple.append(n1)
simple.append(nodes[-1]);path=[vec(start.x+x*step,start.y+y*step) for x,y in simple]+[end]
power_added=[]
for i,(s,e) in enumerate(zip(path,path[1:])):
 if s==e:continue
 t=p.PCB_TRACK(b);t.SetStart(s);t.SetEnd(e);t.SetWidth(500000);t.SetLayer(p.B_Cu);t.SetNet(b.FindNet('+3.3V'));t.SetLocked(True)
 t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/rx7-power-detour/%d/%d/%d/%d/%d'%(i,s.x,s.y,e.x,e.y)))))
 b.Add(t);power_added.append(m.uid(t))
after=m.connectivity(b);assert before['disconnectedNetGroups']==after['disconnectedNetGroups']
assert fp_before==m.native_footprints(b) and zones_before=={m.uid(z):m.zone_signature(z) for z in b.Zones()}
now={m.uid(t):m.copper(t) for t in b.GetTracks()};key=m.uid(via)
assert all(now.get(k)==v for k,v in cu_before.items() if k!=key and k not in remove_ids and k not in power_ids)
dest.parent.mkdir(parents=True,exist_ok=True);p.SaveBoard(str(dest),b)
assert m.blocks(raw,'footprint')==m.blocks(dest.read_bytes(),'footprint') and source.read_bytes()==raw
for f in source.parent.iterdir():
 if f.suffix=='.kicad_pro':shutil.copyfile(f,dest.parent/f.name)
 elif f.suffix in ('.kicad_sch','.kicad_sym') or f.name.endswith('lib-table') or f.name in ('libraries','3dmodels','reference','footprints.pretty'):
  (dest.parent/f.name).symlink_to(f.resolve(),target_is_directory=f.is_dir())
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'outputSha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'movedGenericVia':key,'oldMm':[old.x/1e6,old.y/1e6],'newMm':[point.x/1e6,point.y/1e6],'removedGenericFTracks':{k:cu_before[k] for k in sorted(remove_ids)},'added150umTracks':{k:now[k] for k in added},'removedGeneric500umPowerTracks':{k:cu_before[k] for k in sorted(power_ids)},'added500umPowerTracks':{k:now[k] for k in power_added},'allPadPartitionsUnchanged':True,'allUnrelatedCopperPreserved':True,'connectivity':after}
(dest.parent/'rx7-shift-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))

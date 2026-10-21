"""Minimal same-layer detours of generic tracks to free GND stitches."""
from pathlib import Path
from collections import defaultdict
import hashlib,heapq,importlib.util,json,math,time,uuid
import pcbnew as p

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
SOURCE=HERE/'ChryslerScanner_V240_SD.kicad_pcb'
OUTPUT=HERE/'c60-attempt1.kicad_pcb'
raw=SOURCE.read_bytes();mtime=SOURCE.stat().st_mtime_ns
assert hashlib.sha256(raw).hexdigest()=='6a7870d922311723f64d4e48be9a4f853f12c7c44705bfec7105e6da4671d345'
spec=importlib.util.spec_from_file_location('audit',ROOT/'audit-stage/audit_routed_board.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
b=p.LoadBoard(str(SOURCE));before=audit.connectivity(b)
old_copper={audit.uid(t):audit.copper(t) for t in b.GetTracks()}
old_zones={audit.uid(z):audit.zone_signature(z) for z in b.Zones()}
mm=lambda n:round(n*1e6)
vec=lambda q:p.VECTOR2I(mm(q[0]),mm(q[1]))
to_mm=lambda q:[p.ToMM(q.x),p.ToMM(q.y)]
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)

SITES={
 'C60.2':dict(xy=[188.725,133.9],vippo=False,neck=[[189.725,135.4],[188.725,133.9]]),
}
CHAINS=[
 ('C60.2',['00c1b17d-72f3-4bcf-85ab-fe5fc9367a1f']),
 ('C60.2',['c6d6065d-75d9-45bb-8ad5-aef176227016']),
]
tracks={audit.uid(t):t for t in b.GetTracks()}
removed=[]
for _,ids in CHAINS:
 for key in ids:
  t=tracks[key];assert t.GetClass()=='PCB_TRACK' and not t.IsLocked()
  assert t.GetLayer() in (p.F_Cu,p.In2_Cu,p.B_Cu)
  removed.append(t);b.Remove(t)

new=[]
def add_tracks(points,layer,width,net,label,locked=False):
 for a,z in zip(points,points[1:]):
  if a==z:continue
  t=p.PCB_TRACK(b);t.SetStart(a);t.SetEnd(z);t.SetWidth(width);t.SetLayer(layer)
  t.SetNet(b.FindNet(net));t.SetLocked(locked)
  t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler/final-detour/%s/%d/%d/%d/%d/%d'%(label,layer,a.x,a.y,z.x,z.y)))))
  b.Add(t);new.append(t)

for label,site in SITES.items():
 q=p.PCB_VIA(b);q.SetPosition(vec(site['xy']));q.SetWidth(mm(.6));q.SetDrill(mm(.3))
 q.SetLayerPair(p.F_Cu,p.B_Cu);q.SetViaType(p.VIATYPE_THROUGH);q.SetNet(b.FindNet('GND'));q.SetLocked(True)
 q.SetFrontTentingMode(p.TENTING_MODE_TENTED);q.SetBackTentingMode(p.TENTING_MODE_TENTED)
 q.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler/final-ground/%s'%label))))
 if site['vippo']:q.SetPrimaryDrillFilledFlag(True);q.SetPrimaryDrillCappedFlag(True)
 b.Add(q);new.append(q)
 if site['neck']:add_tracks([vec(a) for a in site['neck']],p.B_Cu,mm(.25),'GND',label,True)

class Grid:
 def __init__(self):self.items=[];self.cells=defaultdict(set)
 def keys(self,box):
  return [(x,y) for x in range(math.floor(box.GetLeft()/2e6),math.floor(box.GetRight()/2e6)+1)
                for y in range(math.floor(box.GetTop()/2e6),math.floor(box.GetBottom()/2e6)+1)]
 def add(self,item,layer,shape):
  i=len(self.items);self.items.append((item,layer,shape))
  for key in self.keys(shape.BBox(mm(.7))):self.cells[key].add(i)
 def nearby(self,shape):
  ids=set()
  for key in self.keys(shape.BBox(mm(.7))):ids.update(self.cells.get(key,()))
  return [self.items[i] for i in ids]

def grid():
 copper,holes=Grid(),Grid()
 for fp in b.GetFootprints():
  for q in fp.Pads():
   if q.HasDrilledHole():holes.add(q,None,q.GetEffectiveHoleShape())
   for layer in layers:
    if q.IsOnLayer(layer):copper.add(q,layer,q.GetEffectiveShape(layer))
 for t in b.GetTracks():
  if t.GetClass()=='PCB_VIA':holes.add(t,None,t.GetEffectiveHoleShape())
  for layer in layers:
   if t.IsOnLayer(layer):copper.add(t,layer,t.GetEffectiveShape(layer))
 return copper,holes

edges=[d.GetEffectiveShape(p.Edge_Cuts) for d in b.GetDrawings() if d.GetLayer()==p.Edge_Cuts]
keepouts=[z for z in b.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowTracks()]

def route(start,end,layer,width,net):
 copper,holes=grid();step=mm(.1);began=time.monotonic();cache={}
 def clear(a,z):
  key=(a.x,a.y,z.x,z.y)
  if key in cache:return cache[key]
  shape=p.SHAPE_SEGMENT(a,z,width)
  valid=not any(l==layer and item.GetNetname()!=net and p.SHAPE.Collide(shape,s,mm(.155)) for item,l,s in copper.nearby(shape))
  if valid:valid=not any(item.GetNetname()!=net and p.SHAPE.Collide(shape,s,mm(.205)) for item,_,s in holes.nearby(shape))
  if valid:valid=not any(z.IsOnLayer(layer) and p.SHAPE.Collide(shape,z.Outline(),mm(.02)) for z in keepouts)
  if valid:valid=not any(p.SHAPE.Collide(shape,e,mm(.3)) for e in edges)
  cache[key]=valid;return valid
 if clear(start,end):return [start,end],0
 queue=[(math.hypot(end.x-start.x,end.y-start.y),0.0,0,0)];costs={(0,0):0.0};prev={};expanded=0;found=None
 minx,maxx=min(start.x,end.x)-mm(2),max(start.x,end.x)+mm(2)
 miny,maxy=min(start.y,end.y)-mm(2),max(start.y,end.y)+mm(2)
 while queue and expanded<22000 and time.monotonic()-began<15:
  _,cost,ix,iy=heapq.heappop(queue);node=(ix,iy)
  if costs[node]!=cost:continue
  expanded+=1;a=p.VECTOR2I(start.x+ix*step,start.y+iy*step)
  if math.hypot(end.x-a.x,end.y-a.y)<step*1.6 and clear(a,end):found=node;break
  for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
   target=(ix+dx,iy+dy);value=cost+step*math.hypot(dx,dy)
   if value>=costs.get(target,math.inf):continue
   z=p.VECTOR2I(start.x+target[0]*step,start.y+target[1]*step)
   if not(minx<=z.x<=maxx and miny<=z.y<=maxy) or not clear(a,z):continue
   costs[target]=value;prev[target]=node
   heapq.heappush(queue,(value+math.hypot(end.x-z.x,end.y-z.y),value,*target))
 if found is None:raise RuntimeError('No localdetour for %s on%s after%d nodes'%(net,p.LayerName(layer),expanded))
 nodes=[found]
 while nodes[-1]!=(0,0):nodes.append(prev[nodes[-1]])
 nodes.reverse();simple=[nodes[0]]
 for i in range(1,len(nodes)-1):
  a,z,e=nodes[i-1:i+2]
  if (z[0]-a[0],z[1]-a[1])!=(e[0]-z[0],e[1]-z[1]):simple.append(z)
 simple.append(nodes[-1]);points=[p.VECTOR2I(start.x+x*step,start.y+y*step) for x,y in simple]
 if points[-1]!=end:points.append(end)
 return points,expanded

recipes=[]
for label,ids in CHAINS:
 old=[tracks[key] for key in ids];layer=old[0].GetLayer();width=old[0].GetWidth();net=old[0].GetNetname()
 assert all(t.GetLayer()==layer and t.GetWidth()==width and t.GetNetname()==net for t in old)
 start,end=old[0].GetStart(),old[-1].GetEnd()
 if len(old)==1:
  a,z=old[0].GetStart(),old[0].GetEnd();v=vec(SITES[label]['xy'])
  dx,dy=z.x-a.x,z.y-a.y;length=math.hypot(dx,dy)
  projection=max(0,min(length,((v.x-a.x)*dx+(v.y-a.y)*dy)/length))
  lo,hi=max(0,projection-mm(1.4)),min(length,projection+mm(1.4))
  start=p.VECTOR2I(round(a.x+lo*dx/length),round(a.y+lo*dy/length))
  end=p.VECTOR2I(round(a.x+hi*dx/length),round(a.y+hi*dy/length))
  add_tracks([a,start],layer,width,net,label+'-retained-start')
  add_tracks([end,z],layer,width,net,label+'-retained-end')
 points,expanded=route(start,end,layer,width,net)
 add_tracks(points,layer,width,net,label+'-'+net)
 recipes.append({'target':label,'removedUnprotectedUuids':ids,'net':net,'layer':p.LayerName(layer),
                 'widthMm':p.ToMM(width),'newMiddlePathMm':[to_mm(point) for point in points],
                 'searchedNodes':expanded})
 print('detour',net,p.LayerName(layer),len(points),'points',expanded,'nodes',flush=True)

after=audit.connectivity(b)
allowed={key for _,ids in CHAINS for key in ids}
now={audit.uid(t):audit.copper(t) for t in b.GetTracks()}
assert all(now.get(key)==value for key,value in old_copper.items() if key not in allowed)
assert all(not old_copper[key]['locked'] for key in allowed)
assert old_zones=={audit.uid(z):audit.zone_signature(z) for z in b.Zones()}
assert {n:groups for n,groups in before['disconnectedNetGroups'].items() if n!='GND'}==\
       {n:groups for n,groups in after['disconnectedNetGroups'].items() if n!='GND'}
p.SaveBoard(str(OUTPUT),b)
assert audit.blocks(raw,'footprint')==audit.blocks(OUTPUT.read_bytes(),'footprint')
assert SOURCE.read_bytes()==raw and SOURCE.stat().st_mtime_ns==mtime
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidateSha256':hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
 'sourceUnchanged':True,'all263FootprintBlocksUnchanged':True,'all9ZonesUnchanged':True,
 'allSourceCopperExceptNamedUnprotectedTracksUnchanged':True,'recipes':recipes,'groundSites':SITES,
 'before':before,'after':after}
(HERE/'c60-attempt1-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print('Groundgroups',before['ground']['connectedGroupCount'],'→',after['ground']['connectedGroupCount'],
      'airwires',before['fullNativeAirwires'],'→',after['fullNativeAirwires'],flush=True)

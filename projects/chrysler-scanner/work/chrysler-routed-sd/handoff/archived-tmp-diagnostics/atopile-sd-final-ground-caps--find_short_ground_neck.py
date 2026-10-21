from pathlib import Path
from collections import defaultdict
import hashlib,heapq,importlib.util,json,math,time,uuid
import pcbnew as p
HERE=Path('/private/tmp/atopile-sd-final-ground-caps');ROOT=Path('/Users/justinkobely/Documents/Codex/2026-10-13/a/work/chrysler-routed-sd')
SOURCE=HERE/'ChryslerScanner_V240_SD.kicad_pcb';raw=SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='0913aec472e0613652af3d2a674ef223071eb895c6bb0cd65545f8ade68b4d9f'
spec=importlib.util.spec_from_file_location('audit',ROOT/'audit-stage/audit_routed_board.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
b=p.LoadBoard(str(SOURCE));before=audit.connectivity(b)
mm=lambda n:round(n*1e6)
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)
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


pads=[q for fp in b.GetFootprints() for q in fp.Pads()]
q=next(q for fp in b.GetFootprints() if fp.GetReference()=='C26' for q in fp.Pads() if q.GetNumber()=='2');origin=q.GetPosition()
mainpad=next(q for fp in b.GetFootprints() if fp.GetReference()=='C23' for q in fp.Pads() if q.GetNumber()=='2')
mainitems=list(b.GetConnectivity().GetConnectedItems(mainpad))+[mainpad]
mainpoints=[item.GetPosition() for item in mainitems if item.GetClass() in ('PAD','PCB_TRACK','PCB_VIA') and item.IsOnLayer(p.F_Cu)]
regions=[]
for zone in b.Zones():
 if zone.GetIsRuleArea() or zone.GetNetname()!='GND' or not zone.IsOnLayer(p.F_Cu):continue
 poly=zone.GetFilledPolysList(p.F_Cu)
 for i in range(poly.OutlineCount()):
  if not poly.Contains(origin,i) and any(poly.Contains(point,i) for point in mainpoints):regions.append((poly,i))
options=[]
for ix in range(-30,31):
 for iy in range(-30,31):
  distance=math.hypot(ix*.1,iy*.1)
  if distance>3:continue
  point=p.VECTOR2I(origin.x+mm(ix*.1),origin.y+mm(iy*.1))
  if any(poly.Contains(point,i) for poly,i in regions):options.append((distance,ix,iy))
options.sort();print('Connected target regions',len(regions),'targets',len(options),'nearest',options[:6],flush=True)
found=None
# Prefer endpoints spread over the local area rather than repeated attempts in one trapped corridor.
tried=[]
for distance,ix,iy in options:
 if len(tried)>=16:break
 if any(math.hypot(ix-x,iy-y)<4 for x,y in tried):continue
 tried.append((ix,iy));end=p.VECTOR2I(origin.x+mm(ix*.1),origin.y+mm(iy*.1))
 try:
  points,nodes=route(origin,end,p.F_Cu,mm(.15),'GND');found=points
  print('Found GND neck',[(p.ToMM(v.x),p.ToMM(v.y)) for v in points],flush=True);break
 except RuntimeError as error:print(str(error),flush=True)
if not found:raise RuntimeError('No short legal F ground neck')
new=[]
for a,z in zip(found,found[1:]):
 t=p.PCB_TRACK(b);t.SetStart(a);t.SetEnd(z);t.SetWidth(mm(.15));t.SetLayer(p.F_Cu);t.SetNet(b.FindNet('GND'));t.SetLocked(True)
 t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler/C26-ground/%d/%d/%d/%d'%(a.x,a.y,z.x,z.y)))));b.Add(t);new.append(t)
after=audit.connectivity(b);print('Ground',after['ground'],'airwires',after['fullNativeAirwires'],flush=True)
assert after['ground']['connectedGroupCount']==1
assert {n:g for n,g in before['disconnectedNetGroups'].items() if n!='GND'}=={n:g for n,g in after['disconnectedNetGroups'].items() if n!='GND'}
output=HERE/'final/ChryslerScanner_V240_SD.kicad_pcb';output.parent.mkdir(exist_ok=True);p.SaveBoard(str(output),b)
assert audit.blocks(raw,'footprint')==audit.blocks(output.read_bytes(),'footprint')
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidateSha256':hashlib.sha256(output.read_bytes()).hexdigest(),'pointsMm':[[p.ToMM(v.x),p.ToMM(v.y)] for v in found],'widthMm':.15,'lengthMm':sum(math.hypot(a.x-z.x,a.y-z.y)/1e6 for a,z in zip(found,found[1:])),'onlyAddedGroundTracks':True,'before':before,'after':after,'newCopperUuids':[audit.uid(t) for t in new]}
(HERE/'C26-ground-neck-proof.json').write_text(json.dumps(proof,indent=2)+'\n')

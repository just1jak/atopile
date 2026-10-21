from pathlib import Path
from collections import defaultdict
import hashlib,heapq,importlib.util,json,math,time,uuid
import pcbnew as p
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
SOURCE=HERE/'input/ChryslerScanner_V240_SD.kicad_pcb';raw=SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='2f528b2be3fae336cd450178b0b0271a0f80f16cb4a6e65e577221f564d61bb7'
spec=importlib.util.spec_from_file_location('audit',ROOT/'audit-stage/audit_routed_board.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
b=p.LoadBoard(str(SOURCE));before=audit.connectivity(b)
mm=lambda n:round(n*1e6)
vec=lambda q:p.VECTOR2I(mm(q[0]),mm(q[1]))
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
 copper,holes=grid();step=mm(.025);began=time.monotonic();cache={}
 def clear(a,z):
  key=(a.x,a.y,z.x,z.y)
  if key in cache:return cache[key]
  shape=p.SHAPE_SEGMENT(a,z,width)
  valid=not any(l==layer and item.GetNetname()!=net and p.SHAPE.Collide(shape,s,mm(.1501)) for item,l,s in copper.nearby(shape))
  if valid:valid=not any(item.GetNetname()!=net and p.SHAPE.Collide(shape,s,mm(.2001)) for item,_,s in holes.nearby(shape))
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


found=None
for width in (.25,.2,.15):
 for start,end in (([175.525,120.5],[175.525,122.25]),([175.525,120.5],[176.232107,122.957107]),([178.775,121.25],[179.075,125.0]),([178.775,121.25],[181.55,124.25]),([178.775,121.25],[178.8,126.0])):
  try:
   points,nodes=route(vec(start),vec(end),p.F_Cu,mm(width),'GND')
   length=sum(math.hypot(a.x-z.x,a.y-z.y)/1e6 for a,z in zip(points,points[1:]))
   if length>5:print('Reject >5mm GND neck',length,flush=True);continue
   found=(points,width);break
  except RuntimeError as error:print('No neck',width,start,end,str(error),flush=True)
 if found:break
if not found:raise RuntimeError('No <=5mm ground neck to existing connected reference')
points,width=found
new=[]
for aa,zz in zip(points,points[1:]):
 t=p.PCB_TRACK(b);t.SetStart(aa);t.SetEnd(zz);t.SetWidth(mm(width));t.SetLayer(p.F_Cu);t.SetNet(b.FindNet('GND'));t.SetLocked(True)
 t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler/C31-to-C28-GND/%d/%d/%d/%d'%(aa.x,aa.y,zz.x,zz.y)))));b.Add(t);new.append(t)
after=audit.connectivity(b)
assert set(after['ground']['isolatedFromMainGroup'])=={'C23.2','C26.2'}
assert {n:g for n,g in before['disconnectedNetGroups'].items() if n!='GND'}=={n:g for n,g in after['disconnectedNetGroups'].items() if n!='GND'}
output=HERE/'island-joined/ChryslerScanner_V240_SD.kicad_pcb';output.parent.mkdir(exist_ok=True);p.SaveBoard(str(output),b)
assert audit.blocks(raw,'footprint')==audit.blocks(output.read_bytes(),'footprint')
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidateSha256':hashlib.sha256(output.read_bytes()).hexdigest(),'newPointsMm':[[p.ToMM(q.x),p.ToMM(q.y)] for q in points],'widthMm':width,'lengthMm':sum(math.hypot(a.x-z.x,a.y-z.y)/1e6 for a,z in zip(points,points[1:])),'onlyAddedGroundTracks':True,'newCopperUuids':[audit.uid(t) for t in new],'before':before,'after':after}
(HERE/'island-neck-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'points':proof['newPointsMm'],'lengthMm':proof['lengthMm'],'ground':after['ground'],'airwires':after['fullNativeAirwires']},indent=2),flush=True)

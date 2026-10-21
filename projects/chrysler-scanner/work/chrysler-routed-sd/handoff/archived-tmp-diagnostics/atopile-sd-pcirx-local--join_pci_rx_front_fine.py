from pathlib import Path
from collections import defaultdict
import hashlib,heapq,importlib.util,json,math,time,uuid
import pcbnew as p
HERE=Path('/private/tmp/atopile-sd-pcirx-local');HERE.mkdir(exist_ok=True)
ROOT=Path('/Users/justinkobely/Documents/Codex/2026-10-13/a/work/chrysler-routed-sd')
SOURCE=Path('/private/tmp/atopile-sd-c26-anchor/ChryslerScanner_V240_SD.kicad_pcb');raw=SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='eb42e88dbe9110808eab571d71b5f4ebb297e4fcf9ebac5f767cb7e36bf371c8'
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


net='PCI_RX';copper,holes=grid();pads=[q for f in b.GetFootprints() for q in f.Pads() if q.GetAttribute()==p.PAD_ATTRIB_SMD]
options=[]
for ix in range(0,101):
 point=p.VECTOR2I(mm(170.0-ix*.05),mm(121.0216));circle=p.SHAPE_CIRCLE(point,mm(.3))
 if any(item.GetNetname()!=net and p.SHAPE.Collide(circle,s,mm(.1505)) for item,l,s in copper.nearby(circle)):continue
 if any(p.SHAPE.Collide(circle,s,mm(.2005)) for item,l,s in holes.nearby(circle)):continue
 if any(p.SHAPE.Collide(circle,q.GetEffectiveShape(q.GetLayer()),mm(.1)) for q in pads if abs(q.GetPosition().x-point.x)<mm(2) and abs(q.GetPosition().y-point.y)<mm(2)):continue
 if any(z.GetIsRuleArea() and z.GetDoNotAllowVias() and p.SHAPE.Collide(circle,z.Outline(),mm(.02)) for z in b.Zones()):continue
 options.append(point)
print('Legal PCI_RX transition sites',len(options),[(p.ToMM(q.x),p.ToMM(q.y)) for q in options[:10]],flush=True)
start=vec([172.9878,119.9911]);found=None
for end in options:
 try:
  points,nodes=route(start,end,p.F_Cu,mm(.15),net);found=(end,points);break
 except RuntimeError as error:print(str(error),flush=True)
if not found:raise RuntimeError('No local via transition solution')
end,points=found
removed=[]
for key in ('df3dd8c1-dc62-47a5-bf60-ab1b06dbb49a','37ff9221-8ee4-44ec-8a9a-f05b50565763'):
 t=next(t for t in b.GetTracks() if audit.uid(t)==key);assert not t.IsLocked();removed.append(audit.uid(t));b.Remove(t)
retained=next(t for t in b.GetTracks() if t.GetNetname()==net and t.GetClass()=='PCB_TRACK' and t.GetLayer()==p.B_Cu and t.GetStart()==vec([170.05,121.0216]))
assert not retained.IsLocked();modified=audit.uid(retained);retained.SetStart(end)
via=p.PCB_VIA(b);via.SetPosition(end);via.SetWidth(mm(.6));via.SetDrill(mm(.3));via.SetLayerPair(p.F_Cu,p.B_Cu);via.SetViaType(p.VIATYPE_THROUGH);via.SetNet(b.FindNet(net));via.SetLocked(True)
via.SetFrontTentingMode(p.TENTING_MODE_TENTED);via.SetBackTentingMode(p.TENTING_MODE_TENTED);via.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler/C26-PCIRX-transition'))));b.Add(via)
for aa,zz in zip(points,points[1:]):
 t=p.PCB_TRACK(b);t.SetStart(aa);t.SetEnd(zz);t.SetWidth(mm(.15));t.SetLayer(p.F_Cu);t.SetNet(b.FindNet(net));t.SetLocked(True)
 t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler/PCIRX-In2/%d/%d/%d/%d'%(aa.x,aa.y,zz.x,zz.y)))));b.Add(t)
after=audit.connectivity(b);assert 'PCI_RX' not in after['disconnectedNetGroups'];assert after['ground']['connectedGroupCount']==1
assert {n:g for n,g in before['disconnectedNetGroups'].items() if n!='PCI_RX'}==after['disconnectedNetGroups']
output=HERE/'ChryslerScanner_V240_SD.kicad_pcb';p.SaveBoard(str(output),b);assert audit.blocks(raw,'footprint')==audit.blocks(output.read_bytes(),'footprint')
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidateSha256':hashlib.sha256(output.read_bytes()).hexdigest(),'removedRedundantPciRxStubs':removed,'shortenedRetainedBTrack':modified,'newViaMm':[p.ToMM(end.x),p.ToMM(end.y)],'newIn2PointsMm':[[p.ToMM(q.x),p.ToMM(q.y)] for q in points],'widthMm':.15,'before':before,'after':after}
(HERE/'pci-rx-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print('PCI_RX joined; remaining',after['fullNativeAirwires'],'ground',after['ground'],flush=True)

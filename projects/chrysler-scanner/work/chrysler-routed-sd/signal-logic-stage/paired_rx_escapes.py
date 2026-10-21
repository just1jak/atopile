"""Reserve native RX7/RX15 pin escapes before restoring displaced soft signals.

This produces a physical prototype, never a routing-complete release. Unchanged
150um clearance is checked again by native KiCad after all replacement copper.
"""
from pathlib import Path
from collections import defaultdict
import hashlib,heapq,importlib.util,json,math,shutil,time,uuid
import pcbnew as p
root=Path(__file__).resolve().parent.parent
source=root/'ground-final-stage/combined/ChryslerScanner_V240_SD.kicad_pcb'
dest=Path('/private/tmp/atopile-sd-paired-rx-escapes/ChryslerScanner_V240_SD.kicad_pcb');assert not dest.exists()
s=importlib.util.spec_from_file_location('paired_audit',root/'audit-stage/audit_routed_board.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
b=p.LoadBoard(str(source));raw=source.read_bytes();before=m.connectivity(b)
assert before['ground']['largestConnectedGroupCount']==175
before_fp=m.native_footprints(b);before_cu={m.uid(t):m.copper(t) for t in b.GetTracks()};before_zones={m.uid(z):m.zone_signature(z) for z in b.Zones()}
mm=lambda n:round(n*1e6);vec=lambda x,y:p.VECTOR2I(round(x),round(y));xy=lambda point:[point.x/1e6,point.y/1e6]
hit=lambda a,b,c:p.SHAPE.Collide(a,b,c)
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)
old_rx7={'29af10c1-f9ab-45e3-a039-e45499efe4ed','d9fdeb72-192e-4d50-86c9-3d4c3cc2fcaf','f8657eb5-bc57-4b8e-9014-e79fc2aff7ef','92559ee8-fd35-41a6-9b11-cc155f43f096'}
power_ids={'c719d16e-1e81-44de-9cc3-2cac617efd43','e42a15df-6938-426d-b053-c3658b3e390f'}
rails={'+3.3V','+5V','+7.5V','GND','VPP','VBB','VBUS'}
class Grid:
 def __init__(self):self.items=[];self.cells=defaultdict(set)
 def cells_for(self,box):return [(x,y) for x in range(math.floor(box.GetLeft()/2e6),math.floor(box.GetRight()/2e6)+1) for y in range(math.floor(box.GetTop()/2e6),math.floor(box.GetBottom()/2e6)+1)]
 def add(self,key,layer,shape):
  i=len(self.items);self.items.append((key,layer,shape))
  for cell in self.cells_for(shape.BBox(mm(.7))):self.cells[cell].add(i)
 def candidates(self,shape):
  ids=set()
  for cell in self.cells_for(shape.BBox(mm(.7))):ids.update(self.cells.get(cell,()))
  return (self.items[i] for i in ids)
fixed=Grid();all_cu=Grid();holes=Grid();soft={}
for f in b.GetFootprints():
 for q in f.Pads():
  if q.HasDrilledHole():holes.add(m.uid(q),q.GetNetname(),q.GetEffectiveHoleShape())
  for layer in layers:
   if q.IsOnLayer(layer):
    key=('pad',m.uid(q),q.GetNetname());sh=q.GetEffectiveShape(layer);fixed.add(key,layer,sh);all_cu.add(key,layer,sh)
for t in b.GetTracks():
 key=m.uid(t)
 if key in old_rx7 or key in power_ids:
  assert not t.IsLocked();continue
 # A prototype may displace generic power as well as generic signals. Every
 # such victim is recorded and MUST be restored before it can be accepted.
 # Existing GND copper remains fixed to preserve the completed plane joins.
 is_fixed=t.IsLocked() or t.GetNetname()=='GND'
 if not is_fixed:soft[key]=t
 if isinstance(t,p.PCB_VIA):holes.add(key,t.GetNetname(),t.GetEffectiveHoleShape())
 for layer in layers:
  if t.IsOnLayer(layer):
   item=('fixed' if is_fixed else 'soft',key,t.GetNetname());sh=t.GetEffectiveShape(layer)
   all_cu.add(item,layer,sh)
   if is_fixed:fixed.add(item,layer,sh)
new_items=[];virtual=[]
def track_shape(a,z,width=.15):return p.SHAPE_SEGMENT(a,z,mm(width))
def fixed_clear(shape,layer,net):
 # Collide() is inclusive at equality; one nanometer below the nominal
 # threshold lets EXACT150um gaps through. Native DRC remains authoritative.
 return not any(l==layer and key[2]!=net and hit(shape,other,149999) for key,l,other in fixed.candidates(shape))
def via_clear(point,net):
 sh=p.SHAPE_CIRCLE(point,300000);drill=p.SHAPE_CIRCLE(point,150000)
 if any(key[2]!=net and hit(sh,other,149999) for key,_,other in fixed.candidates(sh)):return False
 if any(hit(drill,other,249999) for key,n,other in holes.candidates(sh) if key not in soft):return False
 return True
points7=[vec(mm(x),mm(y)) for x,y in [(169.9,138),(170.525,138),(170.6,138.075),(172.425,138.075),(172.5,138.0)]]
point7=points7[-1];point15=vec(mm(173.4),mm(138.425))
for label,point,net in (('RX7',point7,'RX7_BIAS_EN'),('RX15',point15,'RX15_EN')):
 if not via_clear(point,net):
  sh=p.SHAPE_CIRCLE(point,300000)
  print(label,'via blockers',[(key,l) for key,l,other in fixed.candidates(sh) if key[2]!=net and hit(sh,other,149999)],flush=True)
  print(label,'hole blockers',[(key,n) for key,n,other in holes.candidates(sh) if key not in soft and hit(p.SHAPE_CIRCLE(point,150000),other,249999)],flush=True)
  raise SystemExit(2)
for a,z in zip(points7,points7[1:]):
 sh=track_shape(a,z);assert fixed_clear(sh,p.F_Cu,'RX7_BIAS_EN'),'RX7 F escape collides with immutable copper'
 virtual.append(('RX7_BIAS_EN',p.F_Cu,sh));fixed.add(('new','rx7-F','RX7_BIAS_EN'),p.F_Cu,sh)
for layer in layers:
 sh=p.SHAPE_CIRCLE(point7,300000);fixed.add(('new','rx7-via','RX7_BIAS_EN'),layer,sh);virtual.append(('RX7_BIAS_EN',layer,sh))
bridge7=[vec(170656200,138440600),point7]
for a,z in zip(bridge7,bridge7[1:]):
 sh=track_shape(a,z);assert fixed_clear(sh,p.In2_Cu,'RX7_BIAS_EN'),'RX7 In2 bridge hits immutable copper'
 virtual.append(('RX7_BIAS_EN',p.In2_Cu,sh));fixed.add(('new','rx7-In2','RX7_BIAS_EN'),p.In2_Cu,sh)
def maze(start,end,layer,width,net,step,budget,max_len,bounds=None,grid=None):
 grid=grid or fixed;queue=[(math.hypot(end.x-start.x,end.y-start.y),0.,0,0)];distance={(0,0):0.};previous={};began=time.monotonic();count=0
 def clear(a,z):
  sh=track_shape(a,z,width)
  return not any(l==layer and key[2]!=net and hit(sh,other,149999) for key,l,other in grid.candidates(sh))
 while queue and count<200000 and time.monotonic()-began<budget:
  _,cost,ix,iy=heapq.heappop(queue);node=(ix,iy)
  if distance[node]!=cost:continue
  count+=1;pt=vec(start.x+ix*step,start.y+iy*step)
  if math.hypot(pt.x-end.x,pt.y-end.y)<step*1.5 and clear(pt,end):
   nodes=[node]
   while nodes[-1]!=(0,0):nodes.append(previous[nodes[-1]])
   nodes.reverse();chosen=[nodes[0]]
   for i in range(1,len(nodes)-1):
    n0,n1,n2=nodes[i-1:i+2]
    if (n1[0]-n0[0],n1[1]-n0[1])!=(n2[0]-n1[0],n2[1]-n1[1]):chosen.append(n1)
   chosen.append(nodes[-1]);path=[vec(start.x+x*step,start.y+y*step) for x,y in chosen]+[end]
   print('Found',net,'maze',count,'nodes',time.monotonic()-began,'seconds',flush=True);return path
  for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
   nxt=(ix+dx,iy+dy);new=cost+step*math.hypot(dx,dy)
   if new>mm(max_len) or new>=distance.get(nxt,float('inf')):continue
   q=vec(start.x+nxt[0]*step,start.y+nxt[1]*step)
   if bounds and not(bounds[0]<=q.x<=bounds[1] and bounds[2]<=q.y<=bounds[3]):continue
   if clear(pt,q):distance[nxt]=new;previous[nxt]=node;heapq.heappush(queue,(new+math.hypot(q.x-end.x,q.y-end.y),new,*nxt))
 print('No',net,'maze',count,'nodes',time.monotonic()-began,'seconds',flush=True);return None
points15=maze(vec(169900000,138500000),point15,p.F_Cu,.15,'RX15_EN',10000,30,8,(169500000,174800000,137700000,139200000))
assert points15,'No physical RX15 path through immutable pads'
for a,z in zip(points15,points15[1:]):
 sh=track_shape(a,z);virtual.append(('RX15_EN',p.F_Cu,sh));fixed.add(('new','rx15-F','RX15_EN'),p.F_Cu,sh)
for layer in layers:
 sh=p.SHAPE_CIRCLE(point15,300000);virtual.append(('RX15_EN',layer,sh));fixed.add(('new','rx15-via','RX15_EN'),layer,sh)
victims=set()
for net,layer,shape in virtual:
 for key,l,other in all_cu.candidates(shape):
  if key[2]==net or l!=layer or not hit(shape,other,149999):continue
  assert key[0]=='soft',('Immutable collision escaped guard',key,net)
  victims.add(key[1])
print('Displaced soft signal objects',len(victims),flush=True)
remove=old_rx7|power_ids|victims
for t in list(b.GetTracks()):
 if m.uid(t) in remove:assert not t.IsLocked();b.Remove(t)
def add_path(points,net,layer,width,label):
 for i,(a,z) in enumerate(zip(points,points[1:])):
  if a==z:continue
  t=p.PCB_TRACK(b);t.SetStart(a);t.SetEnd(z);t.SetWidth(mm(width));t.SetLayer(layer);t.SetNet(b.FindNet(net));t.SetLocked(True)
  t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/paired-rx/%s/%d/%d/%d/%d/%d'%(label,i,a.x,a.y,z.x,z.y)))))
  b.Add(t);new_items.append(t)
def add_via(point,net,label):
 v=p.PCB_VIA(b);v.SetPosition(point);v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetViaType(p.VIATYPE_THROUGH);v.SetNet(b.FindNet(net));v.SetLocked(True)
 v.SetFrontTentingMode(p.TENTING_MODE_TENTED);v.SetBackTentingMode(p.TENTING_MODE_TENTED);v.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/paired-rx/via/'+label))));b.Add(v);new_items.append(v)
add_path(points7,'RX7_BIAS_EN',p.F_Cu,.15,'rx7F');add_path(bridge7,'RX7_BIAS_EN',p.In2_Cu,.15,'rx7In2');add_via(point7,'RX7_BIAS_EN','rx7')
add_path(points15,'RX15_EN',p.F_Cu,.15,'rx15F');add_via(point15,'RX15_EN','rx15')
# Restore the same .5mm power trunk while avoiding both simultaneously fixed
# signal escapes and all remaining actual copper; power membership must survive.
power=Grid()
for f in b.GetFootprints():
 for q in f.Pads():
  if q.IsOnLayer(p.B_Cu):power.add(('pad',m.uid(q),q.GetNetname()),p.B_Cu,q.GetEffectiveShape(p.B_Cu))
for t in b.GetTracks():
 if t.IsOnLayer(p.B_Cu):power.add(('copper',m.uid(t),t.GetNetname()),p.B_Cu,t.GetEffectiveShape(p.B_Cu))
power_path=maze(vec(167516500,134184400),vec(174835000,138390900),p.B_Cu,.5,'+3.3V',50000,20,16,grid=power)
assert power_path,'No same-width power detour for paired escapes'
add_path(power_path,'+3.3V',p.B_Cu,.5,'power')
after=m.connectivity(b);assert after['ground']['largestConnectedGroupCount']==175
assert m.native_footprints(b)==before_fp and {m.uid(z):m.zone_signature(z) for z in b.Zones()}==before_zones
now={m.uid(t):m.copper(t) for t in b.GetTracks()};assert all(now.get(k)==v for k,v in before_cu.items() if k not in remove)
dest.parent.mkdir(parents=True,exist_ok=True);p.SaveBoard(str(dest),b);assert m.blocks(raw,'footprint')==m.blocks(dest.read_bytes(),'footprint') and source.read_bytes()==raw
for f in source.parent.iterdir():
 if f.suffix=='.kicad_pro':shutil.copyfile(f,dest.parent/f.name)
 elif f.suffix in ('.kicad_sch','.kicad_sym') or f.name.endswith('lib-table') or f.name in ('libraries','3dmodels','reference','footprints.pretty'):
  (dest.parent/f.name).symlink_to(f.resolve(),target_is_directory=f.is_dir())
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidateSha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'rx7ViaMm':xy(point7),'rx15ViaMm':xy(point15),'rx7FPathMm':list(map(xy,points7)),'rx15FPathMm':list(map(xy,points15)),
 'removedCopper':{k:before_cu[k] for k in sorted(remove)},'addedCopper':{m.uid(t):m.copper(t) for t in new_items},'allUnrelatedCopperAndFootprintsPreserved':True,'before':before,'after':after,'requiresFreshNativeDrc':True,'prototypeVictimsMustBeRestoredBeforeAcceptance':True}
(dest.parent/'paired-rx-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print('Prototype',proof['candidateSha256'],'gaps',after['fullNativeAirwires'],flush=True)

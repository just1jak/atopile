"""Read-only native collision search for short power-pad dogbones."""
from pathlib import Path
from collections import defaultdict
import json,math,hashlib,heapq
import pcbnew as p

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'edge-stage/ChryslerScanner_V240_SD.kicad_pcb'
raw=SOURCE.read_bytes();mtime=SOURCE.stat().st_mtime_ns
b=p.LoadBoard(str(SOURCE));mm=lambda x:round(x*1e6)
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)

class Grid:
    def __init__(self):self.items=[];self.cells=defaultdict(set)
    def keys(self,box):
        return [(x,y) for x in range(math.floor(box.GetLeft()/2e6),math.floor(box.GetRight()/2e6)+1)
                      for y in range(math.floor(box.GetTop()/2e6),math.floor(box.GetBottom()/2e6)+1)]
    def add(self,net,layer,shape):
        i=len(self.items);self.items.append((net,layer,shape))
        for key in self.keys(shape.BBox(mm(.7))):self.cells[key].add(i)
    def nearby(self,shape):
        ids=set()
        for key in self.keys(shape.BBox(mm(.7))):ids.update(self.cells.get(key,()))
        return (self.items[i] for i in ids)

copper,holes,apertures=Grid(),Grid(),Grid()
pad_by_label={}
for fp in b.GetFootprints():
    for pad in fp.Pads():
        pad_by_label[fp.GetReference()+'.'+pad.GetNumber()]=pad
        if pad.HasDrilledHole():holes.add(pad.GetNetname(),None,pad.GetEffectiveHoleShape())
        for layer in layers:
            if not pad.IsOnLayer(layer):continue
            shape=pad.GetEffectiveShape(layer)
            copper.add(pad.GetNetname(),layer,shape)
            if pad.GetAttribute()==p.PAD_ATTRIB_SMD:apertures.add(pad.GetNetname(),layer,shape)
for t in b.GetTracks():
    if t.GetClass()=='PCB_VIA':holes.add(t.GetNetname(),None,t.GetEffectiveHoleShape())
    for layer in layers:
        if t.IsOnLayer(layer):copper.add(t.GetNetname(),layer,t.GetEffectiveShape(layer))
keepouts=[z for z in b.Zones() if z.GetIsRuleArea()]
collide=lambda a,z,clearance:p.SHAPE.Collide(a,z,mm(clearance))

def via_clear(net,point):
    shape=p.SHAPE_CIRCLE(point,mm(.3))
    if any(n!=net and collide(shape,s,.155) for n,_,s in copper.nearby(shape)):return False
    if any(collide(shape,s,.205) for _,_,s in holes.nearby(shape)):return False
    if any(collide(shape,s,.10) for _,_,s in apertures.nearby(shape)):return False
    if any(z.GetDoNotAllowVias() and collide(shape,z.Outline(),.02) for z in keepouts):return False
    return True

def neck_clear(net,start,end):
    shape=p.SHAPE_SEGMENT(start,end,mm(.2))
    if any(layer==p.F_Cu and n!=net and collide(shape,s,.155) for n,layer,s in copper.nearby(shape)):return False
    if any(n!=net and collide(shape,s,.205) for n,_,s in holes.nearby(shape)):return False
    if any(z.IsOnLayer(p.F_Cu) and z.GetDoNotAllowTracks() and collide(shape,z.Outline(),.02) for z in keepouts):return False
    return True

offsets=[(x,y) for x in range(-30,31) for y in range(-30,31) if .4<=math.hypot(x*.1,y*.1)<=3.0]
offsets.sort(key=lambda point:point[0]**2+point[1]**2)
result={}
for name in ('U6.5','U19.21','U10.46','U10.43'):
    pad=pad_by_label[name];origin=pad.GetPosition();candidates=[]
    for x,y in offsets:
        point=p.VECTOR2I(origin.x+mm(x*.1),origin.y+mm(y*.1))
        if via_clear(pad.GetNetname(),point) and neck_clear(pad.GetNetname(),origin,point):
            candidates.append({'xy':[p.ToMM(point.x),p.ToMM(point.y)],'neckLengthMm':round(math.hypot(x*.1,y*.1),5)})
        if len(candidates)>=20:break
    # If no straight dogbone exists, search a bounded curved 200um escape.
    queue=[(0.0,0,0)];costs={(0,0):0.0};previous={};found=None;expanded=0
    while queue and expanded<4000:
        cost,ix,iy=heapq.heappop(queue);node=(ix,iy)
        if costs[node]!=cost:continue
        expanded+=1;point=p.VECTOR2I(origin.x+mm(ix*.1),origin.y+mm(iy*.1))
        if cost>=.4 and via_clear(pad.GetNetname(),point):found=node;break
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            target=(ix+dx,iy+dy);newcost=cost+.1*math.hypot(dx,dy)
            if newcost>3.0 or newcost>=costs.get(target,math.inf):continue
            end=p.VECTOR2I(origin.x+mm(target[0]*.1),origin.y+mm(target[1]*.1))
            if not neck_clear(pad.GetNetname(),point,end):continue
            costs[target]=newcost;previous[target]=node;heapq.heappush(queue,(newcost,*target))
    path=[]
    if found:
        nodes=[found]
        while nodes[-1]!=(0,0):nodes.append(previous[nodes[-1]])
        nodes.reverse();simple=[nodes[0]]
        for i in range(1,len(nodes)-1):
            a,z,e=nodes[i-1:i+2]
            if (z[0]-a[0],z[1]-a[1])!=(e[0]-z[0],e[1]-z[1]):simple.append(z)
        simple.append(nodes[-1])
        path=[[p.ToMM(origin.x+mm(x*.1)),p.ToMM(origin.y+mm(y*.1))] for x,y in simple]
    result[name]={'net':pad.GetNetname(),'straight200umNeckToLegal600umVia':candidates,
        'bounded200umDoglegToLegal600umVia':path,'doglegLengthMm':round(costs[found],5) if found else None,
        'expandedGridNodes':expanded}
assert SOURCE.read_bytes()==raw and SOURCE.stat().st_mtime_ns==mtime
report={'sourceSha256':hashlib.sha256(raw).hexdigest(),'sourceUnchanged':True,'note':'Native shape collision preflight only; entire routed connection still needs native DRC','sites':result}
(Path(__file__).resolve().parent/'legal-via-sites.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

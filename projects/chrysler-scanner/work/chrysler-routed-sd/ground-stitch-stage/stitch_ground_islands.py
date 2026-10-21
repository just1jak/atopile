"""Native targeted GND stitching on a new copy; exact input preservation gates."""
from pathlib import Path
from collections import defaultdict
import argparse,hashlib,heapq,importlib.util,json,math,shutil,sys,time,uuid
import pcbnew as p

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('input',type=Path)
ap.add_argument('--output',type=Path,default=HERE/'ground-stitched.kicad_pcb');a=ap.parse_args()
assert a.input.resolve()!=a.output.resolve()
raw=a.input.read_bytes();mtime=a.input.stat().st_mtime_ns
s=importlib.util.spec_from_file_location('audit_helper',ROOT/'audit-stage/audit_routed_board.py')
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
b=p.LoadBoard(str(a.input.resolve()));before_fp=m.native_footprints(b)
before_copper={m.uid(t):m.copper(t) for t in b.GetTracks()}
before_zones={m.uid(z):m.zone_signature(z) for z in b.Zones()}
initial=m.connectivity(b)
mm=lambda n:round(n*1e6)
v=lambda x,y:p.VECTOR2I(round(x),round(y))
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)
pads={m.uid(q):q for f in b.GetFootprints() for q in f.Pads()}
labels={m.uid(q):f.GetReference()+'.'+q.GetNumber() for f in b.GetFootprints() for q in f.Pads()}
parent={m.uid(q):f for f in b.GetFootprints() for q in f.Pads()}
ground={key for key,q in pads.items() if q.GetNetname()=='GND'}
assert len(ground)==175

class Grid:
    def __init__(self):self.items=[];self.cells=defaultdict(set)
    def keys(self,box):
        return [(x,y) for x in range(math.floor(box.GetLeft()/2e6),math.floor(box.GetRight()/2e6)+1)
                     for y in range(math.floor(box.GetTop()/2e6),math.floor(box.GetBottom()/2e6)+1)]
    def add(self,name,layer,shape):
        i=len(self.items);self.items.append((name,layer,shape))
        for key in self.keys(shape.BBox(mm(.65))):self.cells[key].add(i)
    def candidates(self,shape):
        ids=set()
        for key in self.keys(shape.BBox(mm(.65))):ids.update(self.cells.get(key,()))
        return (self.items[i] for i in ids)

copper=Grid();holes=Grid();apertures=Grid()
for key,q in pads.items():
    if q.HasDrilledHole():holes.add(labels[key],q.GetNetname(),q.GetEffectiveHoleShape())
    for layer in layers:
        if not q.IsOnLayer(layer):continue
        shape=q.GetEffectiveShape(layer)
        if q.GetNetname()!='GND':copper.add(labels[key],layer,shape)
        if q.GetAttribute()==p.PAD_ATTRIB_SMD:apertures.add(key,layer,shape)
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):holes.add(m.uid(t),t.GetNetname(),t.GetEffectiveHoleShape())
    if t.GetNetname()!='GND':
        for layer in layers:
            if t.IsOnLayer(layer):copper.add(m.uid(t),layer,t.GetEffectiveShape(layer))
edges=[d.GetEffectiveShape(p.Edge_Cuts) for d in b.GetDrawings() if d.GetLayer()==p.Edge_Cuts]
outline=p.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(outline,False,None,True)
keepouts=[z for z in b.Zones() if z.GetIsRuleArea()]
outer=[z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND' and (z.IsOnLayer(p.F_Cu) or z.IsOnLayer(p.B_Cu))]
inner=[z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND' and z.IsOnLayer(p.In1_Cu)]
assert outer and inner
collide=lambda x,y,c:p.SHAPE.Collide(x,y,c)

def via_clear(point,thermal_pad=None):
    circle=p.SHAPE_CIRCLE(point,mm(.3))
    if not outline.Contains(point):return False
    if any(collide(circle,e,mm(.3)) for e in edges):return False
    if any(z.GetDoNotAllowVias() and collide(circle,z.Outline(),mm(.02)) for z in keepouts):return False
    if any(collide(circle,shape,mm(.17)) for _,_,shape in copper.candidates(circle)):return False
    if any(collide(circle,shape,mm(.22)) for _,_,shape in holes.candidates(circle)):return False
    if any(key!=thermal_pad and collide(circle,shape,mm(.10)) for key,_,shape in apertures.candidates(circle)):return False
    return any(z.GetFilledPolysList(p.In1_Cu).Contains(point) for z in inner)

added=[];thermal=[]
def add_via(point,label,thermal_pad=None):
    q=p.PCB_VIA(b);q.SetPosition(point);q.SetWidth(mm(.6));q.SetDrill(mm(.3))
    q.SetLayerPair(p.F_Cu,p.B_Cu);q.SetViaType(p.VIATYPE_THROUGH);q.SetNet(b.FindNet('GND'));q.SetLocked(True)
    exposed=thermal_pad and labels[thermal_pad] in ('U10.49','U12.29','U19.25','U3.7','U4.7','U8.7')
    q.SetFrontTentingMode(p.TENTING_MODE_NOT_TENTED if exposed else p.TENTING_MODE_TENTED)
    q.SetBackTentingMode(p.TENTING_MODE_TENTED)
    if thermal_pad:q.SetPrimaryDrillFilledFlag(True);q.SetPrimaryDrillCappedFlag(True)
    q.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/ground-stitch/%s/%d/%d'%(label,point.x,point.y)))))
    b.Add(q);holes.add(m.uid(q),'GND',q.GetEffectiveHoleShape())
    entry={'kind':'via','uuid':m.uid(q),'positionMm':[p.ToMM(point.x),p.ToMM(point.y)],
           'diameterMm':.6,'drillMm':.3,'filledCappedThermal':bool(thermal_pad),'target':label}
    added.append(entry)
    if thermal_pad:thermal.append(entry)
    return q

# Required MCU exposed-pad ground: revalidate four sites against the latest
# actual routed copper, allowing only its own exposed-pad aperture overlap.
ep=next(key for key in ground if labels[key]=='U10.49');center=pads[ep].GetPosition()
array=None
for pitch in (1.8,1.4,2.2,1.1):
    for ox,oy in ((0,0),(.25,0),(-.25,0),(0,.25),(0,-.25)):
        points=[v(center.x+mm(ox+dx*pitch/2),center.y+mm(oy+dy*pitch/2)) for dx,dy in ((-1,-1),(1,-1),(-1,1),(1,1))]
        if all(via_clear(point,ep) for point in points):array=points;break
    if array:break
if array:
    for point in array:add_via(point,'U10.49',ep)
else:
    legal=[]
    for ix in range(-5,6):
        for iy in range(-5,6):
            point=v(center.x+mm(ix*.3),center.y+mm(iy*.3))
            if via_clear(point,ep):legal.append(point)
    # Prefer one legal point in each quadrant, allowing the latest In2 tracks
    # to determine exact spacings instead of forcing the earlier symmetricarray.
    quadrants=[]
    for sx,sy in ((-1,-1),(1,-1),(-1,1),(1,1)):
        q=[point for point in legal if (point.x-center.x)*sx>0 and (point.y-center.y)*sy>0]
        q.sort(key=lambda point:(point.x-center.x-sx*mm(.9))**2+(point.y-center.y-sy*mm(.9))**2)
        quadrants.append(q)
    def select(index,chosen):
        if index==4:return chosen
        for point in quadrants[index]:
            if all((point.x-old.x)**2+(point.y-old.y)**2>=mm(.75)**2 for old in chosen):
                found=select(index+1,chosen+[point])
                if found:return found
        return None
    array=select(0,[])
    if not array:
        legal.sort(key=lambda point:(point.x-center.x)**2+(point.y-center.y)**2)
        array=[]
        for point in legal:
            if all((point.x-old.x)**2+(point.y-old.y)**2>=mm(.75)**2 for old in array):array.append(point)
            if len(array)==4:break
    for point in array:add_via(point,'U10.49',ep)
    print('AdaptiveU10thermalviasadded:',len(array),'legalsites:',len(legal),flush=True)
p.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()

def groups():
    pending=set(ground);result=[];c=b.GetConnectivity()
    while pending:
        anchor=next(iter(pending))
        found={m.uid(x) for x in c.GetConnectedItems(pads[anchor])}&ground
        found.add(anchor);result.append(found);pending-=found
    return sorted(result,key=lambda g:(-len(g),sorted(labels[k] for k in g)))

def regions(group):
    result=[]
    for z in outer:
        layer=p.F_Cu if z.IsOnLayer(p.F_Cu) else p.B_Cu;poly=z.GetFilledPolysList(layer)
        for i in range(poly.OutlineCount()):
            if any(pads[key].IsOnLayer(layer) and (poly.Contains(pads[key].GetPosition(),i) or
                   collide(poly.COutline(i),pads[key].GetEffectiveShape(layer),1000)) for key in group):
                result.append((layer,poly,i))
    return result

def points_for(group):
    seen=set()
    for key in sorted(group,key=lambda k:(-pads[k].GetSize().x*pads[k].GetSize().y,labels[k])):
        q=pads[key];pt=q.GetPosition();fc=parent[key].GetPosition()
        preferred=math.atan2(pt.y-fc.y,pt.x-fc.x) if pt!=fc else 0
        for distance in (.8,1.0,1.2,1.5,1.8,2.2,2.7,3.3,4.0):
            for shift in (0,math.pi/4,-math.pi/4,math.pi/2,-math.pi/2,3*math.pi/4,-3*math.pi/4,math.pi):
                angle=preferred+shift;point=v(pt.x+mm(distance)*math.cos(angle),pt.y+mm(distance)*math.sin(angle))
                if (point.x,point.y) not in seen:
                    seen.add((point.x,point.y));yield key,point
        offsets=[(ix,iy) for ix in range(-18,19) for iy in range(-18,19) if 0<ix*ix+iy*iy<=18*18]
        offsets.sort(key=lambda point:point[0]**2+point[1]**2)
        for ix,iy in offsets:
            point=v(pt.x+mm(ix*.2),pt.y+mm(iy*.2))
            if (point.x,point.y) not in seen:
                seen.add((point.x,point.y));yield key,point

def track_clear(points,layer,width=.25):
    for start,end in zip(points,points[1:]):
        if start==end:continue
        shape=p.SHAPE_SEGMENT(start,end,mm(width))
        if any(l==layer and collide(shape,other,mm(.155)) for _,l,other in copper.candidates(shape)):return False
        if any(net!='GND' and collide(shape,hole,mm(.205)) for _,net,hole in holes.candidates(shape)):return False
        if any(z.IsOnLayer(layer) and z.GetDoNotAllowTracks() and collide(shape,z.Outline(),mm(.02)) for z in keepouts):return False
        if any(collide(shape,e,mm(.3)) for e in edges):return False
    return True

def add_tracks(points,layer,label,width=.25):
    for start,end in zip(points,points[1:]):
        if start==end:continue
        t=p.PCB_TRACK(b);t.SetStart(start);t.SetEnd(end);t.SetWidth(mm(width));t.SetLayer(layer)
        t.SetNet(b.FindNet('GND'));t.SetLocked(True)
        t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/gnd-dogbone/%s/%d/%d/%d/%d'%(label,start.x,start.y,end.x,end.y)))))
        b.Add(t);added.append({'kind':'track','uuid':m.uid(t),'target':label,'layer':p.LayerName(layer),
            'startMm':[p.ToMM(start.x),p.ToMM(start.y)],'endMm':[p.ToMM(end.x),p.ToMM(end.y)],'widthMm':width,
            'lengthMm':p.ToMM(t.GetLength())})

def local_maze(group,width,max_length):
    # Bounded local search, not a board autorouter: short8-direction escape
    # from an isolated groundpad to a legally clear plane-via site.
    began=time.monotonic();step=mm(.15)
    for key in sorted(group,key=lambda k:pads[k].GetSize().x*pads[k].GetSize().y):
        if time.monotonic()-began>8:break
        origin=pads[key].GetPosition();layer=p.F_Cu if pads[key].IsOnLayer(p.F_Cu) else p.B_Cu
        queue=[(0.0,0,0)];distance={(0,0):0.0};previous={};expanded=0
        while queue and expanded<3500 and time.monotonic()-began<8:
            cost,ix,iy=heapq.heappop(queue);node=(ix,iy)
            if distance[node]!=cost:continue
            expanded+=1;point=v(origin.x+ix*step,origin.y+iy*step)
            if cost>=mm(.6) and via_clear(point):
                nodes=[node]
                while nodes[-1]!=(0,0):nodes.append(previous[nodes[-1]])
                nodes.reverse();simple=[nodes[0]]
                for i in range(1,len(nodes)-1):
                    a0,a1,a2=nodes[i-1:i+2]
                    if (a1[0]-a0[0],a1[1]-a0[1])!=(a2[0]-a1[0],a2[1]-a1[1]):simple.append(a1)
                simple.append(nodes[-1])
                return layer,[v(origin.x+x*step,origin.y+y*step) for x,y in simple]
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                nxt=(ix+dx,iy+dy);new_cost=cost+step*math.hypot(dx,dy)
                if new_cost>mm(max_length) or new_cost>=distance.get(nxt,float('inf')):continue
                end=v(origin.x+nxt[0]*step,origin.y+nxt[1]*step)
                if not track_clear([point,end],layer,width):continue
                distance[nxt]=new_cost;previous[nxt]=node;heapq.heappush(queue,(new_cost,*nxt))
    return None

failed=[]
pending_groups=groups()[1:]
print('Afterthermalarray,remaininggroundgroups:',len(pending_groups),flush=True)
for group in pending_groups:
    label=','.join(sorted(labels[k] for k in group));legal_regions=regions(group);done=False
    for key,point in points_for(group):
        if not any(poly.Contains(point,index) for _,poly,index in legal_regions):continue
        if via_clear(point):add_via(point,label);done=True;break
    if not done:
        # A ground island can extend beyond a pad's immediate vicinity. Search
        # its actual filled contour before adding any longer escape track.
        for _,poly,index in legal_regions:
            box=poly.COutline(index).BBox();step=mm(.25)
            if box.GetWidth()*box.GetHeight()>mm(30)**2:continue
            sites=[v(x,y) for x in range(box.GetLeft(),box.GetRight()+1,step)
                           for y in range(box.GetTop(),box.GetBottom()+1,step)]
            sites.sort(key=lambda point:min((point.x-pads[k].GetPosition().x)**2+(point.y-pads[k].GetPosition().y)**2 for k in group))
            for point in sites:
                if poly.Contains(point,index) and via_clear(point):
                    add_via(point,label);done=True;break
            if done:break
    if not done:
        # Use existing plane-connected ground vias or main-group pads first;
        # plated same-net drill contact is legitimate, unlike NPTH clearance.
        main=groups()[0]
        destinations=[t.GetPosition() for t in b.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND']
        destinations += [pads[key].GetPosition() for key in main]
        for width,max_length in ((.25,8.0),(.15,2.0)):
            for key in group:
                pad=pads[key];layer=p.F_Cu if pad.IsOnLayer(p.F_Cu) else p.B_Cu;start=pad.GetPosition()
                ends=sorted(destinations,key=lambda pt:(pt.x-start.x)**2+(pt.y-start.y)**2)
                for point in ends:
                    if (point.x-start.x)**2+(point.y-start.y)**2>mm(max_length)**2:break
                    for points in ([start,point],[start,v(start.x,point.y),point],[start,v(point.x,start.y),point]):
                        length=sum(math.hypot(t.x-s.x,t.y-s.y) for s,t in zip(points,points[1:]))
                        if length<=mm(max_length) and track_clear(points,layer,width):
                            add_tracks(points,layer,label,width);done=True;break
                    if done:break
                if done:break
            if done:break
    if not done:
        for key,point in points_for(group):
            if not via_clear(point):continue
            pad=pads[key];layer=p.F_Cu if pad.IsOnLayer(p.F_Cu) else p.B_Cu;start=pad.GetPosition()
            for width,max_length in ((.25,8.0),(.15,2.0)):
                for points in ([start,point],[start,v(start.x,point.y),point],[start,v(point.x,start.y),point]):
                    length=sum(math.hypot(t.x-s.x,t.y-s.y) for s,t in zip(points,points[1:]))
                    if length<=mm(max_length) and track_clear(points,layer,width):
                        add_tracks(points,layer,label,width);add_via(point,label);done=True;break
                if done:break
            if done:break
    if not done:
        for width,max_length in ((.25,6.0),(.15,2.0)):
            found=local_maze(group,width,max_length)
            if found:
                layer,points=found;add_tracks(points,layer,label,width);add_via(points[-1],label)
                done=True;break
    if not done:failed.append(label)
    print(('Stitched ' if done else 'UNRESOLVED ')+label,flush=True)

final=m.connectivity(b)
# Only after outside-pad escape options were exhausted: explicit VIPPO sites.
# Ordinary SMD sites retain tenting on both sides so the original footprint
# soldermask window defines the solderable land; copper filling/capping is
# mandatory anywhere the via barrel overlaps an assembly pad.
for group in groups()[1:]:
    label=','.join(sorted(labels[k] for k in group));chosen=None
    keys=sorted(group,key=lambda k:(labels[k] not in ('U12.29','U19.25'),-pads[k].GetSize().x*pads[k].GetSize().y))
    for key in keys:
        q=pads[key];layer=p.F_Cu if q.IsOnLayer(p.F_Cu) else p.B_Cu
        shape=q.GetEffectiveShape(layer);box=shape.BBox(mm(.2));origin=q.GetPosition();step=mm(.05)
        offsets=[(ix,iy) for ix in range(-math.ceil(box.GetWidth()/2/step),math.ceil(box.GetWidth()/2/step)+1)
                         for iy in range(-math.ceil(box.GetHeight()/2/step),math.ceil(box.GetHeight()/2/step)+1)]
        offsets.sort(key=lambda pt:pt[0]*pt[0]+pt[1]*pt[1])
        for ix,iy in offsets:
            point=v(origin.x+ix*step,origin.y+iy*step)
            # Minimum .10mm annular-copper overlap with the existing pad.
            if collide(p.SHAPE_CIRCLE(point,mm(.2)),shape,0) and via_clear(point,key):
                chosen=(key,point);break
        if chosen:break
    if chosen:
        key,point=chosen;add_via(point,label,key);print('Filled/cappedVIPPO '+label,flush=True)
    else:print('VIPPOsiteblocked '+label,flush=True)
final=m.connectivity(b)
assert m.native_footprints(b)==before_fp
assert {m.uid(z):m.zone_signature(z) for z in b.Zones()}==before_zones
current={m.uid(t):m.copper(t) for t in b.GetTracks()}
assert all(current.get(key)==value for key,value in before_copper.items())
a.output.parent.mkdir(exist_ok=True,parents=True)
shutil.copyfile(a.input.with_suffix('.kicad_pro'),a.output.with_suffix('.kicad_pro'))
shutil.copyfile(ROOT/'design/fp-lib-table',HERE/'fp-lib-table')
for name in ('footprints.pretty','libraries','3dmodels'):
    path=HERE/name
    if not path.exists():path.symlink_to(ROOT/'design'/name,target_is_directory=True)
p.SaveBoard(str(a.output.resolve()),b)
saved=p.LoadBoard(str(a.output.resolve()))
assert m.native_footprints(saved)==before_fp
saved_copper={m.uid(t):m.copper(t) for t in saved.GetTracks()}
assert all(saved_copper.get(key)==value for key,value in before_copper.items())
assert m.blocks(raw,'footprint')==m.blocks(a.output.read_bytes(),'footprint')
by_id={m.uid(t):t for t in saved.GetTracks()};saved_vias=[]
for entry in added:
    if entry['kind']!='via':continue
    q=by_id[entry['uuid']]
    filled=q.GetPrimaryDrillFilledFlag();capped=q.GetPrimaryDrillCappedFlag()
    assert isinstance(filled,bool) and isinstance(capped,bool)
    assert filled==capped==entry['filledCappedThermal']
    saved_vias.append({'uuid':entry['uuid'],'target':entry['target'],'xyMm':entry['positionMm'],
        'filled':filled,'capped':capped,'frontTenting':int(q.GetFrontTentingMode()),
        'backTenting':int(q.GetBackTentingMode())})
assert a.input.read_bytes()==raw and a.input.stat().st_mtime_ns==mtime
report={'source':str(a.input),'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidate':str(a.output),
    'candidateSha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),
    'originalCopperPreserved':len(before_copper),'all263FootprintsPadsNetsAndPlanesPreserved':True,
    'before':initial,'after':final,'added':added,'outsidePadSearchUnresolvedBeforeVIPPO':failed,
    'unresolvedSearchGroups':[','.join(group['pads']) for group in final['disconnectedNetGroups'].get('GND',[])[1:]],
    'savedViaFabricationFlags':saved_vias,'nativeSavedViaFlagsVerified':True,
    'allOriginalFootprintBlocksByteExact':True,
    'neckdownSegments':[x for x in added if x['kind']=='track' and x['widthMm']==.15],
    'thermalViaManufacturingRequirement':'Every listedfilledCappedThermal via is VIPPO and requires filled/copper-capped/planarized fabrication. U10/U12/U19 exposed-pad vias have bottom tenting; other VIPPO sites have both sides tented to retain the original footprint mask land. Do not substitute ordinary open vias.',
    'nativeDRCPending':True}
(HERE/'ground-stitch-proof.json').write_text(json.dumps(report,indent=2)+'\n')
print('FINAL',final['ground'],'airwires',final['fullNativeAirwires'],'added',len(added),flush=True)

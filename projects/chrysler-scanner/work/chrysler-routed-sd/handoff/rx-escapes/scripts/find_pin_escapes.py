"""Add bounded native signal escape anchors to an owned copy, preserving input."""
from pathlib import Path
from collections import defaultdict
import argparse, hashlib, heapq, importlib.util, json, math, shutil, sys, time, uuid
import pcbnew as p

here=Path(__file__).resolve().parent; root=here.parent
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('input',type=Path);ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--diagnose',action='store_true')
ap.add_argument('--targets',default='U10.16,U10.11,U10.6,U10.33,U19.15')
ap.add_argument('--max-length',type=float,default=5.0)
ap.add_argument('--hints',type=Path)
ap.add_argument('--step',type=float,default=.05)
a=ap.parse_args();assert a.input.resolve()!=a.output.resolve()
raw=a.input.read_bytes();source_sha=hashlib.sha256(raw).hexdigest()
rules=json.loads(a.input.with_suffix('.kicad_pro').read_text())['board']['design_settings']['rules']
assert rules['min_track_width']==.15 and rules['min_via_diameter']==.6 and rules['min_through_hole_diameter']==.3
cu_gap=round((rules['min_clearance']+.0005)*1e6)
hole_gap=round((rules['min_hole_clearance']+.0005)*1e6)
hole_to_hole_gap=round((rules['min_hole_to_hole']+.0005)*1e6)
s=importlib.util.spec_from_file_location('escape_audit',root/'audit-stage/audit_routed_board.py')
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
b=p.LoadBoard(str(a.input.resolve()));before=m.native_footprints(b)
before_copper={m.uid(t):m.copper(t) for t in b.GetTracks()}
before_zones={m.uid(z):m.zone_signature(z) for z in b.Zones()}
mm=lambda x:round(x*1e6)
vec=lambda x,y:p.VECTOR2I(round(x),round(y))
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)
collide=lambda x,y,c:p.SHAPE.Collide(x,y,c)
pads={m.uid(q):(f,q) for f in b.GetFootprints() for q in f.Pads()}
outline=p.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(outline,False,None,True)
edges=[d.GetEffectiveShape(p.Edge_Cuts) for d in b.GetDrawings() if d.GetLayer()==p.Edge_Cuts]
keepouts=[z for z in b.Zones() if z.GetIsRuleArea()]
targets=a.targets.split(',');assert 0<a.max_length<=8 and a.step in (.025,.05)
if a.hints:
    raw_hints=json.loads(a.hints.read_text())
    hints={h['reference']+'.'+h['pin']:{'nearbyOwnCopper':[{'kind':'PCB_VIA','start':item['positionMm']} for item in h.get('items',[]) if item['kind']=='via']} for h in raw_hints['hints']}
else:hints=json.loads((here/'pin-hints.json').read_text())['alternate4-native']

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

results=[];added=[]
for label in targets:
    fp,pad=next((f,q) for f,q in pads.values() if f.GetReference()+'.'+q.GetNumber()==label)
    net=pad.GetNetname();origin=pad.GetPosition();layer=p.F_Cu if pad.IsOnLayer(p.F_Cu) else p.B_Cu
    cu=Grid();holes=Grid();apertures=Grid()
    for key,(f,q) in pads.items():
        if q.HasDrilledHole():holes.add(f.GetReference()+'.'+q.GetNumber(),q.GetNetname(),q.GetEffectiveHoleShape())
        for l in layers:
            if not q.IsOnLayer(l):continue
            sh=q.GetEffectiveShape(l)
            if q.GetNetname()!=net:cu.add(f.GetReference()+'.'+q.GetNumber(),l,sh)
            if q.GetAttribute()==p.PAD_ATTRIB_SMD:apertures.add(key,l,sh)
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):holes.add(m.uid(t),t.GetNetname(),t.GetEffectiveHoleShape())
        if t.GetNetname()!=net:
            for l in layers:
                if t.IsOnLayer(l):cu.add(m.uid(t),l,t.GetEffectiveShape(l))
    def via_clear(point,allow_vip=False):
        circle=p.SHAPE_CIRCLE(point,mm(.3));drill=p.SHAPE_CIRCLE(point,mm(.15))
        if not outline.Contains(point):return False
        if any(collide(circle,e,mm(.3005)) for e in edges):return False
        if any(z.GetDoNotAllowVias() and collide(circle,z.Outline(),500) for z in keepouts):return False
        if any(collide(circle,shape,cu_gap) for _,_,shape in cu.candidates(circle)):return False
        for _,n,shape in holes.candidates(circle):
            if collide(drill,shape,hole_to_hole_gap):return False
            if n!=net and collide(circle,shape,hole_gap):return False
        if not allow_vip and any(collide(circle,shape,mm(.0605)) for _,_,shape in apertures.candidates(circle)):return False
        return True
    def track_clear(points):
        for start,end in zip(points,points[1:]):
            if start==end:continue
            sh=p.SHAPE_SEGMENT(start,end,mm(.15))
            if any(l==layer and collide(sh,shape,cu_gap) for _,l,shape in cu.candidates(sh)):return False
            if any(n!=net and collide(sh,shape,hole_gap) for _,n,shape in holes.candidates(sh)):return False
            if any(z.IsOnLayer(layer) and z.GetDoNotAllowTracks() and collide(sh,z.Outline(),500) for z in keepouts):return False
            if any(collide(sh,e,mm(.3005)) for e in edges):return False
        return True
    def length(points):return sum(math.hypot(z.x-x.x,z.y-x.y) for x,z in zip(points,points[1:]))
    def simple_paths(point):
        yield [origin,point]
        yield [origin,vec(origin.x,point.y),point]
        yield [origin,vec(point.x,origin.y),point]
        dx,dy=point.x-origin.x,point.y-origin.y;diag=min(abs(dx),abs(dy))
        for d in (vec(origin.x+math.copysign(diag,dx),origin.y+math.copysign(diag,dy)),
                  vec(point.x-math.copysign(diag,dx),point.y-math.copysign(diag,dy))):
            yield [origin,d,point]
    # Record exact blockers at the first50um step; a fully boxed pin cannot
    # be solved by exploring wider empty space without rerouting a neighbor.
    first_steps=[]
    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
        sh=p.SHAPE_SEGMENT(origin,vec(origin.x+mm(dx*.05),origin.y+mm(dy*.05)),mm(.15))
        first_steps.append({'direction':[dx,dy],'copper':[name for name,l,other in cu.candidates(sh) if l==layer and collide(sh,other,mm(.1505))],
            'drills':[name for name,n,other in holes.candidates(sh) if n!=net and collide(sh,other,mm(.2005))],
            'keepouts':[{ 'uuid':m.uid(z),'name':z.GetZoneName()} for z in keepouts if z.IsOnLayer(layer) and z.GetDoNotAllowTracks() and collide(sh,z.Outline(),500)],
            'edges':sum(collide(sh,e,mm(.3005)) for e in edges)})
    began=time.monotonic();answer=None;vip=False
    hint_vias=[vec(mm(t['start'][0]),mm(t['start'][1])) for t in hints.get(label,{}).get('nearbyOwnCopper',[]) if t['kind']=='PCB_VIA']
    if a.diagnose:
        h=[]
        for point in hint_vias:
            sh=p.SHAPE_CIRCLE(point,mm(.3))
            h.append({'point':[point.x/1e6,point.y/1e6],
                'inside':outline.Contains(point),'edges':sum(collide(sh,e,mm(.3005)) for e in edges),
                'viaKeepouts':[m.uid(z) for z in keepouts if z.GetDoNotAllowVias() and collide(sh,z.Outline(),500)],
                'holeHole':[name for name,n,other in holes.candidates(sh) if collide(p.SHAPE_CIRCLE(point,mm(.15)),other,mm(.2005))],
                'copper':[(name,l) for name,l,other in cu.candidates(sh) if collide(sh,other,mm(.1505))],
                'holeCopper':[name for name,n,other in holes.candidates(sh) if n!=net and collide(sh,other,mm(.2005))],
                'apertures':[key for key,l,other in apertures.candidates(sh) if collide(sh,other,mm(.0605))]})
        print(json.dumps({'pad':label,'firstSteps':first_steps,'hints':h}),flush=True);continue
    radius=round(a.max_length/a.step)
    offsets=[(ix,iy) for ix in range(-radius,radius+1) for iy in range(-radius,radius+1) if 8<=ix*ix+iy*iy<=radius*radius]
    outward=math.atan2(origin.y-fp.GetPosition().y,origin.x-fp.GetPosition().x)
    offsets.sort(key=lambda ij:math.hypot(*ij)+.08*abs(math.atan2(math.sin(math.atan2(ij[1],ij[0])-outward),math.cos(math.atan2(ij[1],ij[0])-outward))))
    points=hint_vias+[vec(origin.x+mm(ix*a.step),origin.y+mm(iy*a.step)) for ix,iy in offsets]
    legal_vias=0;expanded=0
    for point in points:
        if not via_clear(point):continue
        legal_vias+=1
        for path in simple_paths(point):
            if length(path)<=mm(a.max_length) and track_clear(path):answer=path;break
        if answer:break
    # A local 50um lattice can navigate pin escapes without moving obstacles.
    if answer is None:
        step=mm(a.step);dist={(0,0):0.0};prev={};queue=[(0.,0,0)];expanded=0
        while queue and expanded<100000 and time.monotonic()-began<18:
            cost,ix,iy=heapq.heappop(queue);node=(ix,iy)
            if dist[node]!=cost:continue
            expanded+=1;point=vec(origin.x+ix*step,origin.y+iy*step)
            if cost>=mm(.4) and via_clear(point):
                nodes=[node]
                while nodes[-1]!=(0,0):nodes.append(prev[nodes[-1]])
                nodes.reverse();chosen=[nodes[0]]
                for i in range(1,len(nodes)-1):
                    n0,n1,n2=nodes[i-1:i+2]
                    if (n1[0]-n0[0],n1[1]-n0[1])!=(n2[0]-n1[0],n2[1]-n1[1]):chosen.append(n1)
                chosen.append(nodes[-1]);answer=[vec(origin.x+x*step,origin.y+y*step) for x,y in chosen];break
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                nxt=(ix+dx,iy+dy);new=cost+step*math.hypot(dx,dy)
                if new>mm(a.max_length) or new>=dist.get(nxt,float('inf')):continue
                end=vec(origin.x+nxt[0]*step,origin.y+nxt[1]*step)
                if track_clear([point,end]):dist[nxt]=new;prev[nxt]=node;heapq.heappush(queue,(new,*nxt))
    if answer is None:
        for point in points:
            if not via_clear(point,True):continue
            for path in simple_paths(point):
                if length(path)<=mm(a.max_length) and track_clear(path):answer=path;vip=True;break
            if answer:break
    if answer is None:
        results.append({'pad':label,'net':net,'status':'blocked','seconds':time.monotonic()-began,'legalViaCandidates':legal_vias,'expanded':expanded,'firstStepBlockers':first_steps});print(label,'BLOCKED','legalVias',legal_vias,'expanded',expanded,first_steps,flush=True);continue
    for start,end in zip(answer,answer[1:]):
        if start==end:continue
        t=p.PCB_TRACK(b);t.SetStart(start);t.SetEnd(end);t.SetWidth(mm(.15));t.SetLayer(layer);t.SetNet(pad.GetNet());t.SetLocked(True)
        t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/pin-escape/%s/%d/%d/%d/%d'%(label,start.x,start.y,end.x,end.y)))))
        b.Add(t);added.append({'uuid':m.uid(t),**m.copper(t)})
    point=answer[-1];via=p.PCB_VIA(b);via.SetPosition(point);via.SetWidth(mm(.6));via.SetDrill(mm(.3));via.SetLayerPair(p.F_Cu,p.B_Cu);via.SetViaType(p.VIATYPE_THROUGH);via.SetNet(pad.GetNet());via.SetLocked(True)
    via.SetFrontTentingMode(p.TENTING_MODE_TENTED);via.SetBackTentingMode(p.TENTING_MODE_TENTED)
    if vip:via.SetPrimaryDrillFilledFlag(True);via.SetPrimaryDrillCappedFlag(True)
    via.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/pin-escape-via/%s/%d/%d'%(label,point.x,point.y)))))
    b.Add(via);added.append({'uuid':m.uid(via),**m.copper(via),'filled':vip,'capped':vip})
    result={'pad':label,'net':net,'status':'escape_added','viaMm':[p.ToMM(point.x),p.ToMM(point.y)],'pathMm':[[p.ToMM(pt.x),p.ToMM(pt.y)] for pt in answer],'lengthMm':length(answer)/1e6,'widthMm':.15,'filledCappedRequired':vip,'seconds':time.monotonic()-began}
    results.append(result);print(json.dumps(result),flush=True)

if a.diagnose:raise SystemExit(0)
a.output.parent.mkdir(parents=True,exist_ok=True)
for f in a.input.parent.iterdir():
    if f.suffix in ('.kicad_pro','.kicad_sch','.kicad_sym') or f.name.endswith('lib-table'):
        shutil.copyfile(f,a.output.parent/f.name)
for name in ('libraries','footprints.pretty','3dmodels','reference'):
    if not (a.output.parent/name).exists():(a.output.parent/name).symlink_to((root/'design'/name).resolve(),target_is_directory=True)
after_conn=m.connectivity(b);assert m.native_footprints(b)==before
assert all(next((m.copper(t) for t in b.GetTracks() if m.uid(t)==key),None)==value for key,value in before_copper.items())
assert {m.uid(z):m.zone_signature(z) for z in b.Zones()}==before_zones
p.SaveBoard(str(a.output.resolve()),b)
saved=p.LoadBoard(str(a.output.resolve()))
assert m.blocks(raw,'footprint')==m.blocks(a.output.read_bytes(),'footprint')
assert a.input.read_bytes()==raw
proof={'source':str(a.input.resolve()),'sourceSha256':source_sha,'outputSha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'results':results,'added':added,'connectivity':after_conn,'allOriginalCopperAndFootprintsAndZoneDefinitionsPreserved':True}
(a.output.parent/'pin-escape-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print('FINAL',after_conn['fullNativeAirwires'],after_conn['ground'],flush=True)

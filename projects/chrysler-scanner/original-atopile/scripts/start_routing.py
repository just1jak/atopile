"""Create a reviewable first routing pass from native KiCad pad polygons.

Route selected USB and local power connections with clearance-aware 45-degree
paths, then add ground escapes to through vias. This is deliberately a partial
pass. Native KiCad DRC and connectivity, rather than this pathfinder, decide
whether the resulting copper is acceptable.
"""
from pathlib import Path
from collections import defaultdict
import argparse, heapq, itertools, json, math, time
import numpy as np
import shapely
from shapely.geometry import Point, Polygon, LineString, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reference/routing-pass-1'
source=json.loads((ROOT/'reference/v240-netlist.json').read_text())
native=json.loads((OUT/'native-input.json').read_text())
pads=native['pads'];by_pin=defaultdict(list)
assert sum('F.Cu' in p['layers'] for p in pads)>700,'Native pad layers must use canonical KiCad copper IDs'
for p in pads:by_pin[p['ref'],p['number']].append(p)
shapes=[unary_union([Polygon(poly) for poly in p['polygons']]) for p in pads]
tree=STRtree(shapes)
drills=[(p,Point(*p['xy']).buffer(max(p['drill'])/2)) for p in pads if max(p['drill'])>0]
tracks=[];vias=[];results=[];skipped=[]
CLEAR=.155;STEP=.10
keepout=box(*json.loads((ROOT/'reference/layout-plan.json').read_text())['rf_keepout_mm'])
allowed=box(.4,.4,109.6,54.6).difference(keepout.buffer(.15))

def pad(ref,n):return by_pin[ref,str(n)][0]
def xy(p):return tuple(p['xy'])
def effective_net(p):return source['parts'].get(p['ref'],{}).get('pins',{}).get(p['number'],{}).get('net') or p['net']
def obstacles(net,width,layer,bounds):
    region=box(*bounds).buffer(1)
    gs=[]
    for i in tree.query(region):
        p=pads[int(i)]
        if layer not in p['layers'] or effective_net(p)==net:continue
        gs.append(shapes[int(i)].buffer(width/2+CLEAR))
    for p,g in drills:
        if effective_net(p)==net:continue
        if g.intersects(region):gs.append(g.buffer(width/2+.205))
    for t in tracks:
        if t['net']!=net and t['layer']==layer:
            g=LineString(t['points'])
            if g.intersects(region):gs.append(g.buffer((t['width']+width)/2+CLEAR))
    for v in vias:
        if v['net']!=net and region.covers(Point(*v['xy'])):gs.append(Point(*v['xy']).buffer(.3+width/2+CLEAR))
    gs.append(region.difference(allowed))
    return unary_union(gs)

def clear(points,blocked):return not LineString(points).intersects(blocked)
def simple(a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1;d=min(abs(dx),abs(dy))
    options=[[a,b],[a,(b[0],a[1]),b],[a,(a[0],b[1]),b],
             [a,(a[0]+sx*d,a[1]+sy*d),b],
             [a,(b[0]-sx*d,b[1]-sy*d),b]]
    # Prefer orthogonal/45-degree geometry. A direct line is used only if it
    # already follows one of those angles.
    if min(abs(dx),abs(dy),abs(abs(dx)-abs(dy)))>.00001:options.pop(0)
    return [[p for i,p in enumerate(q) if i==0 or math.dist(p,q[i-1])>.000001] for q in options]

def route_path(a,b,net,width,layer='F.Cu',max_margin=7):
    if math.dist(a,b)<.00001:return [a,b]
    for margin in [2.0,4.0,float(max_margin)]:
        bounds=[min(a[0],b[0])-margin,min(a[1],b[1])-margin,max(a[0],b[0])+margin,max(a[1],b[1])+margin]
        blocked=obstacles(net,width,layer,bounds)
        if blocked.covers(Point(*a)) or blocked.covers(Point(*b)):return None
        candidates=[q for q in simple(a,b) if clear(q,blocked)]
        if candidates:return min(candidates,key=lambda q:LineString(q).length)
        x0,y0=math.floor(bounds[0]/STEP)*STEP,math.floor(bounds[1]/STEP)*STEP
        nx,ny=math.ceil((bounds[2]-x0)/STEP)+1,math.ceil((bounds[3]-y0)/STEP)+1
        xx,yy=np.meshgrid(x0+np.arange(nx)*STEP,y0+np.arange(ny)*STEP)
        occupied=shapely.intersects_xy(blocked.buffer(.01),xx,yy)
        def index(p):return (int(round((p[0]-x0)/STEP)),int(round((p[1]-y0)/STEP)))
        def coord(p):return (round(x0+p[0]*STEP,6),round(y0+p[1]*STEP,6))
        start,goal=index(a),index(b)
        if occupied[start[1],start[0]] or occupied[goal[1],goal[0]]:continue
        if not clear([a,coord(start)],blocked) or not clear([coord(goal),b],blocked):continue
        dirs=[(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1)]
        h=lambda p:math.hypot(p[0]-goal[0],p[1]-goal[1])
        costs={(start[0],start[1],8):0};parent={};queue=[(h(start),0,*start,8)];last=None;seen=0
        while queue and seen<180000:
            _,g,x,y,d=heapq.heappop(queue);state=x,y,d
            if g>costs.get(state,float('inf'))+.0001:continue
            if (x,y)==goal:last=state;break
            seen+=1
            for nd,(dx,dy) in enumerate(dirs):
                u,v=x+dx,y+dy
                if not(0<=u<nx and 0<=v<ny) or occupied[v,u]:continue
                if dx and dy and (occupied[y,u] or occupied[v,x]):continue
                ng=g+(math.sqrt(2) if dx and dy else 1)+(.65 if d!=nd and d!=8 else 0)
                ns=u,v,nd
                if ng<costs.get(ns,float('inf')):
                    costs[ns]=ng;parent[ns]=state;heapq.heappush(queue,(ng+h((u,v)),ng,u,v,nd))
        if last is None:continue
        path=[]
        while last in parent:path.append(coord(last[:2]));last=parent[last]
        path=[a]+list(reversed(path+[coord(start)]))+[b]
        # Remove collinear grid points and redundant exact/grid anchors.
        compact=[]
        for p in path:
            if compact and math.dist(p,compact[-1])<.000001:continue
            while len(compact)>1:
                u,v=compact[-2:];cross=(v[0]-u[0])*(p[1]-v[1])-(v[1]-u[1])*(p[0]-v[0])
                if abs(cross)>.000001:break
                compact.pop()
            compact.append(p)
        if clear(compact,blocked):return compact
    return None

def install_path(points,net,width,layer,kind):
    if points and LineString(points).length>.00001:tracks.append({'net':net,'width':width,'layer':layer,'points':[list(p) for p in points],'kind':kind})

def via_options(p,net):
    a=xy(p);options=[]
    # Via centres stay outside solder-pad openings. The first ring is large
    # enough for a 0.6/0.3 mm ordinary through via, with no via-in-pad process.
    for distance in [.9,1.2,1.5,1.8,2.2]:
        for angle in range(0,360,45):
            t=math.radians(angle);q=(round((a[0]+distance*math.cos(t))/.05)*.05,round((a[1]+distance*math.sin(t))/.05)*.05)
            # Put the reversible-contact crossovers behind the connector
            # contact row, preserving the short ESD signal corridor in front.
            if p['ref']=='J2' and p['number'] in ['B6','B7'] and q[0]<103.5:continue
            if not allowed.covers(Point(*q).buffer(.5)):continue
            if any(math.dist(q,v['xy'])<.65 for v in vias):continue
            region=[q[0]-.8,q[1]-.8,q[0]+.8,q[1]+.8]
            if any(obstacles(net,.6,l,region).covers(Point(*q)) for l in ['F.Cu','B.Cu']):continue
            if any(shapes[i].distance(Point(*q))<.35 for i in tree.query(Point(*q).buffer(1))):continue
            path=route_path(a,q,net,.20,max_margin=2)
            if path:options.append((LineString(path).length,q,path))
    return sorted(options,key=lambda q:q[0])[:8]

def connect(a,b,width=.2,kind='local',force_back=False):
    net=effective_net(a);assert net==effective_net(b),(a,b)
    aa,bb=xy(a),xy(b)
    preferred=[]
    if (a['ref'],a['number'],b['ref'],b['number'])==('U11','6','U12','4'):
        preferred=[aa,(96,aa[1]),(95.4,aa[1]-.6),(95.4,22.0),(96,21.4),(103.4,21.4),(bb[0],21.4-(bb[0]-103.4)),bb]
    if (a['ref'],a['number'],b['ref'],b['number'])==('U11','4','U12','5'):
        preferred=[aa,(96.35,aa[1]),(95.75,aa[1]-.6),(95.75,22.144975),(96.144975,21.75),(103.9,21.75),(bb[0],21.75-(bb[0]-103.9)),bb]
    if preferred:
        bounds=LineString(preferred).bounds
        if clear(preferred,obstacles(net,width,'F.Cu',bounds)):
            install_path(preferred,net,width,'F.Cu',kind);results.append({'from':[a['ref'],a['number']],'to':[b['ref'],b['number']],'net':net,'length_mm':round(LineString(preferred).length,4),'layers':['F.Cu'],'kind':kind,'preferred_parallel_USB_geometry':True});return True
    if not force_back:
        path=route_path(aa,bb,net,width)
        if path:
            install_path(path,net,width,'F.Cu',kind);results.append({'from':[a['ref'],a['number']],'to':[b['ref'],b['number']],'net':net,'length_mm':round(LineString(path).length,4),'layers':['F.Cu'],'kind':kind});return True
    if force_back:
        starts,ends=via_options(a,net),via_options(b,net)
        pairs=sorted(itertools.product(starts,ends),key=lambda q:q[0][0]+q[1][0]+math.dist(q[0][1],q[1][1]))
        for start,end in pairs[:30]:
            _,u,front_a=start;_,v,front_b=end
            if math.dist(u,v)<.65:continue
            path=route_path(u,v,net,width,'B.Cu',max_margin=4)
            if not path:continue
            for q in [u,v]:vias.append({'net':net,'xy':list(q),'diameter':.6,'drill':.3,'kind':kind})
            install_path(front_a,net,.20,'F.Cu',kind);install_path(path,net,width,'B.Cu',kind);install_path(front_b,net,.20,'F.Cu',kind)
            results.append({'from':[a['ref'],a['number']],'to':[b['ref'],b['number']],'net':net,'length_mm':round(sum(LineString(q).length for q in [front_a,path,front_b]),4),'layers':['F.Cu','B.Cu'],'kind':kind});return True
    skipped.append({'from':[a['ref'],a['number']],'to':[b['ref'],b['number']],'net':net,'kind':kind,'reason':'No clear local path in this first pass'});return False

done=set()
def pair(ra,na,rb,nb,width=.2,kind='local',force_back=False):
    key=tuple(sorted([(ra,str(na)),(rb,str(nb))]))
    if key in done:return
    if connect(pad(ra,na),pad(rb,nb),width,kind,force_back):done.add(key)

# USB signal routing precedes power fan-out in the dense connector channel.
for a,b in [('B6','1'),('B7','3')]:pair('J2',a,'U11',b,kind='USB reversible contact crossover',force_back=True)
for a,b in [('A6','1'),('A7','3')]:pair('J2',a,'U11',b,kind='USB connector to ESD')
pair('U11','6','U12','4',kind='USB D+ ESD to CP2102')
pair('U11','4','U12','5',kind='USB D- ESD to CP2102')
pair('J2','A5','R102','1',kind='USB CC1 pull-down')
pair('J2','B5','R103','1',kind='USB CC2 pull-down')
pair('U1','2','U1','3',.25,'USB switch VBUS')
pair('U1','2','C2','1',.35,'USB switch input capacitor')
pair('U1','4','C3','1',.35,'USB switch output capacitor')
pair('J2','A9','U11','5',.35,'USB ESD supply')
pair('J2','A4','U1','2',.35,'USB VBUS feed')
pair('J2','A4','J2','A9',.35,'USB VBUS contact bridge')

print(f'USB stage: {len(results)} connected pairs, {len(vias)} crossover vias',flush=True)
plan=json.loads((ROOT/'reference/layout-plan.json').read_text())
power=set(r for g in plan['groups'] if g['id'].startswith('power-') or g['id']=='vehicle-input' for r in g['members'])
usb=set(next(g['members'] for g in plan['groups'] if g['id']=='usb'))
global_rails={'GND','+3.3V','+5V','+12V','+7.5V','VBUS','VBB','VPP'}
# Complete small local power/USB nets with a minimum spanning tree of pads.
for net,terminals in source['nets'].items():
    if net in global_rails:continue
    if not all(r in power|usb for r,n in terminals):continue
    if net.startswith('D') or net.startswith('USB_CC'):continue
    remaining=[pad(r,n) for r,n in terminals]
    if not remaining:continue
    connected=[remaining.pop(0)]
    while remaining:
        a,b=min(itertools.product(connected,remaining),key=lambda ab:math.dist(xy(ab[0]),xy(ab[1])))
        width=.35 if net.startswith(('N_C','N_R2_','N_R14_','N_R11_')) else .20
        pair(a['ref'],a['number'],b['ref'],b['number'],width,'Local power / USB net')
        connected.append(b);remaining.remove(b)
# Explicit close rail/decoupling links, preserving the original placement.
for link in plan['links']:
    a,b=link['part'],link['anchor'];n,m=link['pad'],link['anchor_pad']
    net=source['parts'][a]['pins'][n]['net']
    if net=='GND' or a in ['R23','R24'] or b in ['R22','R23','R24','AE1']:continue
    if a not in power|usb and b not in power|usb:continue
    pair(a,n,b,m,.30 if net in global_rails else .20,'Critical supply / decoupling')
# LDO sense/enable straps are package-local and should stay short.
for r in ['U3','U4','U8']:
    if effective_net(pad(r,'1'))==effective_net(pad(r,'2')):pair(r,'1',r,'2',.25,'LDO output sense')
    pair(r,'4',r,'6',.25,'LDO enable/input')
    pair(r,'3',r,'7',.20,'LDO exposed-pad ground')
    pair(r,'5',r,'7',.20,'Corrected LDO ground pin')

print(f'Power stage: {len(results)} connected pairs',flush=True)
# Add a local ground-plane connection for critical power/USB packages only.
ground_parts=power|usb|{'U10','U19','C26','C27','C28','C29','C30','C31','C32','C33','C45','C46','C56','C57'}
for r in sorted(ground_parts):
    grounds=[pad(r,n) for n,q in source['parts'][r]['pins'].items() if q['net']=='GND']
    for p in grounds:
        if p['drill'][0]>0:continue
        # Avoid duplicate ground vias for pads already near a same-net via.
        shared=False
        for v in vias:
            if v['net']!='GND' or math.dist(v['xy'],xy(p))>=1.7:continue
            path=route_path(xy(p),tuple(v['xy']),'GND',.20,max_margin=2)
            if path:
                install_path(path,'GND',.20,'F.Cu','Shared local ground-plane escape');shared=True;break
        if shared:continue
        choices=via_options(p,'GND')
        if not choices:skipped.append({'ref':r,'pin':p['number'],'kind':'ground via','reason':'No ordinary through-via escape clear of pads'});continue
        length,q,path=choices[0];vias.append({'net':'GND','xy':list(q),'diameter':.6,'drill':.3,'kind':'Local ground-plane escape'})
        install_path(path,'GND',.20,'F.Cu','Local ground-plane escape')

report={'date':'2026-10-19','input_pcb_sha256':native['pcb_sha256'],'routing_complete':False,'tracks':tracks,'vias':vias,'connections':results,'deferred':skipped,
        'routing_clearance_mm':CLEAR,'grid_mm':STEP,'through_via_diameter_drill_mm':[.6,.3],
        'limits':['First routing pass only; native DRC and connectivity must be checked.',
                  'USB geometry uses the provisional stackup; impedance and length matching require review.',
                  'RF matching/feed routing is deliberately deferred.']}
(OUT/'routes.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'Prepared {len(tracks)} route paths, {len(vias)} vias, {len(results)} pad-pair connections; {len(skipped)} deferred',flush=True)

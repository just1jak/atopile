"""Refine an existing, unrouted placement using real pad connectivity.

By default write a candidate JSON, leaving the PCB untouched. --apply installs
that candidate without changing the circuit, package geometry or board outline.
This is placement optimization; distances are proxies, not routed lengths.
"""
from pathlib import Path
from collections import defaultdict
import argparse,copy,csv,hashlib,json,math
import numpy as np
import sexpdata as sx
from shapely.geometry import box,Point
from shapely.affinity import rotate,translate
from pcb_geometry import nodes,one,courtyard,local_courtyard,board_area,board_mechanics

ROOT=Path(__file__).resolve().parents[1]
BOARD=ROOT/'elec/layout/v240/v240.kicad_pcb'
parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--passes',type=int,default=10);args=parser.parse_args()
source=json.loads((ROOT/'reference/v240-netlist.json').read_text())
plan=json.loads((ROOT/'reference/layout-plan.json').read_text())
saved=json.loads((ROOT/'reference/v240-placement.json').read_text())
candidate_path=ROOT/'reference/placement-pass-1-candidate.json'
before_path=ROOT/'reference/placement-pass-1-before.json'
board=sx.loads(BOARD.read_text())
fps={next(q[2] for q in nodes(fp,'property') if q[1]=='Reference'):fp for fp in nodes(board,'footprint')}
refs=list(source['parts']);index={r:i for i,r in enumerate(refs)}
group={r:g['id'] for g in plan['groups'] for r in g['members']}
regions={g['id']:g['bounds_mm'] for g in plan['groups']}
# C16 remains a VPP filter capacitor electrically; locate this parallel VPP
# capacitor at the VBB converter's VIN instead of beside the remote boost.
region_overrides={**plan.get('placement_region_overrides',{}),'C16':'power-vbb'}
anchors=json.loads((ROOT/'reference/mechanical-anchors.json').read_text())
fixed=set(anchors)|{'AE1','U10','C1','SW1','SW2'}
mechanics=board_mechanics();holes=mechanics['mounting_holes_mm'];rf=plan['rf_keepout_mm']
pos=np.array([saved[r]['xy_mm']+[saved[r]['rotation_deg']] for r in refs],float);initial=pos.copy()
pads={r:{str(p[1]):np.array(one(p,'at')[1:3],float) for p in nodes(fps[r],'pad') if p[1]} for r in refs}
angles=np.array([0,90,180,270]);courts={r:local_courtyard(fps[r]) for r in refs}
local_bounds={r:np.array([rotate(courts[r],-a,origin=(0,0)).bounds for a in angles]) for r in refs}
offset={r:{n:np.array([[x*math.cos(math.radians(a))+y*math.sin(math.radians(a)),y*math.cos(math.radians(a))-x*math.sin(math.radians(a))] for a in angles]) for n,(x,y) in pp.items()} for r,pp in pads.items()}
def pin(r,n,placements=None):
    placements=pos if placements is None else placements;i=index[r];x,y,a=placements[i]
    return np.array([x,y])+offset[r][n][int(round(a/90))%4]
def bounds(placements):
    return np.array([local_bounds[r][int(round(a/90))%4]+[x,y,x,y] for r,(x,y,a) in zip(refs,placements)])
occupied=bounds(pos)

# Existing checks remain hard constraints. Added targets cover previously
# unconstrained feedback, local LDO capacitors and USB power-switch capacitors.
edges=[];extra=[]
def edge(r,n,a,m,kind,target,weight=10,hard=False):
    assert source['parts'][r]['pins'][n]['net']==source['parts'][a]['pins'][m]['net'],(r,n,a,m)
    q={'part':r,'pad':n,'anchor':a,'anchor_pad':m,'kind':kind,'target_mm':target,'weight':weight,'hard':hard}
    edges.append(q)
    if not hard:extra.append(q)
for q in plan['links']:
    weight=18 if 'bypass' in q['kind'].lower() or q['kind'].startswith('USB-C') else 8 if q['kind']=='OBD protection' else 12
    edge(q['part'],q['pad'],q['anchor'],q['anchor_pad'],q['kind'],q['max_distance_mm'],weight,True)
for hi,lo,ic in [('R2','R3','U2'),('R8','R9','U5'),('R11','R12','U6'),('R14','R15','U7')]:
    edge(hi,'2',ic,'3','Regulator feedback',3.5,16)
    edge(lo,'1',ic,'3','Regulator feedback',3.5,16)
for r,n,a,m,kind,target in [
 ('C5','2','U2','6','Bootstrap switch return',3.5),('C17','2','U6','6','Bootstrap switch return',3.5),('C21','2','U7','6','Bootstrap switch return',3.5),
 ('C6','1','L1','2','Buck output capacitor',5),('C7','1','U3','6','LDO input capacitor',3.5),('C8','1','U3','1','LDO output capacitor',4),
 ('C9','1','U4','6','LDO input capacitor',3.5),('C10','1','U4','1','LDO output capacitor',4),
 ('D7','2','U5','1','Boost rectifier to switch',4),('C13','1','L2','1','Boost input capacitor',4.5),('C14','1','D7','1','Boost output capacitor',4),
 ('C18','1','L4','2','Buck output capacitor',5),('C19','1','L5','2','Filtered output capacitor',3.5),
 ('C22','1','L6','2','Buck output capacitor',5),('C23','1','U8','6','LDO input capacitor',3.5),('C24','1','U8','1','LDO output capacitor',4),
 ('R16','2','U8','2','LDO feedback',3.5),('R17','1','U8','2','LDO feedback',3.5),
 ('C2','1','U1','2','USB switch input capacitor',3.5),('C3','1','U1','4','USB switch output capacitor',3.5),('C35','1','U12','6','USB bridge bulk bypass',5),
 ('C56','1','U19','21','I/O expander bulk bypass',5)]:
    edge(r,n,a,m,kind,target,12)
edge('C16','1','U6','5','VBB input capacitor',4.5,20)
edge('C16','2','U6','2','Local power ground return',5,8)
lna_pin=next(n for n,p in source['parts']['U10']['pins'].items() if p['net']=='LNA_IN')
for r,n,a,m,target in [('R22','2','U10',lna_pin,3.5),('R24','1','U10',lna_pin,3.5),('R23','1','R22','1',3),('R24','1','R22','2',3)]:
    edge(r,n,a,m,'RF matching proximity',target,20)
# Include the local ground return on the input and catch-diode hot loops.
for r,n,a,m in [('C4','2','U2','2'),('D4','2','U2','2'),('D8','2','U6','2'),('C20','2','U7','2'),('D9','2','U7','2'),('C2','2','U1','1'),('C3','2','U1','1')]:
    edge(r,n,a,m,'Local power ground return',5,6)
edges_by_ref={r:[q for q in edges if r in [q['part'],q['anchor']]] for r in refs}
global_rails={'GND','+3.3V','+5V','+12V','+7.5V','VBUS','VBB','VPP'}
net_terms=[]
for net,endpoints in source['nets'].items():
    if net=='GND':continue
    if net not in global_rails:net_terms.append((net,list(map(tuple,endpoints)),.10))
    for gid in regions:
        pp=[tuple(p) for p in endpoints if group[p[0]]==gid]
        if len(pp)>1:
            weight=.35 if net in global_rails else 1.2
            net_terms.append((net+' / '+gid,pp,weight))
terms_by_ref={r:[t for t in net_terms if any(a==r for a,n in t[1])] for r in refs}
feedback_to_coil={r:l for hi,lo,l in [('R2','R3','L1'),('R8','R9','L2'),('R11','R12','L4'),('R14','R15','L6'),('R16','R17','L6')] for r in [hi,lo]}

def candidate(r,ignore=()):
    i=index[r];x0,y0,x1,y1=regions[region_overrides.get(r,group[r])];rows=[]
    for ai,a in enumerate(angles):
        u0,v0,u1,v1=local_bounds[r][ai]
        xs=np.arange(math.ceil((x0-u0)/.25),math.floor((x1-u1)/.25)+1)*.25
        ys=np.arange(math.ceil((y0-v0)/.25),math.floor((y1-v1)/.25)+1)*.25
        if not len(xs) or not len(ys):continue
        xx,yy=np.meshgrid(xs,ys);rows.append(np.column_stack([xx.ravel(),yy.ravel(),np.full(xx.size,ai)]))
    c=np.concatenate(rows);bb=local_bounds[r][c[:,2].astype(int)]+c[:,[0,1,0,1]]
    good=np.ones(len(c),bool);gap=.2
    for j,ob in enumerate(occupied):
        if i==j or refs[j] in ignore:continue
        good&=~((bb[:,0]<ob[2]+gap-1e-7)&(bb[:,2]>ob[0]-gap+1e-7)&(bb[:,1]<ob[3]+gap-1e-7)&(bb[:,3]>ob[1]-gap+1e-7))
    for hx,hy in holes:
        dx=np.maximum.reduce([bb[:,0]-hx,hx-bb[:,2],np.zeros(len(bb))]);dy=np.maximum.reduce([bb[:,1]-hy,hy-bb[:,3],np.zeros(len(bb))]);good&=dx*dx+dy*dy>=3.5**2-1e-7
    good&=~((bb[:,0]<rf[2])&(bb[:,2]>rf[0])&(bb[:,1]<rf[3])&(bb[:,3]>rf[1]))
    # Put the feedback network on the quiet side, separated from inductors.
    pairs=[(r,feedback_to_coil[r])] if r in feedback_to_coil else [(f,r) for f,l in feedback_to_coil.items() if l==r]
    for f,l in pairs:
        ob=occupied[index[l if f==r else f]]
        dx=np.maximum.reduce([bb[:,0]-ob[2],ob[0]-bb[:,2],np.zeros(len(bb))]);dy=np.maximum.reduce([bb[:,1]-ob[3],ob[1]-bb[:,3],np.zeros(len(bb))]);good&=dx*dx+dy*dy>=.75**2-1e-7
    # Always retain the current legal location as an option. Existing gaps
    # can be smaller than the new 0.20 mm candidate spacing target.
    current=pos[i].copy();current[2]=int(round(current[2]/90))%4
    cb=occupied[i]
    current_legal=all(not (cb[0]<ob[2]-1e-7 and cb[2]>ob[0]+1e-7 and cb[1]<ob[3]-1e-7 and cb[3]>ob[1]+1e-7) for j,ob in enumerate(occupied) if j!=i and refs[j] not in ignore)
    return np.vstack([current,c[good]]) if current_legal else c[good]

def score(r,c,ignore_hard=()):
    i=index[r];xy=c[:,:2];ai=c[:,2].astype(int)
    pp={n:xy+v[ai] for n,v in offset[r].items()};s=.012*np.sum((xy-initial[i,:2])**2,axis=1)+.02*(ai!=int(initial[i,2]/90)%4)
    for _,ends,weight in terms_by_ref[r]:
        moving=[pp[n] for a,n in ends if a==r];other=[pin(a,n) for a,n in ends if a!=r]
        pts=np.stack(moving);low=pts.min(axis=0);high=pts.max(axis=0)
        if other:low=np.minimum(low,np.min(other,axis=0));high=np.maximum(high,np.max(other,axis=0))
        s+=weight*np.sum(high-low,axis=1)
    for q in edges_by_ref[r]:
        own=q['part']==r;n=q['pad'] if own else q['anchor_pad'];a=q['anchor'] if own else q['part'];m=q['anchor_pad'] if own else q['pad']
        d=np.linalg.norm(pp[n]-pin(a,m),axis=1);s+=q['weight']*d*d
        if q['hard'] and a not in ignore_hard:s[d>q['target_mm']+.000001]=np.inf
        else:s+=80*np.maximum(d-q['target_mm'],0)**2
    return s

def objective():
    overlap=(occupied[:,None,0]<occupied[None,:,2]-1e-7)&(occupied[:,None,2]>occupied[None,:,0]+1e-7)&(occupied[:,None,1]<occupied[None,:,3]-1e-7)&(occupied[:,None,3]>occupied[None,:,1]+1e-7)
    np.fill_diagonal(overlap,False)
    if np.any(overlap):return float('inf')
    total=.012*float(np.sum((pos[:,:2]-initial[:,:2])**2))+.02*float(np.sum(pos[:,2]!=initial[:,2]))
    for _,ends,weight in net_terms:
        xy=np.array([pin(r,n) for r,n in ends]);total+=weight*float(np.sum(xy.max(axis=0)-xy.min(axis=0)))
    for q in edges:
        d=float(np.linalg.norm(pin(q['part'],q['pad'])-pin(q['anchor'],q['anchor_pad'])))
        if q['hard'] and d>q['target_mm']+.000001:return float('inf')
        total+=q['weight']*d*d
        if not q['hard']:total+=80*max(d-q['target_mm'],0)**2
    return total

def coupled_move(r,a):
    # Two connected parts can exchange occupied space in a single move,
    # avoiding the local minimum of moving just one component at a time.
    ri,ai=index[r],index[a];start=pos.copy();start_bounds=occupied.copy();best=objective();choice=None
    candidates=candidate(r,ignore={a});scores=score(r,candidates,ignore_hard={a})
    order=np.argsort(scores)
    # Include diverse positions/rotations rather than twelve adjacent cells.
    selected=[]
    for j in order:
        if not np.isfinite(scores[j]):continue
        p=candidates[j]
        if any(p[2]==old[2] and np.linalg.norm(p[:2]-old[:2])<.75 for old in selected):continue
        selected.append(p)
        if len(selected)>=16:break
    for p in selected:
        pos[:]=start;occupied[:]=start_bounds
        pos[ri]=[*p[:2],angles[int(p[2])]];occupied[ri]=local_bounds[r][int(p[2])]+p[[0,1,0,1]]
        other=candidate(a)
        if not len(other):continue
        values=score(a,other)
        for j in np.argsort(values)[:3]:
            if not np.isfinite(values[j]):continue
            q=other[j];pos[ai]=[*q[:2],angles[int(q[2])]];occupied[ai]=local_bounds[a][int(q[2])]+q[[0,1,0,1]]
            value=objective()
            if value<best-.001:best=value;choice=(pos.copy(),occupied.copy())
    if choice is None:pos[:]=start;occupied[:]=start_bounds;return False
    pos[:],occupied[:]=choice;return True

def measurements(placements):
    spans=0
    for net,pp in source['nets'].items():
        if net in global_rails:continue
        for gid in regions:
            xy=np.array([pin(r,n,placements) for r,n in pp if group[r]==gid])
            if len(xy)>1:spans+=float(np.sum(xy.max(axis=0)-xy.min(axis=0)))
    return {'local_signal_half_perimeter_sum_mm':round(spans,4),'critical_links':[{'part':q['part'],'pad':q['pad'],'anchor':q['anchor'],'anchor_pad':q['anchor_pad'],'kind':q['kind'],'target_mm':q['target_mm'],'existing_hard_constraint':q['hard'],'distance_mm':round(float(np.linalg.norm(pin(q['part'],q['pad'],placements)-pin(q['anchor'],q['anchor_pad'],placements))),4)} for q in edges]}

if not args.apply:
    rng=np.random.default_rng(240)
    movable=[r for r in refs if r not in fixed]
    for sweep in range(args.passes):
        # Constrain weak power placements first, then visit the remaining parts.
        priority=sorted(movable,key=lambda r:-max([float(np.linalg.norm(pin(q['part'],q['pad'])-pin(q['anchor'],q['anchor_pad'])))/q['target_mm'] for q in edges_by_ref[r]] or [0]))
        if sweep%3==2:rng.shuffle(priority)
        changes=0
        for r in priority:
            c=candidate(r);s=score(r,c);j=int(np.argmin(s))
            if s[j]>=s[0]-.0001:continue
            i=index[r];pos[i]=[*c[j,:2],angles[int(c[j,2])]];occupied[i]=local_bounds[r][int(c[j,2])]+c[j,[0,1,0,1]];changes+=1
        print(f'Placement sweep {sweep+1}: {changes} improving moves',flush=True)
        if not changes:break
    for sweep in range(2):
        changes=0
        for r,a in [('C5','D4'),('C17','D8'),('C17','C16'),('C21','D9'),('U2','L1'),('U5','L2'),('U6','L4'),('U7','L6'),('R2','R3'),('R8','R9'),('R11','R12'),('R14','R15'),('R22','R24'),('U8','C24')]:
            if coupled_move(r,a):changes+=1
        print(f'Coupled placement sweep {sweep+1}: {changes} improving paired moves',flush=True)
        for r in movable:
            c=candidate(r);s=score(r,c);j=int(np.argmin(s))
            if s[j]>=s[0]-.0001:continue
            i=index[r];pos[i]=[*c[j,:2],angles[int(c[j,2])]];occupied[i]=local_bounds[r][int(c[j,2])]+c[j,[0,1,0,1]]
    out={r:{**saved[r],'xy_mm':[round(float(q),6) for q in pos[i,:2]],'rotation_deg':int(pos[i,2]),'courtyard_mm':[float(q) for q in occupied[i]],'reason':'First placement pass: local net spans, feedback/loop and bypass proximity; connector/RF/mechanical anchors retained'} for r,i in index.items()}
    changed=[r for r,i in index.items() if not np.array_equal(pos[i],initial[i])]
    for r in fixed:out[r]=saved[r]
    report={'baseline_pcb_sha256':hashlib.sha256(BOARD.read_bytes()).hexdigest(),'source_netlist_sha256':hashlib.sha256((ROOT/'reference/v240-netlist.json').read_bytes()).hexdigest(),'placement':out,'fixed_references':sorted(fixed),'moved_references':changed,'before':measurements(initial),'after':measurements(pos),'placement_region_overrides':region_overrides,'method':'Deterministic coordinate descent and paired moves, 0.25 mm candidate grid, actual terminal offsets, existing hard distance constraints, 0.20 mm new courtyard spacing, 0.75 mm feedback-to-inductor separation. C16 relocates to the VBB input while retaining its VPP circuit membership. Distances and HPWL are placement proxies, not routed lengths.','routing_complete':False}
    candidate_path.write_text(json.dumps(report,indent=2)+'\n');before_path.write_text(json.dumps(saved,indent=2)+'\n')
    print(f'Candidate: {len(changed)} moved references; local signal HPWL {report["before"]["local_signal_half_perimeter_sum_mm"]} -> {report["after"]["local_signal_half_perimeter_sum_mm"]} mm')
else:
    result=json.loads(candidate_path.read_text());assert result['baseline_pcb_sha256']==hashlib.sha256(BOARD.read_bytes()).hexdigest(),'Candidate baseline changed'
    assert result['source_netlist_sha256']==hashlib.sha256((ROOT/'reference/v240-netlist.json').read_bytes()).hexdigest()
    positions=result['placement']
    for r,p in positions.items():
        fp=fps[r];at=one(fp,'at');old_angle=float(at[3]) if len(at)>3 else 0;angle=p['rotation_deg'];at[1:]=[100+v for v in p['xy_mm']]+[angle]
        fp.remove(at);fp.insert(2,at)
        for pad in nodes(fp,'pad'):
            q=one(pad,'at');old_pad_angle=float(q[3]) if len(q)>3 else old_angle
            if len(q)>3:q[3]=(old_pad_angle+angle-old_angle)%360
            elif angle:q.append(angle)
        p['courtyard_mm']=list(courtyard(fp).bounds)
    # Promote achieved targets to reproducible checks with 0.10 mm rounding room.
    keys={(q['part'],q['pad'],q['anchor'],q['anchor_pad']) for q in plan['links']}
    for q in result['after']['critical_links']:
        key=(q['part'],q['pad'],q['anchor'],q['anchor_pad'])
        if key in keys:continue
        if q['distance_mm']<=q['target_mm']+.001:
            plan['links'].append({k:q[k] for k in ['part','pad','anchor','anchor_pad','kind']}|{'max_distance_mm':q['target_mm']+.1});keys.add(key)
    for g in plan['groups']:
        for r in g['anchors']:g['anchors'][r]=positions[r]['xy_mm']+[positions[r]['rotation_deg']]
    plan['status']='First placement pass, unrouted';plan['placement_pass']='reference/placement-pass-1-candidate.json'
    plan['placement_region_overrides']=result['placement_region_overrides']
    hardware=json.loads((ROOT/'reference/hardware-overrides.json').read_text())
    for r in hardware['placement']:hardware['placement'][r].update(positions[r])
    BOARD.write_text(sx.dumps(board)+'\n')
    for path,data in [('v240-placement.json',positions),('layout-plan.json',plan),('hardware-overrides.json',hardware)]:
        (ROOT/'reference'/path).write_text(json.dumps(data,indent=2)+'\n')
    with (ROOT/'migration.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['V240Reference','Value','FunctionalGroup','PlacementBasis','BoardX_mm','BoardY_mm','Rotation_deg'])
        for r,p in positions.items():w.writerow([r,source['parts'][r]['value'],p['group'],p['reason'],*p['xy_mm'],p['rotation_deg']])
    print(f'Applied {len(result["moved_references"])} reference placements; {len(plan["links"])} physical proximity checks; circuit/packages/outline untouched')

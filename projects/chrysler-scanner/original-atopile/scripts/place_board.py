"""Place V240 functional groups on the configured board outline; never runs implicitly on ato build.

This is an unrouted four-layer layout. Re-running deliberately resets placement.
Group regions and pin-distance constraints are in reference/layout-plan.json.
"""
from pathlib import Path
import json,math,uuid,csv
import sexpdata as sx
from shapely.geometry import box,Point
from shapely.affinity import rotate,translate
ROOT=Path(__file__).resolve().parents[1]
BOARD=ROOT/'elec/layout/v240/v240.kicad_pcb'
data=json.load(open(ROOT/'reference/v240-netlist.json'));parts=data['parts']
old=json.load(open(ROOT/'reference/v140-layout-reference.json'))
plan=json.load(open(ROOT/'reference/layout-plan.json'))
mechanical=json.load(open(ROOT/'reference/mechanical-anchors.json'))
groups={g['id']:g for g in plan['groups']}
groupbyref={r:g for g in plan['groups'] for r in g['members']}
assert set(groupbyref)==set(parts)
def sym(v):return sx.Symbol(v)
def name(e):return str(e[0]) if isinstance(e,list) and e else ''
def nodes(e,k):return [q for q in e if name(q)==k]
def one(e,k):return next((q for q in e if name(q)==k),None)
def setone(e,k,q):
 prev=one(e,k)
 if prev is not None:e.remove(prev)
 e.append(q)
def uid(v):return str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240-migration/'+v))
from pcb_geometry import local_courtyard,board_mechanics
mechanics=board_mechanics();width,height=mechanics["size_mm"]
def rect(fp):return box(*local_courtyard(fp).bounds)
b=sx.loads(BOARD.read_text());fps={};hole_fps={}
setone(one(b,'setup'),'pad_to_mask_clearance',[sym('pad_to_mask_clearance'),.0508])
for fp in nodes(b,'footprint'):
 ref=next(q[2] for q in nodes(fp,'property') if q[1]=='Reference')
 if ref in parts:fps[ref]=fp
 elif ref in ['H1','H2','H3','H4']:hole_fps[ref]=fp
assert set(fps)==set(parts),(set(parts)-set(fps),set(fps)-set(parts))
for r in ['D23','D24','D25','D26']:
 for e in nodes(fps[r],'fp_rect'):
  if one(e,'layer')[1]=='F.CrtYd':one(e,'start')[2]=-1.355;one(e,'end')[2]=1.355
base={r:rect(fp) for r,fp in fps.items()}
holes=mechanics.get('mounting_holes_mm',[(x-9.254,59.254-y) for x,y in old['mounting_holes_mm']])
placed={};occupied=[Point(x,y).buffer(3.5) for x,y in holes]
occupied_bounds=[]
angles=[0,90,180,270]
bounds_by_ref={r:{a:rotate(base[r],-a,origin=(0,0)).bounds for a in angles} for r in parts}
def put(r,x,y,a=0,reason='functional group placement'):
 g=translate(rotate(base[r],-a,origin=(0,0)),x,y)
 placed[r]={'xy_mm':[round(x,6),round(y,6)],'rotation_deg':a,'reason':reason,'group':groupbyref[r]['id'],'courtyard_mm':list(g.bounds)}
 occupied.append(g);occupied_bounds.append(g.bounds)
def padxy(r,n,x=None,y=None,a=None):
 if x is None:
  pp=placed[r];x,y=pp['xy_mm'];a=pp['rotation_deg']
 pad=next(p for p in nodes(fps[r],'pad') if str(p[1])==str(n))
 px,py=one(pad,'at')[1:3];t=math.radians(a)
 return (x+px*math.cos(t)+py*math.sin(t),y-px*math.sin(t)+py*math.cos(t))
for r,p in mechanical.items():put(r,*p['xy_mm'],p['rotation_deg'],p['reason'])
for r in ['SW1','SW2','AE1','U10','R22']:
 x,y,a=groupbyref[r]['anchors'][r];put(r,x,y,a,'fixed functional anchor')
occupied.append(box(*plan['rf_keepout_mm']));occupied_bounds.append(tuple(plan['rf_keepout_mm']))
# Local pin-to-pin costs exclude global rails except explicit capacitor/loop links.
globalnets={'GND','+3.3V','+5V','+12V','+7.5V','VBUS','VBB','VPP'}
netpins={r:{} for r in parts}
for r,p in parts.items():
 for n,v in p['pins'].items():
  if v['net'] and v['net'] not in globalnets:netpins[r].setdefault(v['net'],[]).append(n)
def choose(r,preferred=None):
 group=groupbyref[r];gx0,gy0,gx1,gy1=group['bounds_mm']
 if preferred:tx,ty,preferred_angle=preferred
 else:tx,ty=(gx0+gx1)/2,(gy0+gy1)/2;preferred_angle=0
 direct=[q for q in plan['links'] if q['part']==r and q['anchor'] in placed]
 # Only local circuit nets influence uncritical placement. Cross-group signals
 # are routed later; their average must not scatter passives between groups.
 pairs=[]
 for other in group['members']:
  if other not in placed or other==r:continue
  for net in netpins[r].keys()&netpins[other].keys():
   for n in netpins[r][net]:
    for m in netpins[other][net]:pairs.append((n,padxy(other,m)))
 if direct and not preferred:
  coords=[padxy(q['anchor'],q['anchor_pad']) for q in direct]
  tx=sum(v[0] for v in coords)/len(coords);ty=sum(v[1] for v in coords)/len(coords)
 candidates=[];step=plan['placement_grid_mm'];gap=plan['courtyard_gap_mm']
 for a in ([preferred_angle] if preferred else angles):
  x0,y0,x1,y1=bounds_by_ref[r][a]
  for ix in range(math.ceil((gx0-x0)/step),math.floor((gx1-x1)/step)+1):
   x=round(ix*step,6)
   for iy in range(math.ceil((gy0-y0)/step),math.floor((gy1-y1)/step)+1):
    y=round(iy*step,6)
    bx0,by0,bx1,by1=x+x0-gap,y+y0-gap,x+x1+gap,y+y1+gap
    if any(bx0<qx1 and bx1>qx0 and by0<qy1 and by1>qy0 for qx0,qy0,qx1,qy1 in occupied_bounds):continue
    if any(math.hypot(hx-max(bx0,min(hx,bx1)),hy-max(by0,min(hy,by1)))<3.5 for hx,hy in holes):continue
    score=(1000 if preferred else 1)*((x-tx)**2+(y-ty)**2)+.08*(a!=preferred_angle)
    valid=True
    for q in direct:
     d=math.dist(padxy(r,q['pad'],x,y,a),padxy(q['anchor'],q['anchor_pad']))
     if d>q['max_distance_mm']:valid=False;break
     score+=20*d*d
    if not valid:continue
    for n,xy in pairs:score+=3*math.dist(padxy(r,n,x,y,a),xy)**2/max(1,len(pairs))
    candidates.append((score,x,y,a))
 if not candidates:
  raise RuntimeError(f'No local placement for {r} in {group["id"]}; revise its circuit region/anchors')
 _,x,y,a=min(candidates)
 put(r,x,y,a,('pin-adjacent '+direct[0]['kind']) if direct else 'functional group '+group['label'])
# Active anchors first. Critical bypass/loop parts then get priority over
# feedback/bias passives and bulk caps, rather than being displaced by them.
for gid in ['usb','power-5v','power-vpp','power-vbb','power-7v5','leds','program-6','program-9','program-12','program-14','vehicle-input','obd-protection','ccd','pci','sci-14-9','sci-6-12','sci-rx','control']:
 for r,xyz in groups[gid]['anchors'].items():
  if r not in placed:choose(r,xyz)
critical=list(dict.fromkeys(q['part'] for q in sorted(plan['links'],key=lambda q:0 if q['kind']=='Buck catch diode' else 1)))
for r in critical:
 if r not in placed:choose(r)
for g in plan['groups']:
 remaining=sorted(set(g['members'])-set(placed),key=lambda r:(-base[r].area,0 if r[0] in 'UQ' else 1,r))
 for r in remaining:choose(r)
for r,fp in fps.items():
 p=placed[r];x,y=p['xy_mm'];a=p['rotation_deg']
 old_at=one(fp,'at');old_a=float(old_at[3]) if old_at and len(old_at)>3 else 0
 fp[:]=[e for e in fp if not (name(e)=='pad' and str(e[1])=='' and one(e,'layers') and one(e,'layers')[1:]==['F.Paste']) and name(e)!='locked' and e!=sym('locked')]
 # KiCad stores DNP as an attribute, not as a footprint-level expression.
 fp[:]=[q for q in fp if name(q)!='dnp']
 attr=one(fp,'attr')
 if attr is None:attr=[sym('attr')];fp.append(attr)
 attr[:]=[q for q in attr if q!=sym('dnp')]
 if parts[r]['dnp']:attr.append(sym('dnp'))
 setone(fp,'at',[sym('at'),100+x,100+y,a])
 for q in nodes(fp,'property'):
  if q[1]=='Value':q[2]=parts[r]['value']
 for q in nodes(fp,'fp_text'):
  if str(q[1])=='reference':q[2]=r
  if str(q[1])=='value':q[2]=parts[r]['value']
  if str(q[1]) in ['value','user']:q.append(sym('hide')) if sym('hide') not in q else None
  eff=one(q,'effects')
  if eff:
   font=one(eff,'font')
   if font:setone(font,'size',[sym('size'),.65,.65]);setone(font,'thickness',[sym('thickness'),.1])
 for pad in nodes(fp,'pad'):
  at=one(pad,'at')
  if len(at)==3:at.append(a)
  else:at[3]=(float(at[3])-old_a+a)%360
 # NCs deliberately have no copper-net assignment.
 for pad in nodes(fp,'pad'):
  if not parts[r]['pins'].get(str(pad[1]),{}).get('net'):
   oldnet=one(pad,'net')
   if oldnet:pad.remove(oldnet)
 if r in mechanical:fp.insert(2,sym('locked'))
 # Long single EP paste apertures need a stencil plan, not an unreviewed full square.
 if r in ['U10','U19','U12']:
  for pad in nodes(fp,'pad'):
   if str(pad[1])==str(max(int(n) for n in parts[r]['pins'])):
    lay=one(pad,'layers');lay[:]=[q for q in lay if q!='F.Paste']
    w,h=one(pad,'size')[1:3]
    for dx in [-w/4,w/4]:
     for dy in [-h/4,h/4]:fp.append(sx.loads(f'(pad "" smd rect (at {dx} {dy} {a}) (size {w/2-.2} {h/2-.2}) (layers "F.Paste"))'))
# Remove only migration-generated mechanical geometry, making this script idempotent.
b[:]=[e for e in b if name(e) not in ['gr_line','gr_arc','gr_text','zone'] and not (name(e)=='footprint' and any(q[1]=='Reference' and q[2].startswith('H') for q in nodes(e,'property')))]
def add(s):b.append(sx.loads(s))
for i,(x,y) in enumerate(holes,1):
 fp=hole_fps[f'H{i}'];setone(fp,'at',[sym('at'),100+x,100+y]);fp[:]=[q for q in fp if name(q)!='locked' and q!=sym('locked')];fp.insert(2,sym('locked'));b.append(fp)
x1,y1=100+width,100+height
for a,z in [((102,100),(x1-2,100)),((x1,102),(x1,y1-2)),((x1-2,y1),(102,y1)),((100,y1-2),(100,102))]:add(f'(gr_line (start {a[0]} {a[1]}) (end {z[0]} {z[1]}) (stroke (width .05) (type default)) (layer "Edge.Cuts") (uuid "{uid(str(a))}"))')
for a,m,z in [((100,102),(100.585786,100.585786),(102,100)),((x1-2,100),(x1-.585786,100.585786),(x1,102)),((x1,y1-2),(x1-.585786,y1-.585786),(x1-2,y1)),((102,y1),(100.585786,y1-.585786),(100,y1-2))]:add(f'(gr_arc (start {a[0]} {a[1]}) (mid {m[0]} {m[1]}) (end {z[0]} {z[1]}) (stroke (width .05) (type default)) (layer "Edge.Cuts") (uuid "{uid(str(m))}"))')
add(f'(gr_text "V240 / configured mechanical outline" (at {100+width/2} {100+height+1.5}) (layer "Dwgs.User") (uuid "{uid("title")}") (effects (font (size 1.2 1.2) (thickness .2))))')
add(f'(gr_text "UNROUTED - ENGINEERING REVIEW REQUIRED" (at {100+width/2} {100+height+4}) (layer "Dwgs.User") (uuid "{uid("status")}") (effects (font (size 1 1) (thickness .15))))')
rx0,ry0,rx1,ry1=plan['rf_keepout_mm']
add(f'(zone (net 0) (net_name "") (layers "F.Cu" "In1.Cu" "In2.Cu" "B.Cu") (uuid "{uid("rf-keepout")}") (hatch edge .5) (connect_pads (clearance .5)) (min_thickness .25) (keepout (tracks allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed)) (fill (thermal_gap .5) (thermal_bridge_width .5)) (polygon (pts (xy {100+rx0} {100+ry0}) (xy {100+rx1} {100+ry0}) (xy {100+rx1} {100+ry1}) (xy {100+rx0} {100+ry1}))))')
layers=one(b,'layers')
layers[:]=[layers[0],[0,'F.Cu',sym('signal'),'L1 - Components / critical signals'],[1,'In1.Cu',sym('power'),'L2 - GND'],[2,'In2.Cu',sym('power'),'L3 - Power'],[31,'B.Cu',sym('signal'),'L4 - Signals']]+[q for q in layers[1:] if isinstance(q,list) and int(q[0])>31]
# Nominal 1.6 mm symmetric 4-layer construction, including copper/masks.
# This is a planning stackup, NOT a fabricator impedance specification.
stack=sx.loads('(stackup (layer "F.SilkS" (type "Top Silk Screen")) (layer "F.Paste" (type "Top Solder Paste")) (layer "F.Mask" (type "Top Solder Mask") (color "Black") (thickness 0.01) (material "Solder mask") (epsilon_r 3.3)) (layer "F.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 1" (type "prepreg") (thickness 0.18) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02)) (layer "In1.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 2" (type "core") (thickness 1.08) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02)) (layer "In2.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 3" (type "prepreg") (thickness 0.18) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02)) (layer "B.Cu" (type "copper") (thickness 0.035)) (layer "B.Mask" (type "Bottom Solder Mask") (color "Black") (thickness 0.01) (material "Solder mask") (epsilon_r 3.3)) (layer "B.Paste" (type "Bottom Solder Paste")) (layer "B.SilkS" (type "Bottom Silk Screen")) (copper_finish "ENIG"))')
setone(one(b,'setup'),'stackup',stack)
gnd=next(q for q in nodes(b,'net') if q[2]=='GND')[1]
add(f'(zone (net {gnd}) (net_name "GND") (layer "In1.Cu") (uuid "{uid("l2-ground-plane")}") (name "L2 GND reference - fill after routing") (hatch edge .5) (connect_pads (clearance .25)) (min_thickness .2) (fill yes (thermal_gap .25) (thermal_bridge_width .25)) (polygon (pts (xy 100 100) (xy {x1} 100) (xy {x1} {y1}) (xy 100 {y1}))))')
add(f'(zone (net {gnd}) (net_name "GND") (layer "In2.Cu") (uuid "{uid("l3-rf-ground")}") (name "L3 GND beneath RF feed - provisional") (hatch edge .5) (connect_pads (clearance .25)) (min_thickness .2) (fill yes (thermal_gap .25) (thermal_bridge_width .25)) (polygon (pts (xy {100+rx0} {100+ry1}) (xy {100+rx1} {100+ry1}) (xy {100+rx1} {100+ry1+9.4}) (xy {100+rx0} {100+ry1+9.4}))))')
# Zone definitions intentionally have no invented filled_polygon. KiCad must
# refill them against actual pads/vias/holes after the routing stage.
BOARD.write_text(sx.dumps(b)+'\n')
(ROOT/'reference/v240-placement.json').write_text(json.dumps(placed,indent=2))
with (ROOT/'migration.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['V240Reference','Value','FunctionalGroup','PlacementBasis','BoardX_mm','BoardY_mm','Rotation_deg'])
 for r,p in placed.items():w.writerow([r,parts[r]['value'],p['group'],p['reason'],*p['xy_mm'],p['rotation_deg']])
print(f'Placed {len(placed)} circuit footprints + 4 configured mounting holes; four copper layers; no tracks generated')

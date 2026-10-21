"""Spread the saved 100 x 50 mm placement onto the approved 110 x 55 mm board.

Critical pin-distance pairs move as rigid clusters; pads, rotations, nets,
paste apertures and component models are preserved. No routing is generated.
"""
from pathlib import Path
import csv,json,math,uuid
import sexpdata as sx
from shapely.geometry import box,Point
from shapely.affinity import translate
from shapely.ops import unary_union
from pcb_geometry import name,nodes,one,courtyard,board_area,board_mechanics

ROOT=Path(__file__).resolve().parents[1]
BOARD=ROOT/'elec/layout/v240/v240.kicad_pcb'
base=json.loads((ROOT/'reference/v240-100x50-placement.json').read_text())
hardware=json.loads((ROOT/'reference/hardware-overrides.json').read_text())
if 'J1' in hardware['parts']:
 base['J1'].update({k:hardware['placement']['J1'][k] for k in ['xy_mm','rotation_deg','reason']})
plan=json.loads((ROOT/'reference/layout-plan.json').read_text())
source=json.loads((ROOT/'reference/v240-netlist.json').read_text())
anchor_refs=set(json.loads((ROOT/'reference/mechanical-anchors.json').read_text()))
mechanical=board_mechanics();width,height=mechanical['size_mm']
assert [width,height]==[110,55]
board=sx.loads(BOARD.read_text())
fps={next(q[2] for q in nodes(fp,'property') if q[1]=='Reference'):fp for fp in nodes(board,'footprint')}
# Reset just positions to the preserved baseline, so re-running is idempotent.
for ref,p in base.items():
 fp=fps[ref];at=one(fp,'at');old_angle=float(at[3]) if len(at)>3 else 0
 delta=p['rotation_deg']-old_angle
 at[1:]=[100+v for v in p['xy_mm']]+[p['rotation_deg']]
 for pad in nodes(fp,'pad'):
  position=one(pad,'at')
  if len(position)>3:position[3]=(float(position[3])+delta)%360
shapes={r:courtyard(fps[r]) for r in base}
parents={r:r for r in base}
def parent(r):
 if parents[r]!=r:parents[r]=parent(parents[r])
 return parents[r]
def join(a,b):parents[parent(a)]=parent(b)
for link in plan['links']:
 if link['kind']!='OBD protection':join(link['part'],link['anchor'])
# Keep the recovered OBD/protection positions and their original pin distances.
protected=['J1']+[r for r,p in base.items() if p['group']=='obd-protection']
for ref in protected:join(ref,'J1')
clusters={}
for ref in base:clusters.setdefault(parent(ref),[]).append(ref)
holes=[Point(*p).buffer(3.5) for p in mechanical['mounting_holes_mm']]
rf_shift=6.6
rf=box(59.5+rf_shift,0,72.5+rf_shift,6)
occupied=[];positions={};cluster_ids={}
groups={g['id']:g for g in plan['groups']}
original_plan=json.loads((ROOT/'reference/v240-100x50-layout-plan.json').read_text())
original_groups={g['id']:g for g in original_plan['groups']}
for gid,g in groups.items():
 bounds=original_groups[gid]['bounds_mm']
 if gid in ['obd','obd-protection']:g['bounds_mm']=bounds
 elif gid=='usb':g['bounds_mm']=[bounds[0]+10,bounds[1],bounds[2]+10,height-.7]
 else:g['bounds_mm']=[bounds[0]*1.1,bounds[1]*1.1,bounds[2]*1.1,bounds[3]*1.1]
def desired(refs):
 cx=sum(base[r]['xy_mm'][0] for r in refs)/len(refs)
 cy=sum(base[r]['xy_mm'][1] for r in refs)/len(refs)
 if 'J1' in refs:return 0,0
 if base[refs[0]]['group']=='usb':return 10,(5 if cy>35 else 0)
 if 'AE1' in refs:return rf_shift,0
 return cx*.1,cy*.1
def valid(refs,dx,dy,gap):
 moved=[translate(shapes[r],dx,dy) for r in refs]
 if any(any(g.distance(o)<gap-1e-7 for o in occupied) for g in moved):return False
 if any(any(g.intersects(h) for h in holes) for g in moved):return False
 for r,g in zip(refs,moved):
  if r not in ['J2','J1'] and not board_area().covers(g):return False
  if r!='AE1' and g.intersects(rf):return False
  if r not in anchor_refs|{'AE1'}:
   region=box(*groups[base[r]['group']]['bounds_mm'])
   if not region.buffer(.000001).covers(g):return False
 return True
fixed=[refs for refs in clusters.values() if any(r in refs for r in ['J1','J2','U12','AE1'])]
remaining=[refs for refs in clusters.values() if refs not in fixed]
remaining.sort(key=lambda refs:(-len(refs),-sum(shapes[r].area for r in refs)))
for i,refs in enumerate(fixed+remaining):
 tx,ty=desired(refs)
 candidates=[(0,tx,ty)]
 if refs not in fixed:
  candidates+=sorted((ox*ox+oy*oy,tx+ox*.25,ty+oy*.25) for ox in range(-20,21) for oy in range(-20,21) if ox or oy)
 choice=None
 for gap in ([0] if refs in fixed else [.3,.15]):
  for _,dx,dy in candidates:
   if valid(refs,dx,dy,gap):choice=(dx,dy);break
  if choice is not None:break
 if choice is None:raise RuntimeError(f'Cannot place rigid cluster: {refs}')
 dx,dy=choice
 for r in refs:
  x,y=base[r]['xy_mm'];x=round(x+dx,6);y=round(y+dy,6)
  one(fps[r],'at')[1:3]=[100+x,100+y]
  positions[r]={**base[r],'xy_mm':[x,y],'reason':'Expanded-board spacing; critical pin-distance pairs preserved as rigid clusters','courtyard_mm':list(courtyard(fps[r]).bounds)}
  occupied.append(courtyard(fps[r]));cluster_ids[r]=i
for i,xy in enumerate(mechanical['mounting_holes_mm'],1):one(fps[f'H{i}'],'at')[1:3]=[100+v for v in xy]
# Update fixed anchors, group anchors and explicit USB-C placements.
anchors=json.loads((ROOT/'reference/mechanical-anchors.json').read_text())
for r,p in anchors.items():
 p['xy_mm']=positions[r]['xy_mm'];p['reason']=positions[r]['reason']
anchors['J1']['reason']=base['J1']['reason']
for g in plan['groups']:
 for r in g['anchors']:g['anchors'][r]=positions[r]['xy_mm']+[positions[r]['rotation_deg']]
plan['rf_keepout_mm']=[59.5+rf_shift,0,72.5+rf_shift,6]
plan['expanded_inter_cluster_gap_target_mm']=.3
hardware=json.loads((ROOT/'reference/hardware-overrides.json').read_text())
for r in hardware['placement']:hardware['placement'][r].update(positions[r])
offsets={r:[round(positions[r]['xy_mm'][i]-base[r]['xy_mm'][i],6) for i in [0,1]] for r in ['J1','U12','D23','D24','D25','D26'] if not (r=='J1' and r in hardware['parts'])}
mechanical['gerber_component_offsets_mm']=offsets
# Generate a rounded outline at the original top-left origin and extend L2.
board[:]=[q for q in board if not (name(q) in ['gr_line','gr_arc'] and one(q,'layer')[1]=='Edge.Cuts')]
def uid(v):return str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240-expanded/'+v))
def add(text):board.append(sx.loads(text))
x0,y0,x1,y1=100,100,100+width,100+height;r=2;s=r*(1-1/math.sqrt(2))
for a,z in [((x0+r,y0),(x1-r,y0)),((x1,y0+r),(x1,y1-r)),((x1-r,y1),(x0+r,y1)),((x0,y1-r),(x0,y0+r))]:add(f'(gr_line (start {a[0]} {a[1]}) (end {z[0]} {z[1]}) (stroke (width .05) (type default)) (layer "Edge.Cuts") (uuid "{uid(str(a))}"))')
for a,m,z in [((x0,y0+r),(x0+s,y0+s),(x0+r,y0)),((x1-r,y0),(x1-s,y0+s),(x1,y0+r)),((x1,y1-r),(x1-s,y1-s),(x1-r,y1)),((x0+r,y1),(x0+s,y1-s),(x0,y1-r))]:add(f'(gr_arc (start {a[0]} {a[1]}) (mid {m[0]} {m[1]}) (end {z[0]} {z[1]}) (stroke (width .05) (type default)) (layer "Edge.Cuts") (uuid "{uid(str(m))}"))')
for zone in nodes(board,'zone'):
 pts=one(one(zone,'polygon'),'pts')
 if one(zone,'layer') and one(zone,'layer')[1]=='In1.Cu':pts[1:]=[[sx.Symbol('xy'),x,y] for x,y in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]]
 elif one(zone,'keepout'):pts[1:]=[[sx.Symbol('xy'),100+x,100+y] for x,y in [(66.1,0),(79.1,0),(79.1,6),(66.1,6)]]
 else:pts[1:]=[[sx.Symbol('xy'),100+x,100+y] for x,y in [(66.1,6),(79.1,6),(79.1,15.4),(66.1,15.4)]]
for text in nodes(board,'gr_text'):
 at=one(text,'at');at[1]=155;at[2]=156.5 if 'mechanical reference' in str(text[1]) or 'expanded board' in str(text[1]) else 159
 if 'mechanical reference' in str(text[1]):text[1]='V240 / 110 x 55 mm expanded board'
BOARD.write_text(sx.dumps(board)+'\n')
for filename,value in [('v240-placement.json',positions),('layout-plan.json',plan),('mechanical-anchors.json',anchors),('hardware-overrides.json',hardware),('board-mechanics.json',mechanical)]:
 (ROOT/'reference'/filename).write_text(json.dumps(value,indent=2)+'\n')
with (ROOT/'migration.csv').open('w') as f:
 writer=csv.writer(f);writer.writerow(['V240Reference','Value','FunctionalGroup','PlacementBasis','BoardX_mm','BoardY_mm','Rotation_deg'])
 for r,p in positions.items():writer.writerow([r,source['parts'][r]['value'],p['group'],p['reason'],*p['xy_mm'],p['rotation_deg']])
def gaps(shapes):
 return [g.distance(shapes[s]) for i,(r,g) in enumerate(shapes.items()) for s in list(shapes)[i+1:] if cluster_ids[r]!=cluster_ids[s]]
before=gaps(shapes);after=gaps({r:courtyard(fps[r]) for r in base})
report={'size_before_mm':[100,50],'size_after_mm':[width,height],'area_increase_percent':21,'critical_links_preserved':len(plan['links']),'rigid_clusters':len(clusters),'inter_cluster_neighbors_under_025mm_before':sum(d<.25 for d in before),'inter_cluster_neighbors_under_025mm_after':sum(d<.25 for d in after),'minimum_inter_cluster_gap_mm':round(min(after),4),'original_obd_drill_locations_retained':'J1' not in hardware['parts'],'routing_complete':False}
(ROOT/'reference/board-expansion.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

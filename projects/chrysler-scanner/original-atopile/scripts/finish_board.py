"""Restore mechanical locks and real visible KiCad reference properties.

Run after ato build. Does not move footprints or change nets/tracks/zones.
Labels are placed clear of physical bodies, pad/mask openings and hardware.
"""
from pathlib import Path
import json,math,uuid,hashlib
import sexpdata as sx
from shapely.geometry import box,Point
from shapely.strtree import STRtree
from pcb_geometry import name,nodes,one,courtyard,local_courtyard,board_area,physical_envelope,board_mechanics,layer_outline,transform
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[1]
BOARD=ROOT/'elec/layout/v240/v240.kicad_pcb'
b=sx.loads(BOARD.read_text());source=json.loads((ROOT/'reference/v240-netlist.json').read_text())['parts']
mechanical=json.loads((ROOT/'reference/mechanical-anchors.json').read_text());fixed=set(mechanical)|{'H1','H2','H3','H4'}
fps={next(q[2] for q in nodes(fp,'property') if q[1]=='Reference'):fp for fp in nodes(b,'footprint')}
# Native KiCad applies a late footprint `at` clause to already-read children.
# Keep placement ahead of fields/pads, otherwise their absolute angles rotate
# a second time after a manual package/placement edit.
for fp in fps.values():
 at=one(fp,'at')
 if at is not None:fp.remove(at);fp.insert(2,at)
def sym(v):return sx.Symbol(v)
def setone(e,k,q):
 e[:]=[a for a in e if name(a)!=k];e.append(q)
def uid(v):return str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240-migration/'+v))
def unhide(e):e[:]=[q for q in e if name(q)!='hide' and q!=sym('hide')]
def globalxy(fp,xy):
 at=one(fp,'at');a=math.radians(float(at[3]) if len(at)>3 else 0);u,v=xy
 return (at[1]-100+u*math.cos(a)+v*math.sin(a),at[2]-100-u*math.sin(a)+v*math.cos(a))
def localxy(fp,xy):
 at=one(fp,'at');a=math.radians(float(at[3]) if len(at)>3 else 0);x,y=xy[0]-(at[1]-100),xy[1]-(at[2]-100)
 return (x*math.cos(a)-y*math.sin(a),x*math.sin(a)+y*math.cos(a))
metrics=json.loads((ROOT/'reference/silkscreen-text-metrics.json').read_text())
FONT=metrics['font_height_mm'];WIDTH=metrics['font_width_mm'];STROKE=metrics['stroke_mm'];GAP=metrics['pad_mask_clearance_mm'];LABEL_GAP=metrics['label_clearance_mm']
POLICY=metrics['label_policy_version'];text_bounds=metrics['bounds_mm_by_reference_angle']
assert set(text_bounds)==set(fps)
metrics_hash=hashlib.sha256((ROOT/'reference/silkscreen-text-metrics.json').read_bytes()).hexdigest()
courts={r:courtyard(fp) for r,fp in fps.items()}
allowed=board_area(.3);labels={};boxes=[]
board_width,board_height=board_mechanics()['size_mm']
obstacles=[physical_envelope(fp).buffer(GAP) for fp in fps.values()]
# Printed package outlines extend beyond fabrication bodies. Keep reference
# ink clear of their actual strokes, not just bodies and mask openings.
silk=[]
for fp in fps.values():
 for e in fp:
  if name(e) not in ['fp_line','fp_rect','fp_circle','fp_poly','fp_arc']:continue
  if not one(e,'layer') or one(e,'layer')[1]!='F.SilkS':continue
  stroke=one(one(e,'stroke') or [],'width');width=float(stroke[1]) if stroke else .15
  for g in layer_outline([fp[0],fp[1],one(fp,'at'),e],'F.SilkS'):
   silk.append(transform(g.buffer(width/2+LABEL_GAP+.025),fp))
obstacles.extend(silk)
obstacle_tree=STRtree(obstacles)
mounts=[(one(fps[r],'at')[1]-100,one(fps[r],'at')[2]-100) for r in ['H1','H2','H3','H4']]
nominal={}
for r,fp in fps.items():
 text=next((q for q in nodes(fp,'fp_text') if str(q[1])=='reference'),None)
 if text:nominal[r]=globalxy(fp,one(text,'at')[1:3])
 else:
  x0,y0,x1,y1=courts[r].bounds;nominal[r]=((x0+x1)/2,y0-1)
def candidate_positions(r,radius=4):
 own=courts[r];nx,ny=nominal[r]
 candidates=[];ox0,oy0,ox1,oy1=own.bounds
 for angle in [0,90]:
  dx0,dy0,dx1,dy1=text_bounds[r][str(angle)]
  for ix in range(math.floor((ox0-radius)/.25),math.ceil((ox1+radius)/.25)+1):
   x=ix*.25
   for iy in range(math.floor((oy0-radius)/.25),math.ceil((oy1+radius)/.25)+1):
    y=iy*.25;x0,y0,x1,y1=x+dx0,y+dy0,x+dx1,y+dy1
    if x0<.3 or y0<.3 or x1>board_width-.3 or y1>board_height-.3:continue
    if len(obstacle_tree.query(box(x0,y0,x1,y1),predicate='intersects')):continue
    if any(math.hypot(hx-max(x0,min(hx,x1)),hy-max(y0,min(hy,y1)))<3.5 for hx,hy in mounts):continue
    dx=max(ox0-x1,x0-ox1,0);dy=max(oy0-y1,y0-oy1,0)
    score=dx*dx+dy*dy+.025*((x-nx)**2+(y-ny)**2)+.025*(angle!=0)
    candidates.append((score,x,y,angle,(x0,y0,x1,y1)))
 return sorted(candidates)
from shapely import normalize,set_precision
physical_signatures={r:hashlib.sha256(normalize(set_precision(physical_envelope(fp),.000001)).wkb).hexdigest() for r,fp in fps.items()}
import numpy as np
# Resolve label competition globally: the most constrained remaining field
# gets a slot first, rather than discovering at the end that its only slot
# was consumed by a neighbor with many alternatives.
def arrange(radius):
 choices={r:candidate_positions(r,radius) for r in fps}
 arrays={r:np.asarray([c[4] for c in v],dtype=float).reshape((-1,4)) for r,v in choices.items()}
 masks={r:np.ones(len(v),dtype=bool) for r,v in choices.items()};assigned={}
 remaining=set(fps)
 while remaining:
  counts={r:int(np.count_nonzero(masks[r])) for r in remaining}
  r=min(remaining,key=lambda r:(counts[r],-len(r),r))
  if not counts[r]:
   print(f'No remaining label slot for {r} after assigning {len(assigned)} fields',flush=True);return None
  best=None;feasible_options=0
  # Examine 24 feasible choices. The 24 closest raw choices can all block
  # another field even when a slightly farther valid slot is available.
  for index in np.flatnonzero(masks[r]):
   candidate=choices[r][index];x0,y0,x1,y1=candidate[4]
   if not allowed.covers(box(x0,y0,x1,y1)):continue
   impact=0;conflicts={};bad=False
   for other in remaining-{r}:
    a=arrays[other];hit=(a[:,0]<x1+LABEL_GAP)&(a[:,2]>x0-LABEL_GAP)&(a[:,1]<y1+LABEL_GAP)&(a[:,3]>y0-LABEL_GAP)
    lost=int(np.count_nonzero(hit&masks[other]))
    if lost==counts[other]:bad=True;break
    impact+=lost/counts[other];conflicts[other]=hit
   if bad:continue
   score=candidate[0]+2*impact
   if best is None or score<best[0]:best=(score,candidate,conflicts)
   feasible_options+=1
   if feasible_options>=24:break
  if best is None:
   print(f'Label choice for {r} would block another field after assigning {len(assigned)} fields',flush=True);return None
  _,candidate,conflicts=best;assigned[r]=candidate;remaining.remove(r)
  for other,hit in conflicts.items():masks[other]&=~hit
 return assigned
assignment=None
saved_path=ROOT/'reference/silkscreen-labels.json'
if saved_path.exists():
 saved=json.loads(saved_path.read_text())
 def same_geometry(r):
  q=saved.get(r,{})
  at=one(fps[r],'at');xy=[float(at[1])-100,float(at[2])-100,float(at[3]) if len(at)>3 else 0]
  return q.get('footprint_at_mm_deg')==xy and q.get('courtyard_bounds_mm')==list(courts[r].bounds) and q.get('font_mm')==FONT and q.get('font_width_mm')==WIDTH and q.get('stroke_mm')==STROKE and q.get('label_policy_version')==POLICY and q.get('text_metrics_sha256')==metrics_hash and q.get('physical_geometry_sha256')==physical_signatures[r]
 if set(saved)==set(fps) and all(same_geometry(r) for r in fps):
  assignment={r:(0,*q['xy_mm'],q['rotation_deg'],tuple(q['bounds_mm'])) for r,q in saved.items()}
  print('Reusing validated label positions; footprint geometry is unchanged',flush=True)
if assignment is None:
 for radius in [4,6,8]:
  assignment=arrange(radius)
  if assignment is not None:break
  print(f'Label neighborhood {radius} mm is too congested; expanding the search',flush=True)
if assignment is None:raise RuntimeError('No complete pad/body-clear reference-label layout; revise component placement')
for r in fps:
 fp=fps[r];own=courts[r];_,x,y,a,bounds=assignment[r];rect=box(*bounds);distance=own.distance(rect)
 fp[1]='footprints:'+source.get(r,{}).get('footprint','MountingHole_4mm')
 if r=='JP1':setone(fp,'net_tie_pad_groups',[sym('net_tie_pad_groups'),'1,2'])
 if r=='J2':
  attr=one(fp,'attr')
  if attr is not None:attr[:]=[q for q in attr if q!=sym('smd')];attr.append(sym('through_hole')) if sym('through_hole') not in attr else None
 prop=next(q for q in nodes(fp,'property') if q[1]=='Reference');prop[2]=r;unhide(prop)
 u,v=localxy(fp,(x,y));setone(prop,'at',[sym('at'),round(u,6),round(v,6),a]);setone(prop,'layer',[sym('layer'),'F.SilkS'])
 # KiCad serializes font size as height then width (native vector is x/y).
 setone(prop,'effects',sx.loads(f'(effects (font (size {FONT} {WIDTH}) (thickness {STROKE})))'))
 # Remove stale REF**/library-value text restored by the compiler. Canonical
 # properties carry actual circuit references and values in KiCad 9.
 fp[:]=[q for q in fp if not (name(q)=='fp_text' and (str(q[1]) in ['reference','value'] or str(q[2]) in ['REF**','${REFERENCE}','%R']))]
 value=next((q for q in nodes(fp,'property') if q[1]=='Value'),None)
 if value is not None and r in source:value[2]=source[r]['value']
 body=local_courtyard(fp).centroid
 fp.append(sx.loads(f'(fp_text user "${{REFERENCE}}" (at {body.x} {body.y} 0) (layer "F.Fab") (uuid "{uid("fab-reference/"+r)}") (effects (font (size .8 .8) (thickness .12))))'))
 if r in fixed:
  fp[:]=[q for q in fp if name(q)!='locked' and q!=sym('locked')];fp.insert(2,sym('locked'))
 labels[r]={'xy_mm':[x,y],'rotation_deg':a,'font_mm':FONT,'font_width_mm':WIDTH,'stroke_mm':STROKE,'bounds_mm':list(rect.bounds),'courtyard_distance_mm':round(distance,4),'layer':'F.SilkS','label_policy_version':POLICY,'text_metrics_sha256':metrics_hash,'pad_mask_clearance_mm':GAP,'label_clearance_mm':LABEL_GAP,'physical_geometry_sha256':physical_signatures[r],'footprint_at_mm_deg':[float(one(fp,'at')[1])-100,float(one(fp,'at')[2])-100,float(one(fp,'at')[3]) if len(one(fp,'at'))>3 else 0],'courtyard_bounds_mm':list(own.bounds)}
board_text=sx.dumps(b)+'\n';label_text=json.dumps(labels,indent=2)+'\n'
if BOARD.read_text()!=board_text:BOARD.write_text(board_text)
label_path=ROOT/'reference/silkscreen-labels.json'
if not label_path.exists() or label_path.read_text()!=label_text:label_path.write_text(label_text)
print(f'Finished {len(labels)} visible reference fields + F.Fab identifiers; {len(fixed)} mechanical locks; no footprint positions or nets changed')
from attach_models import attach_models
attach_models()

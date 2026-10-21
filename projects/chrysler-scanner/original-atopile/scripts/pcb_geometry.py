"""Geometry shared by placement, physical checks, label layout and previews."""
import math,json
from pathlib import Path
from shapely.geometry import Point,box,MultiPoint,Polygon,LineString
from shapely.affinity import rotate,translate
from shapely.ops import unary_union

def name(e):return str(e[0]) if isinstance(e,list) and e else ''
def nodes(e,k):return [q for q in e if name(q)==k]
def one(e,k):return next((q for q in e if name(q)==k),None)
def transform(g,fp,local_board=True):
 at=one(fp,'at');x,y=at[1:3];a=float(at[3]) if len(at)>3 else 0
 return translate(rotate(g,-a,origin=(0,0)),x-(100 if local_board else 0),y-(100 if local_board else 0))
def arc_points(e,steps=48):
 start=one(e,'start')[1:3];mid=one(e,'mid')[1:3];end=one(e,'end')[1:3]
 ax,ay=start;bx,by=mid;cx,cy=end;d=2*(ax*(by-cy)+bx*(cy-ay)+cx*(ay-by))
 if abs(d)<1e-10:return [start,mid,end]
 u=((ax*ax+ay*ay)*(by-cy)+(bx*bx+by*by)*(cy-ay)+(cx*cx+cy*cy)*(ay-by))/d
 v=((ax*ax+ay*ay)*(cx-bx)+(bx*bx+by*by)*(ax-cx)+(cx*cx+cy*cy)*(bx-ax))/d
 r=math.hypot(ax-u,ay-v);a=math.atan2(ay-v,ax-u);m=math.atan2(by-v,bx-u);z=math.atan2(cy-v,cx-u)
 ccw=(z-a)%(2*math.pi);sweep=ccw if (m-a)%(2*math.pi)<=ccw else ccw-2*math.pi
 return [(u+r*math.cos(a+sweep*i/steps),v+r*math.sin(a+sweep*i/steps)) for i in range(steps+1)]
def layer_outline(fp,layer):
 """Return drawn outlines. Circles retain their true radius and offset."""
 result=[]
 for e in fp:
  if name(e) not in ['fp_line','fp_rect','fp_circle','fp_poly','fp_arc']:continue
  if not one(e,'layer') or one(e,'layer')[1]!=layer:continue
  kind=name(e)
  if kind=='fp_circle':
   c=one(e,'center')[1:3];end=one(e,'end')[1:3];g=Point(*c).buffer(math.dist(c,end),quad_segs=64).boundary
  elif kind=='fp_rect':
   a=one(e,'start')[1:3];z=one(e,'end')[1:3];g=box(min(a[0],z[0]),min(a[1],z[1]),max(a[0],z[0]),max(a[1],z[1])).boundary
  elif kind=='fp_poly':g=Polygon([q[1:3] for q in one(e,'pts')[1:] if name(q)=='xy']).boundary
  elif kind=='fp_arc':g=LineString(arc_points(e))
  else:g=LineString([one(e,'start')[1:3],one(e,'end')[1:3]])
  result.append(g)
 return result

def local_courtyard(fp):
 outlines=layer_outline(fp,'F.CrtYd')
 if outlines:
  # Closed outlines and connected line segments define the occupied envelope.
  # Convex hull is conservative for concave courtyards, and includes circles.
  return unary_union(outlines).convex_hull
 pads=[]
 for p in nodes(fp,'pad'):
  x,y=one(p,'at')[1:3];w,h=one(p,'size')[1:3];pads.extend([(x-w/2,y-h/2),(x+w/2,y+h/2)])
 return MultiPoint(pads).convex_hull

def courtyard(fp):return transform(local_courtyard(fp),fp)
def pad_shape(fp,p):
 at=one(fp,'at');a=float(at[3]) if len(at)>3 else 0;t=math.radians(a)
 px,py=one(p,'at')[1:3];x=at[1]-100+px*math.cos(t)+py*math.sin(t);y=at[2]-100-px*math.sin(t)+py*math.cos(t)
 w,h=one(p,'size')[1:3];pa=one(p,'at');angle=float(pa[3]) if len(pa)>3 else a
 if str(p[3])=='circle':return Point(x,y).buffer(max(w,h)/2,quad_segs=32)
 return translate(rotate(box(-w/2,-h/2,w/2,h/2),-angle,origin=(0,0)),x,y)
def physical_envelope(fp,mask_margin=.0508):
 """Body plus copper/mask openings, rather than the assembly courtyard.

 Silk may occupy free assembly clearance space, but never pads or the body.
 A footprint with no drawn fabrication body falls back to its courtyard.
 """
 outlines=layer_outline(fp,'F.Fab')
 body=transform(unary_union(outlines).convex_hull,fp) if outlines else courtyard(fp)
 shapes=[body]
 for p in nodes(fp,'pad'):
  layers=one(p,'layers')[1:]
  if not any(str(q) in ['F.Cu','*.Cu'] for q in layers):continue
  margin=one(p,'solder_mask_margin')
  shapes.append(pad_shape(fp,p).buffer(float(margin[1]) if margin else mask_margin))
 return unary_union(shapes)
def board_mechanics():
 path=Path(__file__).resolve().parents[1]/'reference/board-mechanics.json'
 return json.loads(path.read_text()) if path.exists() else {'size_mm':[100,50],'corner_radius_mm':2}
def board_area(inset=0):
 mechanical=board_mechanics();w,h=mechanical['size_mm'];r=mechanical['corner_radius_mm']
 return box(r,r,w-r,h-r).buffer(r,quad_segs=64).buffer(-inset)

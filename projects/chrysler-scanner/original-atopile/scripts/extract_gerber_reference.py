"""Recover exact mechanical geometry and selected pad coordinates from V1.40."""
from pathlib import Path
import json,warnings
from collections import Counter
from gerbonara import GerberFile,ExcellonFile
from gerbonara.utils import MM
from shapely.geometry import LineString,Point,box
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[1]
warnings.simplefilter('ignore',SyntaxWarning)
mask=GerberFile.open(ROOT/'gerbers/ChryslerCCDSCIScanner_V140.topsoldermask.ger')
for o in mask.objects:o.convert_to(MM)
def geom(o):
 if type(o).__name__=='Line':
  w=o.aperture.equivalent_width(MM);return LineString([(o.x1,o.y1),(o.x2,o.y2)]).buffer(w/2)
 if type(o).__name__=='Flash':
  b=o.bounding_box(MM);return box(*b[0],*b[1]) if 'Rectangle' in type(o.aperture).__name__ else Point(o.x,o.y).buffer(o.aperture.equivalent_width(MM)/2)
def pads(region):
 shapes=[geom(o) for o in mask.objects if box(*region).contains(geom(o))]
 u=unary_union(shapes)
 return sorted([{'xy':[(g.bounds[0]+g.bounds[2])/2,(g.bounds[1]+g.bounds[3])/2],'mask_size':[g.bounds[2]-g.bounds[0],g.bounds[3]-g.bounds[1]],'area':g.area} for g in (u.geoms if hasattr(u,'geoms') else [u]) if not g.is_empty],key=lambda v:(v['xy'][0],v['xy'][1]))
cp=pads((99.8,41.4,106.65,48.25))
esd=pads((100,32.1,104,36.65))
led={f'D{i}':pads((82,yy-1.2,88.6,yy+1.2)) for i,yy in [(1,29.827982),(2,27.033982),(3,24.239982),(4,21.445982)]}
outline=GerberFile.open(ROOT/'gerbers/ChryslerCCDSCIScanner_V140.boardoutline.ger')
bb=outline.bounding_box(MM)
d=ExcellonFile.open(ROOT/'gerbers/ChryslerCCDSCIScanner_V140.drills.xln')
holes=[];obd=[]
for o in d.objects:
 o.convert_to(MM)
 if abs(o.tool.unit.convert_to(MM,o.tool.diameter)-4)<.04:holes.append([o.x,o.y])
 if abs(o.tool.unit.convert_to(MM,o.tool.diameter)-1.2)<.01:obd.append([o.x,o.y])
reference={'origin_mm':[9.254,59.254],'size_mm':[100,50],'corner_radius_mm':2,'outline_bounds_mm':bb,'mounting_holes_mm':holes,'obd_drills_mm':sorted(obd),'cp2102':{'center_mm':[103.233982,44.813982],'pads':cp},'usb_esd':{'pads':esd},'led_regions':led}
(ROOT/'reference/v140-layout-reference.json').write_text(json.dumps(reference,indent=2))
print('outline',bb,'holes',holes,'CP pads',len(cp),'ESD candidate pads',len(esd))
print('ESD',esd)
print('LED candidates',led)

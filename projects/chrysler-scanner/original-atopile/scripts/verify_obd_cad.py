"""Check the selected connector CAD against PCB drills and nominal hardware.

Run with FreeCAD Python. This checks supplied nominal CAD, not tolerance stacks,
vehicle socket fit, insertion loads, a physical sample or an enclosure.
"""
from pathlib import Path
import hashlib,json,sys
if sys.platform=='darwin':sys.path.insert(0,'/Applications/FreeCAD.app/Contents/Resources/lib')
import FreeCAD as App
import Part
import datetime as clock_datetime

ROOT=Path(__file__).resolve().parents[1]
selection=json.loads((ROOT/'reference/obd-connector-selection.json').read_text())
mechanics=json.loads((ROOT/'reference/board-mechanics.json').read_text())
position=json.loads((ROOT/'reference/v240-placement.json').read_text())['J1']
assert position['rotation_deg']==0
model=ROOT/selection['installed_model'];shape=Part.read(str(model))
assert shape.isValid() and shape.Volume>0
verts,_=shape.tessellate(.03)
bounds=[[min(getattr(v,k) for v in verts),max(getattr(v,k) for v in verts)] for k in ['x','y','z']]
x,y=position['xy_mm'];placed=shape.copy();placed.translate(App.Vector(x,-y,0))
width,height=mechanics['size_mm']
pcb=Part.makeBox(width,height,1.6,App.Vector(0,-height,-1.6))
tails=[]
for n in range(1,17):
    px=x+(-1.5 if n<=8 else 1.5);py=y-14+4*((n-1)%8)
    hole=Part.makeCylinder(.675,1.6,App.Vector(px,-py,-1.6))
    terminal=placed.common(hole)
    assert terminal.Volume>.05,(n,terminal.Volume)
    # OCC's conservative B-spline bounds can extend beyond the actual geometry.
    # Inspect tessellated surface points rather than that bounding box.
    vertices,_=terminal.tessellate(.01)
    xmin,xmax=min(v.x for v in vertices),max(v.x for v in vertices)
    ymin,ymax=min(v.y for v in vertices),max(v.y for v in vertices)
    assert abs((xmin+xmax)/2-px)<.05 and abs((ymin+ymax)/2+py)<.05,n
    assert max(((v.x-px)**2+(v.y+py)**2)**.5 for v in vertices)<=.675+.000001,n
    tails.append({'pin':n,'hole_center_board_mm':[px,py],'tail_volume_in_drill_mm3':round(terminal.Volume,6),'tessellated_tail_center_board_mm':[(xmin+xmax)/2,-(ymin+ymax)/2]})
    pcb=pcb.cut(hole)
clash=placed.common(pcb).Volume
assert clash<.000001,clash
hardware=[]
for n,(hx,hy) in enumerate(mechanics['mounting_holes_mm'],1):
    # 7 mm washer/standoff clearance used in the placement plan; 4 mm bore.
    outer=Part.makeCylinder(3.5,14,App.Vector(hx,-hy,-2))
    bore=Part.makeCylinder(2,14,App.Vector(hx,-hy,-2))
    volume=placed.common(outer.cut(bore)).Volume
    assert volume<.000001,(n,volume)
    hardware.append({'hole':'H'+str(n),'diameter_mm':7,'z_extent_mm':[-2,12],'intersection_volume_mm3':volume})
report={'status':'PASS','verified_utc':clock_datetime.datetime.now(clock_datetime.timezone.utc).isoformat(),
    'engine':'FreeCAD '+'.'.join(App.Version()[:3]),'part':'ATTEND 226A-1202',
    'pcb_sha256':hashlib.sha256((ROOT/'elec/layout/v240/v240.kicad_pcb').read_bytes()).hexdigest(),
    'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
    'model_valid':True,'model_solids':len(shape.Solids),'tessellated_model_bounds_mm':bounds,
    'placement_origin_board_mm':[x,y],'tails_in_manufacturer_drills':tails,
    'pcb_intersection_volume_mm3':clash,'mounting_hardware_checks':hardware,
    'pad_copper_to_board_edge_mm':x-1.5-1.175,
    'pcb_edge_offset_from_recommended_mm':x-2.85,
    'physical_sample_verified':False,'enclosure_fit_verified':False,
    'scope':'Nominal supplied CAD, 1.6 mm board, recommended drills and 7 mm mounting hardware envelopes; no tolerance/load analysis.'}
(ROOT/'reference/obd-cad-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('ATTEND CAD: all 16 tails aligned; zero PCB and mounting-envelope intersections; PASS')

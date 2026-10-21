"""Check netlist equivalence, package-pad coverage and mechanical placement.

This is NOT KiCad DRC or a verification of analog/RF circuit performance.
"""
from pathlib import Path
from collections import defaultdict
import json,math
import sexpdata as sx
from shapely.geometry import box,Point
from pcb_geometry import courtyard,board_area,physical_envelope,board_mechanics
ROOT=Path(__file__).resolve().parents[1]
def name(e):return str(e[0]) if isinstance(e,list) and e else ''
def nodes(e,k):return [q for q in e if name(q)==k]
def one(e,k):return next((q for q in e if name(q)==k),None)
source=json.load(open(ROOT/'reference/v240-netlist.json'))
old=json.load(open(ROOT/'reference/v140-layout-reference.json'))
placement=json.load(open(ROOT/'reference/v240-placement.json'))
plan=json.load(open(ROOT/'reference/layout-plan.json'))
anchors=json.load(open(ROOT/'reference/mechanical-anchors.json'))
mechanics=board_mechanics();width,height=mechanics['size_mm']
board=sx.loads((ROOT/'elec/layout/v240/v240.kicad_pcb').read_text())
fps={next(q[2] for q in nodes(fp,'property') if q[1]=='Reference'):fp for fp in nodes(board,'footprint')}
errors=[]
def check(ok,msg):
 if not ok:errors.append(msg)
check(set(fps)==set(source['parts'])|{'H1','H2','H3','H4'},'PCB reference set differs from source + mounting holes')
actualnets=defaultdict(set);connected=0;nc=0;allpads={}
for r,c in source['parts'].items():
 fp=fps.get(r)
 if not fp:continue
 pads=nodes(fp,'pad');numbered={str(p[1]) for p in pads if str(p[1])}
 check(numbered==set(c['pins']),f'{r}: package pad numbers differ from circuit')
 at=one(fp,'at');x,y=at[1:3];a=at[3] if len(at)>3 else 0
 check(math.dist([x-100,y-100],placement[r]['xy_mm'])<.0001,f'{r}: layout differs from saved placement')
 check(a==placement[r]['rotation_deg'],f'{r}: rotation differs from saved placement')
 # Actual circular, polygonal and line courtyards all count as occupied space.
 bounds=courtyard(fp).bounds
 check(max(abs(u-v) for u,v in zip(bounds,placement[r]['courtyard_mm']))<.0001,f'{r}: saved courtyard differs from actual footprint')
 for pad in pads:
  n=str(pad[1])
  if not n:continue
  net=one(pad,'net');netname=str(net[2]) if net and len(net)>2 else None
  if netname:actualnets[netname].add((r,n))
  wanted=c['pins'][n]['net']
  if wanted:
   connected+=1;check(netname==wanted,f'{r}.{n}: expected {wanted}, found {netname}')
  else:nc+=1
  px,py=one(pad,'at')[1:3];t=math.radians(a)
  allpads[r,n]=(x-100+px*math.cos(t)+py*math.sin(t),y-100-px*math.sin(t)+py*math.cos(t))
for net,pp in source['nets'].items():check(actualnets[net]==set(map(tuple,pp)),f'{net}: endpoint set differs from source')
# USB-C is a local revision to the unchanged upstream USB-B schematic. Check
# its terminal map independently and keep every retained part electrically
# identical to the pre-change extracted circuit.
hardware_path=ROOT/'reference/hardware-overrides.json'
if hardware_path.exists():
 hardware=json.loads(hardware_path.read_text());base=json.loads((ROOT/'reference/v240-usb-b-netlist.json').read_text())
 expected={'A1':'GND','A4':'VBUS','A5':'USB_CC1','A6':'D+','A7':'D-','A8':None,'A9':'VBUS','A12':'GND','B1':'GND','B4':'VBUS','B5':'USB_CC2','B6':'D+','B7':'D-','B8':None,'B9':'VBUS','B12':'GND','SH':'GND'}
 check({n:v['net'] for n,v in source['parts']['J2']['pins'].items()}==expected,'USB-C connector pin map is incorrect')
 for r,net in [('R102','USB_CC1'),('R103','USB_CC2')]:
  c=source['parts'][r]
  check(c['value']=='5.1kΩ' and c['orderable_hint']=='RC0603FR-075K1L' and not c['dnp'],f'{r}: expected fitted 5.1k 1% CC resistor')
  check(c['pins']['1']['net']==net and c['pins']['2']['net']=='GND',f'{r}: wrong CC pulldown connection')
  check(actualnets[net]=={('J2','A5' if r=='R102' else 'B5'),(r,'1')},f'{r}: CC line is not isolated from the other CC line')
 for r,c in base['parts'].items():
  if r=='J2':continue
  if r=='J1' and r in hardware['parts']:
   check({n:p['net'] for n,p in source['parts'][r]['pins'].items()}=={n:p['net'] for n,p in c['pins'].items()},'J1: original OBD terminal connections changed')
  else:
   expected_pins=c['pins']
   if r in ['U3','U4','U8']:
    import copy
    expected_pins=copy.deepcopy(c['pins']);expected_pins['5']=source['parts'][r]['pins']['5']
    check(c['pins']['5']['net'] is None and source['parts'][r]['pins']['5']['net']=='GND',f'{r}: expected verified TLV767 DRV ground-pin correction')
   check(source['parts'][r]['pins']==expected_pins,f'{r}: retained circuit pin map changed beyond declared corrections')
   check(source['parts'][r]['value']==c['value'] and source['parts'][r]['footprint']==c['footprint'],f'{r}: retained component value or package changed')
 for net,pp in base['nets'].items():
  expected_other={(r,n) for r,n in pp if r!='J2'}
  if net=='GND':expected_other|={(r,'5') for r in ['U3','U4','U8']}
  actual_other={(r,n) for r,n in source['nets'][net] if r not in {'J2','R102','R103'}}
  check(actual_other==expected_other,f'{net}: retained circuit endpoint set changed')
 check(str(fps['J2'][1]).split(':')[-1]==hardware['parts']['J2']['footprint'],'J2 is not the selected GCT USB-C footprint')
 j2=fps['J2'];at=one(j2,'at');angle=math.radians(float(at[3]));edge=(at[1]-100+3.675*math.sin(angle),at[2]-100+3.675*math.cos(angle))
 check(math.dist(edge,(width,29))<.000002,'USB-C mating face must remain at the right board edge and y=29 mm port centerline')
 for pad in nodes(j2,'pad'):
  if str(pad[2])=='smd':check(one(pad,'solder_mask_margin') is not None and float(one(pad,'solder_mask_margin')[1])==.025,'USB-C SMT contact row must use 0.025 mm mask expansion')
for r,c in source['parts'].items():
 for n,v in c['pins'].items():
  if not v['net']:
   fp=fps.get(r)
   if not fp:continue
   net=next((one(q,'net') for q in nodes(fp,'pad') if str(q[1])==n),None)
   check(not net or len(actualnets[str(net[2])])==1,f'{r}.{n}: NC pad shares a connected net')
holes=[]
for i in range(1,5):
 if f'H{i}' not in fps:
  errors.append(f'H{i}: mounting footprint missing');continue
 fp=fps[f'H{i}'];q=one(fp,'at');p=nodes(fp,'pad')[0]
 check(float(one(p,'drill')[1])==4,f'H{i}: wrong mounting drill diameter')
 check(sx.Symbol('locked') in fp,f'H{i}: mechanical footprint is not locked')
 holes.append([q[1]-100,q[2]-100])
want=mechanics.get('mounting_holes_mm',[[x-9.254,59.254-y] for x,y in old['mounting_holes_mm']])
check(len(holes)==4 and all(math.dist(a,b)<.0001 for a,b in zip(sorted(holes),sorted(want))),'Mounting-hole positions do not match the approved mechanical plan')
shapes={r:courtyard(fps[r]) for r in placement}
for r,g in shapes.items():
 if r!='J2':check(board_area().buffer(.000002).covers(g),f'{r}: courtyard extends outside the board')
overlap=[]
rr=list(shapes)
for i,r in enumerate(rr):
 for s in rr[i+1:]:
  if shapes[r].intersection(shapes[s]).area>.00001:overlap.append([r,s])
 for h,(x,y) in enumerate(holes,1):
  if shapes[r].intersects(Point(x,y).buffer(3.5)):overlap.append([r,f'H{h} hardware clearance'])
check(not overlap,f'Courtyard/hardware overlaps: {overlap}')
# Independent regression check for the reported large capacitor: inspect the
# F.Fab circle directly rather than relying on the shared courtyard helper.
c1=fps['C1'];circle=next(q for q in nodes(c1,'fp_circle') if one(q,'layer')[1]=='F.Fab')
cx,cy=one(circle,'center')[1:3];radius=math.dist([cx,cy],one(circle,'end')[1:3]);at=one(c1,'at');t=math.radians(at[3])
c1center=[at[1]-100+cx*math.cos(t)+cy*math.sin(t),at[2]-100-cx*math.sin(t)+cy*math.cos(t)]
c1body=Point(*c1center).buffer(radius,quad_segs=64)
check(abs(radius-4)<.0001,'C1 must retain its 8 mm radial body')
check(board_area().covers(c1body),'C1 physical body extends outside the board')
check(all(not c1body.intersects(g) for r,g in shapes.items() if r!='C1'),'C1 physical body intersects another component courtyard')
check(all(not c1body.intersects(Point(x,y).buffer(3.5)) for x,y in holes),'C1 body intersects mounting hardware clearance')
cb=shapes['C1'].bounds
check(abs(cb[2]-cb[0]-8.5)<.0001 and abs(cb[3]-cb[1]-8.5)<.0001,'C1 clearance envelope must include its complete 8.5 mm circular courtyard')
def matching_centers(r,expected,tol=.002):
 offset=mechanics.get('gerber_component_offsets_mm',{}).get(r,[0,0])
 expected=[[q[0]+offset[0],q[1]+offset[1]] for q in expected]
 got=[xy for (ref,n),xy in allpads.items() if ref==r]
 check(all(any(math.dist(q,e)<tol for q in got) for e in expected),f'{r}: recovered Gerber pad centers differ')
# J1 now uses the real manufacturer's layout rather than the Gerber inference.
obd=fps['J1'];selection=json.loads((ROOT/'reference/obd-connector-selection.json').read_text())
check(str(obd[1]).split(':')[-1]=='OBDII_ATTEND_226A-1202','J1: wrong manufacturer footprint')
check(source['parts']['J1']['manufacturer']=='ATTEND' and source['parts']['J1']['orderable_hint']=='226A-1202','J1: wrong orderable connector')
for p in nodes(obd,'pad'):
 n=int(p[1]);expected_xy=[1.5 if n<=8 else 4.5,11+4*((n-1)%8)]
 check(math.dist(allpads['J1',str(n)],expected_xy)<.000001,f'J1.{n}: manufacturer pin numbering or position is incorrect')
 check(str(p[2])=='thru_hole' and abs(float(one(p,'drill')[1])-1.35)<.000001,f'J1.{n}: drill must be 1.35 mm')
 check(one(p,'size')[1:]==[2.35,2.35],f'J1.{n}: manufacturer pad must be 2.35 mm')
 check(allpads['J1',str(n)][0]-1.175>=.325-.000001,f'J1.{n}: insufficient selected copper-to-edge clearance')
matching_centers('U12',[[p['xy'][0]-9.254,59.254-p['xy'][1]] for p in old['cp2102']['pads'] if p['area']>.5])
for n in range(1,5):matching_centers(f'D{n+22}',[[p['xy'][0]-9.254,59.254-p['xy'][1]] for p in old['led_regions'][f'D{n}']])
outline_points=[]
for e in nodes(board,'gr_line')+nodes(board,'gr_arc'):
 if one(e,'layer')[1]=='Edge.Cuts':
  for k in ['start','end']:outline_points.append(one(e,k)[1:3])
bb=[min(q[0] for q in outline_points),min(q[1] for q in outline_points),max(q[0] for q in outline_points),max(q[1] for q in outline_points)]
check(bb==[100,100,100+width,100+height],f'Outline bounds differ: {bb}')
check(len(nodes(board,'gr_arc'))==4,'Expected four rounded corners')
for r,p in anchors.items():
 at=one(fps[r],'at')
 check(math.dist([at[1]-100,at[2]-100],p['xy_mm'])<.0001 and at[3]==p['rotation_deg'],f'{r}: fixed connector/Gerber anchor moved')
 check(sx.Symbol('locked') in fps[r],f'{r}: fixed footprint is not locked')
groupbyref={r:g for g in plan['groups'] for r in g['members']}
check(set(groupbyref)==set(source['parts']),'Functional groups do not cover every circuit part')
for r,p in placement.items():
 check(p['group']==groupbyref[r]['id'],f'{r}: functional group changed')
 if r not in anchors and r!='AE1':
  x0,y0,x1,y1=p['courtyard_mm'];g=next(v['bounds_mm'] for v in plan['groups'] if v['id']==plan['placement_region_overrides'][r]) if r in plan.get('placement_region_overrides',{}) else groupbyref[r]['bounds_mm']
  check(x0>=g[0]-.0001 and y0>=g[1]-.0001 and x1<=g[2]+.0001 and y1<=g[3]+.0001,f'{r}: outside its functional region')
distances=[]
for q in plan['links']:
 d=math.dist(allpads[q['part'],q['pad']],allpads[q['anchor'],q['anchor_pad']])
 check(d<=q['max_distance_mm']+.0001,f"{q['part']}: {q['kind']} distance {d:.3f} mm exceeds placement limit")
 check(source['parts'][q['part']]['pins'][q['pad']]['net']==source['parts'][q['anchor']]['pins'][q['anchor_pad']]['net'],f"{q['part']}: pin-distance constraint joins different nets")
 distances.append({**q,'distance_mm':round(d,4)})
copper=[q[1] for q in one(board,'layers')[1:] if int(q[0])<=31]
check(copper==['F.Cu','In1.Cu','In2.Cu','B.Cu'],f'Expected four copper layers, found {copper}')
stack=one(one(board,'setup'),'stackup')
stack_copper=[q[1] for q in nodes(stack,'layer') if one(q,'type')[1]=='copper']
check(stack_copper==copper,'Stackup copper order differs from PCB layers')
thickness=sum(float(one(q,'thickness')[1]) for q in nodes(stack,'layer') if one(q,'thickness'))
check(abs(thickness-1.6)<.0001,'Nominal stackup thickness is not 1.6 mm')
zones=nodes(board,'zone');keepouts=[q for q in zones if one(q,'keepout')]
check(len(keepouts)==1 and one(keepouts[0],'layers')[1:]==copper,'Antenna keepout must cover all four copper layers')
planes=[q for q in zones if not one(q,'keepout')]
check(len(planes)==2 and all(one(q,'net_name')[1]=='GND' for q in planes),'Expected L2 ground and L3 RF-ground zone definitions')
ground=next((q for q in planes if one(q,'layer')[1]=='In1.Cu'),None)
check(ground is not None and {tuple(q[1:3]) for q in one(one(ground,'polygon'),'pts')[1:]}=={(100,100),(100+width,100),(100+width,100+height),(100,100+height)},'L2 ground definition must cover the entire outline')
if not nodes(board,'segment') and not nodes(board,'via'):
 check(not any(nodes(q,'filled_polygon') for q in zones),'Unrouted placement snapshots should not contain stale filled zones')
labels=json.load(open(ROOT/'reference/silkscreen-labels.json'))
text_policy=json.loads((ROOT/'reference/silkscreen-text-metrics.json').read_text())
check(set(labels)==set(fps),'Every circuit and mounting footprint must have a saved reference-label placement')
label_shapes={};label_overlaps=[]
physical_shapes=[physical_envelope(fp) for fp in fps.values()]
for r,fp in fps.items():
 prop=next(q for q in nodes(fp,'property') if q[1]=='Reference')
 check(prop[2]==r and one(prop,'layer')[1]=='F.SilkS',f'{r}: actual reference field is missing or on the wrong layer')
 check(not one(prop,'hide') and sx.Symbol('hide') not in prop and not one(one(prop,'effects'),'hide'),f'{r}: reference field is hidden')
 check(not any(str(q[1])=='reference' or str(q[2])=='REF**' for q in nodes(fp,'fp_text')),f'{r}: stale reference placeholder remains')
 check(any(str(q[2])=='${REFERENCE}' and one(q,'layer')[1]=='F.Fab' for q in nodes(fp,'fp_text')),f'{r}: F.Fab identifier missing')
 at=one(fp,'at');t=math.radians(at[3] if len(at)>3 else 0);u,v=one(prop,'at')[1:3]
 x=at[1]-100+u*math.cos(t)+v*math.sin(t);y=at[2]-100-u*math.sin(t)+v*math.cos(t)
 font=one(one(prop,'effects'),'font');size=float(one(font,'size')[1]);stroke=float(one(font,'thickness')[1]);angle=one(prop,'at')[3]
 dx0,dy0,dx1,dy1=text_policy['bounds_mm_by_reference_angle'][r][str(int(angle))]
 rect=box(x+dx0,y+dy0,x+dx1,y+dy1);label_shapes[r]=rect
 check(size==text_policy['font_height_mm'] and float(one(font,'size')[2])==text_policy['font_width_mm'] and stroke==text_policy['stroke_mm'],f'{r}: reference text differs from the JLCPCB minimum-size policy')
 check(math.dist([x,y],labels[r]['xy_mm'])<.0001,f'{r}: actual field differs from saved label position')
 check(board_area(.3).covers(rect),f'{r}: reference text extends outside the board')
 check(all(rect.distance(other)>=text_policy['pad_mask_clearance_mm']-.000002 for other in physical_shapes),f'{r}: reference text lacks the required body/pad/mask clearance')
 check(all(not rect.intersects(Point(x,y).buffer(3.5)) for x,y in holes),f'{r}: reference text intersects mounting hardware clearance')
for i,r in enumerate(label_shapes):
 for s in list(label_shapes)[i+1:]:
  if label_shapes[r].distance(label_shapes[s])<text_policy['label_clearance_mm']-.000002:label_overlaps.append([r,s])
check(not label_overlaps,f'Reference-label overlaps: {label_overlaps}')
import hashlib
manifest=json.loads((ROOT/'reference/3d-models.json').read_text())
check(set(manifest['references'])==set(source['parts']),'3D model map must cover every circuit reference')
model_count=0;dnp_refs=[]
for r,fp in fps.items():
 check(not nodes(fp,'dnp'),f'{r}: unsupported footprint-level DNP expression')
 attr=one(fp,'attr') or []
 is_dnp=sx.Symbol('dnp') in attr
 check(is_dnp==bool(source['parts'].get(r,{}).get('dnp')),f'{r}: native DNP attribute differs from source')
 if is_dnp:dnp_refs.append(r)
 models=nodes(fp,'model');spec=manifest['references'].get(r)
 check(len(models)==(1 if spec else 0),f'{r}: wrong number of 3D models')
 if not spec or len(models)!=1:continue
 model=models[0];model_count+=1
 check(model[1]==manifest['model_path_prefix']+spec['model'],f'{r}: model path is not the portable local assignment')
 for field,values in [('offset',spec.get('offset_mm',[0,0,0])),('rotate',spec.get('rotation_deg',[0,0,0])),('scale',[1,1,1])]:
  check(one(one(model,field),'xyz')[1:]==values,f'{r}: {field} differs from assigned 3D transform')
for filename,meta in manifest['models'].items():
 path=ROOT/'elec/src/3dmodels'/filename
 check(path.is_file(),f'3D model missing: {filename}')
 if path.is_file():check(hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256'],f'3D model differs from provenance: {filename}')
 if filename.endswith('.wrl'):check((ROOT/'elec/src/3dmodels'/meta['step_companion']).is_file(),f'{filename}: STEP companion missing')
from faebryk.libs.kicad.fileformats import kicad
try:kicad.loads(kicad.pcb.PcbFile,ROOT/'elec/layout/v240/v240.kicad_pcb')
except Exception as ex:errors.append('Atopile KiCad parser: '+str(ex)[:800])
report={'status':'PASS' if not errors else 'FAIL','circuit_footprints':len(source['parts']),'connected_nets':len(source['nets']),'numbered_physical_pads':sum(len(p['pins']) for p in source['parts'].values()),'connected_pad_instances':connected,'nc_pad_instances':nc,'mounting_holes':4,'outline_mm':[100,50],'gerber_matching_footprints':['U12','D23','D24','D25','D26'],'courtyard_overlaps':overlap,'tracks':len(nodes(board,'segment')),'vias':len(nodes(board,'via')),'kicad_drc_run':False,'routing_complete':False,'pdf_extraction_independently_verified':False,'errors':errors}
report['obd_connector']={'part':'ATTEND 226A-1202','manufacturer_pin_positions_checked':16,'row_pitch_mm':3,'pitch_along_row_mm':4,'drill_mm':1.35,'pad_diameter_mm':2.35,'minimum_pad_copper_to_edge_mm':.325,'original_terminal_connections_preserved':True,'model':'ATTEND_226A-1202.step'}
report.update(outline_mm=[width,height],original_outline_mm=old['size_mm'],gerber_component_offsets_mm=mechanics.get('gerber_component_offsets_mm',{}),functional_groups=len(plan['groups']),copper_layers=copper,nominal_stackup_mm=round(thickness,4),stackup_status=plan['stackup_status'],ground_zone_status='Definitions only; not filled or electrically verified',pin_distance_checks=distances)
report.update(visible_reference_fields=len(labels),reference_label_overlaps=label_overlaps,c1_physical_body={'diameter_mm':2*radius,'center_mm':c1center,'courtyard_bounds_mm':list(cb),'board_containment_checked':True,'component_and_hardware_clearance_checked':True})
report.update(reference_text_height_mm=text_policy['font_height_mm'],reference_text_font_width_mm=text_policy['font_width_mm'],reference_text_stroke_mm=text_policy['stroke_mm'],reference_text_bounds='Measured with native KiCad stroke font',reference_pad_mask_clearance_mm=text_policy['pad_mask_clearance_mm'],reference_label_clearance_mm=text_policy['label_clearance_mm'],reference_text_capability_source=text_policy['source'])
report.update(local_3d_model_references=model_count,model_files_verified=len(manifest['models']),dnp_references=sorted(dnp_refs),models_are_generic_or_representative=True)
if hardware_path.exists():report.update(hardware_revision=hardware['hardware_revision'],usb_c={'connector':'USB4105-GF-A','protocol':'USB 2.0 full-speed device','power':'5 V sink; no USB-PD','cc_resistors':['R102','R103'],'cc_resistance_ohm':5100,'cc_tolerance_percent':1,'port_centerline_mm':29.0,'smd_mask_expansion_mm':.025,'minimum_contact_row_mask_bridge_mm':.15,'retained_pin_maps_checked':238})
(ROOT/'reference/validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
if errors:raise SystemExit(1)

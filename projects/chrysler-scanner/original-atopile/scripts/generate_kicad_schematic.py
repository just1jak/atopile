"""Generate a functional-sheet KiCad visualization of the atopile netlist.

Recover component graphics and circuit layout from the upstream vector PDF.
Use real native symbols, pins, wires and global labels, not embedded images.
Package supply/NC additions are visible extra units. Pin types are passive:
this is a connectivity visualization, not independent ERC certification.
"""
from pathlib import Path
from collections import defaultdict
import json,math,re,uuid,copy
import sexpdata as sx
import pymupdf
from shapely.geometry import Point,LineString,box
from shapely.strtree import STRtree
from clean_schematic_layout import clean_page, scale as scale_library, prepare_footprints

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'elec/schematic';OUT.mkdir(exist_ok=True)
PROJECT='ChryslerScanner_V240'
source=json.loads((ROOT/'reference/v240-netlist.json').read_text())
REVISION=source.get('hardware_revision','V240')
TITLE_REVISION='V240-C/OBD' if REVISION=='V240-USB-C-OBD' else REVISION
raw=json.loads((ROOT/'reference/upstream/v240-extracted.json').read_text())
groups=json.loads((ROOT/'reference/layout-plan.json').read_text())['groups']
pdf=pymupdf.open(ROOT/'reference/upstream/ChryslerScanner_V240_schematic.pdf')
page=pdf[0];drawings=page.get_drawings()
spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans'] if s['text'].strip()]
SCALE=25.4/72
def f(v):return round(float(v),6)
def quote(v):return json.dumps(str(v),ensure_ascii=False)
def uid(v):return str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240-schematic/'+v))
ROOT_ID=uid('root')
def add(doc,text):doc.append(sx.loads(text))
def name(e):return str(e[0]) if isinstance(e,list) and e else ''
def one(e,k):return next((q for q in e if name(q)==k),None)
def effects(size=1.27,hide=False,justify=''):
 return f'(effects (font (size {size} {size}))'+(' (hide yes)' if hide else '')+(f' (justify {justify})' if justify else '')+')'
def property_text(key,value,x,y,size=1.27,hide=False,justify=''):
 return f'(property {quote(key)} {quote(value)} (at {f(x)} {f(y)} 0) {effects(size,hide,justify)})'
def new_doc(key,title,width=420,height=297):
 return sx.loads(f'(kicad_sch (version 20250114) (generator "eeschema") (generator_version "10.0") (uuid "{uid(key)}") (paper "User" {width} {height}) (title_block (title {quote(title)}) (date "2026-10-19") (rev {quote(TITLE_REVISION)}) (company "ChryslerScanner / atopile")) (lib_symbols))')
def write_doc(path,doc):path.write_text(sx.dumps(doc)+'\n')
def text(doc,key,value,x,y,size=1.27):
 add(doc,f'(text {quote(value)} (at {f(x)} {f(y)} 0) {effects(size,False,"left")} (uuid "{uid(key)}"))')
def wire(doc,key,a,b):
 if math.dist(a,b)<.000001:return
 add(doc,f'(wire (pts (xy {f(a[0])} {f(a[1])}) (xy {f(b[0])} {f(b[1])})) (stroke (width 0) (type default)) (uuid "{uid(key)}"))')
group_by_ref={r:g['id'] for g in groups for r in g['members']}
internal_nets={n for n,pp in source['nets'].items() if n.startswith('N_') and len({group_by_ref[r] for r,p in pp})==1}
def label(doc,key,value,p,angle=0):
 if value in internal_nets:return
 add(doc,f'(global_label {quote(value)} (shape input) (at {f(p[0])} {f(p[1])} {angle}) {effects(.95,False,"right" if angle==180 else "left")} (uuid "{uid(key)}") {property_text("Intersheetrefs","${INTERSHEET_REFS}",p[0],p[1],.95,True)})')

# Split original green wires at T junctions and explicit connection dots.
segments=[(tuple(a),tuple(b)) for a,b in raw['wires'] if a!=b]
points=set(q for a,b in segments for q in [a,b])
points.update(tuple(p['pdf_xy']) for part in raw['parts'].values() for p in part['pins'].values())
points.update(tuple(p['pdf_xy']) for p in raw['labels'])
for d in drawings:
 if d['fill'] and d['color'] and abs(d['color'][1]-.588235)<.0001 and d['color'][0]==0:
  r=d['rect'];points.add((round((r.x0+r.x1)/2,2),round((r.y0+r.y1)/2,2)))
points=sorted(points);point_tree=STRtree([Point(*p) for p in points])
parents={p:p for p in points}
def root(p):
 if parents[p]!=p:parents[p]=root(parents[p])
 return parents[p]
def join(a,b):parents[root(a)]=root(b)
split_segments=[]
for a,b in segments:
 line=LineString([a,b]);near=[points[int(i)] for i in point_tree.query(line.buffer(.015)) if line.distance(Point(*points[int(i)]))<.015]
 near.sort(key=lambda p:line.project(Point(*p)))
 for u,v in zip(near,near[1:]):
  join(u,v)
  if u!=v:split_segments.append((u,v))
split_segments=list(dict.fromkeys(split_segments))
root_wires=defaultdict(list)
for a,b in split_segments:root_wires[root(a)].append((a,b))

units={};libraries={};pin_coverage=defaultdict(set)
brown=[d for d in drawings if d['color'] and d['color'][0]>.5 and d['color'][1]==0 and d['color'][2]==0]
brown_tree=STRtree([box(*d['rect']) for d in brown])
def base_symbol(ref):
 p=source['parts'][ref]
 return sx.loads(f'(symbol "ChryslerScanner:{ref}" (pin_names (offset 0) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes) {property_text("Reference",ref,0,0,1.27)} {property_text("Value",p["value"],0,0,1.27)} {property_text("Footprint","footprints:"+p["footprint"],0,0,1.27,True)} {property_text("Datasheet","",0,0,1.27,True)} {property_text("Description","Recovered graphic; pin numbers/net connectivity from current atopile source; passive pin types",0,0,1.27,True)})')
def graphic_poly(symbol,pts,cx,cy,width=.15):
 points_text=' '.join(f'(xy {f((x-cx)*SCALE)} {f((cy-y)*SCALE)})' for x,y in pts)
 add(symbol,f'(polyline (pts {points_text}) (stroke (width {f(width)}) (type default)) (fill (type none)))')
def native_pin(symbol,number,x,y,angle,length=1.27):
 add(symbol,f'(pin passive line (at {f(x)} {f(y)} {angle}) (length {f(length)}) (name "~" {effects(.95)}) (number {quote(number)} {effects(.95)}))')
for ref,p in source['parts'].items():
 lib=base_symbol(ref);libraries[ref]=lib;units[ref]=[]
 if ref.startswith(('R','C','D','L','JP')):add(lib,'(pin_numbers (hide yes))')
 if ref in ['J1','J2','J3','R102','R103']:continue
 for unit_number,raw_ref in enumerate(p['units'],1):
  part=raw['parts'][raw_ref];cx,cy=part['pdf_center'];bounds=part['body_bbox']
  if ref.startswith('L'):bounds=[cx-7.2,cy-3.6,cx+7.2,cy+3.6]
  clip=box(*bounds).buffer(.6)
  # The upstream PDF includes stroke outlines of pin-number text in two
  # logic symbols. Native pins draw their own numbers, so omit those outlines.
  digit_boxes=[box(*s['bbox']).buffer(.15) for s in spans if s['text'].strip().isdigit() and box(*s['bbox']).intersects(clip)] if ref in ['U17','U18'] else []
  sub=sx.loads(f'(symbol "{ref}_{unit_number}_1")')
  # Vector recovery keeps the familiar resistor/capacitor/FET/IC graphics.
  for index in brown_tree.query(clip):
   drawing=brown[int(index)]
   for item in drawing['items']:
    if item[0]=='l':pts=[tuple(item[1]),tuple(item[2])]
    elif item[0]=='re':
     r=item[1];pts=[(r.x0,r.y0),(r.x1,r.y0),(r.x1,r.y1),(r.x0,r.y1),(r.x0,r.y0)]
    elif item[0]=='c':
     a,b,c,d=item[1:];pts=[tuple((1-t)**3*a[j]+3*(1-t)**2*t*b[j]+3*(1-t)*t*t*c[j]+t**3*d[j] for j in [0,1]) for t in [i/12 for i in range(13)]]
    elif item[0]=='qu':
     q=item[1];pts=[tuple(q.ul),tuple(q.ur),tuple(q.lr),tuple(q.ll),tuple(q.ul)]
    else:continue
    clipped=LineString(pts).intersection(clip)
    for line in list(clipped.geoms) if hasattr(clipped,'geoms') else [clipped]:
     if line.geom_type=='LineString' and line.length>.02 and not any(b.covers(line) for b in digit_boxes):graphic_poly(sub,list(line.coords),cx,cy,min(.25,drawing['width']*SCALE))
  # Pin-function text inside IC bodies is recovered as editable text.
  if ref.startswith('U'):
   for span in spans:
    value=span['text'].strip();r=span['bbox'];x,y=(r[0]+r[2])/2,(r[1]+r[3])/2
    if value not in [ref,raw_ref,p['value']] and not re.fullmatch(r'\d+',value) and box(*bounds).contains(Point(x,y)):
     add(sub,f'(text {quote(value)} (at {f((x-cx)*SCALE)} {f((cy-y)*SCALE)} 0) {effects(1.0)})')
  for number,pin in part['pins'].items():
   if number not in p['pins']:continue
   x,y=pin['pdf_xy'];dx,dy=x-cx,cy-y
   if ref=='J1':angle=270 if y<cy else 90
   elif x<bounds[0]:angle=0
   elif x>bounds[2]:angle=180
   elif y<bounds[1]:angle=270
   elif y>bounds[3]:angle=90
   else:angle=(0 if dx<0 else 180) if abs(dx)>abs(dy) else (270 if dy>0 else 90)
   length=max(.01,box(*bounds).distance(Point(x,y))*SCALE)
   native_pin(sub,number,dx*SCALE,dy*SCALE,angle,length)
   pin_coverage[ref].add(number)
  lib.append(sub);units[ref].append({'unit':unit_number,'raw_ref':raw_ref,'center':(cx,cy),'bounds':bounds,'pins':part['pins']})

# Local connector revisions use readable native symbols with outward labels.
for ref in ['J1','J2','J3','R102','R103']:
 p=source['parts'][ref];lib=libraries[ref];sub=sx.loads(f'(symbol "{ref}_1_1")');pins={}
 if ref=='J1':
  rows=[[str(i) for i in range(1,9)],[str(i) for i in range(9,17)]]
  add(sub,'(rectangle (start -10.16 20.32) (end 10.16 -20.32) (stroke (width .254) (type default)) (fill (type background)))')
  add(sub,f'(text "J1962 Type A" (at 0 0 90) {effects(1.05)})')
  for side,numbers in enumerate(rows):
   for i,n in enumerate(numbers):
    x=-12.7 if side==0 else 12.7;y=17.78-i*5.08
    native_pin(sub,n,x,y,0 if side==0 else 180,2.54);pins[n]={'local_mm':[x,y]}
    xx=-8.89 if side==0 else 8.89
    add(sub,f'(rectangle (start {xx-.6} {y+.6}) (end {xx+.6} {y-.6}) (stroke (width .15) (type default)) (fill (type none)))')
 elif ref=='J2':
  rows=[['A1','A4','A5','A6','A7','A8','A9','A12'],['B1','B4','B5','B6','B7','B8','B9','B12','SH']]
  add(sub,'(rectangle (start -10.16 13.97) (end 10.16 -13.97) (stroke (width .254) (type default)) (fill (type background)))')
  for caption,y in [('USB-C',4),('USB 2.0',0),('5 V sink',-4)]:add(sub,f'(text {quote(caption)} (at 0 {y} 0) {effects(1.05)})')
  for side,numbers in enumerate(rows):
   for i,n in enumerate(numbers):
    x=-12.7 if side==0 else 12.7;y=10.16-i*2.54;native_pin(sub,n,x,y,0 if side==0 else 180,2.54);pins[n]={'local_mm':[x,y]}
 elif ref=='J3':
  add(sub,'(rectangle (start -6.35 7.62) (end 6.35 -7.62) (stroke (width .254) (type default)) (fill (type background)))')
  for side,numbers in enumerate([['1','3','5'],['2','4','6']]):
   for i,n in enumerate(numbers):
    x=-8.89 if side==0 else 8.89;y=5.08-i*5.08
    native_pin(sub,n,x,y,0 if side==0 else 180,2.54);pins[n]={'local_mm':[x,y]}
    xx=-5.08 if side==0 else 5.08
    add(sub,f'(rectangle (start {xx-.6} {y+.6}) (end {xx+.6} {y-.6}) (stroke (width .15) (type default)) (fill (type none)))')
 else:
  add(sub,'(rectangle (start -2.54 1.016) (end 2.54 -1.016) (stroke (width .254) (type default)) (fill (type none)))')
  for n,x,angle in [('1',-3.81,0),('2',3.81,180)]:native_pin(sub,n,x,0,angle);pins[n]={'local_mm':[x,0]}
 lib.append(sub);pin_coverage[ref].update(pins);units[ref].append({'unit':1,'synthetic':True,'pins':pins,**({'height':40.64} if ref=='J1' else {'height':15.24} if ref=='J3' else {})})

# Extra units expose package-only supply, ground and NC terminals explicitly.
for ref,p in source['parts'].items():
 missing=set(p['pins'])-pin_coverage[ref]
 if not missing:continue
 number=len(units[ref])+1;sub=sx.loads(f'(symbol "{ref}_{number}_1")');pins={}
 ordered=sorted(missing,key=lambda n:(not n.isdigit(),int(n) if n.isdigit() else n))
 h=max(5.08,(len(ordered)-1)*2.54/2+2.54)
 add(sub,f'(rectangle (start -6.35 {h}) (end 6.35 {-h}) (stroke (width .254) (type default)) (fill (type background)))')
 add(sub,f'(text "Package pins" (at 0 0 90) {effects(.85)})')
 for i,n in enumerate(ordered):
  x=-8.89;y=(len(ordered)-1)*1.27-i*2.54;native_pin(sub,n,x,y,0,2.54);pins[n]={'local_mm':[x,y]}
 libraries[ref].append(sub);units[ref].append({'unit':number,'synthetic':True,'extra':True,'pins':pins,'height':2*h})
 pin_coverage[ref].update(missing)
assert all(pin_coverage[r]==set(p['pins']) for r,p in source['parts'].items())

def instance(doc,gid,ref,unit,x,y):
 p=source['parts'][ref];number=unit['unit'];key=f'{gid}/{ref}/{number}'
 symbol=sx.loads(f'(symbol (lib_id "ChryslerScanner:{ref}") (at {f(x)} {f(y)} 0) (unit {number}) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp {"yes" if p["dnp"] else "no"}) (uuid "{uid(key)}"))')
 if unit.get('synthetic'):h=unit.get('height',27.94 if ref=='J2' else 2.54)/2;ref_y=y-h-4.54;value_y=ref_y+2.0
 else:
  bounds=unit['bounds'];cy=unit['center'][1];ref_y=y+(bounds[1]-cy)*SCALE-4.54;value_y=ref_y+2.0
 for key2,value,xx,yy,hidden in [('Reference',ref,x,ref_y,False),('Value',p['value'],x,value_y,False),('Footprint','footprints:'+p['footprint'],x,y,True),('Datasheet','',x,y,True)]:add(symbol,property_text(key2,value,xx,yy,1.05,hidden))
 add(symbol,property_text('atopile_address','ChryslerScannerV240.'+ref.lower(),x,y,1.05,True))
 for n in unit['pins']:add(symbol,f'(pin {quote(n)} (uuid "{uid(key+"/pin/"+n)}"))')
 add(symbol,f'(instances (project "{PROJECT}" (path "/{ROOT_ID}/{uid(gid)}" (reference "{ref}") (unit {number}))))')
 doc.append(symbol)

sheet_info=[];cleanup_info=[]
for page_number,group in enumerate(groups,2):
 gid=group['id'];members=group['members'];real_units=[(r,u) for r in members for u in units[r] if not u.get('synthetic')]
 if real_units:
  x0=min([u['bounds'][0] for r,u in real_units]+[q['pdf_xy'][0] for r,u in real_units for q in u['pins'].values()])-25
  y0=min([u['bounds'][1] for r,u in real_units]+[q['pdf_xy'][1] for r,u in real_units for q in u['pins'].values()])-25
  x1=max([u['bounds'][2] for r,u in real_units]+[q['pdf_xy'][0] for r,u in real_units for q in u['pins'].values()])+25
  y1=max([u['bounds'][3] for r,u in real_units]+[q['pdf_xy'][1] for r,u in real_units for q in u['pins'].values()])+25
 else:x0,y0,x1,y1=0,0,0,0
 x0=math.floor(x0/3.6)*3.6;x1=math.ceil(x1/3.6)*3.6
 y0=math.floor((y0-.48)/3.6)*3.6+.48;y1=math.ceil((y1-.48)/3.6)*3.6+.48
 crop=box(x0,y0,x1,y1)
 def xy(p):return (f(20.32+(p[0]-x0)*SCALE),f(35.56+(p[1]-y0)*SCALE))
 panel_y=35.56+(y1-y0)*SCALE+20
 synthetics=[(r,u) for r in members for u in units[r] if u.get('synthetic')]
 panel_positions={};px=50.8;py=panel_y;row_h=0
 for r,u in synthetics:
  h=u.get('height',27.94 if r=='J2' else 5.08)+18
  if px>335:px=50.8;py+=row_h+12;row_h=0
  panel_positions[r,u['unit']]=(px,math.ceil((py+h/2)/1.27)*1.27);px+=88.9;row_h=max(row_h,h)
 width=max(210,math.ceil((x1-x0)*SCALE+50),380 if synthetics else 210)
 if gid=='obd':width=210
 height=max(210,math.ceil(py+row_h+35) if synthetics else math.ceil(panel_y+20))
 doc=new_doc(gid,group['label'],width,height);lib=one(doc,'lib_symbols')
 for r in members:lib.append(copy.deepcopy(libraries[r]))
 text(doc,gid+'/heading',group['label'],20,18,2.0)
 text(doc,gid+'/caption',f'Current {REVISION} connectivity | named nets connect across sheets | DNP: R23/R24',20,24,.95)
 roots_in_sheet=defaultdict(list)
 for ref,u in real_units:
  x,y=xy(u['center']);instance(doc,gid,ref,u,x,y)
  for number,pin in u['pins'].items():
   if number not in source['parts'][ref]['pins']:continue
   net=source['parts'][ref]['pins'][number]['net'];p=tuple(pin['pdf_xy'])
   if net:roots_in_sheet[root(p)].append((ref,number,p,net))
   else:add(doc,f'(no_connect (at {xy(p)[0]} {xy(p)[1]}) (uuid "{uid(gid+"/nc/"+ref+"/"+number)}"))')
 for wire_root,terminals in roots_in_sheet.items():
  names={t[3] for t in terminals};assert len(names)==1,(gid,terminals)
  net=next(iter(names));candidates=[];degree=defaultdict(int)
  for i,(a,b) in enumerate(root_wires.get(wire_root,[])):
   clipped=LineString([a,b]).intersection(crop)
   if clipped.geom_type!='LineString' or clipped.length<.001:continue
   aa,bb=tuple(clipped.coords[0]),tuple(clipped.coords[-1]);wire(doc,f'{gid}/wire/{wire_root}/{i}',xy(aa),xy(bb));candidates.extend([aa,bb]);degree[aa]+=1;degree[bb]+=1
  for p,d in degree.items():
   if d>=3:add(doc,f'(junction (at {xy(p)[0]} {xy(p)[1]}) (diameter 0) (color 0 0 0 0) (uuid "{uid(gid+"/junction/"+str(p))}"))')
  preferred=[tuple(q['pdf_xy']) for q in raw['labels'] if q['name']==net and tuple(q['pdf_xy']) in parents and root(tuple(q['pdf_xy']))==wire_root and crop.covers(Point(*q['pdf_xy']))]
  if preferred:location=preferred[0]
  elif candidates:location=min(set(candidates),key=lambda p:(degree[p]!=1,p[1],p[0]))
  else:location=terminals[0][2]
  label_position=xy(location);label_angle=0
  terminal=next((t for t in terminals if t[2]==location),None)
  if terminal and degree.get(location,0)==0 and net not in internal_nets:
   ref,number,p,_=terminal
   unit=next(u for r,u in real_units if r==ref and number in u['pins'])
   bounds=unit['bounds']
   # Keep labels at their existing terminals. Moving them can cross nearby
   # conductors; face left-side labels outward to clear IC pin-name text.
   if p[0]<bounds[0]:label_angle=180
  label(doc,f'{gid}/net/{net}/{wire_root}',net,label_position,label_angle)
  # Cropped branches terminate in named ports, rather than dangling wires.
  terminal_positions={t[2] for t in terminals}
  for p,d in degree.items():
   if d==1 and p not in terminal_positions and p!=location:
    label(doc,f'{gid}/port/{net}/{p}',net,xy(p))
 for ref,u in synthetics:
  x,y=panel_positions[ref,u['unit']];instance(doc,gid,ref,u,x,y)
  for n,pin in u['pins'].items():
   dx,dy=pin['local_mm'];a=(x+dx,y-dy);net=source['parts'][ref]['pins'][n]['net']
   if net:
    b=(a[0]-5.08 if dx<0 else a[0]+5.08,a[1]);wire(doc,f'{gid}/{ref}/extra-wire/{n}',a,b);label(doc,f'{gid}/{ref}/extra-net/{n}',net,b,180 if dx<0 else 0)
   else:add(doc,f'(no_connect (at {f(a[0])} {f(a[1])}) (uuid "{uid(gid+"/nc/"+ref+"/"+n)}"))')
 if synthetics:text(doc,gid+'/package-heading','Pins 1-8: near board edge | 9-16: inboard row' if gid=='obd' else 'Additional package terminals / local hardware revision',20,panel_y-5,1.15)
 text(doc,gid+'/note','Atopile source; passive pins need ERC review.',20,height-20,.8)
 cleanup=clean_page(doc,gid,units,source);width,height=cleanup['size_mm']
 text(doc,gid+'/heading',group['label'],16,18,2.6)
 text(doc,gid+'/caption','Matching signal names connect between sheets. Values and package pins follow the atopile netlist.',16,27,1.15)
 text(doc,gid+'/note','Atopile source / editable KiCad view / passive pins require electrical review.',16,height-15,1.05)
 if gid in ['power-5v','power-7v5']:
  refs='U3 / U4' if gid=='power-5v' else 'U8'
  text(doc,gid+'/review',f'{refs}: DRV package pin 5 is connected to GND, per TI Table 5-1.',16,height-32,1.15)
  text(doc,gid+'/review-scope','Ground-pin correction applied to atopile, PCB and this schematic view.',16,height-27,1.05)
 if gid=='mcu':text(doc,gid+'/rf-dnp','Assembly option: R23 and R24 are DNP.',16,height-27,1.15)
 if gid=='usb':text(doc,gid+'/usb-note','USB-C: USB 2.0 device / 5 V sink. R102 and R103: independent 5.1 kohm CC pull-downs.',16,height-27,1.05)
 if gid=='obd':text(doc,gid+'/obd-note','ATTEND 226A-1202 / J1962 Type A: pins 1-8 near the PCB edge; pins 9-16 inboard.',16,height-27,1.05)
 filename=f'{page_number-1:02d}_{gid}.kicad_sch';write_doc(OUT/filename,doc)
 sheet_info.append({'id':gid,'title':group['label'],'file':filename,'page':page_number,'members':members,'size_mm':[width,height]})
 cleanup_info.append({'id':gid,**cleanup})

overview=new_doc('root',f'ChryslerScanner {REVISION} | circuit overview',420,297)
one(overview,'paper')[1:]=['A3']
text(overview,'overview-heading',f'ChryslerScanner {REVISION}',20,18,3.0)
text(overview,'overview-subtitle','241 components | 142 nets | functional sheets | editable KiCad visualization',20,27,1.4)
for i,sheet in enumerate(sheet_info):
 col,row=i%3,i//3;x,y=25+col*130,42+row*29
 doc=sx.loads(f'(sheet (at {x} {y}) (size 115 18) (stroke (width 0) (type default)) (fill (color 0 0 0 0)) (uuid "{uid(sheet["id"])}") {property_text("Sheetname",sheet["title"],x,y-1,1.27,False,"left")} {property_text("Sheetfile",sheet["file"],x,y+20,1.0,False,"left")} (instances (project "{PROJECT}" (path "/{ROOT_ID}" (page "{sheet["page"]}")))))')
 overview.append(doc)
 text(overview,'overview-count/'+sheet['id'],f'{len(sheet["members"])} parts / page {sheet["page"]}',x+4,y+10,1.1)
text(overview,'overview-note','Open a sheet to inspect symbols and wires. Matching signal names connect across sheets.',20,254,1.1)
text(overview,'overview-source','Includes USB-C and ATTEND OBD-II. Circuit edits belong in atopile; regenerate this view afterward.',20,260,1.05)
text(overview,'overview-review','Ground-pin correction: U3 / U4 / U8 pin 5 now connects to GND (TI TLV767 DRV).',20,266,1.05)
text(overview,'overview-limit','Passive pin types: connectivity checked, independent electrical review still required.',20,272,1.0)
add(overview,f'(sheet_instances (path "/" (page "1")))')
write_doc(OUT/(PROJECT+'.kicad_sch'),overview)
symbol_lib=[sx.Symbol('kicad_symbol_lib'),[sx.Symbol('version'),20241209],[sx.Symbol('generator'),'kicad_symbol_editor']]
for r,lib in libraries.items():
 lib=copy.deepcopy(lib);scale_library(lib);lib[1]=r;symbol_lib.append(lib)
(OUT/'ChryslerScanner.kicad_sym').write_text(sx.dumps(symbol_lib)+'\n')
(OUT/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "ChryslerScanner") (type "KiCad") (uri "${KIPRJMOD}/ChryslerScanner.kicad_sym") (options "") (descr "Recovered V240 circuit visualization symbols")))\n')
prepare_footprints(OUT/'footprints.pretty')
(OUT/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "footprints") (type "KiCad") (uri "${KIPRJMOD}/footprints.pretty") (options "") (descr "Current PCB packages; native schematic viewing copy")))\n')
(OUT/(PROJECT+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':PROJECT+'.kicad_pro','version':1},'schematic':{'meta':{'version':1}}},indent=2)+'\n')
(ROOT/'reference/schematic-generation.json').write_text(json.dumps({'source':'reference/v240-netlist.json','upstream_layout':'reference/upstream/ChryslerScanner_V240_schematic.pdf','root_schematic':'elec/schematic/'+PROJECT+'.kicad_sch','component_count':len(source['parts']),'net_count':len(source['nets']),'numbered_package_terminals':sum(len(p['pins']) for p in source['parts'].values()),'pages':len(sheet_info)+1,'sheets':sheet_info,'pin_electrical_types':'passive visualization types; ERC does not independently certify the circuit','atopile_remains_source_of_truth':True,'native_export_comparison_required':True},indent=2)+'\n')
(ROOT/'reference/schematic-cleanup.json').write_text(json.dumps({'schema':1,'native_text_metrics':'reference/schematic-text-metrics.json','layout_strategy':'Rigid connected-drawing packing; independent reference/value and port text spacing; native A4/A3 pages','resolved_source_issue':'U3/U4/U8 TLV767 DRV pin 5 now connects to GND; TI Table 5-1','sheets':cleanup_info,'native_netlist_validation_required':True},indent=2)+'\n')
print(f'Generated {len(sheet_info)+1} KiCad pages, {len(source["parts"])} component definitions, {sum(len(p["pins"]) for p in source["parts"].values())} package terminals')

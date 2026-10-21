"""Extract the colored KiCad PDF's part values, pins and wire graph.

The PDF is a vector plot. Brown symbol strokes, green wires and hidden text
allow reproducible recovery without OCR. Outputs retain every PDF pin coordinate.
"""
from pathlib import Path
from collections import defaultdict,Counter
from math import hypot
import json,re
import pymupdf as fitz
from shapely.geometry import Point,box,LineString
ROOT=Path(__file__).resolve().parents[1]
p=fitz.open(ROOT/'reference/upstream/ChryslerScanner_V240_schematic.pdf')[0]
D=p.get_drawings()
def fix(t):
 if '\x00' in t:
  try: t=t.encode('latin1').decode('utf-16-be').lstrip('\ufeff')
  except UnicodeError: t=t.replace('\x00','')
 return t
spans=[]; seen=set()
for b in p.get_text('dict')['blocks']:
 for l in b.get('lines',[]):
  # Join UTF16 values split into a BOM span and a body span.
  for s in l['spans']:
   t=fix(s['text']).replace('þÿ','')
   if not t.strip():continue
   key=(t,tuple(round(v,2) for v in s['origin']))
   if key in seen:continue
   seen.add(key);s={**s,'text':t,'dir':l['dir']};spans.append(s)
refs={s['text']:s for s in spans if re.fullmatch(r'(?:R|C|D|Q|U|L|JP|J|SW|H|AE)\d+[AB]?',s['text'])}
def xy(v):return tuple(round(n,2) for n in v)
def center(b):return ((b[0]+b[2])/2,(b[1]+b[3])/2)
def brown(d):return d['color'] and abs(d['color'][0]-.517647)<.0001
lines=[];rects=[];circles=[];triangles=[]
for d in D:
 if not brown(d):continue
 for it in d['items']:
  if it[0]=='l':lines.append((xy(it[1]),xy(it[2]),round(d['width'],3)))
  elif it[0]=='re':rects.append((tuple(round(v,2) for v in it[1]),round(d['width'],3)))
 if d['items'][0][0]=='c' and len(d['items'])==4 and abs(d['rect'].width-15.84)<.2 and abs(d['rect'].height-15.84)<.2:circles.append(tuple(round(v,2) for v in d['rect']))
 if len(d['items'])==3 and all(it[0]=='l' for it in d['items']) and abs(d['width']-.72)<.001:
  triangles.append((tuple(round(v,2) for v in d['rect']),[xy(it[1]) for it in d['items']]))
lines=list(dict.fromkeys(lines));rects=list(dict.fromkeys(rects));circles=list(dict.fromkeys(circles));triangles=list({b:(b,pts) for b,pts in triangles}.values())
parts={}
def assign(prefix,candidates):
 # Match closest pairs globally; disjoint symbol sets avoid neighbor/ref ambiguity.
 rr=[r for r in refs if re.fullmatch(prefix+r'\d+[AB]?',r)]
 choices=sorted((box(*refs[r]['bbox']).distance(box(*b)),hypot(*(a-c for a,c in zip(center(refs[r]['bbox']),center(b)))),r,i) for r in rr for i,b in enumerate(candidates))
 used=set();matched=set()
 for dist,_,r,i in choices:
  if r in matched or i in used:continue
  parts[r]={'ref':r,'body_bbox':list(candidates[i]),'pdf_center':list(center(candidates[i])),'pins':{},'match_distance':dist}
  used.add(i);matched.add(r)
 assert matched==set(rr),(prefix,set(rr)-matched)
# Resistors, including antenna series link with smaller symbol.
rboxes=[b for b,w in rects if w==.72 and (abs((b[2]-b[0])*(b[3]-b[1])-82.944)<.3 or (abs(b[2]-b[0]-7.92)<.02 and abs(b[3]-b[1]-2.88)<.02))]
assign('R',rboxes)
# Capacitor plate pairs (11.52 pt wide, 4.32 pt apart).
plates=[(a,b) for a,b,w in lines if w==1.44 and abs(hypot(b[0]-a[0],b[1]-a[1])-11.52)<.02]
cboxes=[]
for i,(a,b) in enumerate(plates):
 for c,d in plates[i+1:]:
  if abs(a[0]-c[0])<.02 and abs(b[0]-d[0])<.02 and abs(abs(a[1]-c[1])-4.32)<.02 or abs(a[1]-c[1])<.02 and abs(b[1]-d[1])<.02 and abs(abs(a[0]-c[0])-4.32)<.02:
   cboxes.append((min(a[0],b[0],c[0],d[0]),min(a[1],b[1],c[1],d[1]),max(a[0],b[0],c[0],d[0]),max(a[1],b[1],c[1],d[1])))
# Polarized C1 has plates 2.88pt apart: explicit source coordinate.
cboxes.append((235.44,128.64,246.96,131.52))
assign('C',cboxes)
assign('Q',circles)
# Diode triangles; bidirectional TVS D1 is two triangles and handled separately.
dboxes=[b for b,pts in triangles if abs(b[2]-b[0]-7.2)<.02 and abs(b[3]-b[1]-7.2)<.02 and not (185<b[0]<197 and 120<b[1]<140)]
dboxes.append((187.2,122.88,194.4,137.28))
assign('D',dboxes)
# Large IC boxes and the four comparator/buffer triangles.
ubs=[b for b,w in rects if w==.72 and b[2]-b[0]>=28 and b[3]-b[1]>=28 and b[2]-b[0]<150 and b[3]-b[1]<250]
ubs.extend(b for b,pts in triangles if b[2]-b[0]>=21)
# Analog switch symbols are bowties (no rectangular body).
ubs.extend([(748.8,389.28,763.2,403.68),(748.8,443.28,763.2,457.68),(979.2,389.28,993.6,403.68),(979.2,443.28,993.6,457.68),(748.8,576.48,763.2,590.88),(979.2,576.48,993.6,590.88)])
# J2's USB symbol box is among the IC boxes; exclude it before matching.
ubs=[b for b in ubs if b!=(291.6,90.48,320.4,133.68)]
assign('U',ubs)
# Inductor and ferrite coordinates from symbol plots.
for r,c,axis in [('L1',(622.8,97.68),'h'),('L2',(108,223.68),'h'),('L3',(226.8,223.68),'h'),('L4',(421.2,238.08),'h'),('L5',(493.2,238.08),'h'),('L6',(687.6,238.08),'h')]:
 parts[r]={'ref':r,'body_bbox':[c[0]-3,c[1]-3,c[0]+3,c[1]+3],'pdf_center':list(c),'pins':{},'axis':axis}
manual={'J1':[54,79.68,126,166.08],'J2':[291.6,90.48,320.4,133.68],'J3':[565.2,796.08,586.8,810.48],'JP1':[136.8,144.48,136.8,151.68],'JP2':[396,68.88,403.2,68.88],'SW1':[72,666.48,93.6,666.48],'SW2':[180,666.48,201.6,666.48],'AE1':[61.2,504.48,68.4,522.48]}
for r,b in manual.items():parts[r]={'ref':r,'body_bbox':b,'pdf_center':list(center(b)),'pins':{}}
# Nearest value text, constrained to ref direction and same ref/value columns.
for r,c in parts.items():
 ref=refs[r];rc=center(ref['bbox']);horizontal=ref['dir'][0]==1
 cand=[]
 for s in spans:
  t=s['text']
  if t in refs or t=='GND' or t=='PWR_FLAG' or re.fullmatch(r'\d+',t):continue
  if r.startswith('R') and not (t=='nc' or re.fullmatch(r'[0-9.]+[kM]?Ω',t)):continue
  if r.startswith('C') and not re.fullmatch(r'[0-9.]+[pnuμµ]?F',t):continue
  sc=center(s['bbox']);dx=sc[0]-rc[0];dy=sc[1]-rc[1]
  if horizontal and 3<dy<25 and abs(dx)<35: cand.append((abs(dy-7.2)+abs(dx)*.3,t))
  elif not horizontal and abs(dy)<20 and abs(dx)<15 and dx>0:cand.append((abs(dx-7.2)+abs(dy)*.3,t))
 c['value']=min(cand)[1] if cand else ''
# Explicit IC values and packages; PDF does not specify most passive packages.
values={'U1':'SY6283','U2':'LMR14010','U3':'TLV76750DRV','U4':'TLV76733DRV','U5':'LGS6302','U6':'LMR14010','U7':'LMR14010','U8':'TLV76701DRV','U9':'TS391C','U10':'ESP32-PICO-V3-02','U11':'USBLC6-2SC6','U12':'CP2102','U13A':'74LVC2G66','U13B':'74LVC2G66','U14A':'74LVC2G66','U14B':'74LVC2G66','U15A':'74LVC2G66','U15B':'74LVC2G66','U16':'TS391C','U17':'74LVC1G17','U18':'74LVC1G14','U19':'AW9523B','J1':'J1962','J2':'USB-B','J3':'I2C','JP1':'SGND','JP2':'USBPWRBYP','SW1':'RESET','SW2':'BOOT','AE1':'ANT3216LL00R2400A','L1':'22µH','L2':'22µH','L3':'240nH','L4':'22µH','L5':'470nH','L6':'22µH'}
values.update({r:'0.1μF' for r in ['C11','C52','C54','C55']})
values.update({'R50':'1.62kΩ','R52':'1.62kΩ','R54':'1.62kΩ','R25':'499Ω','C37':'220pF','C40':'220pF','D3':'LMBR130T1G','D27':'ESD5Z3V3','D28':'ESD5Z3V3','D29':'ESD5Z3V3'})
values.update({f'Q{i}{unit}':v for i,v in {1:'CJ3439KDW',2:'2N7002DW',3:'2N7002DW',4:'2N7002DW',5:'UMH3N',6:'CJ3439KDW',7:'HSSK8811',**{i:'HSW4602' for i in range(8,16)},16:'CJ3439KDW'}.items() for unit in 'AB'})
values.update({f'Q{i}':'AO3400' for i in range(17,21)})
for r,v in values.items():parts[r]['value']=v
# Green wire graph: endpoints make T junctions, crossings only join at endpoints/dots.
wl=[];dots=[]
for d in D:
 if not d['color'] or abs(d['color'][1]-.588235)>.0001 or d['color'][0]!=0:continue
 for it in d['items']:
  if it[0]=='l':wl.append((xy(it[1]),xy(it[2])))
 if d['fill']:dots.append(xy(center(d['rect'])))
wl=list(dict.fromkeys(wl)); nodes=set(q for l in wl for q in l);nodes.update(dots)
parent={q:q for q in nodes}
def root(q):
 while parent[q]!=q:parent[q]=parent[parent[q]];q=parent[q]
 return q
def union(a,b):parent[root(a)]=root(b)
for a,b in wl:union(a,b)
for q in nodes:
 for a,b in wl:
  if a==b:continue
  if LineString([a,b]).distance(Point(q))<.015:union(q,a)
# Numeric pin text belongs to brown pin lines, not wire labels.
nums=[s for s in spans if re.fullmatch(r'\d{1,2}',s['text']) and 40<s['bbox'][1]<1100]
pinlines=[(a,b) for a,b,w in lines if w==.432 and (abs(a[0]-b[0])<.01 or abs(a[1]-b[1])<.01) and 3.59<=hypot(a[0]-b[0],a[1]-b[1])<=18.01]
def addpin(c,n,q):
 n=str(n);q=xy(q)
 if n in c['pins'] and c['pins'][n]['pdf_xy']!=list(q):raise ValueError((c['ref'],n,c['pins'][n],q))
 if q not in parent:parent[q]=q;nodes.add(q)
 for a,b in wl:
  if LineString([a,b]).distance(Point(q))<.015:union(q,a)
 c['pins'][n]={'pdf_xy':list(q)}
# Two-terminal passive pins. Non-polar passives get arbitrary consistent numbering.
for r,c in parts.items():
 x,y=c['pdf_center'];b=c['body_bbox']
 if r.startswith(('R','C','L')) and not r.startswith('JP'):
  horiz=r.startswith('L') or (r.startswith('R') and b[2]-b[0]>b[3]-b[1]) or (r.startswith('C') and b[2]-b[0]<b[3]-b[1])
  length=10.8
  addpin(c,1,(x-length,y) if horiz else (x,y-length));addpin(c,2,(x+length,y) if horiz else (x,y+length))
 elif r.startswith('D'):
  if r=='D1':addpin(c,1,(x,y-10.8));addpin(c,2,(x,y+10.8));continue
  pts=next(pts for bb,pts in triangles if list(bb)==b)
  countsX=Counter(t[0] for t in pts);countsY=Counter(t[1] for t in pts)
  if len(countsX)==2:
   tip=next(k for k,v in countsX.items() if v==1);sgn=1 if tip>x else -1
   addpin(c,1,(x+sgn*10.8,y));addpin(c,2,(x-sgn*10.8,y))
  else:
   tip=next(k for k,v in countsY.items() if v==1);sgn=1 if tip>y else -1
   addpin(c,1,(x,y+sgn*10.8));addpin(c,2,(x,y-sgn*10.8))
 else:
  bb=box(*b).buffer(15 if r.startswith('Q') else 19)
  for a,z in pinlines:
   # Prefer pin lines with a terminal on a green wire; unconnected pins handled too.
   if not bb.covers(Point(a)) or not bb.covers(Point(z)):continue
   mid=((a[0]+z[0])/2,(a[1]+z[1])/2)
   ns=sorted((box(*s['bbox']).distance(Point(mid)),s['text'],s) for s in nums if box(*s['bbox']).distance(Point(mid))<3)
   if not ns:continue
   n=ns[0][1]
   # Exclude numbers belonging to a neighboring part's pin.
   pc=c['pdf_center'];out=max([a,z],key=lambda q:hypot(q[0]-pc[0],q[1]-pc[1]))
   if r.startswith('Q') and box(*b).distance(Point(out))<5:continue
   # External endpoint is furthest from symbol, within 20 pt.
   if box(*b).distance(Point(out))>19.1:continue
   try:addpin(c,n,out)
   except ValueError:pass
# Explicit hidden pins for switches, jumpers and antenna.
for r,pp in {'JP1':{2:(136.8,140.88),1:(136.8,162.48)},'JP2':{1:(388.8,68.88),2:(410.4,68.88)},'SW1':{1:(68.4,666.48),2:(97.2,666.48)},'SW2':{1:(176.4,666.48),2:(205.2,666.48)},'AE1':{1:(79.2,526.08),2:(64.8,526.08)},'Q5A':{1:(313.2,659.28),2:(284.4,644.88),6:(313.2,630.48)},'Q5B':{3:(313.2,706.08),4:(313.2,677.28),5:(284.4,691.68)},'Q16A':{1:(734.4,1112.88),2:(716.4,1098.48),6:(734.4,1084.08)},'U18':{2:(655.2,1098.48),3:(669.6,1112.88),4:(694.8,1098.48),5:(669.6,1084.08)}}.items():
 parts[r]['pins']={}
 for n,q in pp.items():addpin(parts[r],n,q)
# Refresh roots after adding pin terminals (including directly touching symbols).
for r,c in parts.items():
 for n,v in c['pins'].items():v['wire_root']=list(root(tuple(v['pdf_xy'])))
# Label attachment. Use nearest wire endpoint to the actual hidden text bounding box.
netnames=defaultdict(set)
labels=[]
global_names=set('GND +12V +5V +3.3V +7.5V VBUS VBB VPP SWVPP FBVPP FBVBB SWVBB SW8V5 FB8V5 FB7V5 SW6V FB6V 6V 8V5 EN IO0 LNA_IN SDA SCL TX0 RX0 TX1 RX1 TX2 RX2 PCI_RX PCI_TX PWR_LED RX_LED TX_LED ACT_LED V_BA V_BT V_PR RTS DTR D+ D- D+P D-P CCD+ CCD- TX6_EN TX9_EN TX12_EN TX14_EN RX7_EN RX15_EN RX7_BIAS_EN RX7_BIAS TBEN VBB_TO_TX6 VBB_TO_TX9 VBB_TO_TX12 VBB_TO_TX14 VPP_TO_TX6 VPP_TO_TX9 VPP_TO_TX12 VPP_TO_TX14'.split())
global_names.update(f'J1962-{i}' for i in range(1,17))
glyph_cache={}
for s in spans:
 t=s['text']
 if t not in global_names:continue
 if any(box(*c['body_bbox']).contains(Point(center(s['bbox']))) for r,c in parts.items() if r.startswith('U')):continue
 bb=box(*s['bbox'])
 if t in ['GND','+12V','+5V','+3.3V','+7.5V','VBUS','VBB','VPP']:
  key=t=='GND'
  if key not in glyph_cache:
   glyphs=[]
   if t=='GND':
    for d in D:
     if not brown(d) or len(d['items'])!=5 or not all(i[0]=='l' for i in d['items']):continue
     if abs(d['rect'].width-7.2)<.02 and abs(d['rect'].height-7.2)<.02:glyphs.append((tuple(d['rect']),xy(d['items'][0][1])))
   else:
    for a,b,w in lines:
     if w!=.432 or abs(hypot(a[0]-b[0],a[1]-b[1])-7.2)>.02:continue
     for tip,q in [(a,b),(b,a)]:
      diag=[(c,e) for c,e,ww in lines if ww==.432 and (c==tip or e==tip) and abs(hypot(c[0]-e[0],c[1]-e[1])-hypot(3.6,2.16))<.02]
      if len(diag)>=2:glyphs.append(((min(a[0],b[0])-2,min(a[1],b[1])-2,max(a[0],b[0])+2,max(a[1],b[1])+2),q))
   glyph_cache[key]=glyphs
  glyphs=glyph_cache[key]
  candidates=sorted((bb.distance(box(*gb)),hypot(*(a-b for a,b in zip(center(s['bbox']),center(gb)))),q) for gb,q in glyphs)
  if not candidates or candidates[0][0]>14:continue
  _,_,q=candidates[0];near=[(0,0,q)]
  if q not in parent:parent[q]=q;nodes.add(q)
 else:
  polys=[d for d in D if brown(d) and len(d['items'])==6 and all(i[0]=='l' for i in d['items']) and xy(d['items'][0][1])==xy(d['items'][-1][2]) and (abs(d['rect'].width-7.2)<.02 or abs(d['rect'].height-7.2)<.02)]
  candidates=sorted((bb.distance(box(*d['rect'])),hypot(*(a-b for a,b in zip(center(s['bbox']),center(d['rect'])))),d['seqno'],d) for d in polys)
  if not candidates or candidates[0][0]>4:continue
  q=xy(candidates[0][-1]['items'][0][1]);near=[(0,0,q)]
  if q not in parent:parent[q]=q;nodes.add(q)
 dist,_,q=near[0]
 if dist>5:continue
 netnames[root(q)].add(t);labels.append({'name':t,'pdf_xy':list(q),'distance':dist})
conflicts={str(k):sorted(v) for k,v in netnames.items() if len(v)>1}
# Canonical name of unlabeled wire islands derives from a part/pin, never invented signal intent.
groups=defaultdict(list)
for r,c in parts.items():
 for n,v in c['pins'].items():
  k=tuple(v['wire_root']) if v['wire_root'] else None
  if k:groups[k].append((r,n))
for k,pp in groups.items():
 names=netnames[k]
 name=sorted(names)[0] if names else 'N_'+pp[0][0]+'_'+pp[0][1]
 for r,n in pp:parts[r]['pins'][n]['net']=name
nc=[]
for d in D:
 if d['color'] and abs(d['color'][2]-.517647)<.001 and len(d['items'])==1 and d['items'][0][0]=='l':
  a,b=d['items'][0][1:]
  if abs(abs(a.x-b.x)-3.456)<.02 and abs(abs(a.y-b.y)-3.456)<.02:nc.append(xy(center(d['rect'])))
for r,c in parts.items():
 for n,v in c['pins'].items():
  if 'net' not in v:v['net']=None
  if tuple(v['pdf_xy']) in nc:v['net']=None;v['no_connect']=True
(ROOT/'reference/upstream/v240-extracted.json').write_text(json.dumps({'parts':parts,'labels':labels,'conflicts':conflicts,'wires':wl},indent=2,ensure_ascii=False))
print('parts',len(parts),'pins',sum(len(c['pins']) for c in parts.values()),'nets',len(groups),'conflicts',conflicts)
print('pin counts',[(r,len(c['pins'])) for r,c in parts.items() if r.startswith(('U','Q','J','SW','AE'))])
print('unattached passives',[(r,n,v['pdf_xy']) for r,c in parts.items() if r.startswith(('R','C','D','L')) for n,v in c['pins'].items() if not v['net']])
print('values',[(r,c['value']) for r,c in parts.items() if r.startswith(('R','C','D'))])

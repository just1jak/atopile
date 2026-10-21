"""Generate editable atopile 0.15 source from the audited V240 PDF wire graph.

Only rerun after intentionally changing the extracted source or package choices.
PCB placement is separate so electrical edits do not reset manual placement.
"""
from pathlib import Path
from collections import defaultdict
import json,re,csv,copy,argparse
import sexpdata as sx
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--keep-footprints',action='store_true',help='Regenerate electrical sources while preserving existing footprint geometry and models')
args=parser.parse_args()
SRC=ROOT/'elec/src';FP=SRC/'footprints';FP.mkdir(parents=True,exist_ok=True)
raw=json.load(open(ROOT/'reference/upstream/v240-extracted.json'))
assert not raw['conflicts'],raw['conflicts']
old=json.load(open(ROOT/'reference/v140-layout-reference.json'))
parts={}
for r,c in raw['parts'].items():
 ref=re.sub(r'[AB]$','',r)
 if ref not in parts:parts[ref]={**copy.deepcopy(c),'ref':ref,'units':[],'pins':{}}
 p=parts[ref];p['units'].append(r)
 for n,v in c['pins'].items():
  assert n not in p['pins'],(ref,n)
  p['pins'][n]=copy.deepcopy(v)
def extra(r,n,net,reason):
 assert str(n) not in parts[r]['pins'],(r,n)
 parts[r]['pins'][str(n)]={'net':net,'origin':reason,'no_connect':net is None}
for r in ['U13','U14','U15']:
 extra(r,4,'GND','hidden supply pin');extra(r,8,'+3.3V','hidden supply pin')
for r in ['U17','U18']:extra(r,1,None,'unused package pin')
for r in ['U3','U4','U8']:extra(r,5,'GND','TLV767 DRV GND pad; TI datasheet Table 5-1')
extra('U12',10,None,'CP2102 NC pad');extra('U12',29,'GND','CP2102 exposed pad')
extra('U19',25,'GND','AW9523B exposed pad, datasheet page 5')
for n in [4,43,46]:extra('U10',n,'+3.3V','ESP32-PICO-V3-02 supply pad, Espressif datasheet')
for n in [25,35,36,44,45,47,48]:extra('U10',n,None,'ESP32-PICO-V3-02 NC pad')
override_path=ROOT/'reference/hardware-overrides.json'
hardware=json.loads(override_path.read_text()) if override_path.exists() else {}
for r,change in hardware.get('parts',{}).items():
 if r not in parts:parts[r]={'ref':r,'units':[r],'origin':'local hardware revision'}
 parts[r].update({k:copy.deepcopy(v) for k,v in change.items() if k!='pins'})
 parts[r]['pins']={n:{'net':net,'no_connect':net is None,'origin':'local hardware override: '+hardware['hardware_revision']} for n,net in change['pins'].items()}

def footprint(name,pads,w,h,desc):
 if args.keep_footprints and (FP/(name+'.kicad_mod')).exists():return
 out=[f'(footprint "{name}" (version 20240108) (generator pcbnew)',
  '  (layer "F.Cu")',f'  (descr {json.dumps(desc)})','  (attr smd)',
  f'  (fp_text reference "REF**" (at 0 {-h/2-1}) (layer "F.SilkS") (effects (font (size 0.7 0.7) (thickness 0.12))))',
  f'  (fp_text value "{name}" (at 0 {h/2+1}) (layer "F.Fab") (effects (font (size 0.7 0.7) (thickness 0.12))))',
  f'  (fp_rect (start {-w/2} {-h/2}) (end {w/2} {h/2}) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))',
  f'  (fp_rect (start {-w/2-.25} {-h/2-.25}) (end {w/2+.25} {h/2+.25}) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))']
 for n,x,y,pw,ph,*drill in pads:
  typ='thru_hole' if drill else 'smd';shape='rect' if not drill or str(n)=='1' else 'oval'
  layers='"*.Cu" "*.Mask"' if drill else '"F.Cu" "F.Paste" "F.Mask"'
  out.append(f'  (pad "{n}" {typ} {shape} (at {x:.6f} {y:.6f}) (size {pw:.6f} {ph:.6f})'+(f' (drill {drill[0]})' if drill else '')+f' (layers {layers}))')
 out.append(')');(FP/(name+'.kicad_mod')).write_text('\n'.join(out)+'\n')
def qfn(name,count,dist,pitch,pw,ph,ep,body,desc):
 pads=[];N=count//4
 for i in range(N):
  t=(i-(N-1)/2)*pitch
  pads.extend([(i+1,-dist,t,pw,ph),(N+i+1,t,dist,ph,pw),(2*N+i+1,dist,-t,pw,ph),(3*N+i+1,-t,-dist,ph,pw)])
 pads.append((count+1,0,0,ep,ep));footprint(name,pads,body,body,desc)
qfn('CP2102_V140_Reference',28,2.5,.5,1.518666,.318770,2.80162,6.7,'Recovered V140 pad centers; 0.0508mm mask expansion; pin 1 left/top canonical orientation')
qfn('ESP32_PICO_V3_02',48,3.365,.5,.68,.25,4.5,7.8,'Espressif ESP32-PICO series datasheet Figure 16; 7x7mm LGA48 + GND pad49; thermal vias to be designed')
qfn('AW9523B_QFN24',24,1.9,.5,.6,.25,2.7,4.4,'Awinic AW9523B datasheet page 25 land pattern, rotated to canonical pin 1 left/top')
footprint('USBLC6_V140_Reference',[(1,-.94996,1.300099,.65151,1.101598),(2,0,1.300099,.65151,1.101598),(3,.94996,1.300099,.65151,1.101598),(4,.94996,-1.300099,.65151,1.101598),(5,0,-1.300099,.65151,1.101598),(6,-.94996,-1.300099,.65151,1.101598)],3.2,3.8,'V140 USBLC6 mask pad centers recovered from Gerber; mask expansion 0.0508mm')
footprint('LED_V140_Reference',[(1,-1.739392,0,1.601978,2.10185),(2,1.739392,0,1.601978,2.10185)],5.1,2.21,'V140 status LED pad centers recovered from Gerber; cathode pad1 left')
obd=sorted(old['obd_drills_mm'],key=lambda q:(q[0],-q[1]));cx=sum(q[0] for q in obd)/16;cy=sum(q[1] for q in obd)/16
footprint('OBD16_V140_Reference',[(i+1,x-cx,cy-y,2.5,2.5,1.2) for i,(x,y) in enumerate(obd)],6.0,32.0,'V140 original 16 connector drill positions; pin1 upper-left, pin9 upper-right, inferred from silkscreen')
footprint('SY6283_DFN4',[(1,-.65,-.375,1.1,.25),(2,-.65,.375,1.1,.25),(3,.65,.375,1.1,.25),(4,.65,-.375,1.1,.25)],2.4,1.2,'Silergy SY6283 page9 recommended layout rotated 90deg CCW; DFN1.2x1.6-4')
footprint('ANT3216LL00R2400A',[(1,-1.5,0,.8,1.8),(2,1.5,0,.8,1.8)],3.8,2.0,'Yageo 3.2x1.6 antenna: pad1 S1 feed, pad2 S2 mechanical solder; pad size provisional')
if not args.keep_footprints or not (FP/'MountingHole_4mm.kicad_mod').exists():
 (FP/'MountingHole_4mm.kicad_mod').write_text('(footprint "MountingHole_4mm" (version 20240108) (generator "pcbnew") (layer "F.Cu") (attr exclude_from_bom exclude_from_pos_files) (fp_text reference "REF**" (at 0 -3.1) (layer "F.SilkS") (effects (font (size .7 .7) (thickness .1)))) (pad "" np_thru_hole circle (at 0 0) (size 4 4) (drill 4) (layers "*.Cu" "*.Mask")))\n')

def pick(r,c):
 if r in hardware.get('parts',{}):return c['footprint'],c['package_note'],c['manufacturer']
 if r.startswith('R'):return ('R_1206_3216Metric' if r in ['R19','R20','R29','R30','R33','R37','R40','R43','R46'] else 'R_0603_1608Metric'),'package choice: verify power/voltage/tolerance', 'Generic'
 if r=='C1':return 'CP_Radial_D8.0mm_P3.50mm','package choice: verify 100uF 50V diameter/height','Generic'
 if r.startswith('C'):return ('C_1206_3216Metric' if int(r[1:])<=24 else 'C_0805_2012Metric' if c['value']=='10µF' else 'C_0603_1608Metric'),'package choice: verify voltage/DC bias','Generic'
 if r.startswith('D'):
  n=int(r[1:]);f='LED_V140_Reference' if 23<=n<=26 else 'D_SMB' if n in [1,2] else 'D_SOD-323' if n>=27 else 'D_SOD-123'
  return f,'retained Gerber geometry' if 23<=n<=26 else 'package choice: verify exact diode suffix', 'Generic'
 if r.startswith('Q'):
  n=int(r[1:]);f='SOT-23' if n>=17 else 'SOT-363_SC-70-6' if n==5 else 'SOT-23-6'
  return f,'package choice: verify manufacturer suffix','ROHM' if n==5 else 'Generic'
 if r.startswith('L'):return ('R_1206_3216Metric','ferrite/inductor package provisional: verify impedance/current','Generic') if r in ['L3','L5'] else ('L_7.3x7.3_H3.5','22uH package provisional: >=1.7A per schematic','Generic')
 specific={'U1':('SY6283_DFN4','Silergy'),'U2':('SOT-23-6','Texas Instruments'),'U3':('WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm','Texas Instruments'),'U4':('WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm','Texas Instruments'),'U5':('SOT-23-5','Legend-Si'),'U6':('SOT-23-6','Texas Instruments'),'U7':('SOT-23-6','Texas Instruments'),'U8':('WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm','Texas Instruments'),'U9':('SOT-23-5','STMicroelectronics'),'U10':('ESP32_PICO_V3_02','Espressif'),'U11':('USBLC6_V140_Reference','STMicroelectronics'),'U12':('CP2102_V140_Reference','Silicon Labs'),'U13':('VSSOP-8_2.3x2mm_P0.5mm','Nexperia'),'U14':('VSSOP-8_2.3x2mm_P0.5mm','Nexperia'),'U15':('VSSOP-8_2.3x2mm_P0.5mm','Nexperia'),'U16':('SOT-23-5','STMicroelectronics'),'U17':('SOT-23-5','Nexperia'),'U18':('SOT-23-5','Nexperia'),'U19':('AW9523B_QFN24','Awinic'),'J1':('OBD16_V140_Reference','Generic'),'J2':('USB_B_Lumberg_2411_02_Horizontal','Lumberg'),'J3':('PinHeader_2x03_P2.54mm_Vertical','Generic'),'JP1':('SolderJumper-2_P1.3mm_Bridged_Pad1.0x1.5mm','Generic'),'JP2':('SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm','Generic'),'SW1':('SW_SPST_TL3305A','E-Switch'),'SW2':('SW_SPST_TL3305A','E-Switch'),'AE1':('ANT3216LL00R2400A','Yageo')}
 f,m=specific[r];return f, 'verify chosen orderable package against BOM' if r not in ['U1','U10','U11','U12','U19','J1'] else 'Gerber or manufacturer dimensions',m
def key(r):return (re.sub(r'\d','',r),int(re.sub(r'\D','',r)))
parts=dict(sorted(parts.items(),key=lambda t:key(t[0])))
for r,c in parts.items():
 c['footprint'],c['package_note'],c['manufacturer']=pick(r,c)
 # Every physical footprint pad is represented; genuinely NC package pins remain floating.
 fp=sx.loads((FP/(c['footprint']+'.kicad_mod')).read_text())
 nums={str(e[1]) for e in fp if isinstance(e,list) and str(e[0])=='pad' and str(e[1])}
 for n in nums-set(c['pins']):extra(r,n,None,'footprint-only mechanical/NC pad')
 assert set(c['pins'])<=nums,(r,set(c['pins'])-nums)
 c['dnp']=c['value']=='nc'
 # Assembly suffixes compatible with the selected package; values preserve schematic names.
 c['orderable_hint']=hardware.get('parts',{}).get(r,{}).get('orderable_hint') or {'U1':'SY6283DRC','U5':'LGS6302B5','U13':'74LVC2G66DP','U14':'74LVC2G66DP','U15':'74LVC2G66DP','U19':'AW9523BTQR','U9':'TS391ILT','U16':'TS391ILT'}.get(r,c['value'])
def pin_key(n):
 return (0,int(n)) if n.isdigit() else (1,re.sub(r'\d','',n),int(re.sub(r'\D','',n) or '0'))
out=['# GPL-3.0-or-later; derived from laszlodaniel/ChryslerScanner V240.', '# Generated by scripts/generate_atopile.py; package choices are listed in BOM.csv.', 'import is_atomic_part','import has_designator','']
for r,c in parts.items():
 out.extend([f'# {r}: {c["value"]}; {c["package_note"]}',f'component Part_{r}:',f'    trait is_atomic_part<manufacturer={json.dumps(c["manufacturer"])}, partnumber={json.dumps(c["orderable_hint"])}, footprint="footprints/{c["footprint"]}.kicad_mod", symbol="symbols/{r}.kicad_sym">',f'    trait has_designator<designator="{r}">'])
 out.extend('    pin '+n for n in sorted(c['pins'],key=pin_key));out.append('')
 # Each symbol includes complete physical pad numbers, for inspection/export.
 syms=SRC/'symbols';syms.mkdir(exist_ok=True)
 pins=sorted(c['pins'],key=pin_key);height=max(5,(len(pins)+1)*2.54)
 s=[f'(kicad_symbol_lib (version 20231120) (generator kicad_symbol_editor) (symbol "{r}" (in_bom yes) (on_board yes)',f'(property "Reference" "{re.sub(r"[0-9]","",r)}" (at 0 3.81 0) (effects (font (size 1.27 1.27))))',f'(property "Value" {json.dumps(c["value"])} (at 0 0 0) (effects (font (size 1.27 1.27))))',f'(symbol "{r}_0_1" (rectangle (start -2.54 0) (end 2.54 {-height}) (stroke (width 0) (type default)) (fill (type background))))',f'(symbol "{r}_1_1"']
 for i,n in enumerate(pins):s.append(f'(pin passive line (at -5.08 {-2.54*(i+1)} 0) (length 2.54) (name "{n}" (effects (font (size 1.0 1.0)))) (number "{n}" (effects (font (size 1.0 1.0)))))')
 s.append(')))');(syms/(r+'.kicad_sym')).write_text('\n'.join(s))
for i in range(1,5):
 r=f'H{i}'
 out.extend([f'component Part_{r}:',f'    trait is_atomic_part<manufacturer="Mechanical", partnumber="4mm NPTH", footprint="footprints/MountingHole_4mm.kicad_mod", symbol="symbols/{r}.kicad_sym">',f'    trait has_designator<designator="{r}">',''])
 (SRC/'symbols'/f'{r}.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "kicad_symbol_editor"))\n')
(SRC/'parts.ato').write_text('\n'.join(out))
main=['# ChryslerScanner V240 schematic revision 2.4.0-1 (2026-01-05).','# Complete physical parts, same-numbered multi-unit symbols merged.','# Floating pins are intentional NCs; see reference/v240-netlist.json.']
if hardware:main.append('# Local hardware revision '+hardware['hardware_revision']+': see reference/hardware-overrides.json; upstream PDF unchanged.')
main.extend(f'from "parts.ato" import Part_{r}' for r in parts)
main.extend(f'from "parts.ato" import Part_H{i}' for i in range(1,5))
main.extend(['','module ChryslerScannerV240:'])
main.extend(f'    {r.lower()} = new Part_{r}' for r in parts)
main.extend(f'    h{i} = new Part_H{i}' for i in range(1,5))
nets=defaultdict(list)
for r,c in parts.items():
 for n,v in c['pins'].items():
  if v['net']:nets[v['net']].append((r,n))
for i,(net,pp) in enumerate(sorted(nets.items())):
 var='net_'+re.sub(r'[^A-Za-z0-9_]','_',net)
 # Distinguish D+ from D- and similarly named +/- rails.
 var=f'n{i:03d}_{var}'
 main.extend(['',f'    # {net}',f'    signal {var}',f'    {var}.override_net_name = {json.dumps(net)}'])
 main.extend(f'    {var} ~ {r.lower()}.{n}' for r,n in pp)
(SRC/'main.ato').write_text('\n'.join(main)+'\n')
(ROOT/'ato.yaml').write_text("requires-atopile: '0.15.9'\npaths:\n  src: ./elec/src\n  layout: ./elec/layout\nbuilds:\n  v240:\n    entry: elec/src/main.ato:ChryslerScannerV240\n")
(ROOT/'reference/v240-netlist.json').write_text(json.dumps({'schematic_commit':'4ddc6e5d1c260c87c6139f60079932ffde6e5d9a','hardware_revision':hardware.get('hardware_revision','V240'),'local_hardware_overrides':'reference/hardware-overrides.json' if hardware else None,'parts':parts,'nets':dict(nets)},indent=2,ensure_ascii=False))
with (ROOT/'BOM.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['Reference','SchematicValue','OrderableHint','Manufacturer','Footprint','DNP','PackageReview'])
 for r,c in parts.items():w.writerow([r,c['value'],c['orderable_hint'],c['manufacturer'],c['footprint'],c['dnp'],c['package_note']])
print(f'Generated {len(parts)} physical parts, {len(nets)} connected nets, {sum(len(p["pins"]) for p in parts.values())} physical pads')

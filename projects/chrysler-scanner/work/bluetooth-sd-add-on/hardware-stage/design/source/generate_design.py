"""Generate the reviewed USB/BLE-only XIAO SD carrier native KiCad sources."""
import copy, json, math, uuid, shutil
from pathlib import Path
import sexpdata as sx
HERE=Path(__file__).resolve().parent
OUT=HERE/'design'; OUT.mkdir(exist_ok=True)
SYMS=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols')
FPS=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
S=sx.Symbol
N=lambda k,*v:[S(k),*v]
K=lambda x:str(x[0]) if isinstance(x,list) and x else ''
F=lambda a,k:next((x for x in a if K(x)==k),None)
U=lambda name:str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-ble-sd-revA/'+name))
def pretty(n,i=0):
 t=sx.dumps(n)
 if not isinstance(n,list) or len(t)+i<120:return t
 first=next((j for j,x in enumerate(n) if isinstance(x,list)),len(n))
 return '('+' '.join(sx.dumps(x) for x in n[:first])+'\n'+'\n'.join(' '*(i+2)+pretty(x,i+2) for x in n[first:])+'\n'+' '*i+')'
def effects(size=1.27,hidden=False,justify=None):
 n=N('effects',N('font',N('size',size,size)))
 if hidden:n.append(S('hide'))
 if justify:n.append(N('justify',S(justify)))
 return n
def prop(k,v,x,y,hide=False):return N('property',k,v,N('at',x,y,0),effects(hidden=hide))
def load(lib,name):
 a=sx.loads((SYMS/(lib+'.kicad_sym')).read_text());defs={x[1]:x for x in a if K(x)=='symbol'}
 def merge(name):
  n=copy.deepcopy(defs[name]);e=F(n,'extends')
  if e:
   p=merge(e[1]); n=[*p[:2],*[x for x in p[2:] if not(K(x)=='property' and any(K(q)=='property' and q[1]==x[1] for q in n))],*[x for x in n[2:] if K(x)!='extends']]
  return n
 return merge(name)
parts=[]
def add(ref,value,lib,name,fp,nets,sch,pcb,angle=0,mpn='',url=''):
 parts.append(dict(ref=ref,value=value.split()[0] if ref.startswith('C') else value,lib=lib,name=name,footprint=fp,nets=nets,sch=sch,pcb=pcb,angle=angle,mpn=mpn,url=url,uuid=U(ref)))
add('U1','XIAO ESP32-S3 (base)','Seeed','XIAO-ESP32-S3-SMD','Local:XIAO_ESP32S3_Socket',{'1':'BUTTON','2':'MCU_CS','4':'LED_GPIO','9':'MCU_SCK','10':'SD_MISO','11':'MCU_MOSI','12':'MCU_3V3','13':'GND','14':'USB_5V'},[63.5,60.96],[14,12],90,'113991114','https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/')
add('U2','MCP1825S-3302E/DB','Regulator_Linear','MCP1825S','Package_TO_SOT_SMD:SOT-223-3_TabPin2',{'1':'USB_5V','2':'GND','3':'SD_3V3'},[139.7,38.1],[44,15],0,'MCP1825S-3302E/DB','https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP1825-Family-Data-Sheet-DS20002056.pdf')
add('J1','microSD Hirose DM3AT','Connector','Micro_SD_Card_Det2','Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5',{'1':'SD_DAT2','2':'SD_CS','3':'SD_MOSI','4':'SD_3V3','5':'SD_SCK','6':'GND','7':'SD_MISO','8':'SD_DAT1','SH':'GND'},[222.25,60.96],[43,39],0,'DM3AT-SF-PEJM5','https://www.hirose.com/en/product/p/CL0609-0031-0-00')
# Source termination, close to module output pins.
for ref,net1,net2,pcb,sch in [('R1','MCU_SCK','SD_SCK',[27.5,17],[111.76,86.36]),('R2','MCU_MOSI','SD_MOSI',[27.5,22],[157.48,86.36]),('R3','MCU_CS','SD_CS',[4,27],[203.2,86.36])]:
 add(ref,'33R','Device','R','Resistor_SMD:R_0805_2012Metric',{'1':net1,'2':net2},sch,pcb,90,'RC0805FR-0733RL')
for i,(net,pcb) in enumerate([('SD_CS',[44.5,26]),('SD_MOSI',[42.5,26]),('SD_MISO',[39,26]),('SD_DAT1',[37,26]),('SD_DAT2',[47,26])],4):
 add('R'+str(i),'10k','Device','R','Resistor_SMD:R_0805_2012Metric',{'1':'SD_3V3','2':net},[106.68+(i-4)*30.48,111.76],pcb,90,'RC0805FR-0710KL')
add('R9','1k','Device','R','Resistor_SMD:R_0805_2012Metric',{'1':'LED_GPIO','2':'LED_A'},[38.1,109.22],[14,32],90,'RC0805FR-071KL')
add('D1','GREEN / STATUS','Device','LED','LED_SMD:LED_0805_2012Metric',{'1':'GND','2':'LED_A'},[63.5,119.38],[20,32],180,'LTST-C170GKT')
add('SW1','STOP / EJECT','Switch','SW_Push','Button_Switch_THT:SW_PUSH_6mm',{'1':'BUTTON','2':'GND'},[60.96,139.7],[10,40],0,'B3F-1000')
add('R10','10k','Device','R','Resistor_SMD:R_0805_2012Metric',{'1':'MCU_3V3','2':'BUTTON'},[25.4,139.7],[4,32],90,'RC0805FR-0710KL')
for ref,value,nets,pcb,sch,mpn in [('C1','10uF 10V X7R',{'1':'USB_5V','2':'GND'},[35,17],[109.22,38.1],'GRM21BR71A106KE51L'),('C2','10uF 10V X7R',{'1':'SD_3V3','2':'GND'},[53,17],[167.64,38.1],'GRM21BR71A106KE51L'),('C3','100nF 10V X7R',{'1':'SD_3V3','2':'GND'},[54,30],[246.38,114.3],'GRM21BR71A104KA01L'),('C4','100uF 6.3V polymer',{'1':'SD_3V3','2':'GND'},[29,41],[246.38,139.7],'6SVPC100M')]:
 add(ref,value,'Device','C_Polarized' if ref=='C4' else 'C','Capacitor_SMD:CP_Elec_5x5.9' if ref=='C4' else 'Capacitor_SMD:C_0805_2012Metric',nets,sch,pcb,90 if ref!='C4' else 0,mpn)
for i,xy in enumerate([(30,3),(57,3),(3,47),(57,47)],1):
 add('H'+str(i),'M3 NPTH','Mechanical','MountingHole','MountingHole:MountingHole_3.2mm_M3',{},[111.76+(i-1)*15.24,139.7],xy,0,'3.2mm NPTH')
# PWR_FLAGs express supplies provided through the module USB and regulator.
flags=[('USB_5V',[109.22,22.86]),('GND',[134.62,22.86]),('MCU_3V3',[160.02,22.86])]
root=U('sheet');doc=N('kicad_sch',N('version',20250114),N('generator','eeschema'),N('uuid',root),N('paper','A4'),N('title_block',N('title','Chrysler BLE-to-SD USB carrier'),N('rev','A'),N('company','Local prototype - no vehicle electrical connection')))
libs=N('lib_symbols');doc.append(libs)
local=N('kicad_symbol_lib',N('version',20231120),N('generator','kicad_symbol_editor'))
for p in parts:
 if p['lib']=='Seeed':
  defs=sx.loads((HERE/'Seeed_Studio_XIAO_Series.kicad_sym').read_text());n=copy.deepcopy(next(x for x in defs if K(x)=='symbol' and x[1]==p['name']))
  n=[x for x in n if not(K(x)=='symbol' and x[1].endswith('_1_1'))]
  # Only the14 physical header contacts are exposed on this socket carrier.
 else:n=load(p['lib'],p['name'])
 old=n[1];short=p['ref']+'_'+p['name'].replace(' ','_');n[1]='Carrier:'+short
 for u in n:
  if K(u)=='symbol':u[1]=short+u[1][u[1].rfind('_',0,u[1].rfind('_')):]
 ln=copy.deepcopy(n);ln[1]=short;local.append(ln);libs.append(n);p['libid']=n[1]
 x,y=p['sch'];rot=90 if p['ref'].startswith('R') else 0;sym=N('symbol',N('lib_id',n[1]),N('at',x,y,rot),N('unit',1),N('in_bom',S('no') if p['ref'].startswith('H') else S('yes')),N('on_board',S('yes')),N('dnp',S('no')),N('uuid',p['uuid']),prop('Reference',p['ref'],x,y-15.24 if p['ref']=='U1' else y-6.35),prop('Value',p['value'],x,y-12.7 if p['ref']=='U1' else y-3.81),prop('Footprint',p['footprint'],x,y,True),prop('MPN',p['mpn'],x,y,True),prop('Datasheet',p['url'],x,y,True))
 # Place device text beside vertical two-terminal parts and above the SD body.
 if p['ref'].startswith('C'):
  for field in sym:
   if K(field)=='property' and field[1] in ('Reference','Value'):
    F(field,'at')[1:]=[x+5.08,y+(-1.27 if field[1]=='Reference' else 1.27),0]
    F(field,'effects').append(N('justify',S('left')))
 if p['ref'].startswith('R'):
  for field in sym:
   if K(field)=='property' and field[1] in ('Reference','Value'):F(field,'at')[1:]=[x,y-(5.08 if field[1]=='Reference' else 2.54),90]
 if p['ref'].startswith('C'):
  F(next(field for field in sym if K(field)=='property' and field[1]=='Value'),'at')[1:]=[x+5.08,y+1.27,0]
  next(field for field in sym if K(field)=='property' and field[1]=='Value')[2]=p['value'].split()[0]
 if p['ref']=='J1':
  for field in sym:
   if K(field)=='property' and field[1] in ('Reference','Value'):F(field,'at')[1:]=[x,y-(27.94 if field[1]=='Reference' else 25.4),0]
 pins=[]
 for u in n:
  if K(u)!='symbol':continue
  for pin in u:
   if K(pin)!='pin':continue
   no=str(F(pin,'number')[1]);at=F(pin,'at');r=math.radians(rot);px=round(x+at[1]*math.cos(r)-at[2]*math.sin(r),6);py=round(y-at[1]*math.sin(r)-at[2]*math.cos(r),6);ang=(at[3]+rot)%360;pins.append(no)
   sym.append(N('pin',no,N('uuid',U(p['ref']+'pin'+no))))
   net=p['nets'].get(no)
   if not net:doc.append(N('no_connect',N('at',px,py),N('uuid',U(p['ref']+'nc'+no))));continue
   ex=px-2.54*math.cos(math.radians(ang));ey=py+2.54*math.sin(math.radians(ang));ex=round(ex,6);ey=round(ey,6)
   doc.append(N('wire',N('pts',N('xy',px,py),N('xy',ex,ey)),N('stroke',N('width',0),N('type',S('default'))),N('uuid',U(p['ref']+'wire'+no))))
   la=0 if ang in (90,270) else (180-ang)%360
   doc.append(N('global_label',net,N('shape',S('passive')),N('at',ex,ey,la),effects(1.0,justify='left' if la in (0,90) else 'right'),N('uuid',U(p['ref']+'label'+no))))
 sym.append(N('instances',N('project','chrysler_ble_sd',N('path','/'+root,N('reference',p['ref']),N('unit',1)))))
 doc.append(sym)
for i,(net,xy) in enumerate(flags,1):
 n=load('power','PWR_FLAG');n[1]='power:PWR_FLAG'
 if i==1:libs.append(n)
 x,y=xy;ref='#FLG0'+str(i);sym=N('symbol',N('lib_id','power:PWR_FLAG'),N('at',x,y,0),N('unit',1),N('in_bom',S('no')),N('on_board',S('yes')),N('dnp',S('no')),N('uuid',U(ref)),prop('Reference',ref,x,y-2.54,True),prop('Value','PWR_FLAG',x,y-5.08,True),N('pin','1',N('uuid',U(ref+'pin'))),N('instances',N('project','chrysler_ble_sd',N('path','/'+root,N('reference',ref),N('unit',1)))));doc.append(sym)
 doc.append(N('global_label',net,N('shape',S('passive')),N('at',x,y,0),effects(1,justify='left'),N('uuid',U(ref+'label'))))
doc.append(N('sheet_instances',N('path','/',N('page','1'))));doc.append(N('embedded_fonts',S('no')))
for txt,x,y in [('USB-C on U1 supplies module + SD regulator. NO vehicle/12V input.',24.13,17.78),('SPI mode: DAT0=MISO, CMD=MOSI, DAT3=CS. DET_A/B intentionally unused.',101.6,157.48),('Separate MCU_3V3 and SD_3V3: do not bridge. All logic3.3V.',101.6,165.1),('Press STOP; wait for solid SAFE LED before removing card or USB.',24.13,182.88),('External antenna must be connected; keep radiating antenna outside PCB/metal enclosure.',24.13,190.5)]:
 doc.append(N('text',txt,N('at',x,y,0),effects(1.27,justify='left'),N('uuid',U(txt))))
(OUT/'chrysler_ble_sd.kicad_sch').write_text(pretty(doc)+'\n')
(OUT/'Carrier.kicad_sym').write_text(pretty(local)+'\n')
(OUT/'design.json').write_text(json.dumps(dict(parts=parts,sheet_uuid=root),indent=2)+'\n')
# Socket land pattern derived directly from official through-hole contacts; SMD castellation and extra artwork removed.
fp=sx.loads((HERE/'XIAO-ESP32-S3-DIP.kicad_mod').read_text());fp[1]='XIAO_ESP32S3_Socket'
fp=[x for x in fp if not(K(x)=='pad' and str(x[2])=='smd') and not(K(x) in ('fp_line','fp_arc','fp_rect','fp_poly','fp_circle','fp_text') and F(x,'layer') and str(F(x,'layer')[1]).startswith('User.'))]
fp=[x for x in fp if not(K(x) in ('fp_line','fp_arc','fp_rect','fp_poly','fp_circle') and F(x,'layer') and F(x,'layer')[1]=='F.SilkS' and any(isinstance(v,list) and K(v) in ('start','mid','end','center') and len(v)>2 and isinstance(v[1],(float,int)) and v[1]>11.2 for v in x))]
# Prefer conventional1.0mm finished holes for2.54mm pin/socket headers,1.8mm lands.
for pad in fp:
 if K(pad)=='pad':F(pad,'drill')[1]=1.0;F(pad,'size')[1:]=[1.8,1.8]
(OUT/'Carrier.pretty').mkdir(exist_ok=True);(OUT/'Carrier.pretty'/'XIAO_ESP32S3_Socket.kicad_mod').write_text(pretty(fp)+'\n')
(OUT/'sym-lib-table').write_text('(sym_lib_table (lib (name "Carrier")(type "KiCad")(uri "${KIPRJMOD}/Carrier.kicad_sym")(options "")(descr "Embedded official KiCad/Seeed symbols")))\n')
(OUT/'fp-lib-table').write_text('(fp_lib_table (lib (name "Local")(type "KiCad")(uri "${KIPRJMOD}/Carrier.pretty")(options "")(descr "XIAO socket derived from Seeed geometry")))\n')
print('Generated schematic and BOM:',len(parts),'parts')

(OUT/'chrysler_ble_sd.kicad_pro').write_text(json.dumps({'meta':{'filename':'chrysler_ble_sd.kicad_pro','version':3},'board':{'design_settings':{'rules':{'min_clearance':0.2,'min_track_width':0.2,'min_via_diameter':0.6,'min_through_hole_diameter':0.3,'min_copper_edge_clearance':0.3}}}},indent=2)+'\n')

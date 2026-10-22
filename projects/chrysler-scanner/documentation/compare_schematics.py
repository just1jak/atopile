"""Build a vector, source-bound original/current schematic comparison atlas.

Run with the bundled workspace Python (reportlab, pypdf). No CAD is modified.
"""
from pathlib import Path
import copy, hashlib, io, json, math, sys
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A2, landscape
from reportlab.lib.colors import HexColor, Color, white
from reportlab.lib.utils import simpleSplit
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link
from pypdf.generic import (NameObject, DictionaryObject, ArrayObject, FloatObject,
                          DecodedStreamObject)

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'current/source'))
import specctra_tools as sx
ORIGINAL=P/'original-atopile/reference/upstream/ChryslerScanner_V240_schematic.pdf'
CURRENT=P/'current/ChryslerScanner_V240_SD-Hierarchy.pdf'
OUT=P/'output/pdf/ChryslerScanner_Original-to-Current_Circuit_Comparison.pdf'
TMP=P/'tmp/pdfs/circuit-comparison';TMP.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
uid=lambda n:sx.one(n,'uuid').items[1].value
root=sx.parse((P/'current/ChryslerScanner_V240_SD.kicad_sch').read_text())
pages={}
for sh in root.children('sheet'):
    props={v.items[1].value:v.items[2].value for v in sh.children('property')}
    path=sx.one(sx.one(sx.one(sh,'instances'),'project'),'path')
    pages[props['Sheetfile']]=int(sx.one(path,'page').items[1].value)
orig=PdfReader(ORIGINAL);current=PdfReader(CURRENT)
OW,OH=map(float,(orig.pages[0].mediabox.width,orig.pages[0].mediabox.height))
PARTS=json.loads((P/'original-atopile/reference/upstream/v240-extracted.json').read_text())['parts']

# Original crop coordinates are top-origin fractions of the unmodified A2 page.
regions={
 'obd':(.026,.039,.099,.151),'battery':(.103,.039,.160,.151),
 'usb_power':(.165,.039,.280,.151),'5v':(.284,.039,.490,.151),
 '3v3':(.494,.039,.581,.151),'pci_rx':(.584,.039,.697,.151),
 'vpp':(.026,.157,.160,.270),'vbb':(.165,.157,.319,.270),
 '7v5':(.322,.157,.545,.270),'pci_tx':(.549,.157,.672,.270),
 'mcu':(.026,.275,.220,.496),'usb_uart':(.224,.275,.368,.496),
 'sci6':(.372,.275,.516,.432),'sci14':(.516,.275,.653,.432),
 'sci_rx':(.372,.445,.653,.537),'buttons':(.026,.502,.145,.620),
 'auto':(.149,.502,.208,.620),'adc':(.211,.502,.368,.620),
 'sci_bias':(.372,.544,.475,.671),'ccd_bias':(.477,.544,.561,.671),
 'ccd_filter':(.564,.544,.653,.671),'connector':(.319,.624,.368,.738),
 'ccd_rx':(.372,.677,.475,.790),'ccd_tx':(.372,.791,.475,.962),
 'expander':(.477,.677,.634,.858),'leds':(.637,.677,.767,.858),
}
def old(name,label):
    box=[v*k for v,k in zip(regions[name],[OW,OH,OW,OH])]
    box[1]-=7
    return dict(source='original',page=1,box=box,label=label)
def old_refs(refs,label,pad=23):
    boxes=[PARTS[r]['body_bbox'] for r in refs]
    return dict(source='original',page=1,box=[min(v[0] for v in boxes)-pad,min(v[1] for v in boxes)-pad,max(v[2] for v in boxes)+pad,max(v[3] for v in boxes)+pad],label=label)
def now(file,label=None,box=None):
    if not file.endswith('.kicad_sch'):file+='.kicad_sch'
    if box is None:
        r=sx.parse((P/'current'/file).read_text());pts=[]
        for w in r.children('wire'):
            pts.extend(tuple(float(v.value) for v in x.items[1:]) for x in sx.one(w,'pts').children('xy'))
        for w in r.children('polyline'):
            pts.extend(tuple(float(v.value) for v in x.items[1:]) for x in sx.one(w,'pts').children('xy'))
        for s in r.children('symbol'):
            pts.append(tuple(float(v.value) for v in sx.one(s,'at').items[1:3]))
        box=[max(7,min(x for x,y in pts)-12),max(25,min(y for x,y in pts)-12),max(x for x,y in pts)+28,max(y for x,y in pts)+10]
    return dict(source='current',page=pages[file],box=[v*72/25.4 for v in box],label=label or file.replace('.kicad_sch',''),file=file)

sections=[]
def section(title,status,zone,oldcards,newcards,notes):
    sections.append(dict(title=title,status=status,originalZone=zone,original=oldcards,current=newcards,notes=notes))
section('Vehicle battery input','MODIFIED','A1',[old('battery','Battery input protection: D1, D2, C1')],[now('07_vehicle-input')],
 ['D1 changes from SMBJ30CA to SMBJ16CA. D2, C1 and the JP1 signal-ground link remain.', 'The battery ADC now senses protected +12V after D2, rather than raw J1962-16. This is an intentional safety change.'])
section('OBD connector and line protection','REORGANIZED','A1 / B7-B8 / C-E',[
 old('obd','Original J1962M connector and pin assignments'),old('pci_tx','PCI: C25 / D11 / D12 in transmitter block'),
 old('sci6','SCI TX6 / TX12: C36 / C37'),old('sci14','SCI TX14 / TX9: C39 / C40'),
 old('sci_rx','SCI RX7 / RX15: C42 / C44'),old('ccd_filter','CCD: D13 / D14 in original filter/protection block')],
 [now('06_obd-protection')],['J1 is now an ATTEND 226A-1202; logical vehicle pin assignments are retained.', 'Capacitors and protection diodes formerly scattered across bus blocks are grouped by PCI, SCI and CCD on one page. These crops identify their original locations.'])
section('USB connector and power selection','MODIFIED','A2-A3',[old('usb_power','Original USB-B, U1, JP2, D3 and C2/C3')],
 [now('19_usb','USB-C connector and USB/vehicle power selection',(120,31,340,109))],
 ['USB-B is deliberately replaced by USB-C, with separate CC pull-down resistors R102/R103.', 'U1 SY6283 power switching, JP2 bypass, D3 and the input/output capacitor functions remain. See comparison 11 for UART/ESD circuitry.'])
section('6 V pre-regulator and +5 V output','RETAINED','A4-A6',[old('5v','U2 buck pre-regulator, U3 +5 V regulator and feedback')],
 [now('08_power-5v','U2 / U3 and the +5 V chain',(5,31,246,118)),now('08_power-5v','Additional displayed U3 package unit',(348,36,400,112))],
 ['U2, L1, D4/D5, U3 and feedback/output-sense functions correspond to the original block.', 'The migrated regulator symbol library exposes electrical units/pins explicitly; compare named IN, OUT, FB, SNS and EN connections rather than symbol appearance.'])
section('+3.3 V logic supply','RETAINED','A6-A7',[old('3v3','U4, D6 and C9/C10')],
 [now('08_power-5v','U4 +3.3 V regulator',(246,31,347,119)),now('08_power-5v','Additional displayed U4 unit',(7,119,66,167))],
 ['The original +3.3 V regulation and filtering remain. The additional displayed symbol unit belongs to the same U4 package.', 'The separate SD_3V3 regulator is a later addition, not a replacement for this logic supply.'])
section('VPP programming boost supply','MODIFIED','B1-B3',[old('vpp','U5 boost regulator, L2/L3, D7 and VPP filtering')],[now('09_power-vpp')],
 ['The original boost topology and programming-rail function remain.', 'C14 and C15 now specify at least 50 V, deliberately increased from the original 35 V labels. The bounded prototype still requires protected-input/VPP peaks at or below 28 V.'])
section('VBB bootstrap supply','RETAINED','B3-B5',[old('vbb','U6, L4/L5, D8 and feedback/filtering')],[now('10_power-vbb')],
 ['The original VBB rail and feedback/output-filtering blocks correspond directly.', 'The page title refers to the rail function; original reference designators and named VBB connections identify the match.'])
section('PCI +7.5 V supply','RETAINED','B5-B7',[old('7v5','U7 / U8 power chain and two feedback networks')],[now('11_power-7v5')],
 ['U7, U8, L6, D9/D10 and their feedback/output filters retain the original PCI supply function.', 'This rail is distinct from the new PCI_VCC clamp supplying the comparator. See comparison 29.'])
section('PCI / J1850 receiver and transmitter','MODIFIED','A7-A8 / B7-B8',[old('pci_rx','Original U9 receiver'),old('pci_tx','Original Q1 transmitter and protection')],[now('02_pci')],
 ['U9, Q1, R4-R7 and R18-R21 retain the PCI receive/transmit functions.', 'U9.5 and C11.2 now use the separately clamped PCI_VCC rail instead of direct +12V. C25 and D11/D12 are displayed on the connector/protection page.'])
section('ESP32, RF and local decoupling','MODIFIED','C1-D3',[old('mcu','Original U10 ESP32-PICO-V3-02 and RF network')],[now('16_mcu')],
 ['The original ESP32 package, RF network and existing functional pin assignments remain.', 'Previously unused U10 pads 5, 6, 7, 21, 27 and 38 now serve SD and logging functions. ACT_LED is assigned exclusively to the supervised health heartbeat; legacy activity firmware is incompatible.'])
section('USB / UART bridge and USB ESD','MODIFIED','C3-D4',[old('usb_uart','Original CP2102, USBLC6 and VBUS divider')],
 [now('19_usb','CP2102 serial/control unit',(45,50,132,192)),now('19_usb','USBLC6 ESD and USB-C CC resistors',(135,115,322,209)),now('19_usb','CP2102 supply/ground units',(326,112,408,248)),now('19_usb','VBUS sense divider (continuation at main unit)',(8,32,38,108))],
 ['The classic CP2102 is retained; this is not a CP2102N conversion. U11 retains the USBLC6 protection function.', 'The current symbol drawing is split into several units belonging to U12. USB-C contact mapping and CC termination are intentional additions.'])
section('Reset, boot and automatic programming','REORGANIZED','E1-E3',[old('buttons','SW1 / SW2, R48 and C45/C46'),old('auto','Q5 automatic programming')],
 [now('19_usb','Reset and boot buttons',(210,113,326,146)),now('19_usb','Q5 automatic programming pair',(342,31,407,110)),now('16_mcu','R48 and reset/boot capacitors',(10,25,419,205))],
 ['Buttons and automatic programming are grouped with USB; the reset resistor/capacitors remain on the MCU sheet.', 'Q5 multi-unit drawing and named EN / IO0 / RTS / DTR nets correspond to the original automatic programming topology.'])
section('SCI TX14 and TX9 paths','REORGANIZED','C6-D8',[old('sci14','Original Q3 / U14 SCI TX14 and TX9 paths')],[now('03_sci-14-9')],
 ['Q3, U14, R36-R41 and C41 correspond to the original two transmit paths.', 'C39 and C40 are now grouped on the connector/protection page. Vehicle pins 14 and 9, enable names and shared TX2 function remain identifiable.'])
section('SCI TX6 / TX12 and selectable bias','REORGANIZED','C4-D6 / E5-E6',[old('sci6','Original Q2 / U13 transmit paths'),old('sci_bias','Original Q6 selectable SCI bias')],[now('04_sci-6-12')],
 ['Q2/U13 transmit switching and Q6/R75/R76 selectable bias are grouped on one page.', 'C36/C37 are on connector protection. RX7_BIAS_EN, TX6_EN, TX12_EN and the corresponding vehicle pins retain their original roles.'])
section('SCI RX7 and RX15 paths','REORGANIZED','D4-E8',[old('sci_rx','Original Q4 / U15 receive paths')],[now('05_sci-rx')],
 ['The Q4/U15 sections, R42-R47, C43 and RX2 receive function correspond to the original.', 'C42 and C44 have moved to the grouped connector/protection drawing; they are not missing from the receive networks.'])
section('Battery, VBB and VPP monitoring dividers','MODIFIED','E3-E5',[old('adc','Original three divider / clamp / filter circuits')],[now('17_adc')],
 ['R49/R51/R53 are now 22k 1%; R50/R52/R54 are 1.62k 1%. R49 input moves to protected +12V.', 'The divider outputs are now V_BA_PRE, V_BT_PRE and V_PR_PRE. U21 isolation on the safety page creates the final ADC nets; calibration must reflect these intentional changes.'])
section('CCD termination, bias and input filtering','REORGANIZED','E6-E8',[old('ccd_bias','Original Q7 termination / bias'),old('ccd_filter','Original R81/R82, C50/C51 and D13/D14')],
 [now('01_ccd','CCD input filtering and Q7 bias',(10,30,252,121))],
 ['Q7, R77-R82 and C50/C51 retain the original termination, bias and filter functions.', 'D13/D14 are grouped on the input-protection page. The vehicle input nets and internal CCD+ / CCD- nets remain distinct as drawn.'])
section('CCD receiver','RETAINED','F5-F6',[old('ccd_rx','Original U16 receiver')],[now('01_ccd','U16 / R83-R85 / C52-C53',(256,29,343,116))],
 ['U16 TS391C, R83-R85 and C52/C53 correspond to the original CCD-to-RX1 receiver.', 'The receive logic net is RX1; identify the comparator by reference and net labels, independently of the new sheet position.'])
section('CCD transmitter','RETAINED','G5-H6',[old('ccd_tx','Original U17/U18 and Q16 drive pair')],[now('01_ccd','U17 / U18, Q16 and R97-R101 drive paths',(9,120,226,246))],
 ['U17/U18, both Q16 sections, R97-R101 and C54/C55 correspond to the original TX1 drive circuitry.', 'Extra displayed gate units belong to the same existing IC packages and do not add a new transmitter capability.'])
for i,(pin,file) in enumerate([(6,'12_program-6'),(9,'13_program-9'),(12,'14_program-12'),(14,'15_program-14')]):
    x0=.026+i*.0715;x1=x0+.073
    cards=[dict(source='original',page=1,box=[x0*OW,.624*OH,x1*OW,.750*OH],label=f'Original VBB driver for vehicle pin {pin}'),dict(source='original',page=1,box=[x0*OW,.748*OH,x1*OW,.884*OH],label=f'Original VPP driver for vehicle pin {pin}')]
    section(f'SCI pin {pin}: VBB / VPP programming switches','MODIFIED','F1-G5',cards,[now(file)],
     ['The two rail-switching branches are paired by vehicle pin on a dedicated page.', 'Q8-Q11 and Q12-Q15 use revised FET families. The VPP gate-divider values are intentionally revised to 4.7k / 8.2k; compare current labels rather than assuming identical parts.'])
section('I2C expander and internal connector','MODIFIED','F5-G7',[old('expander','Original U19 AW9523B and pull-ups'),old('connector','Original internal I2C connector J3')],[now('18_control')],
 ['U19 AW9523B, its 16 output functions, grounded address straps, I2C pull-ups and J3 are retained.', 'The reset/permit net N_R88_2 is now driven by the new supervised hardware permit. The original independent reset pull-up is not sufficient by itself to describe the new safety behavior.'])
section('Status LED drivers','MODIFIED','F7-G8',[old('leds','Original four LED / transistor channels')],[now('20_leds')],
 ['D23-D26 and Q17-Q20 retain the four LED driver channels.', 'The ACT_LED channel is now a dedicated health/permit indication. It must not be driven by the old general-purpose activity-blink code.'])
section('Integrated microSD logger','NEW','No original block',[old('mcu','Context only: original MCU unused pins; no SD circuit')],[now('22_sd-logger')],
 ['There is no corresponding microSD block in the original drawing. U20, J4, C58-C61, R104-R114 and SW3 are later additions.', 'SD_3V3 regulation, SPI resistors/pull-ups, card detect and logging control use previously unused MCU pins. C61 is now top-side; that physical move does not change the schematic circuit.'])
section('Added ADC power-off isolation','NEW / MODIFIED','Original ADC: E3-E5',[old('adc','Original direct-to-MCU monitor dividers')],
 [now('23_hardware-safety','Complete safety page; focus: U21 and R120-R122')],
 ['U21 and R120-R122 are new. The original ADC paths now terminate on *_PRE nets before this isolation stage.', 'The additions address powered-off MCU injection; they deliberately depart from the original direct ADC connection. See comparison 16 for the changed divider inputs/ratios.'])
section('Added supervisor, watchdog and hardware permit','NEW / MODIFIED','Original expander reset: F6-G7',[old('expander','Original independent expander reset / control'),old('leds','Original ACT_LED driver context')],
 [now('23_hardware-safety','Complete safety page; focus: U22-U24 / R115-R119')],
 ['U22-U24, R115-R119 and associated bypassing implement a new supervised permit, not an original circuit copied to another page.', 'Dedicated ACT_LED health pulses and LOGIC_PG / HEARTBEAT_VALID govern N_R88_2. Firmware integration and measured timing remain required; the comparison is not a bench qualification.'])
section('Added PCI comparator supply clamp','NEW / MODIFIED','Original PCI receiver: A7-A8',[old('pci_rx','Original U9/C11 supply taken from +12V')],
 [now('23_hardware-safety','New R123 / D30 PCI_VCC clamp',(240,180,387,230)),now('02_pci','PCI page; focus: U9 / C11 PCI_VCC connections')],
 ['R123 and D30 are new. U9.5 and C11.2 now use PCI_VCC rather than direct +12V.', 'The original receiver function remains, while its supply protection is deliberately changed.'])
section('Hook test points and SPI probe pads','NEW','No original block',[],[now('24_debug-testpoints')],
 ['The original PDF has no TP1-TP52 debug-access block. The current design adds 48 Keystone 5015 hook loops and four bare SPI pads, with four local ground clips.', 'Page 24 and rev-c-testpoint-map.md identify every net. Existing circuit geometry is retained; new pads require 230 total filled/capped/planarized via sites in the current fabrication package.'])
assert len(sections)==30
assert {c['page'] for v in sections for c in v['current']}==set(range(2,25))

W,H=landscape(A2);ink=HexColor('#172D42');muted=HexColor('#526474');rule=HexColor('#CED7DE')
buffer=io.BytesIO();cv=canvas.Canvas(buffer,pagesize=(W,H));cv.setTitle('ChryslerScanner: original to current circuit comparison');cv.setAuthor('ChryslerScanner project / Codex');draws=[];indexlinks=[]
def txt(x,y,text,size=12,color=ink,font='Helvetica'):
    cv.setFillColor(color);cv.setFont(font,size);cv.drawString(x,y,text)
def paragraph(text,x,y,width,size=12,leading=None,color=ink):
    leading=leading or size*1.35
    for line in simpleSplit(text,'Helvetica',size,width):txt(x,y,line,size,color);y-=leading
    return y
def footer(number):
    cv.setStrokeColor(rule);cv.line(42,37,W-42,37);txt(42,20,'ChryslerScanner | Original V240 rev 2.4.0-1 -> current Rev C debug-access checkpoint | 2026-10-22',9,muted);cv.setFont('Helvetica',10);cv.drawRightString(W-42,20,str(number))
def overlay(page,card,rect):draws.append(dict(reportPage=page,card=card,rect=list(rect)))
def draw_card(page,card,rect):
    x,y,w,h=rect;cv.setFillColor(white);cv.setStrokeColor(rule);cv.rect(x,y,w,h,fill=1,stroke=1)
    txt(x+10,y+h-20,card['label'],11,ink,'Helvetica-Bold')
    source='Original p1' if card['source']=='original' else f"Current p{card['page']}"
    txt(x+10,y+8,source,9,muted)
    overlay(page,card,(x+9,y+25,w-18,h-56))
def panel(page,cards,rect,empty=None):
    x,y,w,h=rect
    if not cards:
        cv.setFillColor(HexColor('#F1F5F8'));cv.rect(x,y,w,h,fill=1,stroke=0)
        txt(x+25,y+h-55,'No corresponding original circuit',21,ink,'Helvetica-Bold')
        paragraph(empty or 'This is an intentional addition. The original single-sheet drawing contains no equivalent block.',x+25,y+h-90,w-50,15,22)
        return
    cols=2 if len(cards)>3 else 1;rows=math.ceil(len(cards)/cols);gap=14
    cw=(w-gap*(cols-1))/cols;ch=(h-gap*(rows-1))/rows
    for i,card in enumerate(cards):draw_card(page,card,(x+(i%cols)*(cw+gap),y+h-(i//cols+1)*ch-(i//cols)*gap,cw,ch))

# Cover and guidance.
cv.bookmarkPage('cover');cv.addOutlineEntry('Read first / sources and interpretation','cover')
txt(56,H-84,'CIRCUIT COMPARISON',15,muted,'Helvetica-Bold')
txt(56,H-142,'ChryslerScanner',48,ink,'Helvetica-Bold')
txt(56,H-190,'Original schematic -> current circuit sets',30)
paragraph('A visual cross-reference atlas. Each comparison pairs a current circuit set with the corresponding cropped area of the original drawing. The circuit drawings remain vector artwork and can be zoomed without raster blur.',56,H-240,W-112,18,26)
y=H-345
for title,text in [
 ('How to read it','Original drawings are on the left; current drawings are on the right. Original sheet zones and current page numbers accompany every pair. Several original regions can map to one current sheet, and one current sheet can appear in several focused comparisons.'),
 ('What the status means','RETAINED means the original block is represented in the current circuit. REORGANIZED means original components are drawn elsewhere or grouped differently. MODIFIED identifies intentional changes. NEW identifies circuitry with no original equivalent; context crops are explicitly labeled.'),
 ('Material changes','USB-C and the OBD connector replace original connectors. Input protection, comparator supply protection, ADC divider/isolation and supervised reset are revised. The SD logger and TP1-TP52 are additions. Matching a block does not mean electrical identity with the original.'),
 ('Scope','This document compares schematic circuits, not PCB trace geometry or automotive qualification. Original pin details and complete source sheets remain available in the embedded source PDFs. The final appendix reproduces the full original page.')]:
    txt(56,y,title,18,ink,'Helvetica-Bold');y=paragraph(text,56,y-29,W-112,15,21)-36
txt(56,y,'Sources bound to this report',18,ink,'Helvetica-Bold');y-=28
sources=[('Original','original-atopile/reference/upstream/ChryslerScanner_V240_schematic.pdf',sha(ORIGINAL)),('Current','current/ChryslerScanner_V240_SD-Hierarchy.pdf',sha(CURRENT))]
for title,path,digest in sources:
    txt(56,y,title+': '+path,12);y-=20;txt(56,y,'SHA-256 '+digest,10,muted,'Courier');y-=31
txt(56,y,'Original: Daniel Laszlo, revision 2.4.0-1, 2026-01-05. Current: Rev C, 24 pages / 329 circuit-probe endpoints.',12)
txt(56,y-22,'Current PCB checkpoint: '+json.loads((P/'reference/final-status.json').read_text())['pcb_sha256'],10,muted,'Courier')
footer(1);cv.showPage()

# Overview + clickable index.
cv.bookmarkPage('index');cv.addOutlineEntry('Circuit matching index','index')
txt(42,H-60,'Circuit matching index',30,ink,'Helvetica-Bold');txt(42,H-89,'Click a row or use the PDF bookmarks. Full source PDFs are also embedded as attachments.',13,muted)
leftw=710
draw_card(1,dict(source='original',page=1,box=[20,20,1660,1170],label='Original: one A2 page, circuit zones A-H / 1-11'),(42,580,leftw,485))
draw_card(1,dict(source='current',page=1,box=[65,65,2290,1605],label='Current: native hierarchical system block diagram'),(42,65,leftw,485))
x=790;y=H-139;txt(x,y,'Comparison',12,muted,'Helvetica-Bold');txt(W-188,y,'Current p.',12,muted,'Helvetica-Bold');txt(W-110,y,'Atlas p.',12,muted,'Helvetica-Bold');y-=29
for i,v in enumerate(sections,1):
    num=i+2;title=f'{i:02d}  '+v['title'];txt(x,y,title,12)
    currentpages=','.join(str(p) for p in sorted({c['page'] for c in v['current']}));txt(W-188,y,currentpages,11,muted);txt(W-102,y,str(num),12)
    indexlinks.append((i+1,(x,y-6,W-45,y+16)))
    cv.setStrokeColor(rule);cv.line(x,y-12,W-45,y-12);y-=29
footer(2);cv.showPage()

for i,v in enumerate(sections,1):
    reportpage=i+1;cv.bookmarkPage(f'cmp-{i}');cv.addOutlineEntry(f'{i:02d} {v["title"]}',f'cmp-{i}')
    txt(42,H-48,f'{i:02d}  '+v['title'],27,ink,'Helvetica-Bold')
    badge=HexColor('#0C6665') if v['status']=='RETAINED' else HexColor('#9B5B19') if 'MODIFIED' in v['status'] else HexColor('#30578B')
    txt(42,H-79,v['status'],12,badge,'Helvetica-Bold')
    txt(250,H-79,'Original zone: '+v['originalZone']+'   |   Current page(s): '+','.join(str(p) for p in sorted({c['page'] for c in v['current']})),12,muted)
    panelw=(W-112)/2;bottom=184;height=H-310
    txt(42,H-111,'ORIGINAL PROJECT',12,muted,'Helvetica-Bold');txt(70+panelw,H-111,'CURRENT PROJECT',12,muted,'Helvetica-Bold')
    panel(reportpage,v['original'],(42,bottom,panelw,height));panel(reportpage,v['current'],(70+panelw,bottom,panelw,height))
    y=145
    for note in v['notes']:y=paragraph('- '+note,42,y,W-84,12,17)-7
    txt(42,54,'Reference designators are the matching keys. Vector source crops preserve original text and wiring; zoom for pin-level inspection.',10,muted)
    footer(i+2);cv.showPage()
cv.save();template=PdfReader(io.BytesIO(buffer.getvalue()));writer=PdfWriter();writer.append(template)
for target,rect in indexlinks:writer.add_annotation(1,Link(rect=rect,target_page_index=target))

# Import each source page once as a reusable vector Form XObject. Clipping a
# shared form avoids rasterization and avoids copying the complete original for
# every small crop. Original/current PDF source resources are preserved.
forms={}
def form(source,pageindex):
    key=(source,pageindex)
    if key in forms:return forms[key]
    pg=(orig if source=='original' else current).pages[pageindex]
    obj=DecodedStreamObject();obj.set_data(pg.get_contents().get_data())
    obj.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),NameObject('/FormType'):FloatObject(1),NameObject('/BBox'):ArrayObject(FloatObject(float(z)) for z in pg.mediabox),NameObject('/Resources'):pg['/Resources'].clone(writer)})
    ref=writer._add_object(obj.flate_encode());forms[key]=(ref,float(pg.mediabox.height),float(pg.mediabox.width));return forms[key]
for d in draws:
    pg=writer.pages[d['reportPage']];card=d['card'];ref,ph,pw=form(card['source'],card['page']-1)
    left,top,right,bottom=card['box'];left=max(0,left);top=max(0,top);right=min(pw,right);bottom=min(ph,bottom);assert right>left and bottom>top
    x,y,w,h=d['rect'];scale=min(w/(right-left),h/(bottom-top));tx=x+(w-scale*(right-left))/2-scale*left;ty=y+(h-scale*(bottom-top))/2-scale*(ph-bottom)
    resources=pg['/Resources'];xobjs=resources.get('/XObject')
    if xobjs is None:xobjs=DictionaryObject();resources[NameObject('/XObject')]=xobjs
    else:xobjs=xobjs.get_object()
    name=NameObject('/Source_'+card['source']+'_'+str(card['page']));xobjs[name]=ref
    clipx=x+(w-scale*(right-left))/2;clipy=y+(h-scale*(bottom-top))/2
    commands=f'q {clipx:.6f} {clipy:.6f} {scale*(right-left):.6f} {scale*(bottom-top):.6f} re W n {scale:.9f} 0 0 {scale:.9f} {tx:.6f} {ty:.6f} cm {name} Do Q\n'
    stream=DecodedStreamObject();stream.set_data(commands.encode('ascii'))
    oldcontent=pg.get('/Contents');newref=writer._add_object(stream)
    if oldcontent is None:pg[NameObject('/Contents')]=newref
    elif isinstance(oldcontent,ArrayObject):oldcontent.append(newref)
    else:pg[NameObject('/Contents')]=ArrayObject([oldcontent,newref])
writer.add_page(orig.pages[0]);writer.add_outline_item('Full original source page (unmodified)',len(writer.pages)-1)
writer.add_attachment('Original_ChryslerScanner_V240_schematic.pdf',ORIGINAL.read_bytes());writer.add_attachment('Current_ChryslerScanner_V240_SD-Hierarchy.pdf',CURRENT.read_bytes())
writer.add_metadata({'/Title':'ChryslerScanner - original/current circuit comparison','/Author':'ChryslerScanner project; original circuit drawing by Daniel Laszlo','/Subject':'30 vector comparison sets, source hashes, mapping index and complete original appendix','/Keywords':'ChryslerScanner KiCad original current circuit cross-reference'})
OUT.parent.mkdir(parents=True,exist_ok=True)
with OUT.open('wb') as f:writer.write(f)
manifest=dict(title='Original/current circuit comparison atlas',date='2026-10-22',originalPdf=str(ORIGINAL.relative_to(P)),originalSha256=sha(ORIGINAL),currentPdf=str(CURRENT.relative_to(P)),currentSha256=sha(CURRENT),pcbSha256=json.loads((P/'reference/final-status.json').read_text())['pcb_sha256'],comparisonSets=len(sections),pageCount=len(writer.pages),vectorSourcesPreserved=True,embeddedSourcePdfs=2,sections=[dict(atlasPage=i+3,**v) for i,v in enumerate(sections)],outputSha256=sha(OUT))
(OUT.parent/'ChryslerScanner_Circuit_Comparison_Index.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(pdf=str(OUT),pages=len(writer.pages),sets=len(sections),bytes=OUT.stat().st_size),indent=2))

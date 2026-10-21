"""Native validation, manufacturing export, source provenance, and focused checks."""
from pathlib import Path
import subprocess,json,csv,hashlib,xml.etree.ElementTree as ET,shutil,datetime
HERE=Path(__file__).resolve().parent; D=HERE/'design';CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
def run(name,args):
 r=subprocess.run([CLI,*args],cwd=D,capture_output=True,text=True,timeout=60);(D/(name+'-run.log')).write_text(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError(name+' failed: '+str(r.returncode)+' '+r.stdout[-700:]+r.stderr[-700:])
 print(name,'passed',flush=True)
run('erc',['sch','erc','--format','json','--output','erc.json','--exit-code-violations','chrysler_ble_sd.kicad_sch'])
run('drc',['pcb','drc','--format','json','--all-track-errors','--schematic-parity','--exit-code-violations','--output','drc.json','chrysler_ble_sd.kicad_pcb'])
run('netlist',['sch','export','netlist','--format','kicadxml','--output','chrysler_ble_sd.net','chrysler_ble_sd.kicad_sch'])
a=json.loads((D/'design.json').read_text()); expected={}
for p in a['parts']:
 for pin,net in p['nets'].items():expected.setdefault(net,set()).add((p['ref'],pin))
xml=ET.parse(D/'chrysler_ble_sd.net').getroot();actual={}
for net in xml.findall('./nets/net'):
 name=net.attrib['name'];nodes={(n.attrib['ref'],n.attrib['pin']) for n in net.findall('node') if not n.attrib['ref'].startswith('#')}
 if name in expected:actual[name]=nodes
assert actual==expected,[(k,expected[k],actual.get(k)) for k in expected if expected[k]!=actual.get(k)]
print('Exact intended pin/net memberships verified:',len(actual),'functional nets',sum(map(len,actual.values())),'terminals',flush=True)
# Native parity includes physical pad duplicates, NC pads, fields, footprints, references.
drc=json.loads((D/'drc.json').read_text());erc=json.loads((D/'erc.json').read_text());assert not any(drc[k] for k in ['violations','unconnected_items','schematic_parity']);assert not any(s.get('violations') for s in erc.get('sheets',[]))
run('schematic-pdf',['sch','export','pdf','--output','schematic.pdf','chrysler_ble_sd.kicad_sch'])
run('board-render',['pcb','render','--output','board-3d.png','--width','1600','--height','1200','--rotate','315,0,25','--background','opaque','chrysler_ble_sd.kicad_pcb'])
(D/'manufacturing').mkdir(exist_ok=True)
run('gerbers',['pcb','export','gerbers','--output','manufacturing/','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts,F.Paste,B.Paste','chrysler_ble_sd.kicad_pcb'])
run('drills',['pcb','export','drill','--output','manufacturing/','--format','excellon','--excellon-separate-th','--generate-map','chrysler_ble_sd.kicad_pcb'])
run('ipc2581',['pcb','export','ipc2581','--output','manufacturing/chrysler_ble_sd.xml','chrysler_ble_sd.kicad_pcb'])
with (D/'bom.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['Reference','Quantity','Value','ManufacturerPartNumber','Footprint','Datasheet','AssemblyNote'])
 for p in a['parts']:w.writerow([p['ref'],1,p['value'],p['mpn'],p['footprint'],p['url'],'Mechanical hole; no purchased part' if p['ref'].startswith('H') else ''])
 w.writerow(['XIAO carrier sockets',2,'1x7 female socket,2.54mm pitch','SSW-107-01-S-S','Part of U1 socket land pattern','https://www.samtec.com/products/ssw-107-01-s-s','Verify chosen mating header height before enclosure'])
 w.writerow(['XIAO male headers',2,'1x7 male header,2.54mm pitch','TSW-107-07-G-S','Solder to XIAO module','https://www.samtec.com/products/tsw-107-07-g-s','0.635mm square posts; module bought without headers'])
summary={'checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kicadVersion':'10.0.7','schematicParts':len(a['parts']),'physicalFootprints':23,'functionalNets':len(actual),'functionalTerminals':sum(map(len,actual.values())),'ercViolations':0,'drcViolations':0,'unconnectedItems':0,'schematicParityViolations':0,'nativeExactPinNetComparison':'passed','layers':2,'boardMm':[60,50],'thermalVias':8,'sdRegulator':'MCP1825S-3302E/DB','noDrcExclusionsAdded':True,'physicalBenchValidation':'not performed','originalScannerProjectModified':False,'transport':'BLE only; ClassicSPP unsupported by ESP32-S3'}
summary['sourceHashes']={n:hashlib.sha256((D/n).read_bytes()).hexdigest() for n in ['chrysler_ble_sd.kicad_sch','chrysler_ble_sd.kicad_pcb','chrysler_ble_sd.kicad_pro','Carrier.kicad_sym','Carrier.pretty/XIAO_ESP32S3_Socket.kicad_mod']}
(D/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
src=D/'source';src.mkdir(exist_ok=True)
for name in ['generate_design.py','build_board.py','finalize.py','Seeed_Studio_XIAO_Series.kicad_sym','XIAO-ESP32-S3-DIP.kicad_mod','Seeed-LICENSE-MIT.txt','KiCad-LICENSE.md']:shutil.copy2(HERE/name,src/name)
(D/'THIRD_PARTY.md').write_text('''# Third-party hardware-library material\n\nSeeed Studio XIAO ESP32-S3 symbol/footprint are derived from Seeed-Studio/OSHW-XIAO-Series (https://github.com/Seeed-Studio/OSHW-XIAO-Series), Copyright(c)2024Seeed-Projects, MIT. The full notice is in source/Seeed-LICENSE-MIT.txt. Unmodified source definitions are included. The14-pin subset, through-hole socket-only pads,1.0mm drills/1.8mm lands, and USB overhang silk trimming are the local modifications.\n\nOther schematic symbols, PCB footprints, and render models originate from the installed official KiCad10 libraries, contributors to the KiCad libraries. KiCad libraries use CC-BY-SA4.0 with an exception allowing their use in electronic designs without forcing the entire design to that license. Retain source/KiCad-LICENSE.md and the original library attribution. Embedded symbol definitions and footprints are included in native KiCad files. The preview uses installed KiCad3D models; the removable XIAO/socket assembly is not rendered.\n\nNo authentication data, firmware signing keys, or private scanner project files are embedded in this carrier package.\n''')
print(json.dumps(summary,indent=2))

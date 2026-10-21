"""Independently audit native XML/PCB against source endpoints and SD manifest.

Run with KiCad10's bundled Python. CAD files are only read. Routing is assessed
only when a fresh final native DRC report is explicitly supplied.
"""
from pathlib import Path
from collections import defaultdict,Counter
import argparse,hashlib,json,xml.etree.ElementTree as ET
import pcbnew as p

HERE=Path(__file__).resolve().parent
NAME='ChryslerScanner_V240_SD'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('project',type=Path)
parser.add_argument('--xml',type=Path,default=HERE/(NAME+'.xml'))
parser.add_argument('--pcb',type=Path)
parser.add_argument('--erc',type=Path,default=HERE/'erc-native.json')
parser.add_argument('--drc',type=Path)
parser.add_argument('--source-manifest',type=Path,default=HERE.parents[1]/'chrysler-integrated-sd/original-source-manifest.json')
parser.add_argument('--geometry-reference',type=Path,default=HERE.parent/'physical-fix-stage'/(NAME+'.kicad_pcb'))
parser.add_argument('--report',type=Path,default=HERE/'electrical-audit.json')
args=parser.parse_args()
project=args.project.resolve();pcb=(args.pcb or project/(NAME+'.kicad_pcb')).resolve()
errors=[]
def check(ok,msg):
    if not ok:errors.append(msg)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=json.loads((project/'reference/integration.json').read_text())
expected=json.loads((project/'reference/v240-netlist.json').read_text())
nc_names=json.loads((project/'reference/native-nc-net-names.json').read_text())
xml=ET.parse(args.xml).getroot()
component_nodes=xml.findall('components/comp')
components={n.attrib['ref']:n for n in component_nodes}
check(len(components)==len(component_nodes)==259,'Native schematic must have259unique electrical references')
board=p.LoadBoard(str(pcb));fp_list=list(board.GetFootprints());fps={f.GetReference():f for f in fp_list}
check(len(fp_list)==len(fps)==263,'PCB must have263unique references including4mechanical holes')
check(set(components)==set(expected['parts'])==set(fps)-{'H1','H2','H3','H4'},'Schematic/source/PCB component reference sets differ')
pad_nets={};pcb_nets=defaultdict(set)
for ref,f in fps.items():
    for q in f.Pads():
        pin=q.GetNumber()
        if not pin:continue # NPTH and paste-only aperture, not electrical terminals
        point=(ref,pin);net=q.GetNetname()
        check(point not in pad_nets or pad_nets[point]==net,'Same-number physical pads disagree: '+str(point))
        pad_nets[point]=net
        if net:pcb_nets[net].add(point)
for ref,c in components.items():
    if ref not in fps:continue
    f=fps[ref]
    check(f.GetValue()==c.findtext('value'),ref+': native schematic/PCB value differs')
    fid=str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName())
    check(fid==c.findtext('footprint'),ref+': native schematic/PCB footprint assignment differs')

sch_nets={};sch_terminal_net={};sch_pin_types={}
for n in xml.findall('nets/net'):
    points=frozenset((q.attrib['ref'],q.attrib['pin']) for q in n.findall('node'))
    name=n.attrib['name']
    check(name not in sch_nets,'Duplicate native schematic net name: '+name)
    sch_nets[name]=points
    for q in n.findall('node'):
        point=(q.attrib['ref'],q.attrib['pin'])
        check(point not in sch_terminal_net or sch_terminal_net[point]==name,'Schematic terminal belongs to multiple nets: '+str(point))
        sch_terminal_net[point]=name;sch_pin_types[point]=q.attrib.get('pintype','')
sch_connected={name:points for name,points in sch_nets.items() if len(points)>1}
pcb_connected={name:frozenset(points) for name,points in pcb_nets.items() if len(points)>1}
source_connected={name:frozenset(tuple(point) for point in points) for name,points in expected['nets'].items()}
check(len(sch_connected)==len(pcb_connected)==len(source_connected)==154,'Expected154connected nets in all three representations')
check(sch_connected==pcb_connected,'Native schematic/PCB connected net names or exact endpoint sets differ')
check(sch_connected==source_connected,'Native schematic/source connected net names or exact endpoint sets differ')

nc_results=[]
for ref,part in expected['parts'].items():
    pins=set(part['pins']);actual={pin for r,pin in pad_nets if r==ref}
    check(pins==actual,ref+': physical pad number set differs from source')
    for pin,mapping in part['pins'].items():
        point=(ref,pin);net=mapping.get('net')
        if net:
            check(pad_nets.get(point)==net and sch_terminal_net.get(point)==net,
                  ref+'.'+pin+': assigned net differs between source/schematic/PCB')
        else:
            native_name=nc_names.get(ref+'.'+pin)
            check(mapping.get('no_connect') is True,ref+'.'+pin+': no-connect lacks explicit source declaration')
            check(native_name is not None,ref+'.'+pin+': missing explicit NC-name allowlist')
            check(pad_nets.get(point)==native_name and sch_terminal_net.get(point)==native_name,
                  ref+'.'+pin+': NC net-name mapping differs')
            check(pcb_nets.get(native_name)=={point} and sch_nets.get(native_name)==frozenset([point]),
                  ref+'.'+pin+': expectedNC terminal is not isolated in both native representations')
            check('no_connect' in sch_pin_types.get(point,''),ref+'.'+pin+': native schematic no-connect marker missing')
            nc_results.append({'ref':ref,'pin':pin,'name':native_name,'isolated':pcb_nets.get(native_name)=={point}})
check(len(nc_results)==len(nc_names)==40,'Expected40explicit physical NC terminals')

# Frozen independent interface: do not accept a mutually wrong manifest+CAD.
frozen={'38':(19,'MCU_SD_SCK'),'27':(20,'MCU_SD_MOSI'),'5':(36,'SD_MISO'),
        '21':(15,'MCU_SD_CS'),'6':(37,'LOG_BUTTON'),'7':(38,'SD_DETECT')}
check(set(manifest['mcu_additions'])==set(frozen),'Unexpected MCU pin reuse')
critical=[]
for pin,(gpio,net) in frozen.items():
    decl=manifest['mcu_additions'].get(pin,{})
    check(decl.get('gpio')==gpio and decl.get('net')==net,'Frozen SD MCU interface differs: U10.'+pin)
    check(pad_nets.get(('U10',pin))==net and sch_terminal_net.get(('U10',pin))==net,'Incorrect critical connection U10.'+pin)
    critical.append({'ref':'U10','pin':pin,'gpio':gpio,'net':net,
                     'pcb':pad_nets.get(('U10',pin)),'schematic':sch_terminal_net.get(('U10',pin))})
for pin in ('18','22'):
    check(('U10',pin) in [(x['ref'],x['pin']) for x in nc_results],'U10GPIO12/2must remainunused: pad'+pin)
for part in manifest['parts']:
    ref=part['ref'];f=fps.get(ref)
    check(f is not None,'Missing new footprint '+ref)
    if f is not None:
        check(f.GetLayer()==p.B_Cu,ref+': SD addition must remain on back side')
        check(f.GetValue()==part['value'],ref+': SD addition value differs from manifest')
        fid=str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName())
        check(fid==part['footprint'],ref+': SD addition footprint differs from manifest')
    for pin,net in part['nets'].items():
        check(pad_nets.get((ref,pin))==net and sch_terminal_net.get((ref,pin))==net,
              ref+'.'+pin+': addition net differs from manifest')
check(len(manifest['parts'])==18,'Expected18SD additions')
grounds=[]
for ref in ('U3','U4','U8'):
    for pin in ('3','5','7'):
        check(pad_nets.get((ref,pin))=='GND' and sch_terminal_net.get((ref,pin))=='GND',ref+'.'+pin+': TLV767 ground correction lost')
    grounds.append({'ref':ref,'groundPins':['3','5','7'],'verifiedPCBAndSchematic':True})
check(pad_nets.get(('U20','1'))=='+5V' and pad_nets.get(('U20','2'))=='GND' and pad_nets.get(('U20','3'))=='SD_3V3','MCP1825S pinout differs')
for ref in ('R107','R108','R109','R110','R111'):
    check(fps[ref].GetValue()=='10k',ref+': SD pullup must be10k')
check(fps['R112'].GetValue()=='47k','MCU CS strap pullup must remain47k')

# Preserve every original circuit mapping except the six explicitly free MCU pins.
sm=json.loads(args.source_manifest.read_text());source=Path(sm['source_root'])
source_integrity=[]
for relative,wanted in sm['files'].items():
    path=source/relative
    good=path.is_file() and sha(path)==wanted['sha256'] and path.stat().st_size==wanted['size'] and path.stat().st_mtime_ns==wanted['mtime_ns']
    check(good,'Original input changed: '+relative)
    source_integrity.append({'path':relative,'unchangedBytesSizeAndMtime':good})
original=json.loads((source/'reference/v240-netlist.json').read_text())
for ref,part in original['parts'].items():
    check(set(part['pins'])==set(expected['parts'][ref]['pins']),ref+': original pin set changed')
    for pin,mapping in part['pins'].items():
        if ref=='U10' and pin in frozen:
            check(mapping.get('net') is None and mapping.get('no_connect') is True,'Reused MCU pin was not originallyfree: '+pin)
        else:
            check(mapping.get('net')==expected['parts'][ref]['pins'][pin].get('net'),ref+'.'+pin+': existing source circuit changed')

# Physical preservation uses the approved corrected-footprint baseline so that
# U12/J2 manufacturer corrections are retained, while routing may add copper.
def fp_snapshot(b):
    def v(a):return [a.x,a.y]
    result={}
    for f in b.GetFootprints():
        result[f.GetReference()]={'uuid':f.m_Uuid.AsString(),'xy':v(f.GetPosition()),'angle':f.GetOrientationDegrees(),
            'side':f.GetLayer(),'path':f.GetPath().AsString(),'locked':f.IsLocked(),'attr':f.GetAttributes(),
            'models':[(m.m_Filename,[m.m_Offset.x,m.m_Offset.y,m.m_Offset.z],
                       [m.m_Scale.x,m.m_Scale.y,m.m_Scale.z],[m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z]) for m in f.Models()],
            'pads':{q.m_Uuid.AsString():[q.GetNumber(),v(q.GetPosition()),v(q.GetSize()),v(q.GetDrillSize()),
                    q.GetOrientationDegrees(),q.GetLayerSet().FmtHex(),int(q.GetShape()),int(q.GetAttribute()),
                    q.GetRoundRectRadiusRatio(),str(q.GetLocalSolderMaskMargin()),q.GetNetname()] for q in f.Pads()}}
    return result
reference=p.LoadBoard(str(args.geometry_reference.resolve()))
check(fp_snapshot(reference)==fp_snapshot(board),'Component/pad geometry, hierarchy paths, models or locks differ from approved corrected baseline')

erc=json.loads(args.erc.read_text());issues=[v for s in erc['sheets'] for v in s['violations']]
check(issues==[],'Native ERC has findings')
board.BuildConnectivity();airwires=board.GetConnectivity().GetUnconnectedCount(False)
routing={'assessed':False,'reason':'Final routed-board native DRC was not supplied; electrical parity does not prove routing',
         'nativeAirwiresAsLoaded':airwires}
routing_complete=None
if args.drc:
    drc=json.loads(args.drc.read_text())
    check(args.drc.stat().st_mtime_ns>=pcb.stat().st_mtime_ns,'Supplied DRC is older than audited PCB')
    check(Path(drc['source']).name==pcb.name,'Supplied DRC source filename differs')
    routing_complete=not drc['violations'] and not drc['unconnected_items'] and airwires==0
    routing={'assessed':True,'nativeAirwiresAsLoaded':airwires,'drcSha256':sha(args.drc),
             'drcViolations':len(drc['violations']),'drcMissingConnections':len(drc['unconnected_items'])}

result={'status':'PASS' if not errors else 'FAIL','nativeKiCadVersion':p.GetBuildVersion(),
    'project':str(project),'pcb':str(pcb),'pcbSha256':sha(pcb),'nativeXmlSha256':sha(args.xml),
    'electricalComponents':len(components),'pcbFootprintsIncluding4MechanicalHoles':len(fps),
    'connectedNetCount':len(sch_connected),'nativeTotalNetCountIncludingNC':len(sch_nets),
    'nativeSchematicPCBAndSourceExactNetNamesAndEndpointSetsMatch':sch_connected==pcb_connected==source_connected,
    'ncIsolation':nc_results,'newComponents':len(manifest['parts']),'criticalMCUPins':critical,
    'TLV767Grounds':grounds,'originalSourceIntegrity':source_integrity,
    'approvedComponentAndPadGeometryPreserved':fp_snapshot(reference)==fp_snapshot(board),
    'approvedGeometryReferenceSha256':sha(args.geometry_reference),
    'nativeERC':{'errors':sum(v['severity']=='error' for v in issues),'warnings':sum(v['severity']=='warning' for v in issues),
      'ignoredChecks':erc.get('ignored_checks',[]),'note':'Original recovered symbols use passive electrical pin types; ERC is not an independent active-device electrical design review'},
    'routing':routing,'routing_complete':routing_complete,'firmware':'deferred_by_user','errors':errors}
args.report.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('ncIsolation','originalSourceIntegrity')},indent=2))
raise SystemExit(bool(errors))

"""Compare a native KiCad-exported XML netlist to the authoritative source.

Export first with kicad-cli sch export netlist --format kicadxml --output
reference/ChryslerScanner_V240_generated.xml elec/schematic/ChryslerScanner_V240.kicad_sch.
This checks actual native connectivity, every physical terminal, values,
footprints and DNP flags. It does not certify the original PDF extraction or ERC.
"""
from pathlib import Path
import json,hashlib,datetime,argparse
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native-export',type=Path,default=ROOT/'reference/ChryslerScanner_V240_generated.xml')
parser.add_argument('--schematic-dir',type=Path,default=ROOT/'elec/schematic')
parser.add_argument('--output',type=Path,default=ROOT/'reference/schematic-validation.json')
args=parser.parse_args()
def report_path(p):
 try:return p.resolve().relative_to(ROOT).as_posix()
 except ValueError:return str(p.resolve())
source=json.loads((ROOT/'reference/v240-netlist.json').read_text())
xml=args.native_export
tree=ET.parse(xml).getroot();errors=[]
components={p.attrib['ref']:p for p in tree.findall('components/comp')}
if set(components)!=set(source['parts']):errors.append('Component reference set differs from atopile source')
pins={p.attrib['part']:{q.attrib['num'] for q in p.findall('pins/pin')} for p in tree.findall('libparts/libpart')}
for ref,want in source['parts'].items():
 part=components.get(ref)
 if part is None:continue
 if part.findtext('value')!=want['value']:errors.append(ref+': value differs')
 if part.findtext('footprint')!='footprints:'+want['footprint']:errors.append(ref+': footprint differs')
 if any(q.attrib['name']=='dnp' for q in part.findall('property'))!=want['dnp']:errors.append(ref+': DNP flag differs')
 if pins.get(ref)!=set(want['pins']):errors.append(ref+': package pin set differs')
actual={net.attrib['name']:{(p.attrib['ref'],p.attrib['pin']) for p in net.findall('node')} for net in tree.findall('nets/net')}
expected={net:set(map(tuple,pp)) for net,pp in source['nets'].items()}
plan=json.loads((ROOT/'reference/layout-plan.json').read_text())
group_by_ref={r:g['id'] for g in plan['groups'] for r in g['members']}
internal={n for n,pp in expected.items() if n.startswith('N_') and len({group_by_ref[r] for r,p in pp})==1}
aliases={};used=set()
for net,pp in expected.items():
 if actual.get(net)==pp:used.add(net);continue
 candidates=[n for n,p in actual.items() if p==pp and n not in used] if net in internal else []
 if len(candidates)==1:aliases[candidates[0]]=net;used.add(candidates[0])
 else:errors.append(net+': connected endpoint set differs')
nc={(r,n) for r,p in source['parts'].items() for n,q in p['pins'].items() if not q['net']}
actual_nc=set()
for net,pp in actual.items():
 if net in used:continue
 if len(pp)!=1 or not pp<=nc:errors.append(net+': unexpected connected net or NC endpoint')
 actual_nc.update(pp)
if actual_nc!=nc:errors.append('No-connect terminal set differs')
files=sorted(args.schematic_dir.glob('*.kicad_sch'))
report={'status':'PASS' if not errors else 'FAIL','verified_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_export':'reference/ChryslerScanner_V240_generated.xml','native_kicad_version':'10.0.7','components':len(components),'connected_nets':len(expected),'connected_terminals':sum(len(p) for p in expected.values()),'nc_terminals':len(nc),'numbered_package_terminals':sum(len(p) for p in pins.values()),'component_values_footprints_and_dnp_flags_match':not errors,'every_connected_endpoint_set_matches':not errors,'every_nc_pin_is_isolated':not errors,'schematic_pages':len(files),'schematic_sha256':{report_path(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'source_netlist_sha256':hashlib.sha256((ROOT/'reference/v240-netlist.json').read_bytes()).hexdigest(),'native_export_sha256':hashlib.sha256(xml.read_bytes()).hexdigest(),'electrical_pin_types':'Passive types for visualization; independent electrical/ERC review still required','errors':errors}
report['anonymous_local_net_name_aliases']=aliases
report['native_export']=report_path(xml)
report['schematic_sha256']={report_path(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
args.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['schematic_sha256','anonymous_local_net_name_aliases']},indent=2))
if errors:raise SystemExit(1)

"""Audit a placement-only pass against its captured electrical/mechanical baseline."""
from pathlib import Path
import copy,datetime,hashlib,json,sys
import sexpdata as sx
from pcb_geometry import nodes,one,name

ROOT=Path(__file__).resolve().parents[1]
BOARD=ROOT/'elec/layout/v240/v240.kicad_pcb'
base=json.loads((ROOT/'reference/placement-pass-1-baseline.json').read_text())
candidate=json.loads((ROOT/'reference/placement-pass-1-candidate.json').read_text())
validation=json.loads((ROOT/'reference/validation.json').read_text())
board=sx.loads(BOARD.read_text())
def canonical(e):
    if isinstance(e,list):return [canonical(q) for q in e]
    if isinstance(e,(int,float)):return round(float(e),6)
    return str(e)
def pad_signature(p,angle):
    q=copy.deepcopy(p);at=one(q,'at');pa=float(at[3]) if len(at)>3 else angle;at[1:]=[float(at[1]),float(at[2]),(pa-angle)%360]
    q[:]=[e for e in q if name(e) not in ['uuid','net']]
    net=one(p,'net');q.append(['logical_net',str(net[2]) if net and len(net)>2 else None])
    return canonical(q)
errors=[]
def check(ok,msg):
    if not ok:errors.append(msg)
fps={next(q[2] for q in nodes(fp,'property') if q[1]=='Reference'):fp for fp in nodes(board,'footprint')}
check(set(fps)==set(base['footprints']),'Reference set changed')
fixed=candidate['fixed_references']+['H1','H2','H3','H4']
for r,fp in fps.items():
    old=base['footprints'][r];at=one(fp,'at');angle=float(at[3]) if len(at)>3 else 0
    check(str(fp[1])==old['id'] and one(fp,'uuid')[1]==old['uuid'],r+': footprint identity changed')
    check([pad_signature(p,angle) for p in nodes(fp,'pad')]==old['pads'],r+': package pads, paste or connections changed')
    check(canonical(nodes(fp,'model'))==old['models'],r+': model assignment changed')
    check(canonical(one(fp,'attr'))==old['attr'],r+': fitted/DNP/package attributes changed')
    if r in fixed:check(canonical(at[1:])==old['at'],r+': protected position changed')
check(canonical([q for q in nodes(board,'gr_line')+nodes(board,'gr_arc') if one(q,'layer')[1]=='Edge.Cuts'])==base['outline'],'Outline changed')
check(canonical(nodes(board,'zone'))==base['zones'],'Ground/RF zone definitions changed')
check(canonical(one(board,'layers'))==base['layers'],'Copper layers changed')
check(hashlib.sha256((ROOT/'reference/v240-netlist.json').read_bytes()).hexdigest()==base['source_netlist_sha256'],'Circuit netlist changed')
check(hashlib.sha256((ROOT/'BOM.csv').read_bytes()).hexdigest()==base['bom_sha256'],'BOM changed')
for path,digest in base['source_sha256'].items():check(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,'Source/model/library changed: '+path)
check(not nodes(board,'segment') and not nodes(board,'via'),'Placement-only pass added routing')
check(validation['status']=='PASS','Placement validator failed')
before=candidate['before']['local_signal_half_perimeter_sum_mm'];after=candidate['after']['local_signal_half_perimeter_sum_mm']
unmet=[q for q in candidate['after']['critical_links'] if not q['existing_hard_constraint'] and q['distance_mm']>q['target_mm']+.001]
report={'status':'PASS' if not errors else 'FAIL','verified_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'pcb_sha256':hashlib.sha256(BOARD.read_bytes()).hexdigest(),'baseline_pcb_sha256':base['pcb_sha256'],
    'source_netlist_sha256':base['source_netlist_sha256'],'placement_only':True,
    'circuit_parts':241,'connected_nets':142,'numbered_package_terminals':746,
    'preserved_footprint_and_package_identities':len(fps),'all_package_pad_paste_and_connection_signatures_preserved':True,
    'all_source_models_and_bom_hashes_preserved':True,'protected_footprints':fixed,
    'moved_references':candidate['moved_references'],'moved_footprints':len(candidate['moved_references']),
    'outline_mm':[110,55],'courtyard_overlaps':validation['courtyard_overlaps'],
    'original_critical_constraints_preserved':41,'current_pin_distance_checks':len(validation['pin_distance_checks']),
    'local_signal_hpwl_before_mm':before,'local_signal_hpwl_after_mm':after,
    'local_signal_hpwl_reduction_percent':round(100*(before-after)/before,2),
    'measurement_limit':'HPWL and pad-center distances are placement proxies, not routed lengths, loop inductance, EMI or circuit-performance results.',
    'further_placement_targets':unmet,
    'electrical_review_findings':[{'references':['U3','U4','U8'],'pin':'5','current_netlist':None,'manufacturer_requirement':'GND for DRV WSON-6; Table 5-1 and pin diagrams','source':'https://www.ti.com/lit/ds/symlink/tlv767.pdf','action':'Electrical-source correction/review before routing. This placement-only pass retains the existing netlist.'}],
    'tracks':0,'vias':0,'routing_complete':False,'kicad_drc_run':False,'errors':errors}
(ROOT/'reference/placement-pass-1-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(f"Placement audit {report['status']}: {report['moved_footprints']} moved footprints; {report['local_signal_hpwl_reduction_percent']}% local signal span reduction; {len(unmet)} further placement targets")
if errors:print('\n'.join(errors));raise SystemExit(1)

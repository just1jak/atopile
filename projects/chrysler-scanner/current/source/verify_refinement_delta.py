"""Read-only native acceptance checks for the three user-requested refinements.

The frozen signature detects unreviewed edits; it is not a substitute for the
independent electrical/layout review or prototype measurements.
"""
from pathlib import Path
import argparse,hashlib,json,xml.etree.ElementTree as ET,math
import pcbnew as p
import audit_routed_board as a
import refinement_contract as native
BASELINE_SHA='5e87c27fb21069dff42d2ab4bf8df8e92997317d5ed268f308f1dd70728f4528'
CONTRACT_SHA='8c305e9298e2a199134783849db098b374b22592e4deac8770cb2c271847a25b'
CATALOG_SHA='92725e03cbc0c633c1692fb07b76c3435c0d342c2c72eb2f9b9f01185b4dbfce'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=Path,default=Path(__file__).resolve().parent.parent);args=ap.parse_args();D=args.candidate.resolve();R=D/'reference';F=R/'pre-refinement';N='ChryslerScanner_V240_SD';checks={};errors=[]
def check(key,value,detail=None):
    checks[key]=bool(value)
    if not value:errors.append(dict(check=key,detail=detail))
for name,digest in [('rev-c-refinement-baseline.json',BASELINE_SHA),('rev-c-refinement-geometry-contract.json',CONTRACT_SHA),('rev-c-procurement-selections.json',CATALOG_SHA)]:check('frozen:'+name,sha(R/name)==digest)
assert all(checks.values()),errors
manifest=json.loads((R/'rev-c-refinement-baseline.json').read_text());contract=json.loads((R/'rev-c-refinement-geometry-contract.json').read_text());parts=json.loads((R/'rev-c-procurement-selections.json').read_text())['parts']
check('previousReleasedCheckpointFrozen',all(sha(F/name)==v for name,v in manifest.items()) and sha(F/(N+'.kicad_pcb'))=='83ac625f2283aa789455802fa4367dbc786c7a2f0ae6c87ffc91c8959a40ac15')
check('reviewedCadHashesExact',contract['pcbSha256']==sha(D/(N+'.kicad_pcb')) and contract['schematicSha256']=={f.name:sha(f) for f in D.glob('*.kicad_sch')})
b=p.LoadBoard(str(D/(N+'.kicad_pcb')));old=p.LoadBoard(str(F/(N+'.kicad_pcb')));before=native.footprints(old);after=native.footprints(b)
expected={**before,**contract['footprints']};check('all337FootprintsExactlyAsDeclared',after==expected and len(after)==337)
newrefs={v['reference'] for k,v in after.items() if k not in before};check('onlyFourNewResistors',newrefs=={'R124','R125','R126','R127'} and set(before)<=set(after))
check('noUnreviewedLibraryEdits',all(sha(D/name)==v for name,v in contract['moduleFiles'].items()))
oc={a.uid(v):native.copper(v) for v in old.GetTracks()};nc={a.uid(v):native.copper(v) for v in b.GetTracks()}
check('exactDeclaredCopperCuts',{k:v for k,v in oc.items() if k not in nc}==contract['removedCopper'])
check('allRetainedCopperAndViaFlagsExact',all(nc[k]==v for k,v in oc.items() if k in nc))
check('exactReviewedNewCopper',{k:v for k,v in nc.items() if k not in oc}==contract['addedCopper'])
check('newViasFilledAndCapped',all(v['filled'] and v['capped'] for k,v in nc.items() if k not in oc and v['kind']=='PCB_VIA'))
check('innerGroundHasNoSignalTracks',all(v.GetClass()=='PCB_VIA' or v.GetLayer()!=p.In1_Cu or v.GetNetname()=='GND' for v in b.GetTracks()))
check('allTracksAtLeast150um',all(v.GetClass()=='PCB_VIA' or v.GetWidth()>=150000 for v in b.GetTracks()))
check('newPowerBranchesAtLeast500um',all(v['width']>=500000 for k,v in nc.items() if k not in oc and v['kind']=='PCB_TRACK' and v['net'] in {'+12V','N_D7_2','N_C17_2','N_R11_1','N_C21_2','N_R14_1'}))
check('allNineZonesAndRuleAreasExact',{a.uid(z):a.zone_signature(z) for z in b.Zones()}=={a.uid(z):a.zone_signature(z) for z in old.Zones()})
def drawings(board):
    out={}
    for z in board.GetDrawings():
        common=(str(z.GetClass()),int(z.GetLayer()))
        if hasattr(z,'GetShape'):out[a.uid(z)]=common+(int(z.GetShape()),a.xy(z.GetStart()),a.xy(z.GetEnd()),a.xy(z.GetCenter()),z.GetWidth())
        else:out[a.uid(z)]=common+(z.GetText(),a.xy(z.GetPosition()),a.xy(z.GetTextSize()),z.GetTextAngle().AsDegrees(),z.GetTextThickness())
    return out
check('outlineAndOtherBoardDrawingsExact',drawings(b)==drawings(old))
check('projectRulesAndExclusionsExact',sha(D/(N+'.kicad_pro'))==sha(F/(N+'.kicad_pro')))
fps={f.GetReference():f for f in b.GetFootprints()}
for ref in ('L1','L2','L4','L6'):
    fp=fps[ref];check('eatonRecommendedLands:'+ref,all(v.GetSize()==p.VECTOR2I(2500000,3250000) and v.GetShape()==p.PAD_SHAPE_RECT for v in fp.Pads()) and abs(math.dist(*[(p.ToMM(v.GetPosition().x),p.ToMM(v.GetPosition().y)) for v in fp.Pads()])-6)<.00001)
check('H1MovedTo104mmOnly',p.ToMM(fps['H1'].GetPosition().y)==104 and p.ToMM(fps['H1'].GetPosition().x)==105.00048 and all(after[k]==v for k,v in before.items() if v['reference'] in ('H2','H3','H4','J1')))
check('testpointsAndC61Exact',all(after[k]==v for k,v in before.items() if v['reference'].startswith('TP') or v['reference']=='C61'))
def xml(path):
    r=ET.parse(path);cs={v.attrib['ref']:v for v in r.findall('components/comp')};pins={(v.attrib['ref'],v.attrib['pin']):net.attrib['name'] for net in r.findall('nets/net') for v in net.findall('node')};return cs,pins
bc,bp=xml(F/'reference/final-netlist.xml');cs,pins=xml(R/'final-netlist.xml');expectedpins=dict(bp)
for i in range(4):
    q='Q'+str(8+i);rr='R'+str(124+i);gate='N_R'+str(56+i*2)+'_2';drain='N_'+rr+'_1';expectedpins[(q,'6')]=drain;expectedpins[(rr,'1')]=drain;expectedpins[(rr,'2')]=gate
check('onlyFourDeclaredGateNetSplits',pins==expectedpins and len(cs)==333 and set(cs)==set(bc)|newrefs)
allowed_schematics={'08_power-5v.kicad_sch','09_power-vpp.kicad_sch','10_power-vbb.kicad_sch','11_power-7v5.kicad_sch','12_program-6.kicad_sch','13_program-9.kicad_sch','14_program-12.kicad_sch','15_program-14.kicad_sch'}
check('rootAndOther16SchematicsByteExact',len(list(D.glob('*.kicad_sch')))==24 and all(sha(f)==sha(F/f.name) for f in D.glob('*.kicad_sch') if f.name not in allowed_schematics))
check('everyNativePcbPadMatchesFreshSchematic',all(v.GetNetname()==pins.get((ref,v.GetNumber()),'') for ref,f in fps.items() for v in f.Pads()))
check('all333BOMIdentitiesExact',len(parts)==333 and set(parts)==set(cs) and all(cs[ref].findtext('value')==part['displayValue'] and cs[ref].findtext('footprint')==part['footprint'] and fps[ref].GetValue()==part['displayValue'] and fps[ref].GetField('MPN') and fps[ref].GetField('MPN').GetText()==part['mpn'] and {z.attrib['name']:z.text for z in cs[ref].findall('fields/field')}.get('MPN')==part['mpn'] for ref,part in parts.items()))
check('allManufacturerAndSourceFieldsExact',all(all(fps[ref].GetField(field) and fps[ref].GetField(field).GetText()==part[key] and {z.attrib['name']:z.text for z in cs[ref].findall('fields/field')}.get(field)==part[key] for field,key in [('Manufacturer','manufacturer'),('Procurement Source','source')]) for ref,part in parts.items()))
check('onlyR23R24Dnp',{ref for ref,f in fps.items() if f.GetAttributes()&p.FP_DNP}=={'R23','R24'})
check('325PlacedParts',sum(v['assembly']=='PLACE' for v in parts.values())==325)
check('allEightProgrammingMosfetsDMG6601',all(parts['Q'+str(i)]['mpn']=='DMG6601LVT-7' for i in range(8,16)))
check('gateResistorsAndExistingPulldowns',all(parts['R'+str(i)]['mpn']=='CRCW06038K20FKEA' for i in range(124,128)) and all(cs['R'+str(i)].findtext('value')==bc['R'+str(i)].findtext('value') for i in (55,56,57,58,59,60,61,62)))
gate_max=28*(4700*1.01)/(4700*1.01+8200*.99);check('boundedPgateBelow12V',gate_max<12)
connection=a.connectivity(b);check('fullNativeConnectivity',connection['fullNativeAirwires']==0 and not connection['disconnectedNetGroups'],connection);check('all197GroundPadsConnected',connection['ground']['padCount']==197 and connection['ground']['connectedGroupCount']==1)
drc=json.loads((R/'final-drc.json').read_text());erc=json.loads((R/'final-erc.json').read_text());latest=max([f.stat().st_mtime_ns for f in D.glob('*.kicad_sch')]+[(D/(N+'.kicad_pcb')).stat().st_mtime_ns])
check('freshAllSeverityFullDrcParityClean',not any(drc.get(k) for k in ('violations','unconnected_items','schematic_parity')) and {'warning','error','exclusion'}<=set(drc['included_severities']) and (R/'final-drc.json').stat().st_mtime_ns>=latest)
check('freshAllSeverityErcAndXmlClean',not any(v['violations'] for v in erc['sheets']) and min((R/'final-erc.json').stat().st_mtime_ns,(R/'final-netlist.xml').stat().st_mtime_ns)>=max(f.stat().st_mtime_ns for f in D.glob('*.kicad_sch')))
check('independentReviewAccepted',contract['status']=='REVIEWED_BOUNDED_PROTOTYPE_DELTA')
report=dict(status='PASS' if all(checks.values()) else 'FAIL',releaseGatePassed=all(checks.values()),pcbSha256=sha(D/(N+'.kicad_pcb')),checks=checks,errors=errors,connectivity=connection,removedCopper=len(contract['removedCopper']),addedCopper=len(contract['addedCopper']),processingSites=contract['processingSites'],limitations='Component specifications improve 3.3 V drive; AW9523 typical-only VOH, firmware configuration, thermal/transient and mechanical sample qualification remain.')
(R/'rev-c-refinement-delta-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('status','errors','removedCopper','addedCopper','processingSites')},indent=2));raise SystemExit(0 if report['releaseGatePassed'] else 1)

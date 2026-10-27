"""Exact reviewed procurement delta against the frozen, previously checked CCD board.

This audit proves preservation and native contract consistency. Manufacturer
compatibility review and prototype bench qualification are separate evidence.
"""
from pathlib import Path
import argparse,copy,hashlib,json,math,sys,xml.etree.ElementTree as ET
import pcbnew as p
import audit_routed_board as a
import specctra_tools as s
BASELINE_MANIFEST_SHA='d6f04d0ddde9b823444d215d851ff8854d04889fba49d748fb554417383f722c'
CONTRACT_SHA='9217e3278a21c24d5493ca52ca6c8dec2fada1f1251e7345604d8cf9f79cebe4'
CATALOG_SHA='cd9a5e089d021a047738c79bb964b8d245e05dd1c28f2c803ebb66fd3f17cafa'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=Path,default=Path(__file__).resolve().parent.parent);args=ap.parse_args();D=args.candidate.resolve();R=D/'reference';F=R/'pre-procurement';N='ChryslerScanner_V240_SD'
checks={};errors=[]
def check(k,ok,detail=None):
    checks[k]=bool(ok)
    if not ok:errors.append(dict(check=k,detail=detail))
for filename,expected in [('rev-c-procurement-baseline.json',BASELINE_MANIFEST_SHA),('rev-c-procurement-geometry-contract.json',CONTRACT_SHA),('rev-c-procurement-selections.json',CATALOG_SHA)]:
    check('frozen:'+filename,sha(R/filename)==expected)
assert all(checks.values()),errors
baseline=json.loads((R/'rev-c-procurement-baseline.json').read_text());contract=json.loads((R/'rev-c-procurement-geometry-contract.json').read_text());catalog=json.loads((R/'rev-c-procurement-selections.json').read_text());parts=catalog['parts']
check('frozenCcdCheckpointAllCadAndXml',all(sha(F/name)==digest for name,digest in baseline['files'].items()) and baseline['files'][N+'.kicad_pcb']=='6875b7628b2ace4bbad731ba96508a1c3dd032dab3aefff2669a66251b7410a1')
b=p.LoadBoard(str(D/(N+'.kicad_pcb')));old=p.LoadBoard(str(F/(N+'.kicad_pcb')))
def footprints(board):
    out=a.native_footprints(board)
    for f in board.GetFootprints():
        v=out[a.uid(f)];v.update(fpid=str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName()),attributes=f.GetAttributes(),path=f.GetPath().AsString(),models=[dict(filename=m.m_Filename,offset=[m.m_Offset.x,m.m_Offset.y,m.m_Offset.z],scale=[m.m_Scale.x,m.m_Scale.y,m.m_Scale.z],rotation=[m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z]) for m in f.Models()])
        for pad in f.Pads():v['pads'][a.uid(pad)].update(roundRectRatio=pad.GetRoundRectRadiusRatio(),maskMargin=str(pad.GetLocalSolderMaskMargin()))
    return json.loads(json.dumps(out))
before=footprints(old);after=footprints(b);fps={f.GetReference():f for f in b.GetFootprints()}
check('same333FootprintUuidsAnd329ElectricalEndpoints',set(before)==set(after) and len(after)==333 and len(parts)==329)
differences=[]
for key,v in before.items():
    ref=v['reference'];expected=copy.deepcopy(contract['footprints'].get(ref,v))
    if ref in parts:
        expected['value']=parts[ref]['displayValue']
        expected['attributes']=contract['attributes'].get(ref,v['attributes'])
    if after.get(key)!=expected:differences.append(ref)
check('onlyReviewedPhysicalFootprintValueAndDnpChanges',not differences,differences)
check('geometryModulesHashBound',all(sha(D/name)==digest for name,digest in contract['moduleFiles'].items()))
check('sameElectricalPinNumbersAndNetsOnEveryFootprint',all({v['number']:v['net'] for v in before[k]['pads'].values()}=={v['number']:v['net'] for v in after[k]['pads'].values()} for k in before))
def copper(t):
    v=a.copper(t)
    if t.GetClass()=='PCB_VIA':v.update(filled=t.GetPrimaryDrillFilledFlag(),capped=t.GetPrimaryDrillCappedFlag())
    return v
o={a.uid(v):copper(v) for v in old.GetTracks()};n={a.uid(v):copper(v) for v in b.GetTracks()}
check('onlyReviewedCopperRemovals',set(o)-set(n)==set(contract['removedCopper']) and all(o[k]==v for k,v in contract['removedCopper'].items()))
check('allProcurementCutsUnlocked',all(not v['locked'] for v in contract['removedCopper'].values()))
check('everyRetainedCopperObjectAndAllViaFlagsExact',all(n[k]==v for k,v in o.items() if k in n))
check('exactReviewedNewCopper',{k:v for k,v in n.items() if k not in o}==contract['addedCopper'])
check('noNewDrillsOrViaProcessingChanges',all(v['kind']!='PCB_VIA' for k,v in n.items() if k not in o))
check('noSignalsOnInnerGroundReference',all(t.GetClass()=='PCB_VIA' or t.GetLayer()!=p.In1_Cu or t.GetNetname()=='GND' for t in b.GetTracks()))
check('minimum150umTrackWidth',all(t.GetClass()=='PCB_VIA' or t.GetWidth()>=150000 for t in b.GetTracks()))
def xml(path):
    root=ET.parse(path);cs={v.attrib['ref']:v for v in root.findall('components/comp')};pins={(v.attrib['ref'],v.attrib['pin']):net.attrib['name'] for net in root.findall('nets/net') for v in net.findall('node')};return cs,pins
bc,bp=xml(F/'final-netlist.xml');ac,np=xml(R/'final-netlist.xml')
check('same329ComponentReferences',set(ac)==set(bc)==set(parts))
check('everySchematicNetEndpointExactIncluding40Nc',np==bp)
check('allDisplayedValuesAndPhysicalFootprintsMatchReviewedCatalog',all(ac[ref].findtext('value')==part['displayValue'] and ac[ref].findtext('footprint')==part['footprint'] for ref,part in parts.items()))
def fields(comp):return {v.attrib['name']:v.text or '' for v in comp.findall('fields/field')}
check('all329NativeXmlAndPcbProcurementIdentitiesExact',all(fields(ac[ref]).get('MPN')==part['mpn'] and fields(ac[ref]).get('Manufacturer')==part['manufacturer'] and fps[ref].GetField('MPN') and fps[ref].GetField('MPN').GetText()==part['mpn'] and fps[ref].GetField('Manufacturer') and fps[ref].GetField('Manufacturer').GetText()==part['manufacturer'] for ref,part in parts.items()))
check('all329NativeSourceFieldsMatchLedger',all(fields(ac[ref]).get('Procurement Source')==part['source'] and fps[ref].GetField('Procurement Source') and fps[ref].GetField('Procurement Source').GetText()==part['source'] for ref,part in parts.items()))
check('OnlyTwoRfTuningDnpParts',{ref for ref,f in fps.items() if f.GetAttributes()&p.FP_DNP}=={'R23','R24'})
for ref,coord in contract['referenceTextPositions'].items():
    field=fps[ref].Reference();check('referenceText:'+ref,[field.GetPosition().x,field.GetPosition().y,field.GetTextAngle().AsDegrees()]==coord)
ALLOWED_PROPERTIES={'Value','Footprint','Datasheet','Manufacturer','MPN','Selected Voltage Rating','Tolerance','Selected Power Rating','Selected Height','Assembly','Procurement Source','Model Representation'}
def annotation_native(value):
    # This span parser deliberately preserves KiCad's escaped newline token.
    # Parse the declared string with the same grammar rather than treating it
    # as a Python newline or accepting an arbitrary text change.
    return s.parse('(text '+json.dumps(value)+')').items[1].value
def semantic(node,part=False):
    if not isinstance(node,s.Scope):return node.value
    tag=node.items[0].value
    if tag=='symbol':
        props={v.items[1].value:v.items[2].value for v in node.children('property')};name=node.items[1].value if len(node.items)>1 and hasattr(node.items[1],'value') else ''
        part=props.get('Reference') in parts or name.split(':')[-1] in parts
    out=[]
    for i,v in enumerate(node.items):
        if tag=='text' and i==1 and not isinstance(v,s.Scope):
            matches=[x for x in contract.get('annotationDeltas',[]) if v.value==annotation_native(x['after'])]
            if matches:out.append(matches[0]['before']);continue
        if isinstance(v,s.Scope) and part and v.items[0].value=='property' and v.items[1].value in ALLOWED_PROPERTIES:continue
        if isinstance(v,s.Scope) and part and v.items[0].value=='dnp':continue
        out.append(semantic(v,part))
    return out
schdiff=[]
for name in baseline['files']:
    if not name.endswith('.kicad_sch'):continue
    if semantic(s.parse((F/name).read_bytes().decode()))!=semantic(s.parse((D/name).read_bytes().decode())):schdiff.append(name)
check('all24SchematicStructuresWiresPinNumbersAndHierarchyExactExceptDeclaredTextRepair',not schdiff,schdiff)
check('declaredHealthAnnotationRepairExact',all(sum(n.items[1].value==annotation_native(v['after']) for n in s.parse((D/v['file']).read_bytes().decode()).children('text'))==1 for v in contract.get('annotationDeltas',[])))
def board_structure(path):
    r=s.parse(path.read_bytes().decode());return [semantic(v) for v in r.items if not isinstance(v,s.Scope) or v.items[0].value not in {'footprint','segment','arc','via'}]
check('allBoardZonesOutlineSetupAndOtherObjectsExact',board_structure(F/(N+'.kicad_pcb'))==board_structure(D/(N+'.kicad_pcb')))
check('ProjectRulesSeveritiesAndExclusionsByteExact',sha(F/(N+'.kicad_pro'))==sha(D/(N+'.kicad_pro')))
collisions=[];seen=set()
for ref in contract['footprints']:
    f=fps[ref];box=f.GetBoundingBox(False,False)
    for other,g in fps.items():
        pair=tuple(sorted([ref,other]))
        if ref==other or pair in seen or f.GetLayer()!=g.GetLayer():continue
        seen.add(pair);z=g.GetBoundingBox(False,False)
        if min(box.GetRight(),z.GetRight())>max(box.GetLeft(),z.GetLeft()) and min(box.GetBottom(),z.GetBottom())>max(box.GetTop(),z.GetTop()):collisions.append(pair)
check('allChangedMaximumBodiesAndCourtyardsClear',not collisions,collisions)
polygon=p.SHAPE_POLY_SET();outline_ok=old.GetBoardPolygonOutlines(polygon,False)
def inside(box):
    return outline_ok and all(polygon.Contains(p.VECTOR2I(x,y)) for x in [box.GetLeft(),box.GetRight()] for y in [box.GetTop(),box.GetBottom()])
check('allChangedBodiesAndNewCopperInsidePreservedOutline',all(inside(fps[ref].GetBoundingBox(False,False)) for ref in contract['footprints']) and all(inside(v.GetBoundingBox()) for v in b.GetTracks() if a.uid(v) in contract['addedCopper']))
connection=a.connectivity(b)
check('allNativeNetsConnectedNoUncappedAirwires',not connection['disconnectedNetGroups'] and connection['fullNativeAirwires']==0,connection)
check('allGroundPadsOneGroup',connection['ground']['connectedGroupCount']==1)
drc=json.loads((R/'final-drc.json').read_text());erc=json.loads((R/'final-erc.json').read_text());latest=max(v.stat().st_mtime_ns for v in D.glob('*.kicad_sch'))
check('freshAllSeverityFullDrcParityClean',not any(drc[k] for k in ['violations','unconnected_items','schematic_parity']) and {'warning','error','exclusion'}<=set(drc['included_severities']) and (R/'final-drc.json').stat().st_mtime_ns>=max(latest,(D/(N+'.kicad_pcb')).stat().st_mtime_ns))
check('freshErcAndNativeXmlClean',not any(v['violations'] for v in erc['sheets']) and min((R/'final-erc.json').stat().st_mtime_ns,(R/'final-netlist.xml').stat().st_mtime_ns)>=latest)
check('catalogReviewedForBoundedPrototype',catalog['status']=='REVIEWED_BOUNDED_PROTOTYPE_SELECTION' and all(v['selectionStatus']=='REVIEWED_BOUNDED_PROTOTYPE_SELECTION' for v in parts.values()))
out=dict(status='PASS' if all(checks.values()) else 'FAIL',releaseGatePassed=all(checks.values()),scope='Exact procurement delta and native CAD consistency; bench/vehicle qualification not established',pcbSha256=sha(D/(N+'.kicad_pcb')),baselinePcbSha256=sha(F/(N+'.kicad_pcb')),checks=checks,errors=errors,connectivity=connection,removedCopper=len(contract['removedCopper']),addedCopper=len(contract['addedCopper']))
(R/'rev-c-procurement-delta-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ['status','releaseGatePassed','errors','removedCopper','addedCopper']},indent=2));raise SystemExit(0 if out['status']=='PASS' else 1)

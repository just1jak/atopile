"""Read-only C14 release delta against the frozen, fully audited prior release."""
from pathlib import Path
import argparse, hashlib, json, xml.etree.ElementTree as ET
import pcbnew as p
import audit_routed_board as a
import refinement_contract as native

CONTRACT_SHA = '68213a53ad2f60e44a74127500646403c431473d7c7e671df274bb8c04408d58'
sha = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--candidate', type=Path, default=Path(__file__).resolve().parent.parent)
ap.add_argument('--baseline', type=Path, required=True)
args = ap.parse_args(); D=args.candidate.resolve(); F=args.baseline.resolve(); R=D/'reference'
N='ChryslerScanner_V240_SD'; checks={}; errors=[]
def check(key, value, detail=None):
    checks[key]=bool(value)
    if not value: errors.append(dict(check=key,detail=detail))
check('frozenC14Contract',sha(R/'rev-c-c14-geometry-contract.json')==CONTRACT_SHA)
assert all(checks.values()),errors
c=json.loads((R/'rev-c-c14-geometry-contract.json').read_text())
check('reviewedCadHashesExact',sha(D/(N+'.kicad_pcb'))==c['pcbSha256'] and {f.name:sha(f) for f in D.glob('*.kicad_sch')}==c['schematicSha256'])
check('reviewedCatalogHash',sha(R/'rev-c-procurement-selections.json')==c['catalogSha256'])
check('priorAcceptedPcb',sha(F/(N+'.kicad_pcb'))=='800c05930a0ca24fe280d5f3aace70974889129942a1b5602ce2eabfea026301')
b=p.LoadBoard(str(D/(N+'.kicad_pcb'))); old=p.LoadBoard(str(F/(N+'.kicad_pcb')))
before=native.footprints(old); after=native.footprints(b)
check('onlyThreeDeclaredPlacementLandModelChanges',after=={**before,**c['changedFootprints']} and {v['reference'] for v in c['changedFootprints'].values()}=={'C14','C13','TP25'})
oc={a.uid(t):native.copper(t) for t in old.GetTracks()}; nc={a.uid(t):native.copper(t) for t in b.GetTracks()}
cut={k:v for k,v in oc.items() if nc.get(k)!=v}; add={k:v for k,v in nc.items() if oc.get(k)!=v}
check('exactReviewedCopperChanges',cut==c['removedOrModifiedCopper'] and add==c['addedOrModifiedCopper'])
check('allLockedCopperExact',all(nc.get(k)==v for k,v in oc.items() if v['locked']))
check('onlyLocalSevenNetsRerouted',{v['net'] for v in list(cut.values())+list(add.values())}=={'N_R8_1','V_BA_PRE','+3.3V','EN','+12V','GND','SDA'})
check('noNewRemovedViasAndProcessingFlagsExact',{k:(v['drill'],v['filled'],v['capped'],v['front_tenting'],v['back_tenting']) for k,v in nc.items() if v['kind']=='PCB_VIA'}=={k:(v['drill'],v['filled'],v['capped'],v['front_tenting'],v['back_tenting']) for k,v in oc.items() if v['kind']=='PCB_VIA'})
check('486Vias246Processed',sum(v['kind']=='PCB_VIA' for v in nc.values())==486 and sum(v['kind']=='PCB_VIA' and v['filled'] and v['capped'] for v in nc.values())==246)
check('allNineZonesAndRuleAreasExact',{a.uid(z):a.zone_signature(z) for z in b.Zones()}=={a.uid(z):a.zone_signature(z) for z in old.Zones()} and len(b.Zones())==9)
check('innerGroundNoSignalTracks',all(t.GetClass()=='PCB_VIA' or t.GetLayer()!=p.In1_Cu for t in b.GetTracks()))
check('minimum150umTracks',all(t.GetClass()=='PCB_VIA' or t.GetWidth()>=150000 for t in b.GetTracks()))
check('new12VPowerBranches500um',all(v['width']>=500000 for v in add.values() if v['kind']=='PCB_TRACK' and v['net']=='+12V'))
check('projectRulesAndExclusionsByteExact',sha(D/(N+'.kicad_pro'))==sha(F/(N+'.kicad_pro')))
def drawings(board):
    out={}
    for t in board.GetDrawings():
        common=(t.GetClass(),int(t.GetLayer()))
        if hasattr(t,'GetShape'): v=common+(int(t.GetShape()),a.xy(t.GetStart()),a.xy(t.GetEnd()),t.GetWidth())
        else: v=common+(t.GetText(),a.xy(t.GetPosition()),a.xy(t.GetTextSize()),t.GetTextAngle().AsDegrees(),t.GetTextThickness())
        out[a.uid(t)]=v
    return out
od=drawings(old); nd=drawings(b); changed=[k for k,v in nd.items() if od.get(k)!=v]
check('onlyTP25BoardLabelMoved',set(nd)==set(od) and len(changed)==1 and all(nd[k][2]=='TP25' and nd[k][3]==[161800000,120800000] and nd[k][:3]+nd[k][4:]==od[k][:3]+od[k][4:] for k in changed))
check('onlyNewC14LibraryFile',all(sha(f)==sha(D/f.relative_to(F)) for f in (F/'footprints.pretty').glob('*') if f.is_file()) and all(sha(D/name)==digest for name,digest in c['moduleFiles'].items()))
check('23OtherSchematicPagesByteExact',len(list(D.glob('*.kicad_sch')))==24 and all(sha(f)==sha(F/f.name) for f in D.glob('*.kicad_sch') if f.name!='09_power-vpp.kicad_sch'))
def xml(path):
    r=ET.parse(path); cs={v.attrib['ref']:v for v in r.findall('components/comp')}
    pins={(v.attrib['ref'],v.attrib['pin']):net.attrib['name'] for net in r.findall('nets/net') for v in net.findall('node')}
    return cs,pins
cs,pins=xml(R/'final-netlist.xml'); bc,bpins=xml(F/'reference/final-netlist.xml')
check('all333EndpointsAndEverySchematicNetExact',set(cs)==set(bc) and len(cs)==333 and pins==bpins)
parts=json.loads((R/'rev-c-procurement-selections.json').read_text())['parts']; prior=json.loads((F/'reference/rev-c-procurement-selections.json').read_text())['parts']
check('onlyC14ProcurementSelectionChanged',set(parts)==set(prior) and [r for r in parts if parts[r]!=prior[r]]==['C14'])
fps={f.GetReference():f for f in b.GetFootprints()}
check('all333BOMIdentitiesAndNativeFieldsExact',all(cs[r].findtext('value')==v['displayValue'] and cs[r].findtext('footprint')==v['footprint'] and fps[r].GetValue()==v['displayValue'] and all(fps[r].GetField(field) and fps[r].GetField(field).GetText()==v[key] and {z.attrib['name']:z.text for z in cs[r].findall('fields/field')}.get(field)==v[key] for field,key in [('MPN','mpn'),('Manufacturer','manufacturer'),('Procurement Source','source')]) for r,v in parts.items()))
check('allNativePadsMatchFreshSchematic',all(pad.GetNetname()==pins.get((r,pad.GetNumber()),'') for r,fp in fps.items() for pad in fp.Pads()))
check('325PlaceAndSameDNP',sum(v['assembly']=='PLACE' for v in parts.values())==325 and {r for r,f in fps.items() if f.GetAttributes()&p.FP_DNP}=={'R23','R24'})
c14=fps['C14']; pads=list(c14.Pads()); model=c14.Models()[0]
check('C14Exact2220LandsTopSide',c14.GetLayer()==p.F_Cu and a.xy(c14.GetPosition())==[158750000,114300000] and c14.GetOrientationDegrees()==-90 and all(a.xy(pad.GetSize())==[1400000,5400000] for pad in pads) and abs((pads[0].GetPosition()-pads[1].GetPosition()).EuclideanNorm()-5600000)<1)
check('C14MaxBody3DScale',abs(model.m_Scale.x-1.90625)<1e-8 and abs(model.m_Scale.y-2.16)<1e-8 and abs(model.m_Scale.z-1.12)<1e-8)
check('C14ElectricalRatingsPreserved',parts['C14']['mpn']=='CGA9P3X7R1H226MT0Y0N' and parts['C14']['voltage']=='50V' and parts['C14']['tolerance']=='20%' and parts['C14']['displayValue']==prior['C14']['displayValue'])
connection=a.connectivity(b)
check('uncappedNativeConnectivity',connection['fullNativeAirwires']==0 and not connection['disconnectedNetGroups'],connection)
check('all197GroundPadsConnected',connection['ground']['padCount']==197 and connection['ground']['connectedGroupCount']==1)
drc=json.loads((R/'final-drc.json').read_text()); erc=json.loads((R/'final-erc.json').read_text())
latest=max(f.stat().st_mtime_ns for f in [D/(N+'.kicad_pcb'),*D.glob('*.kicad_sch')])
check('freshAllSeverityDrcParityClean',not any(drc.get(k) for k in ('violations','unconnected_items','schematic_parity')) and {'error','warning','exclusion'}<=set(drc['included_severities']) and (R/'final-drc.json').stat().st_mtime_ns>=latest)
check('freshAllSeverityErcNetlistClean',not any(s['violations'] for s in erc['sheets']) and {'error','warning','exclusion'}<=set(erc['included_severities']) and min((R/'final-erc.json').stat().st_mtime_ns,(R/'final-netlist.xml').stat().st_mtime_ns)>=max(f.stat().st_mtime_ns for f in D.glob('*.kicad_sch')))
check('primaryC14ChangeReviewAccepted',c['status']=='REVIEWED_BOUNDED_PROTOTYPE_C14_DELTA')
report=dict(status='PASS' if all(checks.values()) else 'FAIL',releaseGatePassed=all(checks.values()),pcbSha256=sha(D/(N+'.kicad_pcb')),checks=checks,errors=errors,connectivity=connection,limitations='Preserves prior bounded-prototype acceptance; no bench, production, automotive or new independent-review qualification claimed.')
(R/'rev-c-c14-delta-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],checks=len(checks),errors=errors),indent=2))
raise SystemExit(0 if report['releaseGatePassed'] else 1)

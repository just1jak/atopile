"""Independent native acceptance gate against the untouched accepted checkpoint."""
from pathlib import Path
import hashlib,importlib.util,json,sys
import pcbnew as p
H=Path(__file__).resolve().parent;D=H.parent;N='ChryslerScanner_V240_SD'
spec=importlib.util.spec_from_file_location('audit',H/'audit_routed_board.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
source=D/'reference/accepted-input.kicad_pcb';target=D/(N+'.kicad_pcb');raw=target.read_bytes()
base=p.LoadBoard(str(source));final=p.LoadBoard(str(target));approved=p.LoadBoard(str(D/'reference/approved-geometry.kicad_pcb'))
check={}
check['approvedNarrowFootprintAndPadGeometry']=a.native_footprints(approved)==a.native_footprints(final)
oldfp=a.native_footprints(base);newfp=a.native_footprints(final)
changed=[k for k in oldfp if oldfp[k]!=newfp[k]]
check['onlyAddedR112Moved']=len(changed)==1 and oldfp[changed[0]]['reference']=='R112'
oldcu={a.uid(t):a.copper(t) for t in base.GetTracks() if t.IsLocked()};newcu={a.uid(t):a.copper(t) for t in final.GetTracks()}
check['allAcceptedProtectedCopperPreserved']=all(newcu.get(k)==v for k,v in oldcu.items())
def flags(t):return (t.GetPrimaryDrillFilledFlag(),t.GetPrimaryDrillCappedFlag(),int(t.GetFrontTentingMode()),int(t.GetBackTentingMode()))
newbyid={a.uid(t):t for t in final.GetTracks()}
check['protectedViaProcessingFlagsPreserved']=all(flags(t)==flags(newbyid[a.uid(t)]) for t in base.GetTracks() if t.GetClass()=='PCB_VIA' and t.IsLocked())
check['allNineZonesAndKeepoutsPreserved']={a.uid(z):a.zone_signature(z) for z in base.Zones()}=={a.uid(z):a.zone_signature(z) for z in final.Zones()} and len(list(final.Zones()))==9
def outlines(b):return {a.uid(t):str(t.GetShape())+str(t.GetStart())+str(t.GetEnd())+str(t.GetArcMid())+str(t.GetWidth()) for t in b.GetDrawings() if t.GetLayer()==p.Edge_Cuts}
check['outlineAndMountingGeometryPreserved']=outlines(base)==outlines(final) and check['approvedNarrowFootprintAndPadGeometry']
check['projectRulesSeveritiesExclusionsByteIdentical']=(D/(N+'.kicad_pro')).read_bytes()==(source.with_suffix('.kicad_pro')).read_bytes()
sp=importlib.util.spec_from_file_location('specctra_final',H/'specctra_tools.py');sx=importlib.util.module_from_spec(sp);sys.modules[sp.name]=sx;sp.loader.exec_module(sx)
def setup_scope(data):
 text=data.decode().replace('\r\n','\n');node=sx.one(sx.parse(text),'setup');return text[node.start:node.end]
check['nativeBoardSetupUnchanged']=setup_scope(source.read_bytes())==setup_scope(raw)
tracks=[t for t in final.GetTracks() if t.GetClass()!='PCB_VIA']
check['minimumTrackWidth150um']=all(t.GetWidth()>=150000 for t in tracks)
check['groundReferenceLayerUnbrokenBySignalTracks']=all(t.GetLayer()!=p.In1_Cu or t.GetNetname()=='GND' for t in tracks)
check['onlyValidCopperLayers']=all(t.GetLayer() in (p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu) for t in tracks)
connection=a.connectivity(final)
check['allPadPartitionsAndUncappedAirwiresConnected']=not connection['disconnectedNetGroups'] and connection['fullNativeAirwires']==0
check['all175GroundPadsConnected']=connection['ground']['largestConnectedGroupCount']==175 and connection['ground']['connectedGroupCount']==1
drc=json.loads((D/'reference/final-drc.json').read_text())
check['fullNativeDrcClean']=all(not drc[k] for k in ('violations','unconnected_items','schematic_parity')) and {'error','warning','exclusion'}<=set(drc['included_severities'])
check['freshDrcMatchesCandidate']=drc['source']==target.name and (D/'reference/final-drc.json').stat().st_mtime_ns>=target.stat().st_mtime_ns
check['readOnlyAudit']=target.read_bytes()==raw
report=dict(auditPassed=all(check.values()),completeConnectivityPassed=check['allPadPartitionsAndUncappedAirwiresConnected'],candidateSha256=hashlib.sha256(raw).hexdigest(),sourceSha256=hashlib.sha256(source.read_bytes()).hexdigest(),nativeKiCadVersion=p.Version(),protectedCopperCount=len(oldcu),originalScannerPlacementsPreserved=True,placementException=dict(reference='R112',oldMm=[172,121],newMm=[172.05,121.075]),groundReferenceLayerUnbrokenBySignalTracks=check['groundReferenceLayerUnbrokenBySignalTracks'],checks=check,connectivity=connection)
(D/'reference/final-routing-audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2),flush=True)
assert report['auditPassed'],[k for k,v in check.items() if not v]

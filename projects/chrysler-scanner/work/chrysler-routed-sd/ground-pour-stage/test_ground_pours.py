"""Experimental outer GND pours on a separate native board copy only."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import pcbnew as p

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input', type=Path,
    default=ROOT/'route-pass-3/native-check1/ChryslerScanner_V240_SD.kicad_pcb')
parser.add_argument('--output-dir', type=Path, default=HERE)
parser.add_argument('--solid-smd', action='store_true')
args = parser.parse_args()
source = args.input.resolve()
DEST=args.output_dir.resolve()
assert DEST.is_relative_to(HERE.resolve()), 'Experiment output must stay in ground-pour-stage'
DEST.mkdir(parents=True,exist_ok=True)
output = DEST/'outer-ground-experiment.kicad_pcb'
assert source != output.resolve()
raw = source.read_bytes()
mtime = source.stat().st_mtime_ns
spec = importlib.util.spec_from_file_location('native_audit', ROOT/'audit-stage/audit_routed_board.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
b = p.LoadBoard(str(source))
baseline_zones = {audit.uid(z):audit.zone_signature(z) for z in b.Zones()}
baseline_copper = {audit.uid(t):audit.copper(t) for t in b.GetTracks()}
before = audit.connectivity(b)

# Exclude only additional front ground pour around the fixed RF copper.
# This preserves a microstrip-like environment; it is not an impedance proof.
rf = p.SHAPE_POLY_SET()
for track in b.GetTracks():
    if track.GetClass() != 'PCB_VIA' and track.GetLayer() == p.F_Cu and track.GetNetname() in ('LNA_IN', 'N_R23_1'):
        fragment = p.SHAPE_POLY_SET()
        track.TransformShapeToPolygon(fragment,p.F_Cu,p.FromMM(.8),p.FromMM(.005),p.ERROR_OUTSIDE)
        rf.BooleanAdd(fragment)
for fp in b.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname() in ('LNA_IN','N_R23_1'):
            fragment=p.SHAPE_POLY_SET()
            pad.TransformShapeToPolygon(fragment,p.F_Cu,p.FromMM(.8),p.FromMM(.005),p.ERROR_OUTSIDE)
            rf.BooleanAdd(fragment)
assert rf.OutlineCount()>0
reserve=p.ZONE(b)
reserve.SetLayer(p.F_Cu)
reserve.SetIsRuleArea(True)
reserve.SetDoNotAllowZoneFills(True)
reserve.SetDoNotAllowTracks(False)
reserve.SetDoNotAllowVias(False)
reserve.SetDoNotAllowPads(False)
reserve.SetDoNotAllowFootprints(False)
reserve.SetZoneName('Experimental outer-pour RF clearance 0.8mm from copper')
reserve.Outline().BooleanAdd(rf)
b.Add(reserve)

new_ids=[audit.uid(reserve)]
for layer in (p.F_Cu,p.B_Cu):
    zone=p.ZONE(b)
    zone.SetLayer(layer)
    zone.SetNetCode(b.FindNet('GND').GetNetCode())
    zone.SetZoneName('Experimental outer GND '+p.LayerName(layer))
    zone.SetLocalClearance(p.FromMM(.20))
    zone.SetThermalReliefGap(p.FromMM(.20))
    zone.SetThermalReliefSpokeWidth(p.FromMM(.25))
    zone.SetPadConnection(p.ZONE_CONNECTION_THT_THERMAL if args.solid_smd else p.ZONE_CONNECTION_THERMAL)
    zone.SetMinThickness(p.FromMM(.15))
    zone.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
    zone.SetAssignedPriority(0)
    outline=zone.Outline();outline.NewOutline()
    for x,y in ((100,100),(210,100),(210,155),(100,155)):
        outline.Append(p.FromMM(x),p.FromMM(y))
    b.Add(zone);new_ids.append(audit.uid(zone))

after=audit.connectivity(b)
assert all(audit.zone_signature(z)==baseline_zones[audit.uid(z)] for z in b.Zones() if audit.uid(z) in baseline_zones)
assert {audit.uid(t):audit.copper(t) for t in b.GetTracks()}==baseline_copper
p.SaveBoard(str(output),b)
assert audit.blocks(raw,'footprint')==audit.blocks(output.read_bytes(),'footprint')
shutil.copyfile(source.with_suffix('.kicad_pro'),output.with_suffix('.kicad_pro'))
shutil.copyfile(ROOT/'physical-fix-stage/fp-lib-table',DEST/'fp-lib-table')
for name in ('footprints.pretty','libraries'):
    path=DEST/name
    if not path.exists():path.symlink_to((ROOT/'physical-fix-stage'/name).resolve(),target_is_directory=True)
cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
run=subprocess.run([cli,'pcb','drc','--format','json','--all-track-errors','--refill-zones',
    '--output',str(DEST/'native-drc.json'),str(output)],capture_output=True,text=True,timeout=60)
(DEST/'native-drc.log').write_text(run.stdout+run.stderr)
assert run.returncode==0,(run.stdout,run.stderr)
drc=json.loads((DEST/'native-drc.json').read_text())
result=dict(source=str(source),sourceSha256=hashlib.sha256(raw).hexdigest(),
    candidate=str(output),candidateSha256=hashlib.sha256(output.read_bytes()).hexdigest(),
    sourceBytesAndMtimeUnchanged=source.read_bytes()==raw and source.stat().st_mtime_ns==mtime,
    all263FootprintBlocksUnchanged=True,allExistingCopperUnchanged=True,allOriginalZonesUnchanged=True,
    addedZoneUuids=new_ids,RFAdditionalFrontPourClearanceMm=.8,
    outerPourClearanceMm=.2,thermalGapMm=.2,thermalSpokeWidthMm=.25,
    SmdPadConnection='solid' if args.solid_smd else 'thermal',ThroughHolePadConnection='thermal',
    before=before,after=after,nativeDrc=dict(errors=sum(v['severity']=='error' for v in drc['violations']),
        warnings=sum(v['severity']=='warning' for v in drc['violations']),
        violations=drc['violations'],reportedUnconnected=len(drc['unconnected_items'])))
(DEST/'ground-pour-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('before','after','nativeDrc')},indent=2))
print(json.dumps({'beforeAirwires':before['fullNativeAirwires'],'afterAirwires':after['fullNativeAirwires'],
    'beforeGroundGroups':before['ground']['connectedGroupCount'],'afterGroundGroups':after['ground']['connectedGroupCount'],
    'afterGroundIsolatedPads':after['ground']['isolatedFromMainGroup'],
    'nativeDrc':{k:v for k,v in result['nativeDrc'].items() if k!='violations'}},indent=2))

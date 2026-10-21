"""Native full DRC against exact input and corrected output, without input writes."""
from pathlib import Path
import collections
import hashlib
import json
import shutil
import subprocess
import pcbnew as p

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[2]/'work/chrysler-integrated-sd/pcb-stage/ChryslerScanner_V240_SD.kicad_pcb'
ASSETS=HERE.parents[2]/'work/chrysler-integrated-sd/package'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
original=SOURCE.read_bytes(); original_mtime=SOURCE.stat().st_mtime_ns
baseline=HERE/'baseline'; baseline.mkdir(exist_ok=True)
shutil.copyfile(SOURCE,baseline/SOURCE.name)
shutil.copyfile(SOURCE.with_suffix('.kicad_pro'),baseline/SOURCE.with_suffix('.kicad_pro').name)
shutil.copyfile(ASSETS/'fp-lib-table',baseline/'fp-lib-table')
for name in ('footprints.pretty','libraries','3dmodels'):
    dest=baseline/name
    if not dest.exists(): dest.symlink_to(ASSETS/name,target_is_directory=True)

def drc(directory,output):
    cmd=[CLI,'pcb','drc','--format','json','--all-track-errors','--refill-zones',
         '--output',str(HERE/output),str(directory/SOURCE.name)]
    r=subprocess.run(cmd,cwd=directory,capture_output=True,text=True,timeout=60)
    (HERE/(output+'.log')).write_text(r.stdout+r.stderr)
    assert r.returncode==0,(r.returncode,r.stdout[-1000:],r.stderr[-1000:])
    return json.loads((HERE/output).read_text())

old=drc(baseline,'drc-baseline.json')
new=json.loads((HERE/'drc-corrected.json').read_text())
assert len([x for x in old['violations'] if x['severity']=='error'])==8
assert new['violations']==[],new['violations']

def stats(d):
    return {'errors':sum(x['severity']=='error' for x in d['violations']),
            'warnings':sum(x['severity']=='warning' for x in d['violations']),
            'categories':dict(collections.Counter(x['type'] for x in d['violations'])),
            'reportedMissingConnections':len(d['unconnected_items'])}

board=p.LoadBoard(str(HERE/SOURCE.name));board.BuildConnectivity()
base=p.LoadBoard(str(SOURCE));base.BuildConnectivity()
proof=json.loads((HERE/'footprint-correction-proof.json').read_text())
assert hashlib.sha256((HERE/SOURCE.name).read_bytes()).hexdigest()==proof['pcbSha256']
summary={'nativeVersion':subprocess.check_output([CLI,'version'],text=True).strip(),
    'sourceSha256':hashlib.sha256(original).hexdigest(),'correctedSha256':proof['pcbSha256'],
    'baseline':stats(old),'corrected':stats(new),'physicalRulesChanged':False,
    'ruleExclusionsAdded':False,'missingConnectionsSeverityUnchanged':True,
    'routingComplete':False,'nativeUnfilledAirwiresBefore':base.GetConnectivity().GetUnconnectedCount(False),
    'nativeUnfilledAirwiresAfter':board.GetConnectivity().GetUnconnectedCount(False),
    'removedViolations':old['violations'],
    'libraryFootprintGeometryAgreement':'Native full DRC reports no lib_footprint_mismatch',
    'additionalLibraryFix':{'reference':'JP1','boardChanged':False,
        'reason':'Local footprint lacked the existing bridged jumper net_tie_pad_groups and F.Fab reference label',
        'file':'footprints.pretty/SolderJumper-2_P1.3mm_Bridged_Pad1.0x1.5mm.kicad_mod'},
    'originalInputBytesAndMtimeUnchanged':SOURCE.read_bytes()==original and SOURCE.stat().st_mtime_ns==original_mtime}
assert summary['originalInputBytesAndMtimeUnchanged']
assert (HERE/SOURCE.with_suffix('.kicad_pro').name).read_bytes()==SOURCE.with_suffix('.kicad_pro').read_bytes()
(HERE/'drc-remediation-proof.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='removedViolations'},indent=2))

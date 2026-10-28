"""Full layered release gate: frozen prior release plus actual refinement CAD."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,tempfile
HERE=Path(__file__).resolve().parent
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=Path,default=HERE.parent);ap.add_argument('--report',type=Path);args=ap.parse_args();D=args.candidate.resolve();R=D/'reference';F=R/'pre-refinement';N='ChryslerScanner_V240_SD'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def run(*cmd):
    r=subprocess.run([str(v) for v in cmd],capture_output=True,text=True,encoding='utf-8',errors='replace')
    if r.returncode:print(r.stdout[-6000:]);print(r.stderr[-3000:]);raise RuntimeError('Verification failed: '+str(cmd[1]))
    return r
manifest=json.loads((R/'rev-c-refinement-baseline.json').read_text())
assert all(sha(F/name)==value for name,value in manifest.items()),'Frozen prior release changed'
start_hash=sha(D/(N+'.kicad_pcb'));cli=Path(sys.executable).with_name('kicad-cli.exe')
with tempfile.TemporaryDirectory(prefix='chrysler-prior-release-audit-') as folder:
    T=Path(folder)/'checkpoint';shutil.copytree(F,T,ignore=shutil.ignore_patterns('__pycache__'))
    run(cli,'sch','export','netlist','--format','kicadxml','--output',T/'reference/final-netlist.xml',T/(N+'.kicad_sch'))
    run(cli,'sch','erc','--severity-all','--format','json','--output',T/'reference/final-erc.json',T/(N+'.kicad_sch'))
    run(cli,'pcb','drc','--all-track-errors','--schematic-parity','--severity-all','--refill-zones','--format','json','--output',T/'reference/final-drc.json',T/(N+'.kicad_pcb'))
    run(sys.executable,T/'source/verify_safety_revision.py','--candidate',T)
    historical=json.loads((T/'reference/p1-contract-audit.json').read_text())
    assert historical['status']=='PASS' and historical['releaseGatePassed'] and historical['pcbSha256']=='83ac625f2283aa789455802fa4367dbc786c7a2f0ae6c87ffc91c8959a40ac15'
    (R/'rev-c-refinement-historical-audit.json').write_text(json.dumps(historical,indent=2)+'\n')
# The actual delta audit requires clean all-severity reports exported after
# the current CAD, plus exact CAD/review hashes and uncapped connectivity.
# Do not rewrite those hash-bound reports during portable package validation.
run(sys.executable,D/'source/verify_refinement_delta.py','--candidate',D)
delta=json.loads((R/'rev-c-refinement-delta-audit.json').read_text());assert delta['status']=='PASS' and delta['releaseGatePassed'] and delta['pcbSha256']==start_hash
assert sha(D/(N+'.kicad_pcb'))==start_hash,'Audit changed current PCB'
report=dict(status='PASS',releaseGatePassed=True,phase='full_prior_release_and_drive_lands_mounting_delta_gate',pcbSha256=start_hash,netlistSha256=sha(R/'final-netlist.xml'),historicalCheckpointPcbSha256=historical['pcbSha256'],checks={**{'prior:'+k:v for k,v in historical['checks'].items()},**{'refinement:'+k:v for k,v in delta['checks'].items()}},errors=[],connectivity=delta['connectivity'],historicalAudit='rev-c-refinement-historical-audit.json',refinementAudit='rev-c-refinement-delta-audit.json',limitations='Native consistency and preservation pass; prototype bench/firmware/vehicle qualification remains separate.')
out=args.report or R/'p1-contract-audit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status='PASS',releaseGatePassed=True,checks=len(report['checks']),pcbSha256=start_hash,report=str(out)),indent=2))

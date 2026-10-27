"""Layered release audit: frozen safety checkpoint plus exact procurement delta.

The unchanged historical verifier is exercised against the hash-frozen CCD
checkpoint in a temporary project. The actual current CAD then undergoes the
procurement-delta, native connectivity and fresh-report checks. A historical
pass alone or a draft BOM cannot produce a release pass.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,tempfile
HERE=Path(__file__).resolve().parent
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=Path,default=HERE.parent);ap.add_argument('--report',type=Path);args=ap.parse_args();D=args.candidate.resolve();R=D/'reference';N='ChryslerScanner_V240_SD'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def run(*cmd):
    r=subprocess.run([str(v) for v in cmd],capture_output=True,text=True,encoding='utf-8',errors='replace')
    if r.returncode:print(r.stdout[-6000:]);print(r.stderr[-3000:]);raise RuntimeError('Verification failed: '+str(cmd[1]))
    return r
manifest=json.loads((R/'rev-c-procurement-baseline.json').read_text())
assert all(sha(R/'pre-procurement'/name)==v for name,v in manifest['files'].items()),'Frozen CCD checkpoint changed'
assert sha(D/'source/verify_pre_procurement_revision.py')==manifest['historicalVerifierSha256'],'Historical safety verifier changed'
start_hash=sha(D/(N+'.kicad_pcb'));cli=Path(sys.executable).with_name('kicad-cli.exe')
with tempfile.TemporaryDirectory(prefix='chrysler-historical-audit-') as folder:
    T=Path(folder)/'checkpoint'
    shutil.copytree(D,T,ignore=shutil.ignore_patterns('3dmodels','fabrication','previews','parts','pre-procurement','*-backups','*.pdf','*.lck','*.kicad_prl','__pycache__'))
    for name in manifest['files']:
        dest=T/'reference/final-netlist.xml' if name=='final-netlist.xml' else T/name
        shutil.copy2(R/'pre-procurement'/name,dest)
    run(cli,'sch','export','netlist','--format','kicadxml','--output',T/'reference/final-netlist.xml',T/(N+'.kicad_sch'))
    run(cli,'sch','erc','--severity-all','--format','json','--output',T/'reference/final-erc.json',T/(N+'.kicad_sch'))
    run(cli,'pcb','drc','--all-track-errors','--schematic-parity','--severity-all','--refill-zones','--format','json','--output',T/'reference/final-drc.json',T/(N+'.kicad_pcb'))
    run(sys.executable,T/'source/verify_pre_procurement_revision.py','--candidate',T)
    historical=json.loads((T/'reference/p1-contract-audit.json').read_text());assert historical['status']=='PASS' and historical['releaseGatePassed']
    assert historical['pcbSha256']==manifest['files'][N+'.kicad_pcb']
    (R/'rev-c-procurement-historical-audit.json').write_text(json.dumps(historical,indent=2)+'\n')
run(sys.executable,D/'source/verify_procurement_delta.py','--candidate',D)
delta=json.loads((R/'rev-c-procurement-delta-audit.json').read_text())
assert delta['status']=='PASS' and delta['releaseGatePassed'] and delta['pcbSha256']==start_hash
assert sha(D/(N+'.kicad_pcb'))==start_hash,'Audit changed current PCB'
report=dict(status='PASS',releaseGatePassed=True,phase='full_historical_safety_and_procurement_delta_gate',pcbSha256=start_hash,netlistSha256=sha(R/'final-netlist.xml'),historicalCheckpointPcbSha256=historical['pcbSha256'],checks={**{'historical:'+k:v for k,v in historical['checks'].items()},**{'procurement:'+k:v for k,v in delta['checks'].items()}},errors=[],connectivity=delta['connectivity'],historicalAudit='rev-c-procurement-historical-audit.json',procurementAudit='rev-c-procurement-delta-audit.json',limitations='Native consistency and preservation pass; prototype bench/firmware/vehicle qualification remains separate.')
out=args.report or R/'p1-contract-audit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status='PASS',releaseGatePassed=True,checks=len(report['checks']),pcbSha256=start_hash,report=str(out)),indent=2))

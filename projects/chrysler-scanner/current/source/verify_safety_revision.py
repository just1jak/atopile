"""Full layered gate: unchanged prior 130 checks plus the sealed C14 delta."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,tempfile,zipfile,os
HERE=Path(__file__).resolve().parent
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=Path,default=HERE.parent);ap.add_argument('--report',type=Path);args=ap.parse_args();D=args.candidate.resolve();R=D/'reference';N='ChryslerScanner_V240_SD'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
BASELINE_ZIP_SHA='ce33b72befa5c5858b4f93caa0a46077b8ec3fc31ad68e78208b744982403282'
scratch=Path(os.environ.get('CHRYSLER_AUDIT_TEMP',str(Path.cwd()/'.chrysler-audit-tmp'))).resolve();scratch.mkdir(exist_ok=True)
audit_env={**os.environ,'TEMP':str(scratch),'TMP':str(scratch)}
def run(*cmd):
 r=subprocess.run([str(v) for v in cmd],capture_output=True,text=True,encoding='utf-8',errors='replace',env=audit_env)
 if r.returncode:print(r.stdout[-6000:]);print(r.stderr[-3000:]);raise RuntimeError('Verification failed: '+str(cmd[1]))
 return r
archive=R/'rev-c-c14-baseline.zip';assert sha(archive)==BASELINE_ZIP_SHA,'Frozen prior release changed'
start=sha(D/(N+'.kicad_pcb'));cli=Path(sys.executable).with_name('kicad-cli.exe')
with tempfile.TemporaryDirectory(prefix='c14-',dir=scratch) as folder:
 F=Path(folder)/'checkpoint';F.mkdir()
 with zipfile.ZipFile(archive) as z:
  assert all(not Path(x).is_absolute() and '..' not in Path(x).parts for x in z.namelist())
  z.extractall(F)
 run(cli,'sch','export','netlist','--format','kicadxml','--output',F/'reference/final-netlist.xml',F/(N+'.kicad_sch'))
 run(cli,'sch','erc','--severity-all','--format','json','--output',F/'reference/final-erc.json',F/(N+'.kicad_sch'))
 run(cli,'pcb','drc','--all-track-errors','--schematic-parity','--severity-all','--refill-zones','--format','json','--output',F/'reference/final-drc.json',F/(N+'.kicad_pcb'))
 run(sys.executable,F/'source/verify_safety_revision.py','--candidate',F)
 historical=json.loads((F/'reference/p1-contract-audit.json').read_text());assert historical['status']=='PASS' and historical['releaseGatePassed'] and historical['pcbSha256']=='800c05930a0ca24fe280d5f3aace70974889129942a1b5602ce2eabfea026301'
 (R/'rev-c-c14-historical-audit.json').write_text(json.dumps(historical,indent=2)+'\n')
 run(sys.executable,D/'source/verify_c14_delta.py','--candidate',D,'--baseline',F)
delta=json.loads((R/'rev-c-c14-delta-audit.json').read_text());assert delta['status']=='PASS' and delta['releaseGatePassed'] and delta['pcbSha256']==start
assert sha(D/(N+'.kicad_pcb'))==start,'Audit changed current PCB'
report=dict(status='PASS',releaseGatePassed=True,phase='full_prior_130_checks_and_c14_delta_gate',pcbSha256=start,netlistSha256=sha(R/'final-netlist.xml'),historicalCheckpointPcbSha256=historical['pcbSha256'],checks={**{'prior:'+k:v for k,v in historical['checks'].items()},**{'c14:'+k:v for k,v in delta['checks'].items()}},errors=[],connectivity=delta['connectivity'],historicalAudit='rev-c-c14-historical-audit.json',c14Audit='rev-c-c14-delta-audit.json',limitations='Native consistency and preservation pass; prototype bench/firmware/vehicle qualification remains separate.')
out=args.report or R/'p1-contract-audit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status='PASS',releaseGatePassed=True,checks=len(report['checks']),pcbSha256=start,report=str(out)),indent=2))


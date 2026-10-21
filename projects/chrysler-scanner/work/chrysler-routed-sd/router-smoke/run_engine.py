from pathlib import Path
import json,subprocess,time
HERE=Path(__file__).resolve().parent
TOOLS=HERE.parent/'router-tools'
cmd=['/usr/bin/sandbox-exec','-f',str(TOOLS/'offline.sb'),
     '/opt/homebrew/opt/openjdk@17/bin/java','-jar',str(TOOLS/'freerouting-1.9.0.jar'),
     '-da','-dl','-de',str(HERE/'tiny.dsn'),'-do',str(HERE/'tiny.ses'),
     '-mp','2','-mt','1','-dct','0']
t=time.monotonic();process=subprocess.Popen(cmd,cwd=HERE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
timed_out=False
try:
    out,err=process.communicate(timeout=60)
except subprocess.TimeoutExpired:
    timed_out=True;process.terminate()
    try:out,err=process.communicate(timeout=5)
    except subprocess.TimeoutExpired:process.kill();out,err=process.communicate(timeout=5)
(HERE/'engine.stdout.log').write_text(out)
(HERE/'engine.stderr.log').write_text(err)
report={'command':cmd,'elapsedSeconds':round(time.monotonic()-t,3),'returnCode':process.returncode,
        'timeout':timed_out,'sesCreated':(HERE/'tiny.ses').exists(),'networkDenied':True,
        'stdoutBytes':len(out.encode()),'stderrBytes':len(err.encode())}
(HERE/'engine-run.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
print('STDOUT tail:',out[-3000:]);print('STDERR tail:',err[-3000:])
assert not timed_out and process.returncode==0 and report['sesCreated']

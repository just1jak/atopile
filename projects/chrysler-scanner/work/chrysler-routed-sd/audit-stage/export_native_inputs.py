"""Refresh native schematic evidence without changing the design."""
from pathlib import Path
import hashlib,json,subprocess,time
HERE=Path(__file__).resolve().parent
DESIGN=HERE.parent/'design'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
NAME='ChryslerScanner_V240_SD'
def digest(path):
    b=path.read_bytes();return {'sha256':hashlib.sha256(b).hexdigest(),'size':len(b),'mtime_ns':path.stat().st_mtime_ns}
inputs=list(DESIGN.glob('*.kicad_sch'))+list(DESIGN.glob('*.kicad_sym'))+[DESIGN/(NAME+'.kicad_pro'),DESIGN/'sym-lib-table']
before={str(p.relative_to(DESIGN)):digest(p) for p in inputs}
commands=[['sch','export','netlist','--format','kicadxml','--output',str(HERE/(NAME+'.xml')),str(DESIGN/(NAME+'.kicad_sch'))],
          ['sch','erc','--format','json','--output',str(HERE/'erc-native.json'),str(DESIGN/(NAME+'.kicad_sch'))]]
runs=[]
for i,args in enumerate(commands):
    start=time.monotonic();r=subprocess.run([CLI,*args],cwd=DESIGN,capture_output=True,text=True,timeout=60)
    (HERE/('native-export.log' if i==0 else 'native-erc.log')).write_text(r.stdout+r.stderr)
    runs.append({'command':[CLI,*args],'seconds':round(time.monotonic()-start,3),'returnCode':r.returncode})
    assert r.returncode==0,(r.returncode,r.stderr[-1500:],r.stdout[-1500:])
after={str(p.relative_to(DESIGN)):digest(p) for p in inputs}
assert before==after,'Native read/export changed a design input'
report={'design':str(DESIGN),'nativeVersion':subprocess.check_output([CLI,'version'],text=True).strip(),
        'schematicPages':len(list(DESIGN.glob('*.kicad_sch'))),'allDesignInputBytesAndMtimesUnchanged':True,
        'inputs':before,'runs':runs}
(HERE/'native-input-integrity.json').write_text(json.dumps(report,indent=2)+'\n')
erc=json.loads((HERE/'erc-native.json').read_text())
print('Native exports completed; pages',report['schematicPages'],'inputfiles',len(inputs),'runs',runs)
print('ERC top-level keys',list(erc))

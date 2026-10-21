from pathlib import Path
import json,subprocess,tempfile,shutil,collections,hashlib
HERE=Path(__file__).resolve().parent;ORIG=Path('/Users/justinkobely/Downloads/ChryslerCCDSCIScanner_V140/elec/layout/v240/v240.kicad_pcb');CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
raw=ORIG.read_bytes();mtime=ORIG.stat().st_mtime_ns
with tempfile.TemporaryDirectory(prefix='baseline-',dir=HERE) as td:
 t=Path(td);shutil.copyfile(ORIG,t/ORIG.name);shutil.copyfile(ORIG.with_suffix('.kicad_pro'),t/'v240.kicad_pro');(t/'fp-lib-table').write_text((ORIG.parent/'fp-lib-table').read_text().replace('${KIPRJMOD}',str(ORIG.parent)))
 r=subprocess.run([CLI,'pcb','drc','--format','json','--all-track-errors','--refill-zones','--output',str(HERE/'drc-baseline.json'),str(t/ORIG.name)],cwd=t,capture_output=True,text=True,timeout=60);(HERE/'drc-baseline.log').write_text(r.stdout+r.stderr);assert r.returncode==0
r=subprocess.run([CLI,'pcb','drc','--format','json','--all-track-errors','--refill-zones','--output','drc-final.json','ChryslerScanner_V240_SD.kicad_pcb'],cwd=HERE,capture_output=True,text=True,timeout=60);(HERE/'drc-final.log').write_text(r.stdout+r.stderr);assert r.returncode==0
base=json.loads((HERE/'drc-baseline.json').read_text());final=json.loads((HERE/'drc-final.json').read_text())
def key(x):return (x['type'],x['severity'],tuple(sorted(i.get('uuid','') for i in x.get('items',[]))))
old={key(x):x for x in base['violations']};new={key(x):x for x in final['violations']};introduced=[v for k,v in new.items() if k not in old];removed=[v for k,v in old.items() if k not in new]
summary={'baseline':{'violations':len(base['violations']),'unconnected':len(base['unconnected_items']),'categories':dict(collections.Counter(x['type'] for x in base['violations']))},'final':{'violations':len(final['violations']),'unconnected':len(final['unconnected_items']),'categories':dict(collections.Counter(x['type'] for x in final['violations']))},'introducedViolations':introduced,'removedViolations':removed,'newPhysicalErrors':[x for x in introduced if x['severity']=='error'],'routingComplete':False,'manifestWiringOnly':True,'originalPcbUnchanged':ORIG.read_bytes()==raw and ORIG.stat().st_mtime_ns==mtime}
preservation=json.loads((HERE/'pcb-preservation.json').read_text())
summary['nativeAirwireCounts']={'baseline':preservation['baseNativeAirwireCount'],'final':preservation['finalNativeAirwireCount'],'added':preservation['additionalAirwires'],'measurement':'Native connectivity before zone refill'}
summary['cliMissingItemReportingNote']='CLI JSON contains499 missing items; full native API counts are recorded separately'
(HERE/'drc-comparison.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

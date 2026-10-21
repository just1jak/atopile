from pathlib import Path
import hashlib,json,subprocess
import pcbnew as p
HERE=Path(__file__).resolve().parent
source=HERE/'tiny-unrouted.kicad_pcb';raw=source.read_bytes()
b=p.LoadBoard(str(source));old={f.GetReference():[(q.GetNumber(),q.GetNetname(),q.m_Uuid.AsString()) for q in f.Pads()] for f in b.GetFootprints()}
assert p.ImportSpecctraSES(b,str(HERE/'tiny.ses'))
assert list(b.GetTracks()),'SES imported no routed copper'
b.BuildConnectivity();assert b.GetConnectivity().GetUnconnectedCount(False)==0
assert old=={f.GetReference():[(q.GetNumber(),q.GetNetname(),q.m_Uuid.AsString()) for q in f.Pads()] for f in b.GetFootprints()}
p.SaveBoard(str(HERE/'tiny-routed.kicad_pcb'),b)
cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
r=subprocess.run([cli,'pcb','drc','--format','json','--all-track-errors','--output',str(HERE/'drc-routed.json'),str(HERE/'tiny-routed.kicad_pcb')],capture_output=True,text=True,timeout=30)
(HERE/'drc-routed.log').write_text(r.stdout+r.stderr);assert r.returncode==0
d=json.loads((HERE/'drc-routed.json').read_text());assert d['unconnected_items']==[],d['unconnected_items']
assert d['violations']==[],d['violations']
assert source.read_bytes()==raw
report={'engine':'Freerouting1.9.0/Java17','nativeDSNExport':True,'nativeSESImport':True,
        'pads':2,'nets':1,'airwiresBefore':1,'airwiresAfter':0,'tracksOrVias':len(list(b.GetTracks())),
        'allPhysicalDRCErrorsAndWarnings':0,'missingConnections':0,'inputCopyUnchanged':True,
        'dsnSha256':hashlib.sha256((HERE/'tiny.dsn').read_bytes()).hexdigest(),
        'sesSha256':hashlib.sha256((HERE/'tiny.ses').read_bytes()).hexdigest(),
        'routedPcbSha256':hashlib.sha256((HERE/'tiny-routed.kicad_pcb').read_bytes()).hexdigest()}
(HERE/'smoke-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

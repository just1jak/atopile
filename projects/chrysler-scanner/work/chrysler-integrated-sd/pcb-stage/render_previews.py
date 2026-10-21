from pathlib import Path
import subprocess,json,hashlib
HERE=Path(__file__).resolve().parent;CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli';PCB='ChryslerScanner_V240_SD.kicad_pcb'
raw=(HERE/PCB).read_bytes()
for side,layers in [('front','F.Cu,F.SilkS,Edge.Cuts'),('back','B.Cu,B.SilkS,Edge.Cuts')]:
 args=[CLI,'pcb','export','pdf','--mode-single','--output','board-'+side+'.pdf','--layers',layers,'--scale','1',PCB]
 if side=='back':args.insert(-1,'--mirror')
 r=subprocess.run(args,cwd=HERE,capture_output=True,text=True,timeout=60);(HERE/('preview-'+side+'-2d.log')).write_text(r.stdout+r.stderr);assert not r.returncode
 r=subprocess.run([CLI,'pcb','render','--output','board-'+side+'-3d.png','--width','1200','--height','800','--side','top' if side=='front' else 'bottom','--rotate','315,0,20','--background','opaque','--use-board-stackup-colors',PCB],cwd=HERE,capture_output=True,text=True,timeout=60);(HERE/('preview-'+side+'-3d.log')).write_text(r.stdout+r.stderr);assert not r.returncode
 print(side,'previews complete',flush=True)
assert (HERE/PCB).read_bytes()==raw

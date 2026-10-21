"""Convert vendored KiCad5 footprints to modern syntax, preserving geometry."""
from pathlib import Path
import sexpdata as sx
import math
from faebryk.libs.kicad.fileformats import kicad
ROOT=Path(__file__).resolve().parents[1]
def name(v):return str(v[0]) if isinstance(v,list) and v else ''
for path in (ROOT/'elec/src/footprints').glob('*.kicad_mod'):
 a=sx.loads(path.read_text())
 if name(a)=='module':
  backup=ROOT/'reference/kicad-original-footprints'/path.name;backup.parent.mkdir(exist_ok=True)
  if not backup.exists():backup.write_text(path.read_text())
  a[0]=sx.Symbol('footprint');a[1]=str(a[1]);a[:]=[v for v in a if name(v) not in ['tedit','model']]
  a.insert(2,[sx.Symbol('version'),20240108]);a.insert(3,[sx.Symbol('generator'),'pcbnew'])
  def modern(e):
   if not isinstance(e,list):return
   if name(e) in ['layer','layers']:e[1:]=[str(q) for q in e[1:]]
   if name(e).startswith('fp_'):
    w=next((q for q in e if name(q)=='width'),None)
    if w:e.remove(w);e.append([sx.Symbol('stroke'),w,[sx.Symbol('type'),sx.Symbol('default')]])
   if name(e)=='fp_text':e[2]=str(e[2])
   if name(e)=='pad':e[1]=str(e[1])
   for q in e:modern(q)
  modern(a);path.write_text(sx.dumps(a)+'\n')
 for e in a:
  if name(e)=='fp_arc':
   ang=next((q for q in e if name(q)=='angle'),None)
   if ang:
    st=next(q for q in e if name(q)=='start');en=next(q for q in e if name(q)=='end')
    cx,cy=st[1:3];x,y=en[1:3];dx=x-cx;dy=y-cy;t=math.radians(ang[1])
    st[1:3]=[x,y];en[1:3]=[cx+dx*math.cos(t)-dy*math.sin(t),cy+dx*math.sin(t)+dy*math.cos(t)]
    e.remove(ang);e.append([sx.Symbol('mid'),cx+dx*math.cos(t/2)-dy*math.sin(t/2),cy+dx*math.sin(t/2)+dy*math.cos(t/2)])
  if name(e)=='attr' and sx.Symbol('virtual') in e:
   e.remove(sx.Symbol('virtual'));e.extend([sx.Symbol('smd'),sx.Symbol('exclude_from_bom'),sx.Symbol('exclude_from_pos_files')])
 path.write_text(sx.dumps(a)+'\n')
 try:kicad.loads(kicad.footprint.FootprintFile,path)
 except Exception as ex:raise RuntimeError(f'{path.name}: {ex}') from ex
print('All footprints parse with the atopile KiCad reader')

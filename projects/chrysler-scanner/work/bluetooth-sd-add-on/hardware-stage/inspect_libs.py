from pathlib import Path
import sexpdata as s
k=lambda n:str(n[0]) if isinstance(n,list) and n else ''
p=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols')
for fn,name in [('Connector','Micro_SD_Card_Det2'),('Device','R'),('Device','C'),('Device','LED'),('Switch','SW_Push'),('power','PWR_FLAG')]:
 a=s.loads((p/(fn+'.kicad_sym')).read_text()); n=next(n for n in a if k(n)=='symbol' and n[1]==name)
 print(fn,name)
 for u in n:
  if k(u)=='symbol':
   print([(next((v[1] for v in t if k(v)=='number'),''),next((v[1] for v in t if k(v)=='name'),''),next((v[1:] for v in t if k(v)=='at'),''),str(t[1])) for t in u if k(t)=='pin'])

"""Read-only exact native clearance analysis of alternate local pin paths."""
from pathlib import Path
import argparse,json,math
import pcbnew as p
ap=argparse.ArgumentParser();ap.add_argument('board',type=Path);ap.add_argument('hints',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
b=p.LoadBoard(str(a.board.resolve()));layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)
mm=lambda x:round(x*1e6);vec=lambda q:p.VECTOR2I(mm(q[0]),mm(q[1]))
hit=lambda x,y,c:p.SHAPE.Collide(x,y,c)
items=[]
for f in b.GetFootprints():
 for q in f.Pads():
  for l in layers:
   if q.IsOnLayer(l):items.append((f.GetReference()+'.'+q.GetNumber(),q.GetNetname(),l,q.GetEffectiveShape(l),None))
for t in b.GetTracks():
 for l in layers:
  if t.IsOnLayer(l):
   detail={'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'kind':t.GetClass(),'layer':l,'locked':t.IsLocked(),
    'startMm':[t.GetStart().x/1e6,t.GetStart().y/1e6],'endMm':[t.GetEnd().x/1e6,t.GetEnd().y/1e6],
    'widthMm':t.GetWidth(l)/1e6 if isinstance(t,p.PCB_VIA) else t.GetWidth()/1e6}
   items.append((t.m_Uuid.AsString(),t.GetNetname(),l,t.GetEffectiveShape(l),detail))
out=[]
for h in json.loads(a.hints.read_text())['hints']:
 if h['reference']+'.'+h['pin'] not in ('U19.16','U10.15'):continue
 blockers={};stages=[]
 for trace in h['items']:
  if trace['kind']=='trace':
   for start,end in zip(trace['pointsMm'],trace['pointsMm'][1:]):
    sh=p.SHAPE_SEGMENT(vec(start),vec(end),mm(.15));found=[]
    for key,net,l,other,detail in items:
     if net==h['net'] or l!=p.F_Cu:continue
     if hit(sh,other,mm(.1505)):
      blockers[key]=detail or {'pad':key,'net':net,'layer':l};found.append(key)
    stages.append({'startMm':start,'endMm':end,'blockingIds':found})
  elif trace['kind']=='via':
   sh=p.SHAPE_CIRCLE(vec(trace['positionMm']),mm(.3));found=[]
   for key,net,l,other,detail in items:
    if net!=h['net'] and hit(sh,other,mm(.1505)):
     blockers[key]=detail or {'pad':key,'net':net,'layer':l};found.append(key)
   stages.append({'viaMm':trace['positionMm'],'blockingIds':sorted(set(found))})
 out.append({'pin':h['reference']+'.'+h['pin'],'net':h['net'],'stages':stages,'blockingCopper':list(blockers.values())})
a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

from pathlib import Path
import pcbnew as p,json,math
H=Path(__file__).resolve().parent;b=p.LoadBoard(str(H/'input/ChryslerScanner_V240_SD.kicad_pcb'))
mm=lambda x:round(x*1e6);layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)
items=list(b.GetTracks())+[q for f in b.GetFootprints() for q in f.Pads()]
labels={q.m_Uuid.AsString():f.GetReference()+'.'+q.GetNumber() for f in b.GetFootprints() for q in f.Pads()}
def desc(t):
 q=t.GetPosition();return {'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'item':labels.get(t.m_Uuid.AsString(),t.GetClass()),'positionMm':[p.ToMM(q.x),p.ToMM(q.y)],'locked':t.IsLocked()}
result=[]
for net,xy in [('TX_LED',[171.9375,119.3475])]:
 point=p.VECTOR2I(mm(xy[0]),mm(xy[1]));circle=p.SHAPE_CIRCLE(point,mm(.3));hole=p.SHAPE_CIRCLE(point,mm(.15));bad={}
 for t in items:
  reasons=[]
  if t.GetNetname()!=net:
   for layer in layers:
    if t.IsOnLayer(layer) and p.SHAPE.Collide(circle,t.GetEffectiveShape(layer),mm(.1501)):reasons.append(p.LayerName(layer))
  has_hole=t.GetClass()=='PCB_VIA' or t.GetClass()=='PAD' and t.HasDrilledHole()
  if has_hole and p.SHAPE.Collide(hole,t.GetEffectiveHoleShape(),mm(.2501)):reasons.append('drill clearance')
  if reasons:bad[t.m_Uuid.AsString()]={**desc(t),'conflicts':reasons}
 result.append({'net':net,'positionMm':xy,'blockers':list(bad.values())})
(H/'direct-txled-blockers.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

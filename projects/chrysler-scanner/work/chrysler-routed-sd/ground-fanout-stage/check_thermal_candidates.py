"""Read-only geometric probe for U10 exposed-pad ground-via locations.

No PCB is saved. Candidates are not routes or approved manufacturing details.
Uses native KiCad effective shapes across every copper layer and drill.
"""
from pathlib import Path
import json
import pcbnew as p
HERE=Path(__file__).resolve().parent
b=p.LoadBoard(str(HERE.parent/'route-pass-3/seed.kicad_pcb'))
point=lambda x,y:p.VECTOR2I(round(x*1e6),round(y*1e6))
target=next(q for f in b.GetFootprints() for q in f.Pads() if f.GetReference()=='U10' and q.GetNumber()=='49')
cx,cy=p.ToMM(target.GetPosition().x),p.ToMM(target.GetPosition().y)
layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu)
obstacles=[];holes=[]
for f in b.GetFootprints():
    for q in f.Pads():
        if q.HasDrilledHole():holes.append((f.GetReference()+'.'+q.GetNumber(),q.GetEffectiveHoleShape()))
        if q.GetNetname()!='GND':
            for layer in layers:
                if q.IsOnLayer(layer):obstacles.append((f.GetReference()+'.'+q.GetNumber(),layer,q.GetEffectiveShape(layer)))
for t in b.GetTracks():
    if t.GetClass()=='PCB_VIA':holes.append((t.m_Uuid.AsString(),t.GetEffectiveHoleShape()))
    if t.GetNetname()!='GND':
        for layer in layers:
            if t.IsOnLayer(layer):obstacles.append((t.m_Uuid.AsString(),layer,t.GetEffectiveShape(layer)))
results=[]
for dx,dy in [(0,0),(-.9,-.9),(.9,-.9),(-.9,.9),(.9,.9),(-1.2,0),(1.2,0),(0,-1.2),(0,1.2)]:
    position=point(cx+dx,cy+dy);circle=p.SHAPE_CIRCLE(position,300000)
    conflicts=[name for name,layer,shape in obstacles if p.SHAPE.Collide(circle,shape,170000)]
    conflicts += [name+':hole' for name,shape in holes if p.SHAPE.Collide(circle,shape,220000)]
    for z in b.Zones():
        if z.GetIsRuleArea() and z.GetDoNotAllowVias() and z.Outline().Contains(position):
            conflicts.append('via keepout:'+z.m_Uuid.AsString())
    results.append({'xyMM':[cx+dx,cy+dy],'nativeClearanceProbePassed':not conflicts,'conflicts':sorted(set(conflicts))})
report={'status':'read-only candidate probe; not applied','reference':'U10.49',
        'viaDiameterMM':.6,'drillMM':.3,'extraClearanceMarginMM':.02,
        'manufacturingCondition':'Via-in-pad requires explicit filled/capped fabrication treatment and assembly approval; ordinary tenting is not equivalent',
        'candidates':results}
(HERE/'U10-thermal-via-candidates.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

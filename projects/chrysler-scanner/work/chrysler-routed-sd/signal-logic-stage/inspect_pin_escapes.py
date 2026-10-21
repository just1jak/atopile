from pathlib import Path
import json, math
import pcbnew as p

root=Path(__file__).resolve().parent.parent
targets={'U10':['16','11','6','33'],'U19':['15']}
out={}
for case in ('native5-stitched','alternate4-native'):
    path=(root/'signal-logic-stage'/case/'ChryslerScanner_V240_SD.kicad_pcb' if case.startswith('native') else root/case/'ChryslerScanner_V240_SD.kicad_pcb')
    b=p.LoadBoard(str(path.resolve()));out[case]={}
    for fp in b.GetFootprints():
        for q in fp.Pads():
            if q.GetNumber() not in targets.get(fp.GetReference(),[]):continue
            pos=q.GetPosition();key=fp.GetReference()+'.'+q.GetNumber()
            data={'net':q.GetNetname(),'positionMm':[p.ToMM(pos.x),p.ToMM(pos.y)],'sizeMm':[p.ToMM(q.GetSize().x),p.ToMM(q.GetSize().y)],'angle':q.GetOrientationDegrees(),'layer':q.GetLayer(),'nearbyOwnCopper':[]}
            for t in b.GetTracks():
                if t.GetNetname()!=q.GetNetname():continue
                if min(math.hypot(t.GetStart().x-pos.x,t.GetStart().y-pos.y),math.hypot(t.GetEnd().x-pos.x,t.GetEnd().y-pos.y))>4e6:continue
                data['nearbyOwnCopper'].append({'uuid':t.m_Uuid.AsString(),'kind':t.GetClass(),'start':[p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)],'end':[p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y)],'width':p.ToMM(t.GetWidth()),'layer':t.GetLayer(),'locked':t.IsLocked()})
            out[case][key]=data
print(json.dumps(out,indent=2))

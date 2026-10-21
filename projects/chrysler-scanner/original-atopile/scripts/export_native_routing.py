"""Export actual pad copper polygons in board-local coordinates.

Use KiCad's bundled Python. Canonical layer IDs are essential: user-visible
layer names such as 'L1 - Components' are presentation labels, not F.Cu.
"""
from pathlib import Path
import hashlib,json
import pcbnew

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'elec/layout/v240/v240.kicad_pcb'
b=pcbnew.LoadBoard(str(path));pads=[];fps={}
layer_names={pcbnew.F_Cu:'F.Cu',pcbnew.In1_Cu:'In1.Cu',pcbnew.In2_Cu:'In2.Cu',pcbnew.B_Cu:'B.Cu'}
for fp in b.GetFootprints():
    ref=fp.GetReference();fps[ref]=[pcbnew.ToMM(fp.GetPosition().x)-100,pcbnew.ToMM(fp.GetPosition().y)-100,fp.GetOrientationDegrees()]
    for p in fp.Pads():
        poly=p.GetEffectivePolygon(pcbnew.F_Cu,pcbnew.ERROR_OUTSIDE);outlines=[]
        for i in range(poly.OutlineCount()):
            q=poly.COutline(i);outlines.append([[pcbnew.ToMM(q.CPoint(j).x)-100,pcbnew.ToMM(q.CPoint(j).y)-100] for j in range(q.PointCount())])
        pads.append({'ref':ref,'number':p.GetNumber(),'uuid':str(p.m_Uuid.AsString()),'net':p.GetNetname(),'netcode':p.GetNetCode(),'xy':[pcbnew.ToMM(p.GetPosition().x)-100,pcbnew.ToMM(p.GetPosition().y)-100],'size':[pcbnew.ToMM(p.GetSize().x),pcbnew.ToMM(p.GetSize().y)],'drill':[pcbnew.ToMM(p.GetDrillSize().x),pcbnew.ToMM(p.GetDrillSize().y)],'angle':p.GetOrientationDegrees(),'layers':[name for layer,name in layer_names.items() if p.IsOnLayer(layer)],'polygons':outlines,'attribute':int(p.GetAttribute())})
assert sum('F.Cu' in p['layers'] for p in pads)>700
(ROOT/'reference/routing-pass-1/native-input.json').write_text(json.dumps({'pcb_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'footprint_poses':fps,'pads':pads},indent=2)+'\n')
print(f'Exported {len(pads)} native pad polygons with canonical copper-layer identities')

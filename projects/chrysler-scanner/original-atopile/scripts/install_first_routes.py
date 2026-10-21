"""Install a reviewed route plan with native KiCad and tent the through vias.

Run with KiCad's bundled Python after start_routing.py. Existing copper is
never removed; this installer requires an unrouted board for its first run.
"""
from pathlib import Path
import json, math, hashlib
import pcbnew

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'elec/layout/v240/v240.kicad_pcb'
b=pcbnew.LoadBoard(str(path))
assert not list(b.GetTracks()),'Initial route installer requires a board without existing tracks/vias'
plan=json.loads((ROOT/'reference/routing-pass-1/routes.json').read_text())
assert plan['input_pcb_sha256']==hashlib.sha256(path.read_bytes()).hexdigest(),'Board changed after native route export; regenerate the plan'
def point(xy):return pcbnew.VECTOR2I(pcbnew.FromMM(xy[0]+100),pcbnew.FromMM(xy[1]+100))
count=0
for route in plan['tracks']:
    net=b.FindNet(route['net']);assert net,route['net']
    layer=pcbnew.F_Cu if route['layer']=='F.Cu' else pcbnew.B_Cu
    for a,z in zip(route['points'],route['points'][1:]):
        if math.dist(a,z)<.00001:continue
        t=pcbnew.PCB_TRACK(b);t.SetStart(point(a));t.SetEnd(point(z));t.SetWidth(pcbnew.FromMM(route['width']));t.SetLayer(layer);t.SetNetCode(net.GetNetCode());b.Add(t);count+=1
for route in plan['vias']:
    v=pcbnew.PCB_VIA(b);v.SetPosition(point(route['xy']));v.SetWidth(pcbnew.FromMM(route['diameter']));v.SetDrill(pcbnew.FromMM(route['drill']));v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(b.FindNet(route['net']).GetNetCode());v.SetFrontTentingMode(pcbnew.TENTING_MODE_TENTED);v.SetBackTentingMode(pcbnew.TENTING_MODE_TENTED);b.Add(v)
pcbnew.SaveBoard(str(path),b)
print(f'Installed {count} native track segments and {len(plan["vias"])} tented through vias')

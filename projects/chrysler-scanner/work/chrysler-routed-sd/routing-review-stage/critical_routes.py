"""Apply explicit, reviewable RF/USB preroutes to a separate native board copy."""
import argparse
import hashlib
import json
from pathlib import Path
import pcbnew as p

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('input',type=Path)
parser.add_argument('plan',type=Path)
parser.add_argument('output',type=Path)
args=parser.parse_args()
assert args.input.resolve()!=args.output.resolve()
raw=args.input.read_bytes()
plan=json.loads(args.plan.read_text())
assert hashlib.sha256(raw).hexdigest()==plan['input_sha256']
b=p.LoadBoard(str(args.input))
point=lambda xy:p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1]))
for route in plan['tracks']:
    net=b.FindNet(route['net']);assert net,route['net']
    for a,z in zip(route['points'],route['points'][1:]):
        if a==z:continue
        t=p.PCB_TRACK(b);t.SetStart(point(a));t.SetEnd(point(z))
        t.SetWidth(p.FromMM(route['width']));t.SetLayer(p.F_Cu if route['layer']=='F.Cu' else p.B_Cu)
        t.SetNetCode(net.GetNetCode());t.SetLocked(True);b.Add(t)
for via in plan['vias']:
    v=p.PCB_VIA(b);v.SetPosition(point(via['xy']));v.SetWidth(p.FromMM(.6));v.SetDrill(p.FromMM(.3))
    v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu)
    v.SetNetCode(b.FindNet(via['net']).GetNetCode());v.SetLocked(True)
    v.SetFrontTentingMode(p.TENTING_MODE_TENTED);v.SetBackTentingMode(p.TENTING_MODE_TENTED);b.Add(v)
for rule in plan.get('track_keepouts',[]):
    zone=p.ZONE(b);layers=p.LSET()
    for name in rule['layers']:layers.AddLayer({'F.Cu':p.F_Cu,'B.Cu':p.B_Cu,'In1.Cu':p.In1_Cu,'In2.Cu':p.In2_Cu}[name])
    zone.SetLayerSet(layers);zone.SetIsRuleArea(True);zone.SetDoNotAllowTracks(True)
    zone.SetDoNotAllowVias(False);zone.SetDoNotAllowPads(False);zone.SetDoNotAllowZoneFills(False)
    zone.SetDoNotAllowFootprints(False);zone.SetZoneName(rule['name'])
    outline=zone.Outline();outline.NewOutline()
    for xy in rule['polygon']:q=point(xy);outline.Append(q.x,q.y)
    b.Add(zone)
p.SaveBoard(str(args.output),b)
assert args.input.read_bytes()==raw
print(json.dumps({'output':str(args.output),'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
    'route_paths':len(plan['tracks']),'vias':len(plan['vias']),'locked':True,'source_unchanged':True},indent=2))

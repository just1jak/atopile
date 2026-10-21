"""Restore same-width F power branches on the native paired-escape prototype."""
from pathlib import Path
from collections import defaultdict
import ast,hashlib,heapq,importlib.util,json,math,shutil,time,uuid
import pcbnew as p
here=Path(__file__).resolve().parent;root=here.parent
tree=ast.parse((here/'paired_rx_escapes.py').read_text())
selected=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in ('Grid','maze','track_shape')]
mm=lambda n:round(n*1e6);vec=lambda x,y:p.VECTOR2I(round(x),round(y));hit=lambda a,b,c:p.SHAPE.Collide(a,b,c)
exec(compile(ast.Module(body=selected,type_ignores=[]),'paired-maze-definitions','exec'),globals())
source=Path('/private/tmp/atopile-sd-paired-rx-escapes/ChryslerScanner_V240_SD.kicad_pcb')
dest=Path('/private/tmp/atopile-sd-paired-rx-power-restored/ChryslerScanner_V240_SD.kicad_pcb');assert not dest.exists()
s=importlib.util.spec_from_file_location('power_audit',root/'audit-stage/audit_routed_board.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
b=p.LoadBoard(str(source));raw=source.read_bytes();before=m.connectivity(b)
before_cu={m.uid(t):m.copper(t) for t in b.GetTracks()};before_fp=m.native_footprints(b);before_zones={m.uid(z):m.zone_signature(z) for z in b.Zones()}
pads={f.GetReference()+'.'+q.GetNumber():q for f in b.GetFootprints() for q in f.Pads()}
grid=Grid()
for q in pads.values():
 if q.IsOnLayer(p.F_Cu):grid.add(('pad',m.uid(q),q.GetNetname()),p.F_Cu,q.GetEffectiveShape(p.F_Cu))
for t in b.GetTracks():
 if t.IsOnLayer(p.F_Cu):grid.add(('copper',m.uid(t),t.GetNetname()),p.F_Cu,t.GetEffectiveShape(p.F_Cu))
added=[];results=[]
for label in ('R87.1','C57.1'):
 origin=pads[label].GetPosition();assert pads[label].GetNetname()=='+3.3V'
 b.BuildConnectivity();connected={m.uid(x) for x in b.GetConnectivity().GetConnectedItems(pads['J3.3'])};connected.add(m.uid(pads['J3.3']))
 if m.uid(pads[label]) in connected:continue
 targets=[(name,q.GetPosition()) for name,q in pads.items() if m.uid(q) in connected and q.GetNetname()=='+3.3V' and q.IsOnLayer(p.F_Cu) and min(q.GetSize().x,q.GetSize().y)>=500000]
 targets.sort(key=lambda q:(q[1].x-origin.x)**2+(q[1].y-origin.y)**2)
 path=None;target=None
 for name,end in targets[:6]:
  dist=math.hypot(end.x-origin.x,end.y-origin.y)/1e6
  print('Power restore',label,'to',name,'distance',dist,flush=True)
  path=maze(origin,end,p.F_Cu,.5,'+3.3V',50000,8,min(24,dist*2+4),grid=grid)
  if path:target=name;break
 if not path:results.append({'pad':label,'restored':False});continue
 for i,(a,z) in enumerate(zip(path,path[1:])):
  if a==z:continue
  t=p.PCB_TRACK(b);t.SetStart(a);t.SetEnd(z);t.SetWidth(500000);t.SetLayer(p.F_Cu);t.SetNet(b.FindNet('+3.3V'));t.SetLocked(True)
  t.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/paired-power/%s/%d/%d/%d/%d/%d'%(label,i,a.x,a.y,z.x,z.y)))))
  b.Add(t);added.append(t)
 results.append({'pad':label,'restored':True,'target':target,'pathMm':[[pt.x/1e6,pt.y/1e6] for pt in path],'widthMm':.5})
after=m.connectivity(b);assert after['ground']['largestConnectedGroupCount']==175
assert {k:v for k,v in before['disconnectedNetGroups'].items() if k!='+3.3V'}=={k:v for k,v in after['disconnectedNetGroups'].items() if k!='+3.3V'}
assert before_fp==m.native_footprints(b) and before_zones=={m.uid(z):m.zone_signature(z) for z in b.Zones()}
now={m.uid(t):m.copper(t) for t in b.GetTracks()};assert all(now.get(k)==v for k,v in before_cu.items())
dest.parent.mkdir(parents=True,exist_ok=True);p.SaveBoard(str(dest),b);assert m.blocks(raw,'footprint')==m.blocks(dest.read_bytes(),'footprint') and source.read_bytes()==raw
for f in source.parent.iterdir():
 if f.suffix=='.kicad_pro':shutil.copyfile(f,dest.parent/f.name)
 elif f.suffix in ('.kicad_sch','.kicad_sym') or f.name.endswith('lib-table') or f.name in ('libraries','3dmodels','reference','footprints.pretty'):
  (dest.parent/f.name).symlink_to(f.resolve(),target_is_directory=f.is_dir())
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidateSha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'results':results,'addedSame500umPowerCopper':{m.uid(t):m.copper(t) for t in added},'allExistingCopperAndFootprintsAndZoneDefinitionsPreserved':True,'before':before,'after':after,'requiresFreshNativeDrc':True}
(dest.parent/'power-restore-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print('Restored',results,'airwires',after['fullNativeAirwires'],flush=True)

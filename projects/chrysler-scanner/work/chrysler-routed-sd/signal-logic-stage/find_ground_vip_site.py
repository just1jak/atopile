"""Fine native search for one explicitly named residual GND island's VIPPO."""
from pathlib import Path
import argparse,hashlib,json,math,shutil,sys,uuid
import pcbnew as p
ap=argparse.ArgumentParser();ap.add_argument('input',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--pads',required=True);args=ap.parse_args()
assert args.input.resolve()!=args.output.resolve() and not args.output.exists()
script=Path(__file__).with_name('reapply_ground_stitches.py')
geometry=script.read_text().split('added=[];thermal=[]')[0]
saved_argv=sys.argv;sys.argv=[str(script),str(args.input),'--output',str(args.output),'--native-minima']
g={'__file__':str(script),'__name__':'fine_ground_geometry'}
exec(compile(geometry,str(script),'exec'),g);sys.argv=saved_argv
b=g['b'];m=g['m'];raw=g['raw'];mm=g['mm'];vec=g['v'];labels=g['labels'];pads=g['pads'];before=g['initial']
requested=args.pads.split(',');keys=[key for key in pads if labels[key] in requested];assert len(keys)==len(requested)
assert all(pads[key].GetNetname()=='GND' for key in keys)
found=None;examined=0;ordinary=False
for key in keys:
 q=pads[key];origin=q.GetPosition();layer=p.F_Cu if q.IsOnLayer(p.F_Cu) else p.B_Cu;shape=q.GetEffectiveShape(layer)
 box=shape.BBox(mm(.4));step=mm(.025)
 offsets=[(x,y) for x in range(-math.ceil(box.GetWidth()/2/step),math.ceil(box.GetWidth()/2/step)+1)
                 for y in range(-math.ceil(box.GetHeight()/2/step),math.ceil(box.GetHeight()/2/step)+1)]
 offsets.sort(key=lambda xy:xy[0]*xy[0]+xy[1]*xy[1])
 for ix,iy in offsets:
  point=vec(origin.x+ix*step,origin.y+iy*step);examined+=1
  if p.SHAPE.Collide(p.SHAPE_CIRCLE(point,mm(.2)),shape,0) and g['via_clear'](point,key):found=(key,point);break
 if found:break
if found is None:
 # An outside-pad site in the same native filled island avoids solder-pad
 # apertures entirely. Bound this fine search to a small isolated contour.
 for zone in g['outer']:
  layer=p.F_Cu if zone.IsOnLayer(p.F_Cu) else p.B_Cu;poly=zone.GetFilledPolysList(layer)
  for i in range(poly.OutlineCount()):
   if not any(pads[key].IsOnLayer(layer) and poly.Contains(pads[key].GetPosition(),i) for key in keys):continue
   box=poly.COutline(i).BBox()
   if box.GetWidth()*box.GetHeight()>mm(10)**2:continue
   print('Searching actual isolated ground contour',layer,box.GetWidth()/1e6,box.GetHeight()/1e6,flush=True)
   for x in range(box.GetLeft(),box.GetRight()+1,mm(.025)):
    for y in range(box.GetTop(),box.GetBottom()+1,mm(.025)):
     point=vec(x,y);examined+=1
     if poly.Contains(point,i) and g['via_clear'](point):found=(keys[0],point);ordinary=True;break
    if found:break
   if found:break
  if found:break
print('Examined',examined,'fine25um sites; found',None if not found else [labels[found[0]],found[1].x/1e6,found[1].y/1e6],flush=True)
if found is None:raise SystemExit(2)
key,point=found;v=p.PCB_VIA(b);v.SetPosition(point);v.SetWidth(mm(.6));v.SetDrill(mm(.3));v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetViaType(p.VIATYPE_THROUGH);v.SetNet(b.FindNet('GND'));v.SetLocked(True)
v.SetPrimaryDrillFilledFlag(not ordinary);v.SetPrimaryDrillCappedFlag(not ordinary);v.SetFrontTentingMode(p.TENTING_MODE_TENTED);v.SetBackTentingMode(p.TENTING_MODE_TENTED)
v.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/fine-ground/%s/%s/%s'%(labels[key],point.x,point.y)))));b.Add(v)
after=m.connectivity(b)
assert {k:v for k,v in before['disconnectedNetGroups'].items() if k!='GND'}=={k:v for k,v in after['disconnectedNetGroups'].items() if k!='GND'}
assert after['ground']['connectedGroupCount']==before['ground']['connectedGroupCount']-1
assert m.native_footprints(b)==g['before_fp']
current={m.uid(t):m.copper(t) for t in b.GetTracks()};assert all(current.get(k)==v for k,v in g['before_copper'].items())
args.output.parent.mkdir(parents=True,exist_ok=True);p.SaveBoard(str(args.output.resolve()),b)
assert m.blocks(raw,'footprint')==m.blocks(args.output.read_bytes(),'footprint') and args.input.read_bytes()==raw
for f in args.input.parent.iterdir():
 if f.suffix=='.kicad_pro':shutil.copyfile(f,args.output.parent/f.name)
 elif f.suffix in ('.kicad_sch','.kicad_sym') or f.name.endswith('lib-table') or f.name in ('libraries','3dmodels','reference','footprints.pretty'):
  (args.output.parent/f.name).symlink_to(f.resolve(),target_is_directory=f.is_dir())
saved=p.LoadBoard(str(args.output.resolve()));sv=next(t for t in saved.GetTracks() if m.uid(t)==m.uid(v))
assert sv.GetPrimaryDrillFilledFlag()==sv.GetPrimaryDrillCappedFlag()==(not ordinary)
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidateSha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
 'targetPads':requested,'viaTarget':labels[key],'viaUuid':m.uid(v),'viaMm':[point.x/1e6,point.y/1e6],'diameterMm':.6,'drillMm':.3,'savedFilled':not ordinary,'savedCapped':not ordinary,'tentingBothSides':True,'existingCopperPreserved':True,'allFootprintBlocksByteExact':True,'before':before,'after':after,'requiresFreshNativeDrc':True}
(args.output.parent/'fine-ground-vip-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))

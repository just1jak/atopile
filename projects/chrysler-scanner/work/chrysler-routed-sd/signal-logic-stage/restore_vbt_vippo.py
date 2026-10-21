"""Restore reviewed V_BT anchor fabrication attributes omitted by Specctra SES."""
from pathlib import Path
import argparse,hashlib,importlib.util,json
import pcbnew as p
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
ap.add_argument('--restore-reviewed-anchor',action='store_true',help='SES omits new USER_FIXED objects; restore exact reviewed native via and F stub')
a=ap.parse_args()
assert a.input.resolve()!=a.output.resolve() and not a.output.exists()
raw=a.input.read_bytes();stamp=a.input.stat().st_mtime_ns
root=Path(__file__).resolve().parent.parent
s=importlib.util.spec_from_file_location('vippo_audit',root/'audit-stage/audit_routed_board.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
b=p.LoadBoard(str(a.input.resolve()));before={m.uid(t):m.copper(t) for t in b.GetTracks()}
restored=[]
if a.restore_reviewed_anchor:
 prototype=Path('/private/tmp/atopile-sd-vbt-anchor-plus20um/ChryslerScanner_V240_SD.kicad_pcb')
 assert hashlib.sha256(prototype.read_bytes()).hexdigest()=='4325b12bba4776b14e10edcb6afcf78e0f99b71a5e7d8b9ae4c4f5546ec618a8'
 reference=p.LoadBoard(str(prototype));assert m.native_footprints(reference)==m.native_footprints(b)
 target=p.VECTOR2I(170942500,117112500);pin=p.VECTOR2I(170322500,117112500)
 # The exported route must actually continue from the newly fixed anchor.
 assert any(t.GetNetname()=='V_BT' and t.GetLayer()==p.In2_Cu and target in (t.GetStart(),t.GetEnd()) for t in b.GetTracks())
 for refid in ('09fa8030-4f87-508a-b7ff-a6f502b02cad','8cf8242f-4b46-50a7-a351-4b51bd98f7f7'):
  item=next(t for t in reference.GetTracks() if m.uid(t)==refid)
  if isinstance(item,p.PCB_VIA):
   found=[t for t in b.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()=='V_BT' and t.GetPosition()==target]
  else:
   assert item.GetLayer()==p.F_Cu and item.GetWidth()==150000 and item.GetStart()==pin and item.GetEnd()==target
   found=[t for t in b.GetTracks() if not isinstance(t,p.PCB_VIA) and t.GetNetname()=='V_BT' and t.GetLayer()==p.F_Cu and {tuple(m.xy(t.GetStart())),tuple(m.xy(t.GetEnd()))}=={tuple(m.xy(pin)),tuple(m.xy(target))}]
  assert len(found)<=1
  if found:continue
  assert not any(m.uid(t)==refid for t in b.GetTracks())
  if isinstance(item,p.PCB_VIA):
   new=p.PCB_VIA(b);new.SetPosition(target);new.SetWidth(600000);new.SetDrill(300000);new.SetLayerPair(p.F_Cu,p.B_Cu);new.SetViaType(p.VIATYPE_THROUGH)
  else:
   new=p.PCB_TRACK(b);new.SetStart(pin);new.SetEnd(target);new.SetWidth(150000);new.SetLayer(p.F_Cu)
  new.SetNet(b.FindNet('V_BT'));new.SetLocked(True);new.SetUuid(p.KIID(refid));b.Add(new);restored.append(refid)
matches=[t for t in b.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()=='V_BT' and t.GetPosition()==p.VECTOR2I(170942500,117112500)]
assert len(matches)==1,('Expected exactlyone reviewed V_BT anchor',len(matches))
via=matches[0];key=m.uid(via)
assert via.GetWidth(p.F_Cu)==600000 and via.GetDrillValue()==300000
assert via.TopLayer()==p.F_Cu and via.BottomLayer()==p.B_Cu and via.GetViaType()==p.VIATYPE_THROUGH
via.SetPrimaryDrillFilledFlag(True);via.SetPrimaryDrillCappedFlag(True)
via.SetFrontTentingMode(p.TENTING_MODE_TENTED);via.SetBackTentingMode(p.TENTING_MODE_TENTED);via.SetLocked(True)
now={m.uid(t):m.copper(t) for t in b.GetTracks()}
assert all(now[k]==v for k,v in before.items() if k!=key)
if key in before:
 for name in ('net','start','end','width','layer','drill','via_type','top','bottom'):assert now[key][name]==before[key][name]
a.output.parent.mkdir(parents=True,exist_ok=True);p.SaveBoard(str(a.output.resolve()),b)
assert m.blocks(raw,'footprint')==m.blocks(a.output.read_bytes(),'footprint')
saved=p.LoadBoard(str(a.output.resolve()));v=next(t for t in saved.GetTracks() if m.uid(t)==key)
assert v.GetPrimaryDrillFilledFlag() and v.GetPrimaryDrillCappedFlag()
assert v.GetFrontTentingMode()==p.TENTING_MODE_TENTED and v.GetBackTentingMode()==p.TENTING_MODE_TENTED
assert a.input.read_bytes()==raw and a.input.stat().st_mtime_ns==stamp
proof={'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidateSha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),
 'viaUuid':key,'net':'V_BT','positionMm':[170.9425,117.1125],'diameterMm':.6,'drillMm':.3,
 'manufacturing':'Nonconductive filled,copper capped,and planarized VIPPO; tenting alone is not equivalent',
 'savedFilled':True,'savedCapped':True,'frontAndBackTented':True,'existingGeometryAndAllFootprintsPreserved':True,
 'restoredReviewedFixedAnchorObjectsOmittedBySES':restored}
a.output.with_suffix('.vippo.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))

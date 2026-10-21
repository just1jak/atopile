"""Apply reviewed C23/C26 cap repair with one deliberate PCI_RX gap to a NEW copy, rejecting changed source geometry.

Run using KiCad's bundled Python: apply_ground_delta.py INPUT OUTPUT --proof JSON.
Never edits INPUT. A fresh native DRC/refill is mandatory after each rebase.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json
import pcbnew as p

H=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('audit','/Users/justinkobely/Documents/Codex/2026-10-13/a/work/chrysler-routed-sd/audit-stage/audit_routed_board.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)

def signature(t):
 d=a.copper(t);d.pop('locked');d['ends']=sorted([d.pop('start'),d.pop('end')]);return d

def apply(source,output,proof):
 source=source.resolve();output=output.resolve()
 assert source!=output and not output.exists(),'Output must be a NEW file different from input'
 raw=source.read_bytes();mtime=source.stat().st_mtime_ns
 delta=json.loads((H/'cap-repair-delta.json').read_text())
 frozen=Path(delta['frozenCandidate']);assert hashlib.sha256(frozen.read_bytes()).hexdigest()==delta['candidateSha256']
 baseline=Path(delta['source']);assert hashlib.sha256(baseline.read_bytes()).hexdigest()==delta['sourceSha256']
 b=p.LoadBoard(str(source));f=p.LoadBoard(str(frozen));old=p.LoadBoard(str(baseline))
 before=a.connectivity(b)
 assert before['ground']['padCount']==175
 assert set(before['ground']['isolatedFromMainGroup'])=={'C23.2','C26.2'},'Require exactly these two isolated cap pads; reject already-connected sites or extra GND partitions'
 assert 'PCI_RX' not in before['disconnectedNetGroups'],'PCI_RX must be connected before the one known deliberate gap'
 copper={a.uid(t):a.copper(t) for t in b.GetTracks()};zones={a.uid(z):a.zone_signature(z) for z in b.Zones()}
 current=list(b.GetTracks());old_items={a.uid(t):t for t in old.GetTracks()};frozen_items={a.uid(t):t for t in f.GetTracks()}
 matches={}
 for key in delta['removedUnprotectedCopper']:
  expected=signature(old_items[key]);found=[t for t in current if signature(t)==expected and not t.IsLocked()]
  assert len(found)==1,('Expected exactly one unchanged unprotected source track',key,len(found))
  matches[key]=found[0]
 # Verify all prospective UUIDs before changing the in-memory model.
 all_ids={a.uid(x) for x in b.GetTracks()};assert not set(delta['addedCopper'])&all_ids,'Added copper already exists or UUID collision'
 # Refuse newly introduced local copper/hole conflicts before any in-memory edits.
 layers=(p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu);excluded={a.uid(t) for t in matches.values()}
 existing=[item for item in current if a.uid(item) not in excluded]+[q for fp in b.GetFootprints() for q in fp.Pads()]
 holes=[item for item in existing if item.GetClass()=='PCB_VIA' or (item.GetClass()=='PAD' and item.HasDrilledHole())]
 for key in delta['addedCopper']:
  item=frozen_items[key]
  for other in existing:
   if item.GetNetname()==other.GetNetname():continue
   for layer in layers:
    if item.IsOnLayer(layer) and other.IsOnLayer(layer):
     assert not p.SHAPE.Collide(item.GetEffectiveShape(layer),other.GetEffectiveShape(layer),150000),('New copper conflict requiring fresh review',key,a.uid(other),p.LayerName(layer))
  for other in holes:
   if item.GetNetname()!=other.GetNetname():assert not p.SHAPE.Collide(item.GetEffectiveShape(p.F_Cu if item.GetClass()=='PCB_VIA' else item.GetLayer()),other.GetEffectiveHoleShape(),200000),('New copper-to-hole conflict',key,a.uid(other))
   if item.GetClass()=='PCB_VIA':
    assert not p.SHAPE.Collide(item.GetEffectiveHoleShape(),other.GetEffectiveHoleShape(),250000),('New drilled-hole conflict',key,a.uid(other))
 for t in matches.values():b.Remove(t)
 for key in delta['addedCopper']:
  item=frozen_items[key]
  assert item.GetClass() in ('PCB_VIA','PCB_TRACK')
  if item.GetClass()=='PCB_VIA':
   q=p.PCB_VIA(b);q.SetPosition(item.GetPosition());q.SetWidth(item.GetWidth(p.F_Cu));q.SetDrill(item.GetDrillValue())
   q.SetViaType(item.GetViaType());q.SetLayerPair(item.TopLayer(),item.BottomLayer())
   q.SetFrontTentingMode(item.GetFrontTentingMode());q.SetBackTentingMode(item.GetBackTentingMode())
   q.SetPrimaryDrillFilledFlag(item.GetPrimaryDrillFilledFlag());q.SetPrimaryDrillCappedFlag(item.GetPrimaryDrillCappedFlag())
  else:
   q=p.PCB_TRACK(b);q.SetStart(item.GetStart());q.SetEnd(item.GetEnd());q.SetWidth(item.GetWidth());q.SetLayer(item.GetLayer())
  q.SetUuid(p.KIID(key));q.SetLocked(item.IsLocked());q.SetNet(b.FindNet(item.GetNetname()));b.Add(q)
  assert a.copper(q)==a.copper(item),(key,a.copper(q),a.copper(item))
 after=a.connectivity(b)
 remaining={a.uid(t):a.copper(t) for t in b.GetTracks()};removed={a.uid(t) for t in matches.values()}
 assert all(remaining.get(key)==value for key,value in copper.items() if key not in removed)
 assert zones=={a.uid(z):a.zone_signature(z) for z in b.Zones()}
 expected_groups={net:group for net,group in before['disconnectedNetGroups'].items() if net not in ('GND','PCI_RX')}; actual_groups={net:group for net,group in after['disconnectedNetGroups'].items() if net not in ('GND','PCI_RX')}
 assert after['ground']['padCount']==175 and after['ground']['connectedGroupCount']==1,'All 175 GND pads must join one group'
 assert after['disconnectedNetGroups'].get('PCI_RX')==delta['expectedPciRxPadPartitionsAfter'],'Only the reviewed PCI_RX pad partition is allowed'
 if expected_groups!=actual_groups:
  print(json.dumps({'before':expected_groups,'after':actual_groups},indent=2))
 assert expected_groups==actual_groups,'Rebase changed non-ground connectivity'
 output.parent.mkdir(parents=True,exist_ok=True);p.SaveBoard(str(output),b)
 assert a.blocks(raw,'footprint')==a.blocks(output.read_bytes(),'footprint')
 assert source.read_bytes()==raw and source.stat().st_mtime_ns==mtime
 result={'source':str(source),'output':str(output),'sourceSha256':hashlib.sha256(raw).hexdigest(),'candidateSha256':hashlib.sha256(output.read_bytes()).hexdigest(),'sourceUnchanged':True,'allSourceFootprintsPadsUnchanged':True,'allSourceZonesUnchanged':True,'allUnrelatedCopperUnchanged':True,'matchedRemovedSourceUuids':{key:a.uid(t) for key,t in matches.items()},'addedCopperUuids':list(delta['addedCopper']),'before':before,'after':after,'requiresFreshNativeDrc':True,'allowsOnlyReviewedPciRxGap':True,'newCopperAndHoleConflictPreflightPassed':True}
 proof.write_text(json.dumps(result,indent=2)+'\n');print('GND groups',before['ground']['connectedGroupCount'],'→',after['ground']['connectedGroupCount'],'airwires',before['fullNativeAirwires'],'→',after['fullNativeAirwires'])

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('input',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--proof',type=Path,required=True);args=parser.parse_args();apply(args.input,args.output,args.proof)

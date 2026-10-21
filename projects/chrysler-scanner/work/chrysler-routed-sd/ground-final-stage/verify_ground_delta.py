from pathlib import Path
import hashlib,importlib.util,json
import pcbnew as p
H=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('capdelta',H/'apply_ground_repair_delta.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
source=H/'input/ChryslerScanner_V240_SD.kicad_pcb';frozen=H/'combined/ChryslerScanner_V240_SD.kicad_pcb';output=H/'ground-delta-selftest.kicad_pcb'
b=p.LoadBoard(str(output));f=p.LoadBoard(str(frozen))
def copper(board):
 result={}
 for t in board.GetTracks():
  row=m.a.copper(t)
  if t.GetClass()=='PCB_VIA':row.update(filled=bool(t.GetPrimaryDrillFilledFlag()),capped=bool(t.GetPrimaryDrillCappedFlag()))
  result[m.a.uid(t)]=row
 return result
assert copper(b)==copper(f)
assert m.a.blocks(output.read_bytes(),'footprint')==m.a.blocks(frozen.read_bytes(),'footprint')
assert {m.a.uid(z):m.a.zone_signature(z) for z in b.Zones()}=={m.a.uid(z):m.a.zone_signature(z) for z in f.Zones()}
checks={'positiveNativeSelftestExactCopperIncludingFabFlags':True,'positiveExactFootprintsAndZones':True}
never=H/'must-not-exist.kicad_pcb';assert not never.exists()
try:m.apply(frozen,never,H/'must-not-exist-proof.json')
except AssertionError as e:
 assert 'already-connected' in str(e);checks['rejectsAlreadyConnectedGroundSites']=True
else:raise AssertionError('Accepted already connected source')
assert not never.exists()
changed=H/'changed-geometry-selftest.kicad_pcb';mut=p.LoadBoard(str(source));track=next(t for t in mut.GetTracks() if m.a.uid(t)=='63129d61-555a-4eed-b520-b26749204a22');end=track.GetEnd();end.x+=1000;track.SetEnd(end);p.SaveBoard(str(changed),mut)
try:
 try:m.apply(changed,never,H/'must-not-exist-proof.json')
 except AssertionError as e:
  assert 'unchanged unprotected source track' in str(e);checks['rejectsChangedGenericTrackGeometry']=True
 else:raise AssertionError('Accepted changed source geometry')
finally:changed.unlink()
assert not never.exists()
assert hashlib.sha256(source.read_bytes()).hexdigest()=='2f528b2be3fae336cd450178b0b0271a0f80f16cb4a6e65e577221f564d61bb7'
assert hashlib.sha256(frozen.read_bytes()).hexdigest()=='f5b42ba76001f790c445533dfcd8567136b5b018127ac8982a2b04650661a2d1'
checks['frozenInputsUnchanged']=True
(H/'delta-validation.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(checks,indent=2))

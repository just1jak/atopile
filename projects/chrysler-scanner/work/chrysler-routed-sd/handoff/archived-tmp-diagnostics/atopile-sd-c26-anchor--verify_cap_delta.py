from pathlib import Path
import hashlib,importlib.util,json
import pcbnew as p
H=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('capdelta',H/'apply_cap_repair_delta.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
source=Path('/private/tmp/atopile-sd-native3logic-combined/ChryslerScanner_V240_SD.kicad_pcb');frozen=H/'ChryslerScanner_V240_SD.kicad_pcb';output=H/'delta-selftest.kicad_pcb'
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
changed=H/'changed-geometry-selftest.kicad_pcb';mut=p.LoadBoard(str(source));track=next(t for t in mut.GetTracks() if m.a.uid(t)=='9e03668c-37db-4f39-96a0-2e67489b3e1d');end=track.GetEnd();end.x+=1000;track.SetEnd(end);p.SaveBoard(str(changed),mut)
try:
 try:m.apply(changed,never,H/'must-not-exist-proof.json')
 except AssertionError as e:
  assert 'unchanged unprotected source track' in str(e);checks['rejectsChangedGenericTrackGeometry']=True
 else:raise AssertionError('Accepted changed source geometry')
finally:changed.unlink()
assert not never.exists()
assert hashlib.sha256(source.read_bytes()).hexdigest()=='e4834f874067e3c3e2cd32a1131f6e5748ea0a4c31cb44af8e39fbd5bc2aff60'
assert hashlib.sha256(frozen.read_bytes()).hexdigest()=='eb42e88dbe9110808eab571d71b5f4ebb297e4fcf9ebac5f767cb7e36bf371c8'
checks['frozenInputsUnchanged']=True
(H/'delta-validation.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(checks,indent=2))

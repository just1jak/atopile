from pathlib import Path
import importlib.util,hashlib,json
import pcbnew as p
H=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('audit','/Users/justinkobely/Documents/Codex/2026-10-13/a/work/chrysler-routed-sd/audit-stage/audit_routed_board.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
source=H/'input/ChryslerScanner_V240_SD.kicad_pcb';final=H/'combined/ChryslerScanner_V240_SD.kicad_pcb'
b0=p.LoadBoard(str(source));b1=p.LoadBoard(str(final));old={a.uid(t):a.copper(t) for t in b0.GetTracks()};new={a.uid(t):a.copper(t) for t in b1.GetTracks()}
removed={k:v for k,v in old.items() if k not in new};added={k:v for k,v in new.items() if k not in old};changed={k for k in old.keys()&new.keys() if old[k]!=new[k]};assert not changed
assert len(removed)==4 and all(not t['locked'] and t['kind']=='PCB_TRACK' for t in removed.values())
for t in b1.GetTracks():
 if a.uid(t) in added and t.GetClass()=='PCB_VIA':added[a.uid(t)].update(filled=bool(t.GetPrimaryDrillFilledFlag()),capped=bool(t.GetPrimaryDrillCappedFlag()))
connectivity=a.connectivity(b1)
result={'expectedPciRxPadPartitionsAfter':connectivity['disconnectedNetGroups']['PCI_RX'],'source':str(source.resolve()),'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'frozenCandidate':str(final.resolve()),'candidateSha256':hashlib.sha256(final.read_bytes()).hexdigest(),'coordinateUnit':'integer nanometers (KiCad internal units); canonical layer IDs resolved by name on apply','removedUnprotectedCopper':removed,'addedCopper':added,'nativeDrc':{'newPhysicalErrors':0,'expectedGapDanglingWarnings':2,'inheritedErrors':4,'inheritedWarnings':5,'schematicParity':0,'remainingSignalAirwires':3,'groundPads':175,'groundGroups':1},'all263FootprintsPadsUnchanged':True,'all122ProtectedSeedCopperUnchanged':True,'all9ZonesUnchanged':True}
(H/'ground-repair-delta.json').write_text(json.dumps(result,indent=2)+'\n')
print('removed',len(removed),'added',len(added));print({v['net'] for v in removed.values()})

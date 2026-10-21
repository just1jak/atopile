"""Copy the three reviewed outer-GND zones exactly onto a new native copy."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,shutil,sys
import pcbnew as p
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
ap.add_argument('--template',type=Path,default=ROOT/'ground-pour-stage/check3/outer-ground-experiment.kicad_pcb')
ap.add_argument('--context',type=Path,default=ROOT/'design');a=ap.parse_args()
assert a.input.resolve()!=a.output.resolve()
raw=a.input.read_bytes();source_mtime=a.input.stat().st_mtime_ns
s=importlib.util.spec_from_file_location('audit_helpers',ROOT/'audit-stage/audit_routed_board.py')
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
b=p.LoadBoard(str(a.input.resolve()));template=p.LoadBoard(str(a.template.resolve()))
before_copper={m.uid(t):m.copper(t) for t in b.GetTracks()}
before_zones={m.uid(z):m.zone_signature(z) for z in b.Zones()}
templates={m.uid(z):z for z in template.Zones()}
assert len(before_zones)==6 and len(templates)==9
assert all(m.zone_signature(templates[key])==value for key,value in before_zones.items())
extra=set(templates)-set(before_zones);assert len(extra)==3
assert sum(not templates[key].GetIsRuleArea() for key in extra)==2
added=[]
for key in sorted(extra):
    z=p.ZONE(templates[key]);z.SetParent(b);z.SetUuid(p.KIID(key));b.Add(z)
    assert m.zone_signature(z)==m.zone_signature(templates[key])
    added.append({'uuid':key,'name':z.GetZoneName(),'ruleArea':z.GetIsRuleArea(),'layers':list(z.GetLayerSet().Seq())})
assert {m.uid(z):m.zone_signature(z) for z in b.Zones()}=={key:m.zone_signature(z) for key,z in templates.items()}
connection=m.connectivity(b)
assert {m.uid(t):m.copper(t) for t in b.GetTracks()}==before_copper
a.output.parent.mkdir(parents=True,exist_ok=True);p.SaveBoard(str(a.output.resolve()),b)
assert m.blocks(raw,'footprint')==m.blocks(a.output.read_bytes(),'footprint')
name='ChryslerScanner_V240_SD'
shutil.copyfile(a.context/(name+'.kicad_pro'),a.output.with_suffix('.kicad_pro'))
for source in list(a.context.glob('*.kicad_sch'))+list(a.context.glob('*.kicad_sym'))+[a.context/'sym-lib-table',a.context/'fp-lib-table']:
    target=a.output.parent/source.name
    if target.exists():assert target.read_bytes()==source.read_bytes(),str(target)+' context differs'
    else:shutil.copyfile(source,target)
for name in ('footprints.pretty','libraries','3dmodels','reference'):
    target=a.output.parent/name
    if not target.exists():target.symlink_to((a.context/name).resolve(),target_is_directory=True)
assert a.input.read_bytes()==raw and a.input.stat().st_mtime_ns==source_mtime
report={'source':str(a.input),'sourceSha256':hashlib.sha256(raw).hexdigest(),'template':str(a.template),
    'templateSha256':hashlib.sha256(a.template.read_bytes()).hexdigest(),'candidate':str(a.output),
    'candidateSha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'exactAddedZones':added,
    'allExistingCopperAnd263FootprintBlocksPreserved':True,'all9ZoneDefinitionsExactTemplate':True,
    'connectivity':connection}
(a.output.parent/'exact-outer-zone-copy.json').write_text(json.dumps(report,indent=2)+'\n')
print('Exactreviewedzonecopydone',report['candidateSha256'],'airwires',connection['fullNativeAirwires'],
      'groundgroups',connection['ground']['connectedGroupCount'])

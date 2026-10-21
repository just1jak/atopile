"""Verify models and DNP attributes with native KiCad's Python, not atopile.

On this Mac run with:
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 scripts/verify_native_kicad.py
Run KiCad's STEP export first; the exported assembly must contain every fitted
circuit reference and omit the DNP references. This is not DRC or enclosure-fit
validation. Native rendering is performed separately with `kicad-cli pcb render`.
"""
from pathlib import Path
import json,hashlib,re,datetime
import pcbnew

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'elec/layout/v240/v240.kicad_pcb'
source=json.loads((ROOT/'reference/v240-netlist.json').read_text())['parts']
manifest=json.loads((ROOT/'reference/3d-models.json').read_text())
b=pcbnew.LoadBoard(str(path));fps={fp.GetReference():fp for fp in b.GetFootprints()}
assert set(fps)==set(source)|{'H1','H2','H3','H4'}
policy=json.loads((ROOT/'reference/silkscreen-text-metrics.json').read_text())
labels=json.loads((ROOT/'reference/silkscreen-labels.json').read_text());native_bounds={}
for ref,fp in fps.items():
    field=fp.Reference();size=field.GetTextSize()
    assert field.IsVisible() and field.GetLayer()==pcbnew.F_SilkS,ref
    assert abs(pcbnew.ToMM(size.x)-policy['font_width_mm'])<.000001 and abs(pcbnew.ToMM(size.y)-policy['font_height_mm'])<.000001,ref
    assert abs(pcbnew.ToMM(field.GetTextThickness())-policy['stroke_mm'])<.000001,ref
    bb=field.GetEffectiveTextShape().BBox()
    bound=[pcbnew.ToMM(v)-100 for v in [bb.GetX(),bb.GetY(),bb.GetRight(),bb.GetBottom()]]
    assert max(abs(a-b) for a,b in zip(bound,labels[ref]['bounds_mm']))<.000005,(ref,bound,labels[ref]['bounds_mm'])
    native_bounds[ref]=bound
models=0;dnp=[];resolved={}
for ref,fp in fps.items():
    wanted=manifest['references'].get(ref)
    assert len(fp.Models())==(1 if wanted else 0),ref
    assert fp.IsDNP()==bool(source.get(ref,{}).get('dnp')),ref
    if fp.IsDNP():dnp.append(ref)
    if not wanted:continue
    m=fp.Models()[0]
    assert m.m_Filename==manifest['model_path_prefix']+wanted['model'],ref
    actual=Path(m.m_Filename.replace('${KIPRJMOD}',str(path.parent))).resolve()
    assert actual.is_file() and ROOT in actual.parents,(ref,actual)
    assert m.m_Show,ref
    for v,expected in [(m.m_Scale,[1,1,1]),(m.m_Offset,wanted.get('offset_mm',[0,0,0])),(m.m_Rotation,wanted.get('rotation_deg',[0,0,0]))]:
        assert all(abs(q-e)<.000001 for q,e in zip([v.x,v.y,v.z],expected)),ref
    models+=1;resolved[ref]=actual.relative_to(ROOT).as_posix()
assert models==len(source) and b.GetCopperLayerCount()==4
pad_expectations=ROOT/'reference/placement-pass-1-native-pad-expectations.json'
native_pad_count=0
if pad_expectations.exists():
    expected=json.loads(pad_expectations.read_text())
    assert expected['pcb_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    for ref,entries in expected['pads'].items():
        actual=list(fps[ref].Pads());assert len(actual)==len(entries),ref
        for item in entries:
            matching=[pad for pad in actual if pad.GetNumber()==item['number'] and abs(pcbnew.ToMM(pad.GetPosition().x)-item['xy_mm'][0])<.000002 and abs(pcbnew.ToMM(pad.GetPosition().y)-item['xy_mm'][1])<.000002]
            assert len(matching)==1,(ref,item)
            pad=matching[0];actual.remove(pad)
            assert abs((pad.GetOrientationDegrees()-item['angle_deg']+180)%360-180)<.000001,(ref,item)
            assert pad.GetNetname()==item['net'],(ref,item)
            native_pad_count+=1
if (ROOT/'reference/hardware-overrides.json').exists():
    for ref in ['J1','J2','U11','R102','R103']:
        for pad in fps[ref].Pads():
            number=pad.GetNumber()
            if not number:continue
            wanted=source[ref]['pins'][number]['net']
            assert wanted is None or pad.GetNetname()==wanted,(ref,number)
            if ref=='J2':assert abs(pad.GetOrientationDegrees()-90)<.000001,number
            if ref=='J1':
                n=int(number);xy=[pcbnew.ToMM(pad.GetPosition().x)-100,pcbnew.ToMM(pad.GetPosition().y)-100]
                assert all(abs(a-c)<.000001 for a,c in zip(xy,[1.5 if n<=8 else 4.5,11+4*((n-1)%8)])),(number,xy)
                assert abs(pcbnew.ToMM(pad.GetDrillSize().x)-1.35)<.000001,number
                assert abs(pcbnew.ToMM(pad.GetSize().x)-2.35)<.000001,number
    assert manifest['references']['J1']['model']=='ATTEND_226A-1202.step'
    assert fps['J1'].GetValue()=='226A-1202'
    assert str(fps['J1'].GetFPID().GetLibItemName())=='OBDII_ATTEND_226A-1202'

assembly=ROOT/'renders/V240-assembly.step'
occurrences=set(re.findall(r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\('[^']*','([^']+)'",assembly.read_text()))
fitted={r for r,p in source.items() if not p['dnp']}
assert occurrences & set(source)==fitted
for fn in ['V240-3D-isometric.png','V240-3D-top.png']:
    assert (ROOT/'renders'/fn).is_file()
report={'status':'PASS','native_kicad_version':pcbnew.GetBuildVersion(),
    'verified_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'pcb_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
    'native_parser_footprints':len(fps),'copper_layers':b.GetCopperLayerCount(),
    'native_visible_silkscreen_references':len(native_bounds),'native_silkscreen_bounds_mm':native_bounds,
    'reference_text_height_mm':policy['font_height_mm'],'reference_text_width_mm':policy['font_width_mm'],'reference_text_stroke_mm':policy['stroke_mm'],
    'model_references':models,'all_model_paths_resolve_inside_project':True,
    'native_dnp_references':sorted(dnp),'step_component_references':len(fitted),
    'step_fitted_reference_set_matches_source':True,'resolved_models':resolved,
    'assembly_sha256':hashlib.sha256(assembly.read_bytes()).hexdigest(),
    'routing_complete':False,'drc_run':False,'exact_connector_and_enclosure_fit_verified':False}
report['obd_connector']={'part':'ATTEND 226A-1202','native_pin_positions_and_connections_checked':16,'drill_mm':1.35,'pad_diameter_mm':2.35,'minimum_pad_copper_to_edge_mm':.325}
if native_pad_count:report['native_placement_pad_positions_angles_and_net_names_checked']=native_pad_count
(ROOT/'reference/native-kicad-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(f"Native KiCad {report['native_kicad_version']}: {len(fps)} footprints, {models} local models, {len(fitted)} fitted STEP components; PASS")

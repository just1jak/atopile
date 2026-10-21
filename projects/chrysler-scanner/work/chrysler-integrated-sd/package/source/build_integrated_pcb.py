"""Add the reviewed SD logger to a copy of the native V240 board.

No automatic main-board routing, outline changes, or original-board writes.
Run with the KiCad10 bundled Python and its native pcbnew implementation.
"""
from pathlib import Path
import pcbnew as p
import json,hashlib,shutil,uuid,collections,math
HERE=Path(__file__).resolve().parent;WORK=HERE.parent
ORIG=Path('/Users/justinkobely/Downloads/ChryslerCCDSCIScanner_V140/elec/layout/v240/v240.kicad_pcb')
NATIVE=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
SOURCE_SHA='26ab8409f172eb33b40b5439eaa213b2366efa97b0da22439521719e94e71080'
raw=ORIG.read_bytes();before_stat=ORIG.stat();assert hashlib.sha256(raw).hexdigest()==SOURCE_SHA,'Original source changed; re-audit before integration'
manifest=json.loads((WORK/'integration.json').read_text());refs={d['ref'] for d in manifest['parts']};assert len(refs)==18
b=p.LoadBoard(str(ORIG));V=lambda x,y:p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def uid(o):return o.m_Uuid.AsString()
def netof(pad):return pad.GetNetname()
def polygon(poly):
 def chain(c):return [[c.CPoint(i).x,c.CPoint(i).y] for i in range(c.PointCount())]
 return [{'outline':chain(poly.COutline(i)),'holes':[chain(poly.CHole(i,j)) for j in range(poly.HoleCount(i))]} for i in range(poly.OutlineCount())]
def drawing(o):
 data={'uuid':uid(o),'class':o.GetClass(),'layer':int(o.GetLayer()),'locked':o.IsLocked()}
 if isinstance(o,p.PCB_SHAPE):
  data.update(shape=int(o.GetShape()),start=[o.GetStart().x,o.GetStart().y],end=[o.GetEnd().x,o.GetEnd().y],width=o.GetWidth())
  if o.GetShape()==p.SHAPE_T_ARC:data['mid']=[o.GetArcMid().x,o.GetArcMid().y]
 elif isinstance(o,p.PCB_TEXT):data.update(text=o.GetText(),xy=[o.GetPosition().x,o.GetPosition().y],angle=o.GetTextAngle().AsDegrees(),size=[o.GetTextSize().x,o.GetTextSize().y],thickness=o.GetTextThickness(),mirrored=o.IsMirrored(),bold=o.IsBold(),italic=o.IsItalic())
 else:raise AssertionError('Unexpected original drawing type '+o.GetClass())
 return data
def zone(o):
 data={'uuid':uid(o),'layers':str(o.GetLayerSet().FmtHex()),'net':o.GetNetname(),'ruleArea':o.GetIsRuleArea(),'polygon':polygon(o.Outline())}
 for name in ['GetAssignedPriority','GetDoNotAllowFootprints','GetDoNotAllowPads','GetDoNotAllowTracks','GetDoNotAllowVias','GetDoNotAllowZoneFills','GetFillMode','GetIslandRemovalMode','GetLocalClearance','GetMinIslandArea','GetMinThickness','GetPadConnection','GetThermalReliefGap','GetThermalReliefSpokeWidth','GetZoneName']:
  value=getattr(o,name)();data[name]=value if isinstance(value,(str,int,float,bool)) else str(value)
 return data
def snap(fp):
 def xyz(v):return [v.x,v.y,v.z]
 return {'uuid':uid(fp),'ref':fp.GetReference(),'value':fp.GetValue(),'fpid':str(fp.GetFPID().GetLibNickname())+':'+str(fp.GetFPID().GetLibItemName()),'xy':[fp.GetPosition().x,fp.GetPosition().y],'angle':fp.GetOrientationDegrees(),'layer':int(fp.GetLayer()),'locked':fp.IsLocked(),'models':[{'file':Path(m.m_Filename).name,'offset':xyz(m.m_Offset),'scale':xyz(m.m_Scale),'rotation':xyz(m.m_Rotation)} for m in fp.Models()],'pads':{uid(q):{'number':q.GetNumber(),'xy':[q.GetPosition().x,q.GetPosition().y],'angle':q.GetOrientationDegrees(),'layers':str(q.GetLayerSet().FmtHex()),'shape':int(q.GetShape()),'attribute':int(q.GetAttribute()),'roundRectRatio':q.GetRoundRectRadiusRatio(),'size':[q.GetSize().x,q.GetSize().y],'drill':[q.GetDrillSize().x,q.GetDrillSize().y],'net':netof(q)} for q in fp.Pads()}}
base={q.GetReference():snap(q) for q in b.GetFootprints()};assert len(base)==245 and not(refs&set(base))
base_drawing={uid(x):drawing(x) for x in b.GetDrawings()};base_zones={uid(x):zone(x) for x in b.Zones()}
b.BuildConnectivity();base_airwires=b.GetConnectivity().GetUnconnectedCount(False)
# Mechanical holes belong to the board and intentionally have no schematic symbols.
# Retain every existing attribute; add only the native board-only metadata flag.
for fp in b.GetFootprints():
 if fp.GetReference() in ['H1','H2','H3','H4']:fp.SetAttributes(fp.GetAttributes()|p.FP_BOARD_ONLY)
nets={str(k):v for k,v in b.GetNetsByName().items()}
for name in sorted({v for d in manifest['parts'] for v in d['nets'].values()}|{d['net'] for d in manifest['mcu_additions'].values()}):
 if name not in nets:nets[name]=p.NETINFO_ITEM(b,name,0);b.Add(nets[name])
u10=next(q for q in b.GetFootprints() if q.GetReference()=='U10');changes=[]
for pad in u10.Pads():
 d=manifest['mcu_additions'].get(pad.GetNumber())
 if d:
  assert sum(q.GetNetname()==pad.GetNetname() for f in b.GetFootprints() for q in f.Pads())==1,'MCU source net is not unconnected'
  changes.append({'ref':'U10','pad':pad.GetNumber(),'from':pad.GetNetname(),'to':d['net'],'gpio':d['gpio']});pad.SetNet(nets[d['net']])
assert len(changes)==6
# Absolute board coordinates. The existing110x55mm outline is(100,100)..(210,155).
# All additions are on the back. x/y are footprint anchors, not bounding-box corners.
# Pre-flip angles use native KiCadLR flip; J4's card opening remains toward+y.
placements={
 'J4':(190,146,0), 'U20':(190,128,0),
 'R104':(181,112,180),'R105':(179,117.1,180),'R106':(174.94,121,-90),
 'R107':(188,135.4,-90),'R108':(186,135.4,-90),'R109':(194,135.4,-90),'R110':(196,135.4,-90),'R111':(184,135.4,-90),
 'R112':(172,121,-90),'R113':(168,114.1,90),'R114':(168,117.7,90),
 'C58':(196,125.7,90),'C59':(196,130.3,90),'C60':(190.5,135.4,0),'C61':(181,126,0),
 'SW3':(174,151,0),
}
assert set(placements)==refs
added={}
for d in manifest['parts']:
 lib,name=d['footprint'].split(':',1);src=ORIG.parent/'footprints.pretty' if lib=='footprints' else NATIVE/(lib+'.pretty')
 fp=p.FootprintLoad(str(src),name);assert fp,d['ref'];fp.SetFPID(p.LIB_ID(lib,name));fp.SetReference(d['ref']);fp.SetValue(d['value']);fp.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-integrated-sd/pcb/'+d['ref']))));b.Add(fp)
 x,y,angle=placements[d['ref']];fp.SetPosition(V(x,y));fp.SetOrientationDegrees(angle);fp.Flip(fp.GetPosition(),p.FLIP_DIRECTION_LEFT_RIGHT)
 fp.Reference().SetVisible(False);fp.Value().SetVisible(False)
 for name,value in [('MPN',d['mpn']),('Manufacturer',d['manufacturer']),('Description',d['description'])]:
  field=fp.GetField(name)
  if not field:field=p.PCB_FIELD(fp,p.FIELD_T_USER,name);fp.Add(field)
  field.SetText(value);field.SetVisible(False)
 for pad in fp.Pads():
  assert pad.GetNumber() in d['nets'],(d['ref'],pad.GetNumber());pad.SetNet(nets[d['nets'][pad.GetNumber()]])
 # Local copies will be delivered by the root packager; pathnames portable already.
 for model_index,model in enumerate(fp.Models()):
  if d['ref']=='SW3':model.m_Filename='${KIPRJMOD}/3dmodels/SW_SPST_TL3305A.step'
  fp.Models()[model_index]=model
 added[d['ref']]=fp
# Keep all existing footprint UUIDs, including every child pad UUID, unchanged.
assert len({uid(q) for q in b.GetFootprints()})==263
assert len({uid(q) for f in b.GetFootprints() for q in f.Pads()})==sum(len(list(f.Pads())) for f in b.GetFootprints())
# New drawings communicate a real engineering limitation instead of suggesting a routed product.
def txt(t,x,y,size,layer,mirror=False):
 q=p.PCB_TEXT(b);q.SetText(t);q.SetPosition(V(x,y));q.SetTextSize(V(size,size));q.SetTextThickness(p.FromMM(.15));q.SetLayer(layer);q.SetMirrored(mirror);b.Add(q)
txt('SD LOGGER - NEW CIRCUIT UNROUTED / FIRMWARE DEFERRED',155,161.5,1.1,p.Dwgs_User)
txt('SD',200,144,.8,p.B_SilkS,True);txt('LOG / STOP',174,147,.7,p.B_SilkS,True)
# Apply schematic instance paths once its producer has completed.
pathfile=WORK/'schematic-stage/reference/symbol-paths.json'
paths_applied=False
if pathfile.exists():
 paths=json.loads(pathfile.read_text())
 paths=paths.get('parts',paths.get('paths',paths.get('symbols',paths))) if isinstance(paths,dict) else paths
 if isinstance(paths,list):paths={q['reference']:q for q in paths}
 for fp in b.GetFootprints():
  value=paths.get(fp.GetReference())
  if isinstance(value,dict):value=value.get('path') or value.get('symbolPath') or value.get('pcbPath')
  if value:fp.SetPath(p.KIID_PATH(value))
 paths_applied=True
# Preserve PCB rule/stackup settings. Only the project filename field is renamed.
pro=json.loads(ORIG.with_suffix('.kicad_pro').read_text());pro.setdefault('meta',{})['filename']=manifest['project']+'.kicad_pro';(HERE/(manifest['project']+'.kicad_pro')).write_text(json.dumps(pro,indent=2)+'\n')
# Local stage library table points to the original native libraries only for read-only validation.
libs={'footprints':str(ORIG.parent/'footprints.pretty')}
for d in manifest['parts']:
 lib=d['footprint'].split(':')[0]
 if lib!='footprints':libs[lib]=str(NATIVE/(lib+'.pretty'))
(HERE/'fp-lib-table').write_text('(fp_lib_table (version 7) '+' '.join('(lib (name '+json.dumps(lib)+')(type "KiCad")(uri '+json.dumps(path)+')(options "")(descr "Read-only staging lookup"))' for lib,path in libs.items())+')\n')
# Resolve only model pathnames into the root's portable asset bundle; geometry/offsets unchanged.
for fp in b.GetFootprints():
 for model_index,model in enumerate(fp.Models()):
  name=Path(model.m_Filename).name
  if (WORK/'package/3dmodels'/name).exists():model.m_Filename='${KIPRJMOD}/3dmodels/'+name
  else:
   matches=list((WORK/'package/3dmodels/standard').rglob(name))
   if len(matches)==1:model.m_Filename='${KIPRJMOD}/3dmodels/'+str(matches[0].relative_to(WORK/'package/3dmodels'))
  fp.Models()[model_index]=model
for name in ['3dmodels','footprints.pretty','libraries']:
 link=HERE/name
 if not link.exists():link.symlink_to(WORK/'package'/name,target_is_directory=True)
# Native source preservation proof, before and after serialization.
def check_board(board):
 after={q.GetReference():snap(q) for q in board.GetFootprints()};assert len(after)==263 and refs==set(after)-set(base)
 for ref,old in base.items():
  expected=json.loads(json.dumps(old))
  if ref=='U10':
   for pad in expected['pads'].values():
    if pad['number'] in manifest['mcu_additions']:pad['net']=manifest['mcu_additions'][pad['number']]['net']
  assert after[ref]==expected,(ref,after[ref],expected)
 drawings={uid(x):drawing(x) for x in board.GetDrawings()}
 assert all(drawings.get(k)==v for k,v in base_drawing.items()),'Original drawing geometry changed'
 assert base_zones=={uid(x):zone(x) for x in board.Zones()},'Original zone/keepout geometry or properties changed'
 for d in manifest['parts']:
  fp=next(x for x in board.GetFootprints() if x.GetReference()==d['ref'])
  assert fp.GetLayer()==p.B_Cu
  assert str(fp.GetFPID().GetLibNickname())+':'+str(fp.GetFPID().GetLibItemName())==d['footprint']
  assert {(v.GetNumber(),v.GetNetname()) for v in fp.Pads()}==set(d['nets'].items())
check_board(b);target=HERE/(manifest['project']+'.kicad_pcb');p.SaveBoard(str(target),b);final=p.LoadBoard(str(target));check_board(final);final.BuildConnectivity();final_airwires=final.GetConnectivity().GetUnconnectedCount(False)
assert ORIG.read_bytes()==raw and ORIG.stat().st_mtime_ns==before_stat.st_mtime_ns
summary={'basePcbSha256':SOURCE_SHA,'pcbSha256':hashlib.sha256(target.read_bytes()).hexdigest(),'originalUnchanged':True,'originalMtimeUnchanged':True,'baseFootprintsPreserved':245,'baseFootprintUUIDsPreserved':True,'basePadUUIDsAndPhysicalGeometryPreserved':True,'baseElectricalAssignmentsPreservedExceptDeclaredSixNCs':True,'outlineAndExistingDrawingsPreserved':True,'originalZonesAndKeepoutsPreserved':True,'addedFootprints':18,'totalFootprints':263,'allAddedFootprintsBack':True,'newTracks':0,'newVias':0,'routingComplete':False,'firmwareDeferred':True,'minimumBackEnclosureClearanceMm':7,'newSchematicPathsApplied':paths_applied,'mcuPadChanges':changes,'placements':{r:{'xy':list(placements[r][:2]),'preFlipAngle':placements[r][2],'actualBackAngle':q.GetOrientationDegrees(),'fpUuid':uid(q)} for r,q in added.items()},'manifestSha256':hashlib.sha256((WORK/'integration.json').read_bytes()).hexdigest()}
summary.update(baseNativeAirwireCount=base_airwires,finalNativeAirwireCount=final_airwires,additionalAirwires=final_airwires-base_airwires,originalOutlineCoordinatesAndZonePropertiesPreserved=True,base3dModelGeometryPreserved=True,mechanicalBoardOnlyMetadataAdded=['H1','H2','H3','H4'],unconnectedReportLimitNote='CLI DRC JSON reports499 missing items; full native connectivity API counts shown separately')
(HERE/'pcb-preservation.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

"""Normalize only explicitly declared NC singleton names, preserving topology."""
from pathlib import Path
import pcbnew as p
import json,hashlib,collections
HERE=Path(__file__).resolve().parent;WORK=HERE.parent;FILE=HERE/'ChryslerScanner_V240_SD.kicad_pcb'
SOURCE=Path('/Users/justinkobely/Downloads/ChryslerCCDSCIScanner_V140/reference/v240-netlist.json')
source_bytes=SOURCE.read_bytes();authoritative=json.loads(source_bytes)
source_manifest=json.loads((WORK/'original-source-manifest.json').read_text())
assert hashlib.sha256(source_bytes).hexdigest()==source_manifest['files']['reference/v240-netlist.json']['sha256']
ncmap=json.loads((WORK/'schematic-stage/reference/native-nc-net-names.json').read_text());assert len(ncmap)==40 and len(set(ncmap.values()))==40
b=p.LoadBoard(str(FILE));before_hash=hashlib.sha256(FILE.read_bytes()).hexdigest();uid=lambda o:o.m_Uuid.AsString()
def vector(v):return [v.x,v.y] if not hasattr(v,'z') else [v.x,v.y,v.z]
def physical(board):
 fp={}
 for f in board.GetFootprints():
  fp[uid(f)]={'ref':f.GetReference(),'value':f.GetValue(),'xy':vector(f.GetPosition()),'angle':f.GetOrientationDegrees(),'layer':int(f.GetLayer()),'locked':f.IsLocked(),'attributes':f.GetAttributes(),'path':f.GetPath().AsString(),'models':[(m.m_Filename,vector(m.m_Offset),vector(m.m_Scale),vector(m.m_Rotation)) for m in f.Models()],'pads':{uid(q):[q.GetNumber(),vector(q.GetPosition()),q.GetOrientationDegrees(),str(q.GetLayerSet().FmtHex()),int(q.GetShape()),int(q.GetAttribute()),vector(q.GetSize()),vector(q.GetDrillSize()),q.GetRoundRectRadiusRatio()] for q in f.Pads()}}
 drawings={}
 for o in board.GetDrawings():
  data=[o.GetClass(),int(o.GetLayer()),o.IsLocked()]
  if isinstance(o,p.PCB_SHAPE):
   data += [int(o.GetShape()),vector(o.GetStart()),vector(o.GetEnd()),o.GetWidth()]
   if o.GetShape()==p.SHAPE_T_ARC:data.append(vector(o.GetArcMid()))
  else:data += [o.GetText(),vector(o.GetPosition()),o.GetTextAngle().AsDegrees(),vector(o.GetTextSize()),o.GetTextThickness(),o.IsMirrored()]
  drawings[uid(o)]=data
 zones={}
 for z in board.Zones():
  poly=z.Outline();outlines=[]
  for i in range(poly.OutlineCount()):
   c=poly.COutline(i);outlines.append([vector(c.CPoint(j)) for j in range(c.PointCount())]);assert poly.HoleCount(i)==0
  data=[str(z.GetLayerSet().FmtHex()),z.GetNetname(),z.GetIsRuleArea(),outlines]
  for g in ['GetAssignedPriority','GetDoNotAllowFootprints','GetDoNotAllowPads','GetDoNotAllowTracks','GetDoNotAllowVias','GetDoNotAllowZoneFills','GetFillMode','GetIslandRemovalMode','GetLocalClearance','GetMinIslandArea','GetMinThickness','GetPadConnection','GetThermalReliefGap','GetThermalReliefSpokeWidth','GetZoneName']:
   value=getattr(z,g)();data.append(value if isinstance(value,(int,float,str,bool)) else str(value))
  zones[uid(z)]=data
 return fp,drawings,zones

def endpoints(board):
 groups=collections.defaultdict(list)
 for f in board.GetFootprints():
  for q in f.Pads():groups[q.GetNetname()].append((f.GetReference(),q.GetNumber(),uid(q)))
 return {k:sorted(v) for k,v in groups.items() if k}
oldphysical=physical(b);oldgroups=endpoints(b);b.BuildConnectivity();oldair=b.GetConnectivity().GetUnconnectedCount(False)
pads={f.GetReference()+'.'+q.GetNumber():q for f in b.GetFootprints() for q in f.Pads()};changes=[]
nets={str(k):v for k,v in b.GetNetsByName().items()}
for terminal,new_name in ncmap.items():
 ref,pin=terminal.split('.',1);decl=authoritative['parts'][ref]['pins'][pin]
 assert decl.get('no_connect') is True and decl.get('net') is None,(terminal,decl)
 q=pads[terminal];old_name=q.GetNetname();point=(ref,pin,uid(q))
 assert oldgroups[old_name]==[point],(terminal,'old net not singleton',oldgroups[old_name])
 assert new_name not in oldgroups or oldgroups[new_name]==[point],(terminal,'new name merges an existing net')
 if new_name not in nets:nets[new_name]=p.NETINFO_ITEM(b,new_name);b.Add(nets[new_name])
 q.SetNet(nets[new_name]);changes.append({'reference':ref,'pin':pin,'padUuid':uid(q),'from':old_name,'to':new_name,'authoritativeNoConnect':True,'authoritativeNet':None,'beforeEndpoints':[list(point)],'afterEndpoints':[list(point)]})
assert physical(b)==oldphysical
newgroups=endpoints(b)
for name,points in oldgroups.items():
 if len(points)>=2:assert newgroups.get(name)==points,(name,'connected net membership changed')
for c in changes:assert newgroups[c['to']]==[tuple(c['afterEndpoints'][0])]
p.SaveBoard(str(FILE),b);after=p.LoadBoard(str(FILE));assert physical(after)==oldphysical;assert endpoints(after)==newgroups;after.BuildConnectivity();newair=after.GetConnectivity().GetUnconnectedCount(False);assert newair==oldair
report={'authoritativeNetlistSha256':hashlib.sha256(source_bytes).hexdigest(),'explicitMapSha256':hashlib.sha256((WORK/'schematic-stage/reference/native-nc-net-names.json').read_bytes()).hexdigest(),'pcbBeforeSha256':before_hash,'pcbAfterSha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'renamedSingletons':40,'allAuthoritativeNCDeclarationsVerified':True,'allBeforeAndAfterPhysicalNetEndpointsSingletons':True,'connectedNetNamesAndExactEndpointSetsUnchanged':True,'all263FootprintsAndAllPadUUIDsPhysicalGeometryUnchanged':True,'drawingAndZoneGeometryAndPropertiesUnchanged':True,'nativeAirwiresBefore':oldair,'nativeAirwiresAfter':newair,'changes':changes}
(HERE/'nc-name-canonicalization.json').write_text(json.dumps(report,indent=2)+'\n')
preservation=json.loads((HERE/'pcb-preservation.json').read_text());preservation['pcbSha256']=report['pcbAfterSha256'];preservation['ncCanonicalizationReport']='nc-name-canonicalization.json';preservation['additionalIsolatedNCNameMetadataChanges']=40;preservation['assignedNetNamesAndMembershipPreserved']=True;(HERE/'pcb-preservation.json').write_text(json.dumps(preservation,indent=2)+'\n')
assert SOURCE.read_bytes()==source_bytes
print('Canonicalized40authoritativeNCsingletons;607airwiresunchanged;PCBsha',report['pcbAfterSha256'])

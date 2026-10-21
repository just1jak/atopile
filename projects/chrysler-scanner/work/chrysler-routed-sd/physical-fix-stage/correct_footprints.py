"""Manufacturer-based, native KiCad corrections in an isolated PCB copy."""
from pathlib import Path
import collections
import hashlib
import json
import shutil
import uuid
import pcbnew as p

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / 'work/chrysler-integrated-sd/pcb-stage/ChryslerScanner_V240_SD.kicad_pcb'
ASSETS = ROOT / 'work/chrysler-integrated-sd/package'
DEST = HERE / SOURCE.name
EXPECTED = '7eb9e1a94a9ad4c71e47d1c7245f232716e6905fbe046c4cd940806cf378af65'
raw = SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED
source_mtime = SOURCE.stat().st_mtime_ns
uid = lambda x: x.m_Uuid.AsString()
vec = lambda v: [v.x, v.y]
mm = lambda x: int(round(x * 1e6))
xy = lambda x, y: p.VECTOR2I(mm(x), mm(y))

def snapshot(board):
    fps = {}
    endpoints = collections.defaultdict(list)
    for f in board.GetFootprints():
        pads = {}
        for q in f.Pads():
            pads[uid(q)] = {'number': q.GetNumber(), 'xy': vec(q.GetPosition()),
                'local': vec(q.GetFPRelativePosition()), 'angle': q.GetOrientationDegrees(),
                'shape': int(q.GetShape()), 'size': vec(q.GetSize()), 'drill': vec(q.GetDrillSize()),
                'layers': q.GetLayerSet().FmtHex(), 'attribute': int(q.GetAttribute()),
                'roundRatio': q.GetRoundRectRadiusRatio(), 'net': q.GetNetname(),
                'mask': str(q.GetLocalSolderMaskMargin())}
            if q.GetNetname():
                endpoints[q.GetNetname()].append((f.GetReference(), q.GetNumber(), uid(q)))
        fps[uid(f)] = {'ref': f.GetReference(), 'value': f.GetValue(),
            'fpid': str(f.GetFPID().GetLibNickname()) + ':' + str(f.GetFPID().GetLibItemName()),
            'xy': vec(f.GetPosition()), 'angle': f.GetOrientationDegrees(), 'layer': f.GetLayer(),
            'locked': f.IsLocked(), 'attributes': f.GetAttributes(), 'path': f.GetPath().AsString(),
            'models': [(m.m_Filename, [m.m_Offset.x,m.m_Offset.y,m.m_Offset.z],
                        [m.m_Scale.x,m.m_Scale.y,m.m_Scale.z],
                        [m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z]) for m in f.Models()],
            'pads': pads}
    # Native geometry snapshots include all board drawings, keepout polygons, zone settings.
    drawings = {}
    for o in board.GetDrawings():
        d = [o.GetClass(), int(o.GetLayer()), o.IsLocked()]
        if isinstance(o,p.PCB_SHAPE):
            d += [int(o.GetShape()),vec(o.GetStart()),vec(o.GetEnd()),o.GetWidth()]
            if o.GetShape() == p.SHAPE_T_ARC: d.append(vec(o.GetArcMid()))
        else:
            d += [o.GetText(),vec(o.GetPosition()),o.GetTextAngle().AsDegrees(),
                  vec(o.GetTextSize()),o.GetTextThickness(),o.IsMirrored()]
        drawings[uid(o)] = d
    zones = {}
    for z in board.Zones():
        poly = z.Outline(); outlines = []
        for i in range(poly.OutlineCount()):
            c = poly.COutline(i)
            outlines.append([vec(c.CPoint(j)) for j in range(c.PointCount())])
            assert poly.HoleCount(i) == 0
        d = [z.GetLayerSet().FmtHex(),z.GetNetname(),z.GetIsRuleArea(),outlines]
        for g in ['GetAssignedPriority','GetDoNotAllowFootprints','GetDoNotAllowPads',
                  'GetDoNotAllowTracks','GetDoNotAllowVias','GetDoNotAllowZoneFills',
                  'GetFillMode','GetIslandRemovalMode','GetLocalClearance','GetMinIslandArea',
                  'GetMinThickness','GetPadConnection','GetThermalReliefGap',
                  'GetThermalReliefSpokeWidth','GetZoneName']:
            v = getattr(z,g)(); d.append(v if isinstance(v,(str,int,float,bool)) else str(v))
        zones[uid(z)] = d
    return {'footprints':fps,'nets':{k:sorted(v) for k,v in endpoints.items()},
            'drawings':drawings,'zones':zones}

board = p.LoadBoard(str(SOURCE)); before = snapshot(board)
fps = {f.GetReference():f for f in board.GetFootprints()}
changes = []

# CP2102/9 Rev1.8, Figure4/Table11: C1=C2=4.80, E=.50,
# X1=.20..30, Y1=.85..95, X2=Y2=3.20..3.30 millimetres.
u12 = fps['U12']
assert u12.GetValue() == 'CP2102'
for q in u12.Pads():
    old = before['footprints'][uid(u12)]['pads'][uid(q)]
    n = int(q.GetNumber())
    local = q.GetFPRelativePosition()
    if n <= 28:
        if abs(local.x) == mm(2.5):
            q.SetFPRelativePosition(p.VECTOR2I(mm(2.4) if local.x > 0 else -mm(2.4),local.y))
            q.SetSize(xy(.90,.25))
        else:
            assert abs(local.y) == mm(2.5)
            q.SetFPRelativePosition(p.VECTOR2I(local.x,mm(2.4) if local.y > 0 else -mm(2.4)))
            q.SetSize(xy(.25,.90))
    else:
        assert n == 29
        q.SetSize(xy(3.30,3.30))
        layers=q.GetLayerSet(); layers.RemoveLayer(p.F_Paste); q.SetLayerSet(layers)
    q.SetLocalSolderMaskMargin(mm(.06))
    changes.append({'reference':'U12','pad':q.GetNumber(),'uuid':uid(q),'before':old})

# Same manufacturer specifies 3x3 .90mm paste openings on1.10mm pitch (67%).
paste_ids = []
for x in (-1.10,0,1.10):
    for y in (-1.10,0,1.10):
        q=p.PAD(u12); q.SetNumber(''); q.SetAttribute(p.PAD_ATTRIB_SMD)
        q.SetShape(p.PAD_SHAPE_RECT); q.SetSize(xy(.90,.90))
        layers=p.LSET(); layers.AddLayer(p.F_Paste)
        q.SetLayerSet(layers); q.SetFPRelativePosition(xy(x,y))
        q.SetFPRelativeOrientation(p.EDA_ANGLE(0,p.DEGREES_T))
        q.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/cp2102/paste/%s/%s'%(x,y)))))
        u12.Add(q); paste_ids.append(uid(q))

# GCT USB4105 RevB4 nominal pad envelope .60x1.15 and holesØ.65 retained.
# Increase existing roundrect corners to .25mm (from .15): cuts only the
# unnecessary copper corner nearest each locating hole; no mating-hole movement.
j2=fps['J2']
for q in j2.Pads():
    if q.GetNumber() in ('A1','A12','B1','B12'):
        assert vec(q.GetSize()) == [mm(.60),mm(1.15)]
        changes.append({'reference':'J2','pad':q.GetNumber(),'uuid':uid(q),
                        'before':before['footprints'][uid(j2)]['pads'][uid(q)]})
        q.SetRoundRectRadiusRatio(.25/.60)

# Connect both retained GND reference planes at a point outside the RF keepout.
# Through-via is .60/.30mm, matching existing native board manufacturability limits.
via=p.PCB_VIA(board); via.SetPosition(xy(178.5,113.5)); via.SetWidth(mm(.60))
via.SetDrill(mm(.30)); via.SetViaType(p.VIATYPE_THROUGH); via.SetLayerPair(p.F_Cu,p.B_Cu)
via.SetNet(board.FindNet('GND'))
via.SetUuid(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'chrysler-v240/ground-stitch/178.5/113.5'))))
board.Add(via)

shutil.copyfile(SOURCE.with_suffix('.kicad_pro'), DEST.with_suffix('.kicad_pro'))
shutil.copytree(ASSETS/'footprints.pretty',HERE/'footprints.pretty',dirs_exist_ok=True,
                copy_function=shutil.copyfile)
shutil.copyfile(ASSETS/'fp-lib-table',HERE/'fp-lib-table')
for name in ('libraries','3dmodels'):
    dest=HERE/name
    if not dest.exists(): dest.symlink_to(ASSETS/name,target_is_directory=True)

for f in (u12,j2,fps['JP1']):
    local=p.Cast_to_FOOTPRINT(f.Duplicate(False))
    local.SetOrientationDegrees(0); local.SetPosition(xy(0,0)); local.SetLocked(False)
    p.FootprintSave(str(HERE/'footprints.pretty'),local)

board.BuildConnectivity()
p.SaveBoard(str(DEST),board)
reloaded=p.LoadBoard(str(DEST)); after=snapshot(reloaded)
assert before['nets'] == after['nets'], 'Electrical endpoint/net changes are forbidden'
assert before['drawings'] == after['drawings'], 'All drawing/outline geometry must remain exact'
assert before['zones'] == after['zones'], 'Keepouts and reference-plane definitions must remain exact'
assert set(before['footprints']) == set(after['footprints'])
for fid,old in before['footprints'].items():
    new=after['footprints'][fid]
    assert {k:v for k,v in old.items() if k!='pads'} == {k:v for k,v in new.items() if k!='pads'}
    if old['ref'] not in ('U12','J2'):
        assert old['pads']==new['pads']
    else:
        assert set(old['pads']) <= set(new['pads'])
        for pid,pad in old['pads'].items():
            for key in ('number','net','drill','attribute','angle'):
                assert pad[key]==new['pads'][pid][key],(old['ref'],pid,key)
for c in changes:
    c['after']=after['footprints'][uid(fps[c['reference']])]['pads'][c['uuid']]
report={'source':str(SOURCE),'sourceSha256':EXPECTED,'pcb':DEST.name,
        'pcbSha256':hashlib.sha256(DEST.read_bytes()).hexdigest(),
        'footprintsPreserved':len(before['footprints']),
        'originalPadUUIDsPreserved':sum(len(x['pads']) for x in before['footprints'].values()),
        'allElectricalNetEndpointSetsExact':True,'allFootprintAnchorsAnglesPathsModelsAndLocksExact':True,
        'allOtherPadsUnchanged':True,'allOutlineDrawingsKeepoutAndPlaneDefinitionsExact':True,
        'addedPasteOnlyPads':paste_ids,'addedGroundVia':{'uuid':uid(via),'positionMM':[178.5,113.5],
        'diameterMM':.6,'drillMM':.3,'net':'GND','purpose':'Join retained In1/In2 ground reference planes'},
        'CP2102ManufacturerURL':'https://www.silabs.com/documents/public/data-sheets/CP2102-9.pdf',
        'GCTManufacturerURL':'https://gct.co/files/drawings/usb4105.pdf','changes':changes,
        'routingComplete':False}
(HERE/'footprint-correction-proof.json').write_text(json.dumps(report,indent=2)+'\n')
assert SOURCE.read_bytes()==raw and SOURCE.stat().st_mtime_ns==source_mtime
print('Corrected copy:',DEST,'SHA256',report['pcbSha256'])
print('Preserved263footprints+alloldpadUUIDs+allnetsets; added9paste-onlyapertures+1GNDstitchvia')

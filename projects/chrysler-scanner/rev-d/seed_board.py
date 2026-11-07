"""Seed Rev D from accepted Rev C geometry and the native Rev D XML netlist."""
from pathlib import Path
import hashlib
import sys
from xml.etree import ElementTree as ET
import pcbnew as p

root=Path(__file__).resolve().parent.parent
rev_c=root/'current/ChryslerScanner_V240_SD.kicad_pcb'
assert hashlib.sha256(rev_c.read_bytes()).hexdigest()=='e794b86979228ba2275eb4262df848acd16e56ef97a4ccf45402d65b119308d4'
xml, output, dsn = map(Path,sys.argv[1:])
b=p.LoadBoard(str(rev_c))
x=ET.parse(xml)
point=lambda x,y:p.VECTOR2I(p.FromMM(x),p.FromMM(y))
parts={c.get('ref'):c for c in x.findall('./components/comp')}
nets={n.get('name'):{(a.get('ref'),a.get('pin')) for a in n} for n in x.findall('./nets/net')}
pins={pin:name for name, ps in nets.items() for pin in ps}
# These four segments are the only original copper attached to the two J1 pads.
connector_stubs={
    'b89f1e57-d5a1-4db7-803d-95f406737412','ebabd454-9f8b-4c6a-b6a8-481ae5989bb2',
    '7e37a14e-0edd-4715-96b2-6f65ad462b17','9a7bbeab-d49c-4118-bcf5-89151bc7ab77',
}
removed={}
for t in list(b.GetTracks()):
    uid=t.m_Uuid.AsString()
    if uid in connector_stubs:
        assert t.GetNetname() in ('J1962-6','J1962-14')
        removed[uid]=t
assert removed.keys()==connector_stubs
known={pad.GetNetname():pad.GetNet() for f in b.GetFootprints() for pad in f.Pads() if pad.GetNetname()}
for pin in (6,14):
    net=known.pop(f'J1962-{pin}')
    name=f'LEGACY_{pin}_ISOLATED'
    net.SetNetname(name)
    known[name]=net
for name in sorted(nets):
    if name not in known:
        net=p.NETINFO_ITEM(b,name)
        b.Add(net)
        known[name]=net
old_refs={f.GetReference() for f in b.GetFootprints()}
positions={
 'K1':(111,160,0),'K2':(123,160,0),'U25':(109,173,180),'D40':(104,169,0),
 'C140':(114,171,90),'C141':(114,176,90),'U26':(157,166,0),
 'U27':(143,167,0),'U28':(137,174,0),
 'Q25':(117,168,0),'Q26':(126,170.5,0),'Q27':(130,172,0),'Q28':(118,173,0),
 'R140':(149,161,0),'R141':(149,164,0),'R142':(137,166,0),'R143':(137,169,0),
 'R144':(119,176,0),'R145':(131,175,0),'R146':(169,164,0),
 'R147':(180,174,0),'R148':(193,173,0),'R149':(189,174,0),
 'D41':(132,166,0),'D42':(132,169,0),'D43':(111,167,0),'D44':(124,166.7,0),
 'C142':(158,159,0),'C143':(145,160,0),'C144':(137,177,0),
 'C145':(132,178,0),'C146':(142,175,0),
 'U29':(171,170,0),'U30':(166,175,0),'U31':(178,170,0),'U32':(187,170,0),
 'C147':(171,174,0),'C148':(166,178,0),'C149':(179,177,0),'C150':(187,177,0),
}
assert set(positions)==set(parts)-old_refs
for ref, (xx,yy,angle) in positions.items():
    c=parts[ref]
    lib,name=c.findtext('footprint').split(':',1)
    f=p.FootprintLoad(str((root/'rev-d/libraries'/(lib+'.pretty')).resolve()),name)
    assert f,ref
    f.SetFPID(p.LIB_ID(lib,name))
    f.SetReference(ref)
    f.SetValue(c.findtext('value'))
    f.SetPosition(point(xx,yy))
    f.SetOrientationDegrees(angle)
    f.SetPath(p.KIID_PATH('/b35850f9-3522-5e00-90df-092fcfbfe6bd'+c.find('sheetpath').get('tstamps')+c.findtext('tstamps')))
    f.Value().SetVisible(False)
    f.Reference().SetLayer(p.F_Fab)
    b.Add(f)
for f in b.GetFootprints():
    ref=f.GetReference()
    if ref in ('TP14','TP16'):
        f.SetValue(parts[ref].findtext('value'))
    for pad in f.Pads():
        if (ref,pad.GetNumber()) in pins:
            pad.SetNet(known[pins[ref,pad.GetNumber()]])
# Extend the lower edge only. Retain the existing four mounting positions.
for d in b.GetDrawings():
    if d.GetLayer()!=p.Edge_Cuts:
        continue
    if d.GetShape()==p.SHAPE_T_ARC and p.ToMM(d.GetStart().y)>=153:
        d.Move(point(0,30))
        continue
    for get,set_ in ((d.GetStart,d.SetStart),(d.GetEnd,d.SetEnd)):
        pt=get()
        if p.ToMM(pt.y)>=153:
            set_(p.VECTOR2I(pt.x,pt.y+p.FromMM(30)))
for z in b.Zones():
    if z.GetNetname()!='GND':
        continue
    contour=z.Outline().Outline(0)
    for i in range(contour.PointCount()):
        pt=contour.CPoint(i)
        if p.ToMM(pt.y)==155:
            contour.SetPoint(i,p.VECTOR2I(pt.x,p.FromMM(185)))

# Break out the newly used ESP32 pins using the same through-via stack as Rev C.
# Locally reroute copper that occupied the two escape sites.
layers = (p.F_Cu, p.In1_Cu, p.In2_Cu, p.B_Cu)
mm = p.FromMM
mcu = b.FindFootprintByReference('U10')
escapes = (
    ('8', (170.9225, 116.1125), {'GND', 'SD_DETECT'}),
    ('22', (175.7125, 119.5275), {'IO0', 'MCU_SD_CS'}),
)
for pad_number, position, reroute_nets in escapes:
    pad = next(pad for pad in mcu.Pads() if pad.GetNumber() == pad_number)
    start = pad.GetPosition()
    site = point(*position)
    disk = p.SHAPE_CIRCLE(site, mm(.30))
    trace = p.SHAPE_SEGMENT(start, site, mm(.15))
    for existing in b.GetTracks():
        if existing.GetNetname() not in reroute_nets:
            continue
        for layer in layers:
            if not existing.IsOnLayer(layer):
                continue
            shape = existing.GetEffectiveShape(layer)
            if p.SHAPE.Collide(disk, shape, mm(.151)) or (
                    layer == p.F_Cu and p.SHAPE.Collide(trace, shape, mm(.151))):
                removed[existing.m_Uuid.AsString()] = existing
                print('Local reroute', existing.GetNetname(), existing.m_Uuid.AsString())
                break
    track = p.PCB_TRACK(b)
    track.SetStart(start)
    track.SetEnd(site)
    track.SetLayer(p.F_Cu)
    track.SetWidth(mm(.15))
    track.SetNet(pad.GetNet())
    b.Add(track)
    via = p.PCB_VIA(b)
    via.SetViaType(p.VIATYPE_THROUGH)
    via.SetLayerPair(p.F_Cu, p.B_Cu)
    via.SetPosition(site)
    via.SetWidth(mm(.6))
    via.SetDrill(mm(.3))
    via.SetNet(pad.GetNet())
    b.Add(via)
b.BuildConnectivity()
for t in b.GetTracks():
    t.SetLocked(True)
for t in removed.values():
    b.Remove(t)
b.BuildConnectivity()
assert p.SaveBoard(str(output),b)
assert p.ExportSpecctraDSN(b,str(dsn.resolve()))
print('Placed',len(positions),'new footprints. Removed',len(connector_stubs),
      'direct legacy stubs and',len(removed)-len(connector_stubs),'ESP32 escape obstacles.')

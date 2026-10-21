from pathlib import Path
import pcbnew as p

HERE=Path(__file__).resolve().parent
xy=lambda x,y:p.VECTOR2I(round(x*1e6),round(y*1e6))
lib=HERE/'RouterSmoke.pretty';lib.mkdir(exist_ok=True)
(lib/'Pad1.kicad_mod').write_text('''(footprint "Pad1" (version 20240108) (generator pcbnew)
 (layer "F.Cu") (attr smd)
 (fp_text reference "REF**" (at 0 -2) (layer "F.SilkS") (effects (font (size 1 1) (thickness .15))))
 (fp_text value "Pad1" (at 0 2) (layer "F.Fab") (effects (font (size 1 1) (thickness .15))))
 (fp_rect (start -1.25 -1.25) (end 1.25 1.25) (stroke (width .05) (type default)) (fill none) (layer "F.CrtYd"))
 (pad "1" smd rect (at 0 0) (size 2 2) (layers "F.Cu" "F.Mask" "F.Paste")))\n''')
(HERE/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "RouterSmoke") (type "KiCad") (uri "${KIPRJMOD}/RouterSmoke.pretty") (options "") (descr "Local router proof")))\n')
b=p.BOARD();b.SetCopperLayerCount(2)
net=p.NETINFO_ITEM(b,'SMOKE_NET');b.Add(net)
for ref,x in [('P1',103),('P2',117)]:
 f=p.FootprintLoad(str(lib),'Pad1');f.SetFPID(p.LIB_ID('RouterSmoke','Pad1'))
 f.SetReference(ref);f.SetValue('Pad1');f.SetPosition(xy(x,106));b.Add(f)
 next(iter(f.Pads())).SetNet(net)
for start,end in [((100,100),(120,100)),((120,100),(120,112)),((120,112),(100,112)),((100,112),(100,100))]:
 s=p.PCB_SHAPE();s.SetShape(p.SHAPE_T_SEGMENT);s.SetStart(xy(*start));s.SetEnd(xy(*end))
 s.SetWidth(round(.05*1e6));s.SetLayer(p.Edge_Cuts);b.Add(s)
b.BuildConnectivity();assert b.GetConnectivity().GetUnconnectedCount(False)==1
assert len(list(b.GetTracks()))==0
p.SaveBoard(str(HERE/'tiny-unrouted.kicad_pcb'),b)
assert p.ExportSpecctraDSN(b,str(HERE/'tiny.dsn'))
print('Created2pads/1net/1airwire/0copper; native DSN exported')

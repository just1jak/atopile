"""Apply only USB-C, its CC resistors and nearby data ESD placement.

--prepare-connector replaces the obsolete USB-B pad map before ato loads the
board. Ato needs the pad identifiers to agree with the changed atomic part.
Run without the flag after ato has created the two new resistor footprints.
"""
from pathlib import Path
import argparse,json,copy,csv,math
import sexpdata as sx
from pcb_geometry import name,nodes,one,courtyard

ROOT=Path(__file__).resolve().parents[1];BOARD=ROOT/'elec/layout/v240/v240.kicad_pcb'
parser=argparse.ArgumentParser();parser.add_argument('--prepare-connector',action='store_true');args=parser.parse_args()
hardware=json.loads((ROOT/'reference/hardware-overrides.json').read_text())
source=json.loads((ROOT/'reference/v240-netlist.json').read_text())['parts']
b=sx.loads(BOARD.read_text());fps={next(q[2] for q in nodes(fp,'property') if q[1]=='Reference'):fp for fp in nodes(b,'footprint')}
def setone(fp,key,node):
    old=one(fp,key)
    if old is not None:fp[fp.index(old)]=node
    elif key=='at':fp.insert(2,node)
    else:fp.append(node)
def position(fp,p):
    old=one(fp,'at');old_angle=float(old[3]) if old and len(old)>3 else 0
    angle=p['rotation_deg'];setone(fp,'at',[sx.Symbol('at'),100+p['xy_mm'][0],100+p['xy_mm'][1],angle])
    for pad in nodes(fp,'pad'):
        at=one(pad,'at')
        if len(at)==3:at.append(angle)
        else:at[3]=(float(at[3])-old_angle+angle)%360
    ref=next(q[2] for q in nodes(fp,'property') if q[1]=='Reference')
    if ref=='J2':
        for pad in nodes(fp,'pad'):
            if str(pad[2])=='smd':setone(pad,'solder_mask_margin',[sx.Symbol('solder_mask_margin'),hardware['usb_c_smd_solder_mask_margin_mm']])

if args.prepare_connector:
    ref='J2';old=fps[ref];wanted=source[ref]['footprint']
    if str(old[1]).split(':')[-1]!=wanted:
        assert not nodes(b,'segment') and not nodes(b,'via'),'Review the connector replacement against existing routes before changing its pad map'
        fp=sx.loads((ROOT/'elec/src/footprints'/(wanted+'.kicad_mod')).read_text())
        fp[1]='footprints:'+wanted
        fp[:]=[q for q in fp if name(q) not in ['version','generator','generator_version','duplicate_pad_numbers_are_jumpers']]
        # Keep the existing atopile identity and canonical Reference/Value
        # fields. Only the connector's package geometry is replaced.
        old_properties={q[1]:q for q in nodes(old,'property')}
        for key in ['Reference','Value']:
            fp[:]=[q for q in fp if not (name(q)=='property' and q[1]==key)]
            fp.append(copy.deepcopy(old_properties[key]))
        for q in old:
            if name(q) in ['uuid','path','sheetfile','sheetname'] or (name(q)=='property' and q[1] not in ['Reference','Value','Datasheet','Description']):fp.append(copy.deepcopy(q))
        next(q for q in nodes(fp,'property') if q[1]=='Value')[2]=source[ref]['value']
        position(fp,hardware['placement'][ref]);b[b.index(old)]=fp
        BOARD.write_text(sx.dumps(b)+'\n')
        print('Prepared J2 USB-C pad map; retained atopile identity and every other footprint')
    else:print('J2 already has the USB-C pad map')
else:
    placement=json.loads((ROOT/'reference/v240-placement.json').read_text())
    for ref,p in placement.items():
        if ref in hardware['placement']:continue
        at=one(fps[ref],'at')
        assert math.dist([float(at[1])-100,float(at[2])-100],p['xy_mm'])<.000002 and float(at[3] if len(at)>3 else 0)==p['rotation_deg'],f'{ref}: retained placement changed'
    for ref,p in hardware['placement'].items():
        fp=fps[ref];position(fp,p)
        placement[ref]={**p,'courtyard_mm':list(courtyard(fp).bounds)}
    BOARD.write_text(sx.dumps(b)+'\n')
    (ROOT/'reference/v240-placement.json').write_text(json.dumps(placement,indent=2)+'\n')
    with (ROOT/'migration.csv').open('w') as file:
        writer=csv.writer(file);writer.writerow(['V240Reference','Value','FunctionalGroup','PlacementBasis','BoardX_mm','BoardY_mm','Rotation_deg'])
        for ref,p in placement.items():writer.writerow([ref,source[ref]['value'],p['group'],p['reason'],*p['xy_mm'],p['rotation_deg']])
    print('Placed J2, U11 and R102/R103; all other retained parts kept their coordinates and rotation')

"""Install the selected ATTEND J1 package without moving any other footprint.

Run after regenerating the source/placement when intentionally reconstructing
the layout. Ordinary ato rebuilds preserve this package and position.
"""
from pathlib import Path
import copy,csv,json
import sexpdata as sx
from pcb_geometry import name,nodes,one,courtyard

ROOT=Path(__file__).resolve().parents[1]
BOARD=ROOT/'elec/layout/v240/v240.kicad_pcb'
hardware=json.loads((ROOT/'reference/hardware-overrides.json').read_text())
spec=hardware['parts']['J1'];position=hardware['placement']['J1']
assert spec['orderable_hint']=='226A-1202'
board=sx.loads(BOARD.read_text())
old=next(fp for fp in nodes(board,'footprint') if any(p[1:3]==['Reference','J1'] for p in nodes(fp,'property')))
new=sx.loads((ROOT/'elec/src/footprints'/(spec['footprint']+'.kicad_mod')).read_text())
new[1]='footprints:'+spec['footprint']
new[:]=[e for e in new if name(e) not in ['version','generator','fp_text']]
# The placement clause must precede children for native KiCad's parser.
new.insert(2,[sx.Symbol('at'),*[100+x for x in position['xy_mm']],position['rotation_deg']])
for e in old:
    if name(e) in ['uuid','path','sheetname','sheetfile','property']:
        q=copy.deepcopy(e)
        if name(q)=='property' and q[1]=='Value':q[2]=spec['value']
        new.append(q)
new.insert(2,sx.Symbol('locked'))
oldpads={str(p[1]):p for p in nodes(old,'pad')}
for pad in nodes(new,'pad'):
    for key in ['net','uuid']:
        item=one(oldpads[str(pad[1])],key)
        if item:pad.append(copy.deepcopy(item))
board[board.index(old)]=new
BOARD.write_text(sx.dumps(board)+'\n')
placement=json.loads((ROOT/'reference/v240-placement.json').read_text())
placement['J1']={**position,'courtyard_mm':list(courtyard(new).bounds)}
anchors=json.loads((ROOT/'reference/mechanical-anchors.json').read_text())
anchors['J1']={k:position[k] for k in ['xy_mm','rotation_deg','reason']}
plan=json.loads((ROOT/'reference/layout-plan.json').read_text())
for group in plan['groups']:
    if 'J1' in group['anchors']:group['anchors']['J1']=position['xy_mm']+[position['rotation_deg']]
for filename,value in [('v240-placement.json',placement),('mechanical-anchors.json',anchors),('layout-plan.json',plan)]:
    (ROOT/'reference'/filename).write_text(json.dumps(value,indent=2)+'\n')
with (ROOT/'migration.csv').open(newline='') as f:rows=list(csv.DictReader(f));fields=list(rows[0])
for row in rows:
    if row['V240Reference']=='J1':
        row.update(Value=spec['value'],PlacementBasis=position['reason'],BoardX_mm=position['xy_mm'][0],BoardY_mm=position['xy_mm'][1],Rotation_deg=position['rotation_deg'])
with (ROOT/'migration.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
print('Installed ATTEND 226A-1202 at board-local (3, 25) mm; all other footprints preserved')

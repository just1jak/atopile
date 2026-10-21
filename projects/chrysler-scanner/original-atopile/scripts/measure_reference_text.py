"""Measure actual reference ink bounds using KiCad's native stroke font.

Run with KiCad's bundled Python before finish_board.py if text policy changes.
The input PCB is loaded in memory; no PCB geometry or placement is saved.
"""
from pathlib import Path
import json
import pcbnew

ROOT=Path(__file__).resolve().parents[1]
FONT=1.0;WIDTH=.65;STROKE=.15
b=pcbnew.LoadBoard(str(ROOT/'elec/layout/v240/v240.kicad_pcb'))
source=json.loads((ROOT/'reference/v240-netlist.json').read_text())['parts']
references=set(source)|{'H1','H2','H3','H4'}
by_address={r.lower():r for r in references}
metrics={}
for fp in b.GetFootprints():
    # ato restores legacy REF** texts, which override the native reference
    # while loading. Measure the real circuit identifier from its address.
    address=fp.GetField('atopile_address')
    ref=by_address[address.GetText()] if address else fp.GetReference()
    assert ref in references and ref not in metrics,ref
    fp.SetReference(ref);field=fp.Reference();field.SetVisible(True)
    assert not field.GetFontName(),f'{ref}: expected KiCad default stroke font'
    field.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(WIDTH),pcbnew.FromMM(FONT)))
    field.SetTextThickness(pcbnew.FromMM(STROKE))
    field.SetPosition(pcbnew.VECTOR2I(0,0));bounds={}
    for angle in [0,90]:
        field.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        bb=field.GetEffectiveTextShape().BBox()
        bounds[str(angle)]=[pcbnew.ToMM(v) for v in [bb.GetX(),bb.GetY(),bb.GetRight(),bb.GetBottom()]]
    metrics[ref]=bounds
assert set(metrics)==references
out={'schema':1,'native_kicad_version':pcbnew.GetBuildVersion(),'font':'KiCad default stroke font',
    'font_height_mm':FONT,'font_width_mm':WIDTH,'stroke_mm':STROKE,
    'pad_mask_clearance_mm':.15,'label_clearance_mm':.15,'label_policy_version':5,
    'source':'https://jlcpcb.com/capabilities/pcb-capabilities/',
    'policy_note':'Use the main rigid-PCB capability table\'s 1.0 mm minimum text height and 0.15 mm stroke. JLCPCB\'s blog quotes 0.8 mm, which conflicts with the capability table; this project uses the standard capability limit.',
    'bounds_mm_by_reference_angle':metrics}
(ROOT/'reference/silkscreen-text-metrics.json').write_text(json.dumps(out,indent=2)+'\n')
print(f'Measured {len(metrics)} reference strings at {FONT} mm / {STROKE} mm using native KiCad {out["native_kicad_version"]}')

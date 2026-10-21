"""Measure schematic captions with KiCad's native stroke font.

Run with KiCad's bundled Python. This creates text objects in memory and
does not load or save the PCB or user application settings.
"""
from pathlib import Path
import json
import pcbnew

ROOT = Path(__file__).resolve().parents[1]
source = json.loads((ROOT/'reference/v240-netlist.json').read_text())
strings = set(source['parts']) | set(source['nets']) | {p['value'] for p in source['parts'].values()}
strings |= {ref+c for ref in source['parts'] for c in 'AB'}
metrics = {}
for value in sorted(strings):
    text = pcbnew.PCB_TEXT(None)
    text.SetText(value)
    text.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1), pcbnew.FromMM(1)))
    text.SetTextThickness(pcbnew.FromMM(.12))
    text.SetPosition(pcbnew.VECTOR2I(0, 0))
    bb = text.GetEffectiveTextShape().BBox()
    metrics[value] = [pcbnew.ToMM(v) for v in [bb.GetX(), bb.GetY(), bb.GetRight(), bb.GetBottom()]]
(ROOT/'reference/schematic-text-metrics.json').write_text(json.dumps({
    'native_kicad_version': pcbnew.GetBuildVersion(), 'font_height_mm':1,
    'stroke_mm':.12, 'bounds_mm':metrics}, indent=2)+'\n')
print(f'Measured {len(metrics)} strings with native KiCad {pcbnew.GetBuildVersion()}')

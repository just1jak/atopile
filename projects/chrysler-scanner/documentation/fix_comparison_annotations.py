"""Presentation-only repairs; preserve values, symbol pins and PCB bytes."""
from pathlib import Path
import sys, shutil, re, uuid

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P/'current/source'))
from specctra_tools import parse

def value(scope, name):
    return next(p for p in scope.children('property') if p.items[1].value == name)

def polarity(text, library_name):
    root = parse(text)
    libs = root.children('lib_symbols')
    symbols = libs[0].children('symbol') if libs else root.children('symbol')
    symbol = next(s for s in symbols if s.items[1].value == library_name)
    body = next(s for s in symbol.children('symbol') if s.items[1].value == 'C1_1_1')
    # Positive terminal is pin 1, on the upper plate in library coordinates.
    plus = '\n(polyline (pts (xy -3.6 3.2) (xy -1.8 3.2)) (stroke (width 0.254) (type default)) (fill (type none)))\n(polyline (pts (xy -2.7 2.3) (xy -2.7 4.1)) (stroke (width 0.254) (type default)) (fill (type none)))\n'
    return text[:body.end-1]+plus+text[body.end-1:]

changed=[]
for f in (P/'current').glob('*.kicad_sch'):
    text=f.read_text(encoding='utf-8'); edits=[]
    for s in parse(text).children('symbol'):
        ratings=[p for p in s.children('property') if p.items[1].value=='Voltage Rating']
        if not ratings: continue
        rating=ratings[0]; v=value(s,'Value'); at=v.children('at')[0]
        x,y=float(at.items[1].value),float(at.items[2].value)
        # A separate line below the value keeps the electrical value intact.
        replacement=f'(property "Voltage Rating" "{rating.items[2].value}" (at {x:g} {y+2.1:g} 0) (effects (font (size 1 1))))'
        edits.append((rating.start,rating.end,replacement))
    for a,b,r in sorted(edits,reverse=True): text=text[:a]+r+text[b:]
    if f.name=='07_vehicle-input.kicad_sch': text=polarity(text,'ChryslerScanner:C1')
    if f.name=='17_adc.kicad_sch':
        note='Rev C: 22k / (1.62k || 100k), nominal ADC/input gain = 0.06757.\\nCalibrate switch leakage/resistance, tolerances and ADC response.\\nV_BA senses protected +12V after D2; connector voltage needs diode-drop correction.\\nOriginal 8.66k divider conversion constants do not apply.'
        text=text.rstrip()[:-1]+f'\n(text "{note}" (at 16 172 0) (effects (font (size 1.15 1.15)) (justify left)) (uuid "{uuid.uuid5(uuid.NAMESPACE_URL,"chrysler/rev-c/adc-calibration-note")}"))\n)\n'
    if edits or f.name in ('07_vehicle-input.kicad_sch','17_adc.kicad_sch'):
        backup=P/'work/comparison-annotation-baseline'/f.name
        backup.parent.mkdir(parents=True,exist_ok=True)
        assert not backup.exists(), 'Do not apply twice'
        shutil.copy2(f,backup)
        newline='\r\n' if b'\r\n' in backup.read_bytes() else '\n'
        f.write_text(text,encoding='utf-8',newline=newline);changed.append(f.name)
lib=P/'current/ChryslerScanner.kicad_sym'
shutil.copy2(lib,P/'work/comparison-annotation-baseline'/lib.name)
lib.write_text(polarity(lib.read_text(encoding='utf-8'),'C1'),encoding='utf-8',newline='\n')
print(changed)

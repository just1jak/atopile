"""Render a native KiCad plot for inspecting the printed reference designators."""
from pathlib import Path
import shutil,subprocess
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
cli=shutil.which('kicad-cli') or '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
svg=ROOT/'renders/V240-silkscreen-preview.svg'
subprocess.run([cli,'pcb','export','svg','--mode-single','--layers','F.Cu,F.SilkS,Edge.Cuts',
    '--fit-page-to-board','--exclude-drawing-sheet','--output',str(svg),
    str(ROOT/'elec/layout/v240/v240.kicad_pcb')],check=True)
with pymupdf.open(svg) as doc:
    pdf=doc.convert_to_pdf()
with pymupdf.open('pdf',pdf) as doc:
    page=doc[0];scale=2200/page.rect.width
    page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False).save(ROOT/'renders/V240-silkscreen-preview.png')
print('Rendered native KiCad ink paths, pads and outline to SVG/PNG')

"""Attach bundled models and preserve native KiCad DNP flags after an ato build.

Only model expressions and the DNP attribute change. Circuit geometry, labels,
placement, nets, routes and layers remain untouched.
"""
from pathlib import Path
import json
import sexpdata as sx
from pcb_geometry import nodes,one,name

ROOT=Path(__file__).resolve().parents[1]
BOARD=ROOT/'elec/layout/v240/v240.kicad_pcb'
MANIFEST=ROOT/'reference/3d-models.json'
PREFIX='${KIPRJMOD}/../../src/3dmodels/'

def expression(spec):
    model=spec['model']
    return sx.loads('(model "'+PREFIX+model+'" '
        '(offset (xyz '+' '.join(map(str,spec.get('offset_mm',[0,0,0])))+')) '
        '(scale (xyz 1 1 1)) '
        '(rotate (xyz '+' '.join(map(str,spec.get('rotation_deg',[0,0,0])))+')))')

def set_model(fp,spec):
    fp[:]=[q for q in fp if name(q)!='model']
    if spec:fp.append(expression(spec))

def attach_models():
    source=json.loads((ROOT/'reference/v240-netlist.json').read_text())['parts']
    manifest=json.loads(MANIFEST.read_text()) if MANIFEST.exists() else None
    b=sx.loads(BOARD.read_text());count=0;dnp=[]
    for fp in nodes(b,'footprint'):
        ref=next(q[2] for q in nodes(fp,'property') if q[1]=='Reference')
        # Clean up the earlier unsupported (dnp yes) syntax too.
        fp[:]=[q for q in fp if name(q)!='dnp']
        attr=one(fp,'attr')
        if attr is None:attr=[sx.Symbol('attr')];fp.append(attr)
        attr[:]=[q for q in attr if q!=sx.Symbol('dnp')]
        if source.get(ref,{}).get('dnp'):
            attr.append(sx.Symbol('dnp'));dnp.append(ref)
        if manifest:
            spec=manifest['references'].get(ref)
            set_model(fp,spec)
            if spec:
                assert (ROOT/'elec/src/3dmodels'/spec['model']).is_file(),spec['model']
                count+=1
    text=sx.dumps(b)+'\n'
    if BOARD.read_text()!=text:BOARD.write_text(text)
    if manifest:
        for path in (ROOT/'elec/src/footprints').glob('*.kicad_mod'):
            fp=sx.loads(path.read_text())
            set_model(fp,manifest['footprints'].get(path.stem))
            # Avoid touching unchanged source libraries: an editor's source
            # watcher can otherwise enqueue another build after finishing.
            text=sx.dumps(fp)+'\n'
            if path.read_text()!=text:path.write_text(text)
    print(f'Attached {count} local 3D models; native DNP attributes: {", ".join(sorted(dnp))}')

if __name__=='__main__':attach_models()

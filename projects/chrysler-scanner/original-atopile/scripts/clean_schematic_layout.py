"""Readable native KiCad page layout without changing electrical objects.

Move entire connected drawing clusters together, including every symbol pin,
wire endpoint, junction and port. Only text placement is independent of the
electrical drawing. Native KiCad netlist export remains the final check.
"""
from collections import defaultdict
from pathlib import Path
from decimal import Decimal
import json
import math
import re
import sexpdata as sx
from shapely.geometry import box, LineString
from shapely.ops import unary_union

SCALE = 2.0
GRID = 1.27 * SCALE
ROOT = Path(__file__).resolve().parents[1]
METRICS = json.loads((ROOT/'reference/schematic-text-metrics.json').read_text())['bounds_mm']


def prepare_footprints(output):
    """Normalize a viewing library without modifying atopile's PCB packages."""
    output.mkdir(exist_ok=True)
    converted_arcs = 0
    files = []
    for path in sorted((ROOT/'elec/src/footprints').glob('*.kicad_mod')):
        doc = sx.loads(path.read_text())
        for e in doc:
            if tag(e) == 'fp_arc' and one(e, 'mid') is not None:
                # Native KiCad requires start/mid/end in this order.
                coords = [one(e, k) for k in ('start', 'mid', 'end')]
                if e[1:4] != coords:
                    converted_arcs += 1
                e[1:] = coords+[q for q in e[1:] if tag(q) not in ('start', 'mid', 'end')]
            elif tag(e) == 'model':
                e[1] = e[1].replace('${KIPRJMOD}/../../src/3dmodels/', '${KIPRJMOD}/../src/3dmodels/')
        data = sx.dumps(doc)
        data = re.sub(r'(?<=[ (])[-+]?(?:\d+\.\d*|\d*\.\d+|\d+)[eE][-+]?\d+(?=[ )])',
                      lambda m: format(Decimal(m.group()), 'f'), data)
        assert sx.loads(data) == doc, path
        (output/path.name).write_text(data+'\n')
        files.append(path.name)
    (ROOT/'reference/schematic-library-preparation.json').write_text(json.dumps({
        'status':'PASS', 'viewing_library':output.relative_to(ROOT).as_posix(),
        'footprint_files':len(files), 'arc_fields_reordered_for_native_parser':converted_arcs,
        'all_geometry_pad_and_model_transform_parameters_preserved':True,
        'authoritative_pcb_package_files_unchanged':True,
        'model_path_prefix':'${KIPRJMOD}/../src/3dmodels/',
        'files':files}, indent=2)+'\n')


def tag(e):
    return str(e[0]) if isinstance(e, list) and e else ''


def one(e, key):
    return next((q for q in e if tag(q) == key), None)


def point(e):
    return tuple(round(float(v), 5) for v in e[1:3])


def font(e, size):
    one(one(one(e, 'effects'), 'font'), 'size')[1:] = [size, size]


def shift(e, dx, dy):
    """Only sheet-space coordinates; embedded library coordinates stay local."""
    for q in e[1:]:
        if tag(q) in ('at', 'xy'):
            q[1:3] = [round(float(q[1])+dx, 6), round(float(q[2])+dy, 6)]
        elif tag(q) in ('property', 'pts'):
            shift(q, dx, dy)


def scale(e):
    for q in e[1:]:
        if not isinstance(q, list):
            continue
        if tag(q) in ('at', 'xy', 'start', 'end', 'center', 'size'):
            q[1:3] = [round(float(v)*SCALE, 6) for v in q[1:3]]
        elif tag(q) in ('length', 'width', 'radius', 'diameter'):
            q[1] = round(float(q[1])*SCALE, 6)
        else:
            scale(q)
    # Enlarge circuit geometry onto a standard 50 mil connection grid while
    # keeping text at familiar schematic sizes.
    if tag(e) == 'text':
        font(e, 1.4)
    if tag(e) == 'pin' and one(e, 'number') is not None:
        for key in ('name', 'number'):
            font(one(e, key), 1.1)


def extent(value, size):
    b = METRICS.get(value)
    # The schematic renderer spaces stroke-font glyphs a little wider than
    # PCB text. Allow extra room verified against native SVG textLength.
    return (((b[2]-b[0])*size*1.10+.3) if b else len(value)*size*.9, size*1.3)


def centered_text(value, size, x, y):
    w, h = extent(value, size)
    return box(x-w/2-.15, y-h/2-.15, x+w/2+.15, y+h/2+.15)


def port_box(label, x=None, y=None, angle=None):
    at = one(label, 'at')
    x, y = point(at) if x is None else (x, y)
    angle = at[3] if angle is None else angle
    w, h = extent(label[1], 1.27)
    w += 3.2
    return box(x-w, y-h/2-.15, x-.15, y+h/2+.15) if angle == 180 else box(x+.15, y-h/2-.15, x+w, y+h/2+.15)


class Union:
    def __init__(self):
        self.p = {}

    def root(self, p):
        self.p.setdefault(p, p)
        if self.p[p] != p:
            self.p[p] = self.root(self.p[p])
        return self.p[p]

    def join(self, a, b):
        self.p[self.root(a)] = self.root(b)


def clean_page(doc, gid, units, source):
    # Remove the old page furniture; all circuit objects are retained.
    doc[:] = [e for e in doc if tag(e) != 'text']
    for e in doc:
        if tag(e) in ('lib_symbols', 'symbol', 'wire', 'junction', 'global_label', 'no_connect'):
            scale(e)
        if tag(e) == 'global_label':
            font(e, 1.27)
        if tag(e) == 'symbol':
            for p in e:
                if tag(p) == 'property':
                    font(p, 1.27)
    circuit = [e for e in doc if tag(e) in ('symbol', 'wire', 'junction', 'global_label', 'no_connect')]
    symbols = [e for e in circuit if tag(e) == 'symbol']
    wires = [e for e in circuit if tag(e) == 'wire']
    ports = [e for e in circuit if tag(e) == 'global_label']
    libraries = {e[1].split(':')[-1]: e for e in one(doc, 'lib_symbols')[1:]}
    bodies, pins, ref_by_symbol = {}, {}, {}
    pin_lines = []
    for i, e in enumerate(symbols):
        ref = one(e, 'lib_id')[1].split(':')[-1]
        num = one(e, 'unit')[1]
        ref_by_symbol[i] = ref
        lib = next(q for q in libraries[ref] if tag(q) == 'symbol' and q[1] == f'{ref}_{num}_1')
        x, y = point(one(e, 'at'))
        shapes = []
        pins[i] = []
        for q in lib:
            if tag(q) == 'polyline':
                ps = [(x+float(p[1]), y-float(p[2])) for p in one(q, 'pts')[1:]]
                shapes.append(LineString(ps).buffer(.15))
            elif tag(q) == 'rectangle':
                a, b = one(q, 'start'), one(q, 'end')
                shapes.append(box(min(x+a[1], x+b[1]), min(y-a[2], y-b[2]), max(x+a[1], x+b[1]), max(y-a[2], y-b[2])))
            elif tag(q) == 'pin':
                at = one(q, 'at'); a = (round(x+at[1], 5), round(y-at[2], 5))
                pins[i].append(a)
                length = one(q, 'length')[1]; angle = math.radians(at[3])
                b = (a[0]+length*math.cos(angle), a[1]-length*math.sin(angle))
                # Leave room for native pin-number text beside the conductor.
                pin_lines.append(LineString([a, b]).buffer(.75))
        bodies[i] = unary_union(shapes).envelope

    # Electrical roots do not join across a symbol. Drawing clusters do.
    electrical = Union()
    for e in wires:
        a, b = [point(q) for q in one(e, 'pts')[1:]]
        electrical.join(a, b)
    for ps in pins.values():
        for p in ps:
            electrical.root(p)
    unique_ports = []
    seen = set()
    for e in ports:
        p = point(one(e, 'at')); key = (electrical.root(p), e[1])
        if key in seen:
            doc.remove(e); circuit.remove(e)
        else:
            unique_ports.append(e); seen.add(key)
    removed_ports = len(ports)-len(unique_ports)
    ports = unique_ports
    obstacles = unary_union(list(bodies.values())+pin_lines).buffer(.25)
    wire_shapes = [(e, LineString([point(q) for q in one(e, 'pts')[1:]]).buffer(.12)) for e in wires]
    occupied_ports = []
    all_wire_shapes = unary_union([shape for _,shape in wire_shapes])
    label_moves = 0
    for e in ports:
        old = point(one(e, 'at')); eroot = electrical.root(old)
        candidates = {old}
        for w in wires:
            ps = [point(q) for q in one(w, 'pts')[1:]]
            if electrical.root(ps[0]) == eroot:
                candidates.update(ps)
        # Keep every conductor clear of the port text, including its own net.
        blocked = unary_union([obstacles, all_wire_shapes, *occupied_ports])
        best = None
        for p in sorted(candidates):
            for angle in (0, 180):
                shape = port_box(e, *p, angle)
                overlap = shape.intersection(blocked).area
                score = overlap*10000 + math.dist(p, old) + (0 if angle == one(e, 'at')[3] else .4)
                item = (score, p, angle, shape)
                if best is None or score < best[0]:
                    best = item
        _, p, angle, shape = best
        if p != old or angle != one(e, 'at')[3]:
            label_moves += 1
        one(e, 'at')[1:] = [*p, angle]
        justify = one(one(e, 'effects'), 'justify')
        justify[1:] = [sx.Symbol('right' if angle == 180 else 'left')]
        # Hidden intersheet field follows its port anchor.
        for prop in e:
            if tag(prop) == 'property':
                one(prop, 'at')[1:3] = list(p)
        occupied_ports.append(shape)

    # Cropping and duplicate-port removal can leave unused wire tails.
    # Prune only leaves without pins or labels; connected terminals stay put.
    protected = {p for ps in pins.values() for p in ps}
    protected.update(point(one(e, 'at')) for e in ports)
    pruned_wires = 0
    while True:
        degree = defaultdict(int)
        for e in wires:
            for p in one(e, 'pts')[1:]:
                degree[point(p)] += 1
        tails = [e for e in wires if any(degree[point(p)] == 1 and point(p) not in protected for p in one(e, 'pts')[1:])]
        if not tails:
            break
        for e in tails:
            doc.remove(e); circuit.remove(e); wires.remove(e)
        pruned_wires += len(tails)
    wire_shapes = [(e, LineString([point(q) for q in one(e, 'pts')[1:]]).buffer(.12)) for e in wires]

    # Reference/value pairs occupy free space beside small vertical devices.
    # The exact symbol/package values remain unmodified.
    blocked = unary_union([obstacles, *[shape for _, shape in wire_shapes], *occupied_ports])
    captions = []
    caption_moves = 0
    caption_collisions = []
    for i in sorted(range(len(symbols)), key=lambda i: (not ref_by_symbol[i].startswith('U'), ref_by_symbol[i])):
        e = symbols[i]; ref = ref_by_symbol[i]; num = one(e, 'unit')[1]
        props = {p[1]: p for p in e if tag(p) == 'property'}
        shown_ref = ref + (chr(64+num) if len(units[ref]) > 1 else '')
        value = props['Value'][2]
        size = 1.27; rw, _ = extent(shown_ref, size); vw, _ = extent(value, size); cw = max(rw, vw)
        x0, y0, x1, y1 = bodies[i].bounds; cx, cy = (x0+x1)/2, (y0+y1)/2
        candidates = []
        vertical = y1-y0 > x1-x0+1
        primary = [(x1+cw/2+1.2, cy-1.15), (x0-cw/2-1.2, cy-1.15)] if vertical and not ref.startswith(('U', 'J')) else []
        primary += [(cx, y0-3.8), (cx, y1+1.7)]
        primary += [(x1+cw/2+1.2, cy-1.15), (x0-cw/2-1.2, cy-1.15)]
        for x, y in primary:
            for delta in (0, -1.27, 1.27, -2.54, 2.54, -5.08, 5.08, -7.62, 7.62, -10.16, 10.16, -12.7, 12.7, -15.24, 15.24, -20.32, 20.32):
                candidates.append((x, y+delta))
        best = None
        field_obstacles = unary_union([blocked, *captions])
        for rank, (x, y) in enumerate(candidates):
            shape = unary_union([centered_text(shown_ref, size, x, y), centered_text(value, size, x, y+2.1)]).envelope
            overlap = shape.intersection(field_obstacles).area
            score = overlap*100000 + shape.distance(bodies[i])*2 + rank*.07
            if best is None or score < best[0]:
                best = (score, x, y, shape, overlap)
        _, x, y, shape, overlap = best
        if overlap > .01:
            caption_collisions.append({'ref':shown_ref, 'estimated_overlap_mm2':round(overlap, 4)})
        for key, yy in [('Reference', y), ('Value', y+2.1)]:
            if point(one(props[key], 'at')) != (x, yy):
                caption_moves += 1
            one(props[key], 'at')[1:3] = [round(x, 6), round(yy, 6)]
        captions.append(shape)

    clusters = Union()
    for w in wires:
        a, b = [point(q) for q in one(w, 'pts')[1:]]
        clusters.join(a, b)
    for i, ps in pins.items():
        for p in ps:
            clusters.join(ps[0], p)
    objects, geometry, refs = defaultdict(list), defaultdict(list), defaultdict(set)
    for i, e in enumerate(symbols):
        c = clusters.root(pins[i][0]); objects[c].append(e); geometry[c].append(bodies[i]); refs[c].add(ref_by_symbol[i])
        for key, value in [('Reference', ref_by_symbol[i]+(chr(64+one(e, 'unit')[1]) if len(units[ref_by_symbol[i]]) > 1 else '')), ('Value', source['parts'][ref_by_symbol[i]]['value'])]:
            prop = next(p for p in e if tag(p) == 'property' and p[1] == key)
            geometry[c].append(centered_text(value, 1.27, *point(one(prop, 'at'))))
        for p in pins[i]:
            geometry[c].append(box(p[0]-.3, p[1]-.3, p[0]+.3, p[1]+.3))
    for e in circuit:
        if tag(e) == 'symbol':
            continue
        if tag(e) == 'wire':
            ps = [point(q) for q in one(e, 'pts')[1:]]; c = clusters.root(ps[0]); shape = LineString(ps).buffer(.2)
        else:
            p = point(one(e, 'at')); c = clusters.root(p)
            shape = port_box(e) if tag(e) == 'global_label' else box(p[0]-.5, p[1]-.5, p[0]+.5, p[1]+.5)
        objects[c].append(e); geometry[c].append(shape)
    boxes = {c: unary_union(shapes).bounds for c, shapes in geometry.items()}
    # Stable functional order, with USB receptacle and both CC terminations first.
    usb_order = ['J2', 'R102', 'R103', 'U11', 'U1', 'U12', 'R25', 'Q5', 'SW1', 'SW2']
    def order(c):
        if gid == 'usb':
            return (min([usb_order.index(r) for r in refs[c] if r in usb_order] or [100]), boxes[c][1], boxes[c][0])
        return (boxes[c][1], boxes[c][0])
    ordered = sorted(objects, key=order)
    def pack(width):
        positions = {}; x, y, row_h = 16, 40, 0
        for c in ordered:
            x0, y0, x1, y1 = boxes[c]; w, h = x1-x0, y1-y0
            if x+w > width-16 and x > 16:
                x, y = 16, y+row_h+12; row_h = 0
            dx = math.ceil((x-x0)/GRID)*GRID; dy = math.ceil((y-y0)/GRID)*GRID
            positions[c] = (dx, dy)
            x = x1+dx+12; row_h = max(row_h, y1+dy-y)
        return positions, y+row_h
    def pack_compact(width):
        """Fill space beside tall ICs rather than carrying their full row height."""
        positions, placed = {}, []
        for c in sorted(ordered, key=lambda c: (-(boxes[c][3]-boxes[c][1]), order(c))):
            x0, y0, x1, y1 = boxes[c]; w, h = x1-x0, y1-y0
            xs = [16]+[b[2]+12 for b in placed]
            ys = [40]+[b[3]+12 for b in placed]
            choices = []
            for x in xs:
                for y in ys:
                    dx = math.ceil((x-x0)/GRID)*GRID; dy = math.ceil((y-y0)/GRID)*GRID
                    bounds = (x0+dx, y0+dy, x1+dx, y1+dy)
                    if bounds[2] > width-16:
                        continue
                    if any(box(*bounds).intersects(box(b[0]-6, b[1]-6, b[2]+6, b[3]+6)) for b in placed):
                        continue
                    bottom = max([bounds[3]]+[b[3] for b in placed])
                    choices.append((bottom, bounds[1], bounds[0], dx, dy, bounds))
            assert choices, (gid,c,w,width)
            _, _, _, dx, dy, bounds = min(choices)
            positions[c] = (dx,dy);placed.append(bounds)
        return positions, max(b[3] for b in placed)
    width, height = 297, 210
    positions, bottom = pack(width)
    if max(b[2]-b[0] for b in boxes.values()) > width-32 or bottom > height-50:
        width, height = 420, 297
        positions, bottom = pack(width)
    if bottom >= height-45:
        positions, bottom = pack_compact(width)
    assert bottom < height-45, (gid, bottom, height)
    for c, items in objects.items():
        for e in items:
            shift(e, *positions[c])
    paper = one(doc, 'paper'); paper[1:] = ['A4' if width == 297 else 'A3']
    return {'size_mm':[width, height], 'clusters':len(objects), 'content_bottom_mm':round(bottom, 2),
            'reference_value_fields_repositioned':caption_moves, 'ports_repositioned':label_moves,
            'redundant_ports_removed':removed_ports, 'unused_wire_tails_removed':pruned_wires,
            'estimated_caption_collisions':caption_collisions,
            'circuit_scale':SCALE, 'page_format':'A4' if width == 297 else 'A3'}

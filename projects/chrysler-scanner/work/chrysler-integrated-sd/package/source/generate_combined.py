"""Create an additive native SD schematic revision without modifying its base.

The audited base JSON is authoritative for pin connectivity. The saved native
schematic is retained, except project naming, MCU NC additions and three stale
TLV767 ground pins. No board placement, routing, or firmware is generated here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import uuid
from collections import defaultdict
from pathlib import Path

import sexpdata as sx

HERE = Path(__file__).resolve().parents[1]
DEFAULT_BASE = Path('/Users/justinkobely/Downloads/ChryslerCCDSCIScanner_V140')
DEFAULT_MANIFEST = HERE.parent / 'integration.json'
LIBRARIES = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols')
S = sx.Symbol


def node(key, *values):
    return [S(key), *values]


def key(value):
    return str(value[0]) if isinstance(value, list) and value else ''


def first(value, name):
    return next((v for v in value if key(v) == name), None)


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'chrysler-v240-schematic/' + name))


def effects(size=1.1, hidden=False, justify=None):
    result = node('effects', node('font', node('size', size, size)))
    if hidden:
        result.append(S('hide'))
    if justify:
        result.append(node('justify', S(justify)))
    return result


def prop(name, value, x, y, hidden=False, size=1.1):
    return node('property', name, value, node('at', x, y, 0), effects(size, hidden))


def text(doc, identity, value, x, y, size=1.1):
    doc.append(node('text', value, node('at', x, y, 0), effects(size, justify='left'), node('uuid', uid(identity))))


def wire(doc, identity, a, b):
    doc.append(node('wire', node('pts', node('xy', *a), node('xy', *b)),
                    node('stroke', node('width', 0), node('type', S('default'))), node('uuid', uid(identity))))


def label(doc, identity, name, at, angle, hidden=False):
    doc.append(node('global_label', name, node('shape', S('input')), node('at', *at, angle),
                    effects(0.95, hidden=hidden, justify='right' if angle == 180 else 'left'), node('uuid', uid(identity)),
                    prop('Intersheetrefs', '${INTERSHEET_REFS}', *at, hidden=True, size=0.95)))


def attach(doc, identity, name, at, orientation, distance=7.62):
    # Pin orientations point into their symbol. Extend in the opposite direction.
    angle = math.radians(orientation)
    endpoint = (round(at[0] - distance * math.cos(angle), 6),
                round(at[1] + distance * math.sin(angle), 6))
    wire(doc, identity + '/wire', at, endpoint)
    label(doc, identity + '/net', name, endpoint, 180 if endpoint[0] < at[0] - 0.01 else 0)


def rename_project(doc, old, new):
    if not isinstance(doc, list):
        return
    if key(doc) == 'project' and len(doc) > 1 and doc[1] == old:
        doc[1] = new
    for child in doc:
        rename_project(child, old, new)


def library_pins(lib, unit):
    result = {}
    for child in lib:
        if key(child) != 'symbol':
            continue
        suffix = str(child[1]).rsplit('_', 2)
        if len(suffix) != 3 or int(suffix[1]) not in (0, unit):
            continue
        for pin in child:
            if key(pin) == 'pin':
                result[str(first(pin, 'number')[1])] = pin
    return result


def pin_on_sheet(instance, pin):
    placement = first(instance, 'at')
    local = first(pin, 'at')
    assert first(instance, 'mirror') is None, 'Mirrored base symbol needs explicit transform review'
    angle = math.radians(float(placement[3]))
    x = float(local[1]) * math.cos(angle) - float(local[2]) * math.sin(angle)
    y = -(float(local[1]) * math.sin(angle) + float(local[2]) * math.cos(angle))
    return (round(float(placement[1]) + x, 6), round(float(placement[2]) + y, 6)), (float(local[3]) + float(placement[3])) % 360


def connect_previously_nc(doc, ref, number, net):
    definitions = {v[1]: v for v in first(doc, 'lib_symbols')[1:] if key(v) == 'symbol'}
    matches = []
    for instance in doc:
        if key(instance) != 'symbol':
            continue
        reference = next((v[2] for v in instance if key(v) == 'property' and v[1] == 'Reference'), None)
        if reference != ref:
            continue
        pins = library_pins(definitions[first(instance, 'lib_id')[1]], int(first(instance, 'unit')[1]))
        if number in pins:
            matches.append((instance, pins[number]))
    assert len(matches) == 1, (ref, number, len(matches))
    at, orientation = pin_on_sheet(*matches[0])
    markers = [v for v in doc if key(v) == 'no_connect' and
               math.dist([float(q) for q in first(v, 'at')[1:3]], at) < 0.001]
    assert len(markers) == 1, (ref, number, 'Expected one original NC marker')
    doc.remove(markers[0])
    attach(doc, 'sd-revision/' + ref + '/' + number, net, at, orientation,
           12.7 if ref == 'U10' else 7.62)


def preserve_anonymous_net_names(docs, expected):
    """Keep established PCB net names without changing electrical connections.

    The recovered base had unnamed native wires although its PCB used N_* names.
    KiCad's parity checker compares names as well as endpoints. A hidden global
    label on one existing electrical pin preserves each established PCB name.
    KiCad stores the hide flag but its PDF plotter still prints these labels.
    """
    pins = {}
    for filename, doc in docs.items():
        definitions = {v[1]: v for v in first(doc, 'lib_symbols')[1:] if key(v) == 'symbol'}
        for instance in doc:
            if key(instance) != 'symbol':
                continue
            ref = next(v[2] for v in instance if key(v) == 'property' and v[1] == 'Reference')
            definition = definitions[first(instance, 'lib_id')[1]]
            for number, pin in library_pins(definition, int(first(instance, 'unit')[1])).items():
                pins[(ref, number)] = (doc, *pin_on_sheet(instance, pin))
    count = 0
    for name, endpoints in expected['nets'].items():
        if not name.startswith('N_'):
            continue
        doc, at, orientation = pins[tuple(endpoints[0])]
        label(doc, 'preserved-net-name/' + name, name, at,
              180 if orientation % 360 == 0 else 0, hidden=True)
        count += 1
    return count


def align_preserved_board_metadata(docs, pcb):
    """Align recovered symbol metadata with the unchanged existing footprints."""
    footprints = {}
    for footprint in pcb:
        if key(footprint) != 'footprint':
            continue
        properties = {v[1]: v[2] for v in footprint if key(v) == 'property'}
        if 'Reference' not in properties:
            continue
        attributes = first(footprint, 'attr') or []
        footprints[properties['Reference']] = (properties.get('atopile_address'),
                                               S('exclude_from_bom') not in attributes)
    changed = set()
    for doc in docs.values():
        for instance in doc:
            if key(instance) != 'symbol':
                continue
            ref = next(v[2] for v in instance if key(v) == 'property' and v[1] == 'Reference')
            if ref not in footprints:
                continue
            address, in_bom = footprints[ref]
            previous = next((v for v in instance if key(v) == 'property' and v[1] == 'atopile_address'), None)
            if previous is not None and previous[2] != address:
                if address is None:
                    instance.remove(previous)
                else:
                    previous[2] = address
                changed.add(ref)
            first(instance, 'in_bom')[1] = S('yes' if in_bom else 'no')
    return sorted(changed)


def load_standard(library, name, cache):
    if library not in cache:
        document = sx.loads((LIBRARIES / (library + '.kicad_sym')).read_text())
        cache[library] = {v[1]: v for v in document if key(v) == 'symbol'}
    symbol = copy.deepcopy(cache[library][name])
    assert first(symbol, 'extends') is None, (library, name, 'Inherited symbol must be flattened explicitly')
    return symbol


def set_property(symbol, name, value, x, y, hidden=False):
    previous = next((v for v in symbol if key(v) == 'property' and v[1] == name), None)
    if previous:
        symbol.remove(previous)
    symbol.append(prop(name, value, x, y, hidden))


def add_standard(doc, local, part, at, angle, root_id, project, cache):
    ref = part['ref']
    lib, name = part['symbol'].split(':', 1)
    definition = load_standard(lib, name, cache)
    original_name = definition[1]
    definition[1] = 'SDLogger:' + ref
    for child in definition:
        if key(child) == 'symbol':
            child[1] = ref + str(child[1])[len(original_name):]
    set_property(definition, 'Reference', ''.join(c for c in ref if not c.isdigit()), 0, 5.08)
    set_property(definition, 'Value', part['value'], 0, 2.54)
    set_property(definition, 'Footprint', part['footprint'], 0, 0, True)
    set_property(definition, 'Description', part.get('description', ''), 0, 0, True)
    first(doc, 'lib_symbols').append(copy.deepcopy(definition))
    copy_for_library = copy.deepcopy(definition)
    copy_for_library[1] = ref
    local.append(copy_for_library)
    identity = 'sd-logger/' + ref + '/1'
    symbol = node('symbol', node('lib_id', 'SDLogger:' + ref), node('at', *at, angle), node('unit', 1),
                  node('exclude_from_sim', S('no')), node('in_bom', S('yes')), node('on_board', S('yes')),
                  node('dnp', S('no')), node('uuid', uid(identity)))
    # User-visible fields remain horizontal regardless of symbol orientation.
    if ref.startswith('R'):
        if angle == 90:
            field_points = ((at[0], at[1] - 5.08), (at[0], at[1] - 2.54))
        else:
            field_points = ((at[0] + 5.08, at[1] - 1.27), (at[0] + 5.08, at[1] + 1.27))
    elif ref.startswith('C'):
        field_points = ((at[0] + 5.08, at[1] - 1.27), (at[0] + 5.08, at[1] + 1.27))
    else:
        field_points = ((at[0], at[1] - (22.86 if ref == 'J4' else 10.16)),
                        (at[0], at[1] - (20.32 if ref == 'J4' else 7.62)))
    symbol.extend([prop('Reference', ref, *field_points[0]), prop('Value', part['value'], *field_points[1]),
                   prop('Footprint', part['footprint'], *at, hidden=True),
                   prop('Datasheet', '', *at, hidden=True),
                   prop('Manufacturer', part['manufacturer'], *at, hidden=True),
                   prop('MPN', part['mpn'], *at, hidden=True)])
    # Native KiCad interprets field orientation relative to a rotated instance.
    # Counter the 90-degree resistor rotation so its reference/value plot level.
    if angle == 90:
        for field in symbol:
            if key(field) == 'property' and field[1] in ('Reference', 'Value'):
                first(field, 'at')[3] = 90
    pins = library_pins(definition, 1)
    assert set(pins) == set(part['nets']), (ref, set(pins), set(part['nets']))
    for number in pins:
        symbol.append(node('pin', number, node('uuid', uid(identity + '/pin/' + number))))
    symbol.append(node('instances', node('project', project, node('path', '/' + root_id + '/' + uid('sd-logger'),
        node('reference', ref), node('unit', 1)))))
    doc.append(symbol)
    for number, pin in pins.items():
        pin_at, direction = pin_on_sheet(symbol, pin)
        attach(doc, identity + '/pin/' + number, part['nets'][number], pin_at, direction)
    return symbol


def add_power_flag(doc, net, at, root_id, project, cache, index):
    definition = load_standard('power', 'PWR_FLAG', cache)
    if not any(key(s) == 'symbol' and s[1] == 'power:PWR_FLAG' for s in first(doc, 'lib_symbols')):
        definition[1] = 'power:PWR_FLAG'
        first(doc, 'lib_symbols').append(definition)
    identity = 'sd-logger/power-flag/' + net
    instance = node('symbol', node('lib_id', 'power:PWR_FLAG'), node('at', *at, 0), node('unit', 1),
                    node('exclude_from_sim', S('no')), node('in_bom', S('no')), node('on_board', S('no')),
                    node('dnp', S('no')), node('uuid', uid(identity)),
                    prop('Reference', '#FLG' + str(index), at[0], at[1] - 7.62, True),
                    prop('Value', 'PWR_FLAG', at[0], at[1] - 5.08),
                    node('pin', '1', node('uuid', uid(identity + '/pin/1'))),
                    node('instances', node('project', project, node('path', '/' + root_id + '/' + uid('sd-logger'),
                         node('reference', '#FLG' + str(index)), node('unit', 1)))))
    doc.append(instance)
    attach(doc, identity, net, at, 90)


def generate(base, manifest_path, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'reference').mkdir(exist_ok=True)
    manifest = json.loads(manifest_path.read_text())
    project = manifest['project']
    expected = json.loads((base / 'reference/v240-netlist.json').read_text())
    baseline = copy.deepcopy(expected)
    expected['hardware_revision'] = manifest['revision']
    expected['local_hardware_overrides'] = 'reference/integration.json'
    for pin, change in manifest['mcu_additions'].items():
        old = expected['parts']['U10']['pins'][pin]
        assert old['net'] is None and old.get('no_connect'), pin
        old.update(net=change['net'], no_connect=False, origin='Integrated SD revision: ' + change['function'])
    for part in manifest['parts']:
        assert part['ref'] not in expected['parts']
        expected['parts'][part['ref']] = dict(ref=part['ref'], value=part['value'],
            footprint=part['footprint'], manufacturer=part['manufacturer'], orderable_hint=part['mpn'],
            dnp=False, units=[part['ref']], package_note=part['description'],
            pins={n: dict(net=net, no_connect=False, origin='Integrated SD revision') for n, net in part['nets'].items()})
    nets = defaultdict(list)
    for ref, part in expected['parts'].items():
        for number, pin in part['pins'].items():
            if pin['net']:
                nets[pin['net']].append([ref, number])
    expected['nets'] = dict(nets)
    for ref in ('U3', 'U4', 'U8'):
        assert expected['parts'][ref]['pins']['5']['net'] == 'GND'
    for ref, part in baseline['parts'].items():
        for number, pin in part['pins'].items():
            if ref == 'U10' and number in manifest['mcu_additions']:
                continue
            assert expected['parts'][ref]['pins'][number]['net'] == pin['net'], (ref, number)
    (output / 'reference/v240-netlist.json').write_text(json.dumps(expected, indent=2, ensure_ascii=False) + '\n')
    shutil.copy2(manifest_path, output / 'reference/integration.json')
    schematics = base / 'elec/schematic'
    docs = {p.name: sx.loads(p.read_text()) for p in schematics.glob('*.kicad_sch')}
    root = docs.pop('ChryslerScanner_V240.kicad_sch')
    root_id = first(root, 'uuid')[1]
    docs[project + '.kicad_sch'] = root
    for doc in docs.values():
        rename_project(doc, 'ChryslerScanner_V240', project)
    metadata_aligned = align_preserved_board_metadata(docs,
        sx.loads((base / 'elec/layout/v240/v240.kicad_pcb').read_text()))
    for ref, filename in [('U3', '08_power-5v.kicad_sch'), ('U4', '08_power-5v.kicad_sch'), ('U8', '11_power-7v5.kicad_sch')]:
        connect_previously_nc(docs[filename], ref, '5', 'GND')
    for pin, change in manifest['mcu_additions'].items():
        connect_previously_nc(docs['16_mcu.kicad_sch'], 'U10', pin, change['net'])
    preserved_net_labels = preserve_anonymous_net_names(docs, baseline)
    text(docs['16_mcu.kicad_sch'], 'sd-revision/mcu-note',
         'SD revision: GPIO19/20 SPI, GPIO36 MISO, GPIO15 CS, GPIO37 button, GPIO38 detect. Firmware deferred.',
         16, 252, 1.05)

    sd = node('kicad_sch', node('version', 20250114), node('generator', 'eeschema'), node('generator_version', '10.0'),
              node('uuid', uid('sd-logger')), node('paper', S('A3')),
              node('title_block', node('title', 'Integrated microSD logging hardware'), node('date', '2026-10-20'),
                   node('rev', 'V240-SD-A'), node('company', 'ChryslerScanner / local hardware revision')), node('lib_symbols'))
    local = node('kicad_symbol_lib', node('version', 20241209), node('generator', 'kicad_symbol_editor'))
    placements = {'U20': ((71.12, 66.04), 0), 'J4': ((322.58, 66.04), 0),
                  'C58': ((33.02, 88.90), 0), 'C59': ((109.22, 88.90), 0),
                  'C60': ((147.32, 88.90), 0), 'C61': ((185.42, 88.90), 0),
                  'R104': ((71.12, 139.70), 90), 'R105': ((71.12, 160.02), 90), 'R106': ((71.12, 180.34), 90),
                  'R107': ((180.34, 144.78), 0), 'R108': ((218.44, 144.78), 0),
                  'R109': ((256.54, 144.78), 0), 'R110': ((294.64, 144.78), 0),
                  'R111': ((332.74, 144.78), 0), 'R112': ((370.84, 144.78), 0),
                  'R113': ((40.64, 223.52), 0), 'SW3': ((91.44, 241.30), 0),
                  'R114': ((180.34, 223.52), 0)}
    cache = {}
    for part in manifest['parts']:
        add_standard(sd, local, part, *placements[part['ref']], root_id, project, cache)
    add_power_flag(sd, '+5V', (218.44, 91.44), root_id, project, cache, 101)
    add_power_flag(sd, 'GND', (256.54, 91.44), root_id, project, cache, 102)
    for identity, caption, x, y, size in [
        ('heading', 'On-board microSD logger (SPI)', 16, 18, 2.6),
        ('subtitle', 'Existing ESP32-PICO-V3-02 | removable storage | native scanner functions retained | firmware deferred', 16, 26, 1.15),
        ('power-heading', 'Dedicated 3.3 V SD supply from the existing +5 V rail', 20, 42, 1.35),
        ('socket-heading', 'J4: Hirose DM3AT-SF-PEJM5 / SPI mode', 260, 35, 1.35),
        ('spi-heading', 'MCU-side series damping', 20, 119, 1.35),
        ('pu-heading', 'SD CMD/DAT pull-ups / MCU CS strap bias', 165, 119, 1.35),
        ('button-heading', 'Active-low record / safe-stop input', 20, 203, 1.35),
        ('detect-heading', 'Card-detect input', 150, 203, 1.35),
        ('note1', 'GPIO15 CS is biased high at reset; GPIO12 and GPIO2 remain unused.', 245, 211, 1.05),
        ('note2', 'GPIO36/37/38 are input-only and have external pull-ups.', 245, 217, 1.05),
        ('note3', 'GPIO20 is package-specific; use ESP-IDF support for ESP32-PICO-V3.', 245, 223, 1.05),
        ('note4', 'SD rail transient current and total +5 V budget need hardware validation.', 245, 229, 1.05),
        ('note5', 'Bulk capacitance is not a safe-power-off hold-up supply.', 245, 235, 1.05),
        ('note6', 'Firmware deferred: this hardware revision does not yet record data.', 245, 241, 1.05),
        ('note7', 'Future status indication reuses existing ACT_LED / GPIO13.', 245, 247, 1.05),
        ('scope', 'Existing sheets use passive visualization pins; native ERC is not independent certification of the scanner circuit.', 16, 274, 1.0),
    ]:
        text(sd, 'sd-logger/' + identity, caption, x, y, size)
    docs['22_sd-logger.kicad_sch'] = sd
    root.append(node('sheet', node('at', 0, 0), node('size', 90, 18), node('stroke', node('width', 0), node('type', S('default'))),
        node('fill', node('color', 0, 0, 0, 0)), node('uuid', uid('sd-logger')),
        prop('Sheetname', 'Integrated SD logger', 0, 0), prop('Sheetfile', '22_sd-logger.kicad_sch', 0, 0),
        node('instances', node('project', project, node('path', '/' + root_id, node('page', '23'))))))
    sheets = [s for s in root if key(s) == 'sheet']
    assert len(sheets) == 22
    for i, sheet in enumerate(sheets):
        at = first(sheet, 'at')
        oldx, oldy = float(at[1]), float(at[2])
        x, y = 18 + (i % 4) * 98, 42 + (i // 4) * 31
        at[1:] = [x, y]
        first(sheet, 'size')[1:] = [90, 18]
        for name, yy in [('Sheetname', y - 1), ('Sheetfile', y + 20)]:
            property_ = next(v for v in sheet if key(v) == 'property' and v[1] == name)
            first(property_, 'at')[1:3] = [x, yy]
        if i < 21:
            for note_ in root:
                if key(note_) == 'text' and 'parts / page ' in str(note_[1]):
                    oldat = first(note_, 'at')
                    if abs(float(oldat[1]) - oldx - 4) < 0.001 and abs(float(oldat[2]) - oldy - 10) < 0.001:
                        oldat[1:3] = [x + 4, y + 10]
    text(root, 'overview-count/sd-logger', f'{len(manifest["parts"])} added parts / page 23', 22 + 98, 42 + 5 * 31 + 10, 1.05)
    for item in root:
        if key(item) == 'text' and '241 components | 142 nets' in str(item[1]):
            item[1] = f'{len(expected["parts"])} components | {len(expected["nets"])} nets | 23 native KiCad pages | integrated SD revision'
        if key(item) == 'text' and str(item[1]).startswith('ChryslerScanner V240'):
            item[1] = 'ChryslerScanner ' + manifest['revision']
        if key(item) == 'text' and str(item[1]).startswith('Includes USB-C and ATTEND'):
            item[1] = 'Preserves USB-C, ATTEND OBD-II and scanner functions. SD hardware added; firmware remains deferred.'
    for filename, document in docs.items():
        (output / filename).write_text(sx.dumps(document) + '\n')
    shutil.copy2(schematics / 'ChryslerScanner.kicad_sym', output / 'ChryslerScanner.kicad_sym')
    (output / 'SDLogger.kicad_sym').write_text(sx.dumps(local) + '\n')
    (output / 'sym-lib-table').write_text(sx.dumps(node('sym_lib_table', node('version', 7),
        *[node('lib', node('name', lib), node('type', 'KiCad'), node('uri', '${KIPRJMOD}/' + lib + '.kicad_sym'),
               node('options', ''), node('descr', description)) for lib, description in
          [('ChryslerScanner', 'Original recovered scanner symbols'), ('SDLogger', 'Integrated SD symbols from installed KiCad library')]])) + '\n')
    assets = HERE.parent / 'package/fp-lib-table'
    if assets.exists():
        shutil.copy2(assets, output / 'fp-lib-table')
    pro = json.loads((base / 'elec/layout/v240/v240.kicad_pro').read_text())
    pro.setdefault('meta', {})['filename'] = project + '.kicad_pro'
    (output / (project + '.kicad_pro')).write_text(json.dumps(pro, indent=2) + '\n')

    paths = {}
    for filename, document in docs.items():
        if filename == project + '.kicad_sch':
            continue
        sheet_id = first(document, 'uuid')[1]
        for instance in document:
            if key(instance) != 'symbol' or first(instance, 'unit')[1] != 1:
                continue
            ref = next(v[2] for v in instance if key(v) == 'property' and v[1] == 'Reference')
            if ref.startswith('#'):
                continue
            assert ref not in paths, ref
            symbol_id = first(instance, 'uuid')[1]
            paths[ref] = dict(reference=ref, sheet_file=filename, sheet_uuid=sheet_id, symbol_uuid=symbol_id,
                              path='/' + root_id + '/' + sheet_id + '/' + symbol_id)
    assert set(paths) == set(expected['parts'])
    (output / 'reference/symbol-paths.json').write_text(json.dumps(dict(project=project, root_uuid=root_id,
        sd_sheet_uuid=uid('sd-logger'), parts=paths, mechanical_board_only=['H1','H2','H3','H4']), indent=2) + '\n')
    report = dict(project=project, revision=manifest['revision'], components=len(expected['parts']),
        connected_nets=len(expected['nets']), pages=len(docs), firmware_status='deferred_by_user',
        native_connectivity_validation_pending=True, corrected_stale_native_pins=['U3.5', 'U4.5', 'U8.5'],
        preserved_pcb_net_labels=preserved_net_labels,
        net_label_visibility='KiCad PDF plots these labels despite its stored hide flag',
        metadata_only_repairs={'atopile_address_references': metadata_aligned,
                               'excluded_from_bom_jumper_references': ['JP1', 'JP2']},
        mcu_new_connections=manifest['mcu_additions'],
        base_netlist_sha256=hashlib.sha256((base / 'reference/v240-netlist.json').read_bytes()).hexdigest(),
        integration_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        source_files={str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(schematics.glob('*.kicad_sch'))})
    (output / 'reference/schematic-generation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['project','components','connected_nets','pages','firmware_status']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--output', type=Path, default=HERE)
    args = parser.parse_args()
    generate(args.base.resolve(), args.manifest.resolve(), args.output.resolve())

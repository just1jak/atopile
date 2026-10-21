"""Conservative text transforms for locally exported Specctra DSN/SES files.

These helpers never load or write a PCB. KiCad's original board must retain its
locked critical copper, and callers must verify geometry and native DRC after
session import. DSN widths/clearances here are micrometres, not KiCad nanometres.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class Scope:
    items: tuple
    start: int
    end: int

    @property
    def head(self) -> str:
        return self.items[0].value if self.items and isinstance(self.items[0], Token) else ''

    def children(self, name: str) -> list[Scope]:
        return [x for x in self.items if isinstance(x, Scope) and x.head == name]


def parse(text: str) -> Scope:
    """Parse spans while retaining original bytes, quoted parentheses and spaces.

    KiCad's `(string_quote ")` contains a bare quote, unlike a normal quoted
    string. Both backslash-escaped and doubled quotes inside strings are handled.
    Unsupported quote declarations fail rather than corrupting an input file.
    """
    def skip(i):
        while i < len(text):
            if text[i].isspace():
                i += 1
            elif text[i] == ';':
                newline = text.find('\n', i)
                i = len(text) if newline < 0 else newline + 1
            else:
                break
        return i

    def read_scope(i):
        start, i, items = i, i + 1, []
        while True:
            i = skip(i)
            if i >= len(text):
                raise ValueError(f'Unclosed scope at offset {start}')
            if text[i] == ')':
                return Scope(tuple(items), start, i + 1), i + 1
            if text[i] == '(':
                item, i = read_scope(i)
                items.append(item)
                continue
            begin = i
            bare_quote = len(items) == 1 and isinstance(items[0], Token) and items[0].value == 'string_quote' and text[i] == '"' and text[skip(i + 1):skip(i + 1) + 1] == ')'
            if bare_quote:
                items.append(Token('"', i, i + 1))
                i += 1
                continue
            if text[i] == '"':
                i += 1
                value = []
                while i < len(text):
                    if text[i] == '\\' and i + 1 < len(text) and text[i + 1] in ('"', '\\'):
                        value.append(text[i + 1])
                        i += 2
                    elif text[i] == '"':
                        if i + 1 < len(text) and text[i + 1] == '"':
                            value.append('"')
                            i += 2
                        else:
                            i += 1
                            break
                    else:
                        value.append(text[i])
                        i += 1
                else:
                    raise ValueError(f'Unclosed string at offset {begin}')
                items.append(Token(''.join(value), begin, i))
            else:
                while i < len(text) and not text[i].isspace() and text[i] not in '()':
                    i += 1
                items.append(Token(text[begin:i], begin, i))

    begin = skip(0)
    if begin >= len(text) or text[begin] != '(':
        raise ValueError('Expected exactly one parenthesized root')
    root, end = read_scope(begin)
    if skip(end) != len(text):
        raise ValueError('Unexpected content after root')
    for scope in walk(root):
        if scope.head == 'string_quote' and (len(scope.items) != 2 or scope.items[1].value != '"'):
            raise ValueError('Only the KiCad double-quote convention is supported')
    return root


def walk(scope):
    yield scope
    for item in scope.items:
        if isinstance(item, Scope):
            yield from walk(item)


def one(scope, name):
    found = scope.children(name)
    if len(found) != 1:
        raise ValueError(f'Expected one {name} scope; found {len(found)}')
    return found[0]


def atom(scope, index=1):
    if len(scope.items) <= index or not isinstance(scope.items[index], Token):
        raise ValueError(f'Expected token in {scope.head}')
    return scope.items[index].value


def patch(text, changes):
    changes = sorted(changes)
    for left, right in zip(changes, changes[1:]):
        if left[1] > right[0]:
            raise ValueError('Overlapping Specctra edits')
    for start, end, replacement in reversed(changes):
        text = text[:start] + replacement + text[end:]
    return text


def sanitize_ses(text: str) -> tuple[str, dict]:
    """Remove only the SESSION's placement scope, leaving routes byte-exact."""
    root = parse(text)
    if root.head != 'session':
        raise ValueError('Expected SES session root')
    routes = one(root, 'routes')
    placements = root.children('placement')
    if len(placements) > 1:
        raise ValueError('Multiple SESSION placement scopes')
    original_routes = text[routes.start:routes.end]
    result = patch(text, [(p.start, p.end, '') for p in placements])
    checked = parse(result)
    new_routes = one(checked, 'routes')
    if checked.children('placement') or result[new_routes.start:new_routes.end] != original_routes:
        raise ValueError('Session sanitization changed routing or retained placement')
    return result, {'placement_scopes_removed': len(placements), 'routes_bytes_unchanged': True}


def quoted(value):
    if any(c in value for c in '\r\n\x00'):
        raise ValueError('Newlines/NUL are not allowed in identifiers')
    return json.dumps(value, ensure_ascii=False)


def positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Widths and clearances must be finite positive values')
    return value


def configure_dsn(text: str, *, rails: Iterable[str] = (), critical_rf: Iterable[str] = (),
                  critical_usb: Iterable[str] = (), default_width_um=200, rail_width_um=500,
                  rf_width_um=None, usb_width_um=250, clearance_um=150) -> tuple[str, dict]:
    """Configure an audited single-default-class KiCad DSN without touching copper.

    RF/USB classes are restricted to the first physical (front) signal layer.
    Already authored copper on those nets is marked `fix`. This does not create
    impedance-controlled/differential routing or mark native PCB tracks locked.
    """
    root = parse(text)
    if root.head != 'pcb' or atom(one(root, 'unit')) != 'um':
        raise ValueError('Expected native KiCad PCB DSN with unit um')
    structure, network = one(root, 'structure'), one(root, 'network')
    layers = structure.children('layer')
    if not layers or atom(one(layers[0], 'type')) != 'signal':
        raise ValueError('First physical layer must be the front signal layer')
    front = atom(layers[0])
    net_names = [atom(n) for n in network.children('net')]
    if len(set(net_names)) != len(net_names):
        raise ValueError('Duplicate DSN net names')
    existing = network.children('class')
    if len(existing) != 1 or atom(existing[0]) not in ('kicad_default', 'default'):
        raise ValueError('Refusing to replace non-default/custom class rules')
    rails, rf, usb = set(rails), set(critical_rf), set(critical_usb)
    known = set(net_names)
    if (rails | rf | usb) - known:
        raise ValueError(f'Unknown class nets: {sorted((rails | rf | usb) - known)}')
    if rails & rf or rails & usb or rf & usb:
        raise ValueError('Route classes must have disjoint net membership')
    if rf and rf_width_um is None:
        raise ValueError('Reviewed RF width must be explicitly supplied')
    clearance = positive(clearance_um)
    if clearance < 150:
        raise ValueError('Minimum requested clearance must be at least150um')
    default_width, rail_width, usb_width = map(positive, (default_width_um, rail_width_um, usb_width_um))
    rf_width = positive(rf_width_um) if rf_width_um is not None else None
    if min(default_width, rail_width, usb_width, rf_width or default_width) < 150:
        raise ValueError('Requested class widths must be at least150um')
    via_ids = [x.value for via in structure.children('via') for x in via.items[1:] if isinstance(x, Token)]

    def class_text(name, members, width, critical=False):
        if not members:
            return ''
        tokens = ' '.join(quoted(n) for n in net_names if n in members)
        circuit = '(use_via ' + ' '.join(map(quoted, via_ids)) + ')' if via_ids else ''
        if critical:
            circuit += ' (use_layer ' + quoted(front) + ')'
        protection = ' (shove_fixed off) (pull_tight off)' if critical else ''
        return f'\n    (class {name} {tokens} (circuit {circuit}) (rule (width {width:g}) (clearance {clearance:g})){protection})'

    replacement = ''.join([
        class_text('kicad_default', known - rails - rf - usb, default_width),
        class_text('rails', rails, rail_width), class_text('rf_fixed', rf, rf_width, True),
        class_text('usb_fixed', usb, usb_width, True)])
    result = patch(text, [(existing[0].start, existing[0].end, replacement)])
    root = parse(result)
    structure = one(root, 'structure')
    changes, clamped = [], 0
    for scope in walk(root):
        if scope.head == 'clearance':
            value = float(atom(scope))
            if not math.isfinite(value) or value < 0:
                raise ValueError('Invalid existing clearance')
            if value < clearance:
                token = scope.items[1]
                changes.append((token.start, token.end, f'{clearance:g}'))
                clamped += 1
    for rule in structure.children('rule'):
        for width in rule.children('width'):
            token = width.items[1]
            changes.append((token.start, token.end, f'{default_width:g}'))
    result = patch(result, changes)
    root = parse(result)
    protected = 0
    changes = []
    for wiring in root.children('wiring'):
        for scope in wiring.items:
            if not isinstance(scope, Scope) or scope.head not in ('wire', 'via'):
                continue
            net_scopes = scope.children('net')
            if len(net_scopes) != 1 or atom(net_scopes[0]) not in rf | usb:
                continue
            types = scope.children('type')
            if len(types) > 1:
                raise ValueError('Multiple copper fixed-state scopes')
            if types:
                token = types[0].items[1]
                changes.append((token.start, token.end, 'fix'))
            else:
                changes.append((scope.end - 1, scope.end - 1, ' (type fix)'))
            protected += 1
    result = patch(result, changes)
    parse(result)
    return result, {'front_layer': front, 'total_nets': len(net_names),
                    'class_counts': {'default': len(known - rails - rf - usb), 'rails': len(rails), 'rf_fixed': len(rf), 'usb_fixed': len(usb)},
                    'default_width_um': default_width, 'rail_width_um': rail_width,
                    'rf_width_um': rf_width, 'usb_width_um': usb_width,
                    'minimum_clearance_um': clearance, 'clearance_scopes_clamped': clamped,
                    'existing_critical_copper_scopes_fixed': protected,
                    'native_lock_still_required': True}


def ascii_placement_metadata(text: str) -> tuple[str, dict]:
    """Avoid FreeRouting 1.9's blocking Unicode warning dialog for PN values.

    Only optional placement part-number/value annotations change. Electrical
    identifiers, routes, rules and coordinates remain byte-exact. Unknown
    non-ASCII input is rejected rather than silently replacing an identifier.
    """
    root = parse(text)
    if root.head != 'pcb':
        raise ValueError('Expected PCB DSN root')
    changes = []
    for placement in root.children('placement'):
        for scope in walk(placement):
            if scope.head != 'PN':
                continue
            for item in scope.items[1:]:
                if not isinstance(item, Token):
                    raise ValueError('Unexpected nested PN metadata')
                value = item.value.replace('Ω', 'ohm').replace('μ', 'u').replace('µ', 'u')
                if not value.isascii():
                    raise ValueError('Unsupported non-ASCII PN annotation')
                if value != item.value:
                    changes.append((item.start, item.end, quoted(value)))
    result = patch(text, changes)
    if not result.isascii():
        raise ValueError('Non-ASCII data outside supported optional PN annotations')
    parse(result)
    return result, {'pn_annotations_normalized': len(changes),
                    'routing_rules_identifiers_coordinates_unchanged': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['sanitize-ses', 'configure-dsn', 'ascii-metadata'])
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--rails', default='')
    parser.add_argument('--rf', default='')
    parser.add_argument('--usb', default='')
    parser.add_argument('--rf-width-um', type=float)
    parser.add_argument('--usb-width-um', type=float, default=250)
    parser.add_argument('--default-width-um', type=float, default=200)
    parser.add_argument('--rail-width-um', type=float, default=500)
    parser.add_argument('--clearance-um', type=float, default=150)
    args = parser.parse_args()
    text = args.input.read_text()
    if args.operation == 'sanitize-ses':
        result, report = sanitize_ses(text)
    elif args.operation == 'ascii-metadata':
        result, report = ascii_placement_metadata(text)
    else:
        split = lambda x: [n.strip() for n in x.split(',') if n.strip()]
        result, report = configure_dsn(text, rails=split(args.rails), critical_rf=split(args.rf),
            critical_usb=split(args.usb), rf_width_um=args.rf_width_um,
            usb_width_um=args.usb_width_um, default_width_um=args.default_width_um,
            rail_width_um=args.rail_width_um, clearance_um=args.clearance_um)
    with args.output.open('x') as output:
        output.write(result)
    print(json.dumps(report, indent=2))

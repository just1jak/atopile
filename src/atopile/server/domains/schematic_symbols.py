"""Read local KiCad symbol libraries into bounded, SVG-independent geometry.

All coordinates are millimetres, with positive Y pointing down. Pin ``x/y`` is
the electrical connection point; ``endX/endY`` is the end nearest the symbol
body. Library roots are host-owned allowlists, never renderer-supplied paths.
This module neither fetches libraries nor manufactures replacement symbols.
"""

from __future__ import annotations

import math
import os
import re
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import sexpdata

MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_SOURCE_DEPTH = 64
MAX_SOURCE_NODES = 250_000
MAX_DIRECTORY_ENTRIES = 20_000
MAX_LIBRARY_FILES = 256
MAX_PARSED_LIBRARIES = 32
MAX_PRIMITIVES = 10_000
MAX_POLYLINE_POINTS = 4096
MAX_INHERITANCE = 32
_MAX_COORDINATE = 100_000
_SKIP_DIRECTORIES = {".git", ".venv", "node_modules", "build", "__pycache__"}
_UNIT_NAME = re.compile(r"_(\d+)_(\d+)$")


class SymbolReadError(ValueError):
    """A local library is unavailable, invalid, or outside its allowed roots."""


def _tag(node: Any) -> str:
    return str(node[0]) if isinstance(node, list) and node else ""


def _children(node: list, tag: str) -> list[list]:
    return [child for child in node[1:] if _tag(child) == tag]


def _field(node: list, tag: str) -> list:
    return next(iter(_children(node, tag)), [])


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise SymbolReadError("Boolean used as a coordinate")
    result = float(value)
    if not math.isfinite(result) or abs(result) > _MAX_COORDINATE:
        raise SymbolReadError("Non-finite or oversized symbol coordinate")
    return round(result, 8)


def _xy(node: list, tag: str) -> tuple[float, float]:
    item = _field(node, tag)
    if len(item) < 3:
        raise SymbolReadError(f"Missing {tag} coordinate")
    return _number(item[1]), -_number(item[2])


def _value(node: list, tag: str, default: Any = None) -> Any:
    item = _field(node, tag)
    return item[1] if len(item) > 1 else default


def _hidden(node: list) -> bool:
    return any(
        str(child) == "hide" for child in node[1:] if not isinstance(child, list)
    ) or str(_value(node, "hide", "no")) in {"yes", "true"}


def _within(path: Path, roots: list[Path]) -> bool:
    return any(path.is_relative_to(root) for root in roots)


def _read_library(path: Path, roots: list[Path]) -> dict[str, list]:
    """Bound bytes and nesting before handing the string to sexpdata."""
    resolved = path.resolve()
    if not _within(resolved, roots) or resolved.suffix.lower() != ".kicad_sym":
        raise SymbolReadError("Symbol file is outside the allowed library roots")
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise SymbolReadError("KiCad symbol source must be a regular file")
    with resolved.open("rb") as source:
        data = source.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise SymbolReadError("KiCad symbol library exceeds the source size limit")
    text = data.decode("utf-8-sig")
    depth = nodes = 0
    quoted = escaped = comment = False
    for char in text:
        if comment:
            comment = char != "\n"
        elif quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == ";":
            comment = True
        elif char == "(":
            depth += 1
            nodes += 1
            if depth > MAX_SOURCE_DEPTH or nodes > MAX_SOURCE_NODES:
                raise SymbolReadError(
                    "KiCad symbol library exceeds the complexity limit"
                )
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise SymbolReadError("Unbalanced KiCad symbol library")
    if depth or quoted:
        raise SymbolReadError("Unbalanced KiCad symbol library")
    document = sexpdata.loads(text)
    if _tag(document) != "kicad_symbol_lib":
        raise SymbolReadError("File is not a KiCad symbol library")
    symbols = {}
    for symbol in _children(document, "symbol"):
        if len(symbol) > 1:
            name = str(symbol[1])
            if name in symbols:
                raise SymbolReadError(f"Duplicate library symbol {name}")
            symbols[name] = symbol
    return symbols


def _library_candidates(
    roots: list[Path], library: str, name: str
) -> tuple[list[Path], bool]:
    found: list[Path] = []
    seen: set[Path] = set()
    entries = 0
    truncated = False
    for root in roots:
        if not root.is_dir():
            continue
        for directory, directories, files in os.walk(root, followlinks=False):
            directories[:] = sorted(
                (d for d in directories if d not in _SKIP_DIRECTORIES),
                key=lambda d: (d not in {"assets", "parts"}, d),
            )
            entries += len(directories) + len(files)
            if entries > MAX_DIRECTORY_ENTRIES:
                truncated = True
                break
            for filename in sorted(files):
                if not filename.lower().endswith(".kicad_sym"):
                    continue
                candidate = (Path(directory) / filename).resolve()
                if candidate in seen or not _within(candidate, roots):
                    continue
                seen.add(candidate)
                found.append(candidate)
                if len(found) >= MAX_LIBRARY_FILES:
                    truncated = True
                    break
            if truncated:
                break
        if truncated:
            break
    # Explicit library names beat matching symbol filenames. Stable discovery order
    # gives project assets/parts precedence over optional installed libraries.
    found.sort(
        key=lambda p: (
            next(i for i, root in enumerate(roots) if p.is_relative_to(root)),
            p.stem != library if library else True,
            p.stem != name,
        )
    )
    return found, truncated


def _symbol_chain(symbols: dict[str, list], name: str) -> list[list]:
    chain: list[list] = []
    visited: set[str] = set()
    current = name
    while current:
        if current in visited:
            raise SymbolReadError("Cyclic KiCad symbol inheritance")
        if len(visited) >= MAX_INHERITANCE:
            raise SymbolReadError("KiCad symbol inheritance exceeds the depth limit")
        visited.add(current)
        symbol = symbols.get(current)
        if symbol is None:
            raise SymbolReadError(f"Inherited KiCad symbol {current!r} is missing")
        chain.append(symbol)
        # KiCad extends is scoped to this library. Do not resolve arbitrary paths.
        current = str(_value(symbol, "extends", ""))
    return list(reversed(chain))


def _style(node: list, warnings: list[str]) -> dict[str, Any]:
    stroke = _field(node, "stroke")
    width = _number(_value(stroke, "width", 0.254))
    if width < 0:
        raise SymbolReadError("Negative KiCad stroke width")
    stroke_type = str(_value(stroke, "type", "default"))
    if stroke_type not in {"default", "solid"}:
        warnings.append(f"Stroke style {stroke_type!r} is displayed as solid")
    fill = str(_value(_field(node, "fill"), "type", "none"))
    if fill not in {"none", "background", "outline"}:
        warnings.append(f"Unsupported symbol fill {fill!r}")
        fill = "none"
    return {"strokeWidth": width or 0.254, "fill": fill}


def _text(node: list, *, label: str | None = None) -> dict[str, Any] | None:
    effects = _field(node, "effects")
    if _hidden(node) or _hidden(effects):
        return None
    x, y = _xy(node, "at")
    at = _field(node, "at")
    angle = (-_number(at[3]) % 360) if len(at) > 3 else 0
    size = _field(_field(effects, "font"), "size")
    font_size = _number(size[2]) if len(size) > 2 else 1.27
    if font_size <= 0:
        raise SymbolReadError("Invalid KiCad font size")
    justify = _field(effects, "justify")
    anchor = (
        "start"
        if any(str(x) == "left" for x in justify)
        else "end"
        if any(str(x) == "right" for x in justify)
        else "middle"
    )
    content = label if label is not None else str(node[1])
    return {
        "type": "text",
        "x": x,
        "y": y,
        "text": content[:4096],
        "size": font_size,
        "angle": angle,
        "anchor": anchor,
    }


def _arc(node: list, style: dict[str, Any]) -> dict[str, Any]:
    """Sample the circle sweep through the exact start, mid, and end points."""
    start, mid, end = (_xy(node, key) for key in ("start", "mid", "end"))
    ax, ay = start
    bx, by = mid
    cx, cy = end
    determinant = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(determinant) < 1e-10:
        raise SymbolReadError("Degenerate KiCad arc has no unique circle")
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / determinant
    oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / determinant
    radius = _number(math.hypot(ax - ox, ay - oy))
    angles = [math.atan2(y - oy, x - ox) for x, y in (start, mid, end)]
    positive_sweep = (angles[2] - angles[0]) % math.tau
    sweep = (
        positive_sweep
        if (angles[1] - angles[0]) % math.tau <= positive_sweep
        else positive_sweep - math.tau
    )
    # At most five degrees per segment; a midpoint split preserves its exact
    # position and distinguishes major arcs from their shorter counterpart.
    direction = 1 if sweep >= 0 else -1
    mid_sweep = ((angles[1] - angles[0]) * direction) % math.tau * direction
    points = []
    for begin, amount in (
        (angles[0], mid_sweep),
        (angles[0] + mid_sweep, sweep - mid_sweep),
    ):
        count = max(1, math.ceil(abs(amount) / math.radians(5)))
        segment = [
            {
                "x": round(ox + radius * math.cos(begin + amount * i / count), 8),
                "y": round(oy + radius * math.sin(begin + amount * i / count), 8),
            }
            for i in range(count + 1)
        ]
        points.extend(segment if not points else segment[1:])
    points[0], points[-1] = {"x": ax, "y": ay}, {"x": cx, "y": cy}
    return {"type": "polyline", "points": points, "closed": False, **style}


def _graphic(node: list, warnings: list[str]) -> dict[str, Any] | None:
    kind = _tag(node)
    if kind == "text":
        return _text(node)
    style = _style(node, warnings)
    if kind == "rectangle":
        start, end = _xy(node, "start"), _xy(node, "end")
        return {
            "type": "rect",
            "x": min(start[0], end[0]),
            "y": min(start[1], end[1]),
            "width": abs(end[0] - start[0]),
            "height": abs(end[1] - start[1]),
            **style,
        }
    if kind == "circle":
        cx, cy = _xy(node, "center")
        radius = _number(_value(node, "radius", -1))
        if radius < 0:
            raise SymbolReadError("Invalid KiCad circle radius")
        return {"type": "circle", "cx": cx, "cy": cy, "r": radius, **style}
    if kind == "polyline":
        points = [
            {"x": _number(point[1]), "y": -_number(point[2])}
            for point in _children(_field(node, "pts"), "xy")
            if len(point) >= 3
        ]
        if len(points) < 2:
            raise SymbolReadError("KiCad polyline needs at least two points")
        if len(points) > MAX_POLYLINE_POINTS:
            raise SymbolReadError("KiCad polyline exceeds the point limit")
        return {
            "type": "polyline",
            "points": points,
            "closed": points[0] == points[-1],
            **style,
        }
    if kind == "arc":
        return _arc(node, style)
    warnings.append(f"Unsupported KiCad symbol graphic {kind!r} was omitted")
    return None


def _pin(
    node: list, names: list, numbers: list, warnings: list[str]
) -> tuple[dict, list[dict]]:
    if len(node) < 3:
        raise SymbolReadError("Invalid KiCad pin")
    x, y = _xy(node, "at")
    at = _field(node, "at")
    rotation = (-_number(at[3]) % 360) if len(at) > 3 else 0
    radians = math.radians(rotation)
    dx, dy = math.cos(radians), math.sin(radians)
    length = _number(_value(node, "length", 0))
    if length < 0:
        raise SymbolReadError("Negative KiCad pin length")
    ex, ey = round(x + length * dx, 8), round(y + length * dy, 8)
    name_node, number_node = _field(node, "name"), _field(node, "number")
    name, number = str(_value(node, "name", "")), str(_value(node, "number", ""))
    hidden = _hidden(node)
    pin = {
        "number": number[:256],
        "name": name[:1024],
        "electricalType": str(node[1]),
        "shape": str(node[2]),
        "x": x,
        "y": y,
        "endX": ex,
        "endY": ey,
        "rotation": rotation,
        "length": length,
        "hidden": hidden,
    }
    if hidden:
        return pin, []
    shapes: list[dict] = [
        {"type": "line", "x1": x, "y1": y, "x2": ex, "y2": ey, "strokeWidth": 0.254}
    ]
    shape = str(node[2])
    if shape not in {"line", "inverted", "clock", "inverted_clock"}:
        warnings.append(f"Pin shape {shape!r} is displayed as a line")
    if shape in {"inverted", "inverted_clock"}:
        radius = min(0.5, length / 4)
        shapes[0]["x2"], shapes[0]["y2"] = ex - 2 * radius * dx, ey - 2 * radius * dy
        shapes.append(
            {
                "type": "circle",
                "cx": ex - radius * dx,
                "cy": ey - radius * dy,
                "r": radius,
                "strokeWidth": 0.254,
                "fill": "background",
            }
        )
    if shape in {"clock", "inverted_clock"}:
        size = 0.8
        shapes.append(
            {
                "type": "polyline",
                "points": [
                    {"x": ex + dy * size, "y": ey - dx * size},
                    {"x": ex + dx * size, "y": ey + dy * size},
                    {"x": ex - dy * size, "y": ey + dx * size},
                ],
                "closed": False,
                "strokeWidth": 0.254,
                "fill": "none",
            }
        )
    # KiCad positions pin labels from length, orientation and library offset;
    # these remain plain strings, never HTML or SVG from a library.
    horizontal = abs(dx) >= abs(dy)
    angle = 0 if horizontal else 270
    offset = _number(_value(names, "offset", 0.508))
    for label_node, label, show, tx, ty, anchor in (
        (
            name_node,
            name,
            not _hidden(names) and name not in {"", "~"},
            ex + dx * offset,
            ey + dy * offset,
            "start" if dx > 0.5 or dy < -0.5 else "end",
        ),
        (
            number_node,
            number,
            not _hidden(numbers),
            (x + ex) / 2 + (0 if horizontal else -0.35),
            (y + ey) / 2 + (-0.35 if horizontal else 0),
            "middle",
        ),
    ):
        effects = _field(label_node, "effects")
        if not show or not label or _hidden(effects):
            continue
        size_node = _field(_field(effects, "font"), "size")
        size = _number(size_node[2]) if len(size_node) > 2 else 1.27
        if size <= 0:
            raise SymbolReadError("Invalid KiCad pin font size")
        shapes.append(
            {
                "type": "text",
                "x": round(tx, 8),
                "y": round(ty, 8),
                "text": label[:1024],
                "size": size,
                "angle": angle,
                "anchor": anchor,
            }
        )
    return pin, shapes


def _bounds(primitives: list[dict], pins: list[dict]) -> dict[str, float]:
    points: list[tuple[float, float]] = [(p["x"], p["y"]) for p in pins]
    for primitive in primitives:
        kind = primitive["type"]
        if kind == "rect":
            points.extend(
                [
                    (primitive["x"], primitive["y"]),
                    (
                        primitive["x"] + primitive["width"],
                        primitive["y"] + primitive["height"],
                    ),
                ]
            )
        elif kind == "circle":
            points.extend(
                [
                    (
                        primitive["cx"] - primitive["r"],
                        primitive["cy"] - primitive["r"],
                    ),
                    (
                        primitive["cx"] + primitive["r"],
                        primitive["cy"] + primitive["r"],
                    ),
                ]
            )
        elif kind == "line":
            points.extend(
                [(primitive["x1"], primitive["y1"]), (primitive["x2"], primitive["y2"])]
            )
        elif kind == "polyline":
            points.extend((p["x"], p["y"]) for p in primitive["points"])
        elif kind == "text":
            width, height = (
                len(primitive["text"]) * primitive["size"] * 0.65,
                primitive["size"],
            )
            offset = {"start": 0, "middle": -width / 2, "end": -width}[
                primitive["anchor"]
            ]
            angle = math.radians(primitive["angle"])
            for dx, dy in (
                (offset, -height / 2),
                (offset + width, -height / 2),
                (offset, height / 2),
                (offset + width, height / 2),
            ):
                points.append(
                    (
                        primitive["x"] + dx * math.cos(angle) - dy * math.sin(angle),
                        primitive["y"] + dx * math.sin(angle) + dy * math.cos(angle),
                    )
                )
    if not points:
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    minimum_x, minimum_y = min(p[0] for p in points), min(p[1] for p in points)
    return {
        "x": round(minimum_x, 8),
        "y": round(minimum_y, 8),
        "width": round(max(p[0] for p in points) - minimum_x, 8),
        "height": round(max(p[1] for p in points) - minimum_y, 8),
    }


def _normalize(
    symbols: dict[str, list], name: str, unit: int, warnings: list[str]
) -> dict:
    chain = _symbol_chain(symbols, name)
    graphics, pin_nodes = [], []
    names, numbers = [], []
    units: set[int] = set()
    for symbol in chain:
        names = _field(symbol, "pin_names") or names
        numbers = _field(symbol, "pin_numbers") or numbers
        for sub in _children(symbol, "symbol"):
            match = _UNIT_NAME.search(str(sub[1])) if len(sub) > 1 else None
            if match is None:
                warnings.append(
                    "Nested symbol with an unrecognized unit name was omitted"
                )
                continue
            sub_unit, style = map(int, match.groups())
            if sub_unit:
                units.add(sub_unit)
            if sub_unit not in {0, unit} or style not in {0, 1}:
                continue
            for child in sub[2:]:
                if not isinstance(child, list):
                    continue
                if _tag(child) == "pin":
                    pin_nodes.append(child)
                else:
                    graphics.append(child)
    if units and unit not in units:
        warnings.append(
            f"KiCad symbol has no unit {unit}; only common graphics are available"
        )
    primitives, pins = [], []
    for node in graphics:
        if len(primitives) >= MAX_PRIMITIVES:
            warnings.append(
                "Symbol graphic limit reached; remaining graphics were omitted"
            )
            break
        try:
            primitive = _graphic(node, warnings)
            if primitive is not None:
                primitives.append(primitive)
        except (SymbolReadError, ValueError, IndexError, TypeError) as error:
            warnings.append(f"Invalid {_tag(node)} graphic was omitted: {error}")
    for node in pin_nodes:
        if len(primitives) >= MAX_PRIMITIVES:
            warnings.append("Symbol graphic limit reached; remaining pins were omitted")
            break
        try:
            pin, pin_graphics = _pin(node, names, numbers, warnings)
            pins.append(pin)
            primitives.extend(pin_graphics)
        except (SymbolReadError, ValueError, IndexError, TypeError) as error:
            warnings.append(f"Invalid KiCad pin was omitted: {error}")
    return {
        "name": name,
        "unit": unit,
        "availableUnits": sorted(units),
        "primitives": primitives,
        "pins": pins,
        "bounds": _bounds(primitives, pins),
    }


def load_schematic_symbol(
    project_root: Path,
    lib_id: str,
    *,
    symbol_path: str | Path | None = None,
    unit: int = 1,
    library_roots: Iterable[Path] = (),
) -> dict[str, Any]:
    """Load one local symbol, returning an explicit missing/partial result on failure.

    ``lib_id`` is ``Library:Symbol`` or a symbol name. ``symbol_path``, when known
    from an imported part's trait, is preferred and must resolve inside the
    project or a host-supplied library root. Extra roots can point at an installed
    KiCad symbol directory; this function never discovers or downloads one online.
    Reference/value properties are left to the component renderer, avoiding
    duplicate instance labels. All visible pin and graphic text is included.
    """
    warnings: list[str] = []
    result: dict[str, Any] = {
        "libId": str(lib_id)[:1024],
        "name": str(lib_id)[:1024],
        "unit": unit,
        "primitives": [],
        "pins": [],
        "bounds": {"x": 0, "y": 0, "width": 0, "height": 0},
        "missing": True,
        "status": "missing",
        "sourceFile": None,
    }
    try:
        if not isinstance(unit, int) or isinstance(unit, bool) or not 1 <= unit <= 256:
            raise SymbolReadError("KiCad symbol unit must be an integer from 1 to 256")
        if (
            not lib_id
            or len(lib_id) > 1024
            or any(c in lib_id for c in ("/", "\\", "\x00"))
        ):
            raise SymbolReadError("Invalid KiCad library symbol identifier")
        project = Path(project_root).resolve()
        roots = list(
            dict.fromkeys([project, *(Path(p).resolve() for p in library_roots)])
        )
        library, separator, name = lib_id.partition(":")
        if not separator:
            library, name = "", lib_id
        if symbol_path is not None:
            candidate = Path(symbol_path)
            candidate = (
                (project / candidate).resolve()
                if not candidate.is_absolute()
                else candidate.resolve()
            )
            if not _within(candidate, roots):
                raise SymbolReadError(
                    "Symbol file is outside the allowed library roots"
                )
            candidates = [candidate]
        else:
            candidates, truncated = _library_candidates(roots, library, name)
            if truncated:
                warnings.append("Local library discovery reached its search limit")
        selected = None
        for candidate in candidates[:MAX_PARSED_LIBRARIES]:
            try:
                symbols = _read_library(candidate, roots)
            except (OSError, UnicodeError, ValueError, RecursionError) as error:
                warnings.append(
                    f"Could not read local library {candidate.name}: {error}"
                )
                continue
            if name in symbols:
                selected = (candidate, symbols)
                break
        if selected is None:
            if len(candidates) > MAX_PARSED_LIBRARIES:
                warnings.append("Local library parsing reached its file limit")
            raise SymbolReadError(f"No local KiCad symbol found for {lib_id!r}")
        source, symbols = selected
        result.update(_normalize(symbols, name, unit, warnings))
        result["sourceFile"] = (
            str(source.relative_to(project))
            if source.is_relative_to(project)
            else str(source)
        )
        result["missing"] = not bool(result["primitives"] or result["pins"])
        if result["missing"]:
            warnings.append(
                "Local KiCad symbol contains no supported geometry for this unit"
            )
        result["status"] = (
            "missing" if result["missing"] else "partial" if warnings else "loaded"
        )
    except (OSError, ValueError, TypeError, RecursionError) as error:
        warnings.append(str(error))
    result["warnings"] = list(dict.fromkeys(warnings))[:32]
    if result["warnings"]:
        result["warning"] = "; ".join(result["warnings"])
    return result

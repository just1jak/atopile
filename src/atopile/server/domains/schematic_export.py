"""One-way native KiCad schematic snapshots of the PCB's logical pad nets.

The existing PCB is read only. Each fresh schematic embeds its symbol definitions
and is checked by KiCad's own netlist exporter before becoming the latest export.
An unchanged circuit reopens the existing editable file without overwriting it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import sexpdata

from atopile.config import ProjectConfig
from atopile.server.domains.kicad import _clean_env_for_kicad
from atopile.server.domains.schematic import get_schematic_data
from atopile.server.domains.schematic_symbols import (
    _UNIT_NAME,
    _children,
    _field,
    _normalize,
    _read_library,
    _symbol_chain,
    _tag,
)
from faebryk.libs.kicad.fileformats import kicad

MAX_COMPONENTS = 256
MAX_PINS = 16_384
MAX_MANIFEST_BYTES = 16_384
MAX_PROJECT_CONFIG_BYTES = 65_536
MAX_SCHEMATIC_BYTES = 8 * 1024 * 1024
MAX_HIERARCHY_BYTES = 64 * 1024 * 1024
MAX_HIERARCHY_FILES = 512
MAX_HIERARCHY_DEPTH = 32
MAX_NETLIST_BYTES = 32 * 1024 * 1024
NATIVE_VERIFY_TIMEOUT = 45
_ASSOCIATION_WARNING = (
    "PCB association is by reference; this export does not change PCB links."
)


def _node(tag: str, *items: Any) -> list:
    return [sexpdata.Symbol(tag), *items]


def _uuid() -> str:
    return str(uuid.uuid4())


def _safe_path(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Native schematic export path escapes the project root")
    return resolved


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", text)[:64] or "circuit"


def _effects(*, hidden: bool = False, justify: str | None = None) -> list:
    result = _node("effects", _node("font", _node("size", 1.27, 1.27)))
    if justify:
        result.append(_node("justify", sexpdata.Symbol(justify)))
    if hidden:
        result.append(sexpdata.Symbol("hide"))
    return result


def _property(
    name: str, value: str, x: float, y: float, *, hidden: bool = False
) -> list:
    return _node("property", name, value, _node("at", x, y, 0), _effects(hidden=hidden))


def _format(node: Any, indent: int = 0) -> str:
    """Readable S-expression formatting without a lossy typed-model round trip."""
    inline = sexpdata.dumps(node)
    if not isinstance(node, list) or len(inline) + indent <= 110:
        return inline
    first_child = next(
        (i for i, item in enumerate(node) if isinstance(item, list)), len(node)
    )
    head = " ".join(sexpdata.dumps(item) for item in node[:first_child])
    children = [
        " " * (indent + 2) + _format(item, indent + 2) for item in node[first_child:]
    ]
    return "(" + head + "\n" + "\n".join(children) + "\n" + " " * indent + ")"


def _embedded_symbol(
    root: Path, component: dict[str, Any]
) -> tuple[str, list, list[dict]]:
    source = component["symbol"]
    if source.get("missing") or not source.get("sourceFile"):
        raise ValueError(
            f"{component['reference']}: a real local KiCad symbol "
            "is required for native export"
        )
    filename = _safe_path(root, root / source["sourceFile"])
    symbols = _read_library(filename, [root])
    name = str(source["name"])
    chain = _symbol_chain(symbols, name)
    unit = int(source.get("unit") or 1)
    units: set[int] = set()
    fields: dict[str, list] = {}
    properties: dict[str, list] = {}
    parts: dict[str, list] = {}
    for ancestor in chain:
        for field in ancestor[2:]:
            tag = _tag(field)
            if not tag or tag == "extends":
                continue
            if tag == "symbol":
                match = _UNIT_NAME.search(str(field[1])) if len(field) > 1 else None
                if match is None:
                    raise ValueError(
                        f"{component['reference']}: unrecognized KiCad symbol unit name"
                    )
                native_unit, _style = map(int, match.groups())
                if native_unit:
                    units.add(native_unit)
                suffix = match.group(0)
                if suffix in parts and parts[suffix][2:] != field[2:]:
                    raise ValueError(
                        f"{component['reference']}: inherited unit geometry "
                        "overrides are not supported"
                    )
                parts[suffix] = copy.deepcopy(field)
            elif tag == "property" and len(field) >= 3:
                properties[str(field[1])] = copy.deepcopy(field)
            else:
                fields[tag] = copy.deepcopy(field)
    if unit != 1 or any(value != 1 for value in units):
        raise ValueError(
            f"{component['reference']}: native export currently requires a "
            "single-unit symbol; multi-unit symbols are not exported"
        )
    normalized = _normalize(symbols, name, 1, [])
    pins = normalized["pins"]
    expected = {str(pin["number"]) for pin in component["pins"]}
    if not pins or {str(pin["number"]) for pin in pins} != expected:
        raise ValueError(
            f"{component['reference']}: KiCad symbol pins do not exactly "
            "match the PCB terminals"
        )
    for pin in pins:
        # Arbitrary-angle pins are supported by the viewer, but native schematic
        # electrical terminals and label orientation must lie on the KiCad grid.
        if abs(pin["rotation"] % 90) > 1e-7:
            raise ValueError(
                f"{component['reference']}: native export requires "
                "orthogonal symbol pins"
            )
    definition = _node(
        "symbol", name, *fields.values(), *properties.values(), *parts.values()
    )
    digest = hashlib.sha256(sexpdata.dumps(definition).encode()).hexdigest()[:12]
    short_name = f"{_slug(name)}_{digest}"
    lib_id = "AtopileLocal:" + short_name
    definition[1] = lib_id
    for part in _children(definition, "symbol"):
        part[1] = short_name + _UNIT_NAME.search(str(part[1])).group(0)
    return lib_id, definition, pins


def _terminal_assignments(data: dict[str, Any]) -> dict[tuple[str, str], str | None]:
    expected: dict[tuple[str, str], str | None] = {}
    references: set[str] = set()
    for component in data["components"]:
        reference = component["reference"]
        if not reference or reference in references:
            raise ValueError(
                "Native export requires unique, nonempty PCB component references"
            )
        references.add(reference)
        for pin in component["pins"]:
            key = reference, str(pin["number"])
            net = pin["net"]
            if net is not None and (
                not net or len(net) > 1024 or any(ord(c) < 32 for c in net)
            ):
                raise ValueError(f"{reference}: unsupported PCB net label")
            if key in expected and expected[key] != net:
                raise ValueError(
                    f"{reference} pin {key[1]} belongs to conflicting PCB nets"
                )
            expected[key] = net
    if len(expected) > MAX_PINS:
        raise ValueError("Native schematic export exceeds the pin limit")
    return expected


def _pcb_footprints(data: dict[str, Any]) -> dict[str, Any]:
    pcb = kicad.loads(
        kicad.pcb.PcbFile, Path(data["layoutPath"]).read_text(encoding="utf-8")
    )
    return {str(fp.uuid): fp for fp in pcb.kicad_pcb.footprints if fp.uuid}


def _document(root: Path, data: dict[str, Any], path: Path) -> list:
    if not data["components"] or len(data["components"]) > MAX_COMPONENTS:
        raise ValueError(f"Native export requires 1 to {MAX_COMPONENTS} PCB components")
    assignments = _terminal_assignments(data)
    pcb_footprints = _pcb_footprints(data)
    prepared = [(c, *_embedded_symbol(root, c)) for c in data["components"]]
    # Spacious deterministic grid. Native labels connect nets across this sheet;
    # this is an editable electrical snapshot, not an inferred circuit diagram.
    widest = max(c["symbol"]["bounds"]["width"] for c in data["components"])
    tallest = max(c["symbol"]["bounds"]["height"] for c in data["components"])
    label_width = (
        max((len(net) for net in assignments.values() if net), default=1) * 0.9
    )
    step_x = max(65, widest + 2 * label_width + 15)
    step_y = max(45, tallest + 2 * label_width + 15)
    columns = min(3, max(1, math.ceil(math.sqrt(len(prepared)))))
    rows = math.ceil(len(prepared) / columns)
    width, height = max(297, columns * step_x + 40), max(210, rows * step_y + 40)
    root_id = _uuid()
    libraries = _node("lib_symbols")
    document = _node(
        "kicad_sch",
        _node("version", 20250114),
        _node("generator", sexpdata.Symbol("atopile_local")),
        _node("uuid", root_id),
        _node("paper", "User", round(width, 2), round(height, 2)),
        _node(
            "title_block",
            _node("title", f"{root.name} — {data['target']}"),
            _node(
                "comment", 1, "Generated from PCB pad nets; editable one-way snapshot"
            ),
            _node("comment", 2, "Circuit revision " + data["revision"]),
        ),
        libraries,
    )
    added: set[str] = set()
    for index, (component, lib_id, definition, pins) in enumerate(prepared):
        if lib_id not in added:
            libraries.append(definition)
            added.add(lib_id)
        x = round(round((25 + step_x / 2 + index % columns * step_x) / 1.27) * 1.27, 4)
        y = round(round((20 + step_y / 2 + index // columns * step_y) / 1.27) * 1.27, 4)
        try:
            symbol_id = str(uuid.UUID(component["id"]))
        except ValueError:
            symbol_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, data["layoutPath"] + component["id"])
            )
        pcb_fp = pcb_footprints.get(component["id"])
        if pcb_fp is None:
            raise ValueError(
                f"{component['reference']}: PCB changed while preparing "
                "its schematic; try again"
            )
        # North-facing labels extend beyond their pin stubs. Reserve that space
        # before placing the reference/value, so vertical parts stay readable.
        above = y + component["symbol"]["bounds"]["y"] - 2.54 - label_width - 7.62
        source = component.get("source")
        source_location = ""
        if source:
            source_file = _safe_path(root, Path(source["path"]))
            source_location = f"{source_file.relative_to(root)}:{source['line']}"
        item = _node(
            "symbol",
            _node("lib_id", lib_id),
            _node("at", x, y, 0),
            _node("unit", 1),
            _node("in_bom", sexpdata.Symbol("yes")),
            _node("on_board", sexpdata.Symbol("yes")),
            _node("dnp", sexpdata.Symbol("no")),
            _node("uuid", symbol_id),
            _property("Reference", component["reference"], x, above),
            _property("Value", component["value"], x, above + 2.54),
            _property("Footprint", pcb_fp.name, x, y, hidden=True),
            _property("AtopileAddress", component["atoAddress"], x, y, hidden=True),
            _property("AtopileSource", source_location, x, y, hidden=True),
            _property("AtopilePCBFootprintUUID", component["id"], x, y, hidden=True),
            _property(
                "AtopilePCB",
                str(Path(data["layoutPath"]).relative_to(root)),
                x,
                y,
                hidden=True,
            ),
        )
        for pin in pins:
            number = str(pin["number"])
            item.append(_node("pin", number, _node("uuid", _uuid())))
            px, py = round(x + pin["x"], 6), round(y + pin["y"], 6)
            net = assignments[component["reference"], number]
            if net is None:
                document.append(
                    _node("no_connect", _node("at", px, py), _node("uuid", _uuid()))
                )
                continue
            angle = math.radians(pin["rotation"])
            ex, ey = (
                round(px - 2.54 * math.cos(angle), 6),
                round(py - 2.54 * math.sin(angle), 6),
            )
            document.append(
                _node(
                    "wire",
                    _node("pts", _node("xy", px, py), _node("xy", ex, ey)),
                    _node(
                        "stroke",
                        _node("width", 0),
                        _node("type", sexpdata.Symbol("default")),
                    ),
                    _node("uuid", _uuid()),
                )
            )
            label_angle = int((180 - pin["rotation"]) % 360)
            document.append(
                _node(
                    "global_label",
                    net,
                    _node("shape", sexpdata.Symbol("passive")),
                    _node("at", ex, ey, label_angle),
                    _effects(justify="left" if label_angle in {0, 90} else "right"),
                    _node("uuid", _uuid()),
                )
            )
        item.append(
            _node(
                "instances",
                _node(
                    "project",
                    path.stem,
                    _node(
                        "path",
                        "/" + root_id,
                        _node("reference", component["reference"]),
                        _node("unit", 1),
                    ),
                ),
            )
        )
        document.append(item)
    document.append(_node("sheet_instances", _node("path", "/", _node("page", "1"))))
    return document


def _find_cli() -> str:
    executable = shutil.which("kicad-cli")
    if executable:
        return executable
    mac = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    if mac.is_file():
        return str(mac)
    raise RuntimeError(
        "Install KiCad or add kicad-cli to PATH to validate a native schematic export"
    )


def _native_netlist(path: Path) -> list:
    """Read native connectivity without writing any output beside the schematic."""
    environment = {
        key: value
        for key, value in _clean_env_for_kicad().items()
        if key
        not in {
            "VIRTUAL_ENV",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "CODEX_API_KEY",
            "CODEX_ACCESS_TOKEN",
            "ATOPILE_AGENT_API_KEY",
            "ATOPILE_AGENT_OPENAI_API_KEY",
            "ATOPILE_AGENT_ANTHROPIC_API_KEY",
        }
    }
    with tempfile.TemporaryDirectory(prefix="atopile-schematic-verify-") as temp:
        netlist_path = Path(temp) / "native.net"
        try:
            result = subprocess.run(
                [
                    _find_cli(),
                    "sch",
                    "export",
                    "netlist",
                    "--format",
                    "kicadsexpr",
                    "--output",
                    str(netlist_path),
                    str(path),
                ],
                cwd=path.parent,
                env=environment,
                capture_output=True,
                text=True,
                timeout=NATIVE_VERIFY_TIMEOUT,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                "KiCad schematic connectivity verification timed out"
            ) from error
        if result.returncode or not netlist_path.is_file():
            detail = (
                result.stderr or result.stdout or "no netlist was produced"
            ).strip()[-600:]
            raise RuntimeError("KiCad rejected the schematic: " + detail)
        with netlist_path.open("rb") as source:
            raw = source.read(MAX_NETLIST_BYTES + 1)
        if len(raw) > MAX_NETLIST_BYTES:
            raise RuntimeError("KiCad verification netlist exceeds the size limit")
        try:
            native = sexpdata.loads(raw.decode("utf-8"))
        except Exception as error:
            raise RuntimeError(
                "KiCad produced an invalid verification netlist"
            ) from error
        if not isinstance(native, list) or _tag(native) != "export":
            raise RuntimeError("KiCad produced an invalid verification netlist")
    return native


def verify_native_connectivity(
    path: Path, data: dict[str, Any]
) -> dict[str, set[tuple[str, str]]]:
    """Use KiCad's own parser/connectivity engine, requiring exact named nets."""
    expected = _terminal_assignments(data)
    expected_nets: dict[str, set[tuple[str, str]]] = {}
    for terminal, net in expected.items():
        if net is not None:
            expected_nets.setdefault(net, set()).add(terminal)
    native = _native_netlist(path)
    native_references = {
        str(_field(component, "ref")[1])
        for component in _children(_field(native, "components"), "comp")
        if len(_field(component, "ref")) > 1
    }
    if native_references != {
        component["reference"] for component in data["components"]
    }:
        raise RuntimeError("KiCad exported different component references from the PCB")
    actual_nets: dict[str, set[tuple[str, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for net in _children(_field(native, "nets"), "net"):
        name_node = _field(net, "name")
        name = str(name_node[1]) if len(name_node) > 1 else ""
        members = set()
        for member in _children(net, "node"):
            reference, pin = _field(member, "ref"), _field(member, "pin")
            if len(reference) > 1 and len(pin) > 1:
                members.add((str(reference[1]), str(pin[1])))
        if not members:
            continue
        if members & seen:
            raise RuntimeError("KiCad assigned a terminal to multiple exported nets")
        seen.update(members)
        if name in expected_nets:
            actual_nets.setdefault(name, set()).update(members)
        elif (
            len(members) == 1
            and name.startswith("unconnected-")
            and all(
                terminal in expected and expected[terminal] is None
                for terminal in members
            )
        ):
            continue
        else:
            raise RuntimeError(
                "KiCad native connectivity differs from the PCB pad nets"
            )
    if actual_nets != expected_nets:
        raise RuntimeError("KiCad native connectivity differs from the PCB pad nets")
    # KiCad may omit no-connect pins entirely; it must include every connected pin
    # and may never invent a terminal or join two unassigned terminals together.
    if not seen <= expected.keys():
        raise RuntimeError("KiCad exported an unexpected schematic terminal")
    return actual_nets


def _read_local_file(root: Path, path: Path, limit: int) -> bytes:
    path = _safe_path(root, path)
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Configured schematic inputs must be regular project files")
    with path.open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Configured schematic input exceeds its size limit")
    return raw


def _relative_schematic(root: Path, parent: Path, value: Any) -> Path:
    # KiCad expands variables itself. Only literal relative paths can be checked
    # before invoking it, so reject URI/drive/env syntax rather than guessing.
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or any(ord(char) < 32 for char in value)
        or any(char in value for char in ("\\", ":", "$"))
        or value.startswith("~")
        or Path(value).is_absolute()
        or Path(value).suffix.lower() != ".kicad_sch"
    ):
        raise ValueError(
            "Configured schematic paths must be literal project-relative .kicad_sch files"
        )
    return _safe_path(root, parent / value)


def _configured_schematic(root: Path, target: str) -> Path | None:
    config_path = root / ".atopile-local.json"
    if not config_path.exists() and not config_path.is_symlink():
        return None
    raw = _read_local_file(root, config_path, MAX_PROJECT_CONFIG_BYTES)
    try:
        config = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ValueError(".atopile-local.json must contain valid JSON") from error
    if not isinstance(config, dict) or not isinstance(
        config.get("schematics", {}), dict
    ):
        raise ValueError(
            ".atopile-local.json schematics must be an object keyed by target"
        )
    schematics = config.get("schematics", {})
    if target not in schematics:
        return None
    return _relative_schematic(root, root, schematics[target])


def _hierarchy_revision(root: Path, schematic: Path) -> str:
    """Confine and bound every native child sheet before KiCad can load it."""
    files: dict[Path, bytes] = {}
    active: set[Path] = set()
    total = 0

    def visit(path: Path, depth: int) -> None:
        nonlocal total
        path = _safe_path(root, path)
        if path in active:
            raise ValueError("Configured schematic hierarchy contains a sheet cycle")
        if path in files:
            return
        if depth > MAX_HIERARCHY_DEPTH or len(files) >= MAX_HIERARCHY_FILES:
            raise ValueError("Configured schematic hierarchy exceeds its sheet limit")
        raw = _read_local_file(root, path, MAX_SCHEMATIC_BYTES)
        total += len(raw)
        if total > MAX_HIERARCHY_BYTES:
            raise ValueError("Configured schematic hierarchy exceeds its size limit")
        try:
            document = sexpdata.loads(raw.decode("utf-8"))
        except Exception as error:
            raise ValueError(
                "Configured schematic contains invalid KiCad syntax"
            ) from error
        if not isinstance(document, list) or _tag(document) != "kicad_sch":
            raise ValueError(
                "Configured schematic must be a native .kicad_sch document"
            )
        files[path] = raw
        active.add(path)
        for sheet in _children(document, "sheet"):
            filenames = [
                prop[2]
                for prop in _children(sheet, "property")
                if len(prop) > 2
                and str(prop[1]).lower().replace(" ", "") == "sheetfile"
            ]
            if len(filenames) != 1:
                raise ValueError(
                    "Each native schematic sheet needs one Sheetfile property"
                )
            visit(_relative_schematic(root, path.parent, filenames[0]), depth + 1)
        active.remove(path)

    visit(schematic, 0)
    digest = hashlib.sha256()
    for path, raw in sorted(files.items()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()[:16]


def _open_configured_schematic(root: Path, target: str, path: Path) -> dict[str, Any]:
    config = ProjectConfig.from_path(root)
    if config is None or target not in config.builds:
        raise ValueError(f"Unknown build target: {target}")
    layout = _safe_path(root, config.builds[target].paths.layout)
    revision = _hierarchy_revision(root, path)
    native = _native_netlist(path)
    references = [
        str(_field(component, "ref")[1])
        for component in _children(_field(native, "components"), "comp")
        if len(_field(component, "ref")) > 1
    ]
    if not references or len(references) != len(set(references)):
        raise RuntimeError("KiCad exported empty or duplicate schematic references")
    # Single-pin native nets include deliberate no-connects. Count connected
    # native nets, without suggesting they were compared against the PCB.
    net_count = sum(
        len(_children(net, "node")) > 1
        for net in _children(_field(native, "nets"), "net")
    )
    if (
        _configured_schematic(root, target) != path
        or _hierarchy_revision(root, path) != revision
    ):
        raise RuntimeError(
            "Configured schematic changed during native verification; try again"
        )
    return {
        "path": str(path),
        "relativePath": str(path.relative_to(root)),
        "projectRoot": str(root),
        "target": target,
        "revision": revision,
        "layoutPath": str(layout),
        "componentCount": len(references),
        "netCount": net_count,
        "warnings": [
            "Opening the configured existing KiCad schematic; PCB connectivity was not compared."
        ],
        "reused": True,
    }


def _manifest(directory: Path) -> dict[str, Any] | None:
    path = directory / "latest.json"
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(
            "Native schematic export manifest must be a regular local file"
        )
    with path.open("rb") as source:
        raw = source.read(MAX_MANIFEST_BYTES + 1)
    try:
        value = json.loads(raw)
        if (
            len(raw) > MAX_MANIFEST_BYTES
            or not isinstance(value, dict)
            or type(value.get("version")) is not int
            or value.get("version") != 1
        ):
            raise ValueError
        if not isinstance(value.get("revision"), str) or not re.fullmatch(
            r"[0-9a-f]{16,64}", value["revision"]
        ):
            raise ValueError
        filename = value.get("filename")
        if not isinstance(filename, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+\.kicad_sch", filename
        ):
            raise ValueError
        candidate = directory / filename
        if candidate.is_symlink() or candidate.resolve().parent != directory:
            raise ValueError
        if candidate.exists() and not stat.S_ISREG(candidate.stat().st_mode):
            raise ValueError
        return value
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError(
            "Native schematic export manifest is invalid or escapes "
            "its generated directory"
        ) from error


def export_schematic(
    project_root: str | Path, target: str = "default", *, force_new: bool = False
) -> dict[str, Any]:
    """Export or reopen an editable snapshot, never overwriting an edited export."""
    if not isinstance(force_new, bool):
        raise ValueError("force_new must be a boolean")
    root = Path(project_root).resolve()
    if (
        not force_new
        and (configured := _configured_schematic(root, target)) is not None
    ):
        return _open_configured_schematic(root, target, configured)
    data = get_schematic_data(root, target)
    config = ProjectConfig.from_path(root)
    directory = _safe_path(
        root, config.builds[target].paths.output_base.parent / "schematic"
    )
    directory.mkdir(parents=True, exist_ok=True)
    previous = _manifest(directory)
    warnings = list(dict.fromkeys([*data["warnings"], _ASSOCIATION_WARNING]))
    result = {
        "projectRoot": str(root),
        "target": target,
        "revision": data["revision"],
        "layoutPath": data["layoutPath"],
        "componentCount": len(data["components"]),
        "netCount": len(data["nets"]),
        "warnings": warnings,
        "reused": False,
    }
    if previous and previous["revision"] == data["revision"] and not force_new:
        path = directory / previous["filename"]
        if path.is_file():
            return {
                **result,
                "path": str(path),
                "relativePath": str(path.relative_to(root)),
                "reused": True,
            }
    filename = f"schematic-{_slug(target)}-{data['revision']}-{uuid.uuid4().hex[:12]}"
    path = directory / (filename + ".kicad_sch")
    document = _document(root, data, path)
    # Exclusive creation preserves every previous export and every native edit.
    with path.open("x", encoding="utf-8") as output:
        output.write(_format(document) + "\n")
    try:
        verify_native_connectivity(path, data)
        # A PCB/source edit during KiCad's check must not certify an older circuit
        # as the current export. Its earlier editable exports remain untouched.
        if get_schematic_data(root, target)["revision"] != data["revision"]:
            raise RuntimeError(
                "Circuit changed during native schematic export; try again"
            )
        latest = {"version": 1, "revision": data["revision"], "filename": path.name}
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory, prefix=".latest-", delete=False
        ) as output:
            json.dump(latest, output, indent=2)
            output.write("\n")
            temporary_manifest = Path(output.name)
        try:
            os.replace(temporary_manifest, directory / "latest.json")
        finally:
            temporary_manifest.unlink(missing_ok=True)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {**result, "path": str(path), "relativePath": str(path.relative_to(root))}

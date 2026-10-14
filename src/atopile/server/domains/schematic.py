"""Read-only schematic projection of an existing board's logical pad nets.

The PCB is the connectivity authority. Pinout/BOM and KiCad symbol files only
provide labels, source references and artwork; they never create connections.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from atopile.config import ProjectConfig
from atopile.server.domains.schematic_models import SchematicData, SchematicSelection
from faebryk.libs.kicad.fileformats import Property, kicad


def _within(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Schematic artifact/source path escapes the project root")
    return resolved


def _json(root: Path, path: Path, warnings: list[str]) -> Any:
    path = _within(root, path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        warnings.append(f"Could not read {path.relative_to(root)}: {exc}")
        return None


def _property(footprint: Any, name: str) -> str:
    return Property.try_get_property(footprint.propertys, name) or ""


def _address_parts(type_name: str) -> list[tuple[str, str]]:
    return [
        tuple(part.split("::", 1))
        for part in type_name.split("|")
        if "::" in part and part.split("::", 1)[0].endswith((".ato", ".py"))
    ]


def _source_file(root: Path, src_root: Path, name: str) -> Path | None:
    for candidate in (root / name, src_root / name):
        try:
            candidate = _within(root, candidate)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def _source_reference(
    root: Path, src_root: Path, type_name: str
) -> dict[str, Any] | None:
    """Locate a declaration only when the address identifies an unambiguous line."""
    # The last concrete member in the address chain is the physical part's
    # declaration; earlier members may only instantiate an enclosing module.
    for filename, address in reversed(_address_parts(type_name)):
        path = _source_file(root, src_root, filename)
        if path is None:
            continue
        parts = address.split(".")
        if len(parts) < 2:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        module = re.compile(rf"^(?:module|component)\s+{re.escape(parts[0])}\s*:")
        starts = [i for i, line in enumerate(lines) if module.match(line)]
        if len(starts) != 1:
            continue
        start = starts[0] + 1
        end = next(
            (
                i
                for i in range(start, len(lines))
                if lines[i]
                and not lines[i][0].isspace()
                and not lines[i].lstrip().startswith("#")
            ),
            len(lines),
        )
        # The first member is the concrete user instantiation at this source
        # boundary; deeper members are resolved in subsequent type segments.
        declaration = re.compile(rf"^\s+{re.escape(parts[1])}\s*=\s*new\b")
        matches = [i for i in range(start, end) if declaration.match(lines[i])]
        if len(matches) == 1:
            return {"path": str(path), "line": matches[0] + 1}
    return None


def _symbol_reference(
    root: Path, src_root: Path, type_name: str
) -> tuple[str, Path | None]:
    """Read the atomic part's explicit symbol trait; never evaluate source code."""
    for filename, address in reversed(_address_parts(type_name)):
        path = _source_file(root, src_root, filename)
        if path is None or path.suffix != ".ato":
            continue
        text = path.read_text(encoding="utf-8")
        component_name = address.split(".")[0]
        section = re.search(
            rf"^(?:component|module)\s+{re.escape(component_name)}\s*:\s*\n"
            r"(?P<body>(?:[ \t].*\n|\s*\n)*)",
            text + "\n",
            re.MULTILINE,
        )
        if section is None:
            continue
        symbol = re.search(r"\bsymbol\s*=\s*[\"']([^\"']+)[\"']", section["body"])
        if symbol:
            name = symbol[1]
            if name.endswith(".kicad_sym"):
                try:
                    return Path(name).stem, _within(root, path.parent / name)
                except ValueError:
                    return "", None
            return name, None
    return "", None


def _fallback_symbol(pins: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """A marked pin box, not invented component-specific symbol artwork."""
    height = max(7.5, (len(pins) + 1) * 2.5)
    return {
        "name": name or "Missing symbol",
        "libId": name,
        "status": "missing",
        "missing": True,
        "warnings": ["Symbol artwork unavailable; showing a pin box."],
        "bounds": {"x": -7.5, "y": -height / 2, "width": 15, "height": height},
        "primitives": [
            {
                "type": "rect",
                "x": -5,
                "y": -height / 2,
                "width": 10,
                "height": height,
                "fill": "none",
            }
        ],
        "pins": [
            {
                **pin,
                "x": -7.5,
                "y": -height / 2 + (i + 1) * 2.5,
                "endX": -5,
                "endY": -height / 2 + (i + 1) * 2.5,
            }
            for i, pin in enumerate(pins)
        ],
    }


def get_schematic_data(
    project_root: str | Path, target: str = "default"
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    if not (root / "ato.yaml").is_file():
        raise ValueError("Select a project containing ato.yaml")
    cfg = ProjectConfig.from_path(root)
    if cfg is None or target not in cfg.builds:
        raise ValueError(f"Unknown build target: {target}")
    build = cfg.builds[target]
    layout_path = _within(root, build.paths.layout)
    if not layout_path.is_file():
        raise ValueError("Build this target first to generate its PCB connectivity")
    output_base = _within(root, build.paths.output_base)
    src_root = _within(root, cfg.paths.src)
    warnings: list[str] = []
    pinouts: dict[str, Any] = {}
    pinout_dir = _within(root, output_base.parent / "pinout")
    for path in sorted(pinout_dir.glob("*.json")):
        data = _json(root, path, warnings)
        if isinstance(data, dict) and data.get("designator"):
            pinouts[str(data["designator"])] = data
    bom = _json(root, output_base.with_suffix(".bom.json"), warnings)
    usages: dict[str, tuple[dict[str, Any], str]] = {}
    if isinstance(bom, dict):
        for part in bom.get("components", []):
            if not isinstance(part, dict):
                continue
            for usage in part.get("usages", []):
                if isinstance(usage, dict) and usage.get("designator"):
                    usages[str(usage["designator"])] = (
                        part,
                        str(usage.get("address", "")),
                    )

    # Text parsing intentionally bypasses file/path caches for build/editor updates.
    pcb = kicad.loads(
        kicad.pcb.PcbFile, layout_path.read_text(encoding="utf-8")
    ).kicad_pcb
    components: list[dict[str, Any]] = []
    net_members: dict[str, list[dict[str, Any]]] = {}
    for index, fp in enumerate(pcb.footprints):
        reference = _property(fp, "Reference")
        component_id = str(fp.uuid or f"footprint-{index}")
        pinout = pinouts.get(reference, {})
        part, usage_address = usages.get(reference, ({}, ""))
        type_name = str(pinout.get("typeName") or usage_address)
        labels = {
            str(number): str(lead.get("leadDesignator", number))
            for lead in pinout.get("leads", [])
            for number in lead.get("padNumbers", [])
        }
        seen: set[tuple[str, str | None]] = set()
        pins: list[dict[str, Any]] = []
        for pad in fp.pads:
            number = str(pad.name)
            if not number:  # mechanical pads are not electrical terminals
                continue
            net_name = pad.net.name if pad.net and pad.net.name else None
            key = (number, net_name)
            if key in seen:
                continue
            seen.add(key)
            pin = {
                "number": number,
                "name": labels.get(number, number),
                "net": net_name,
            }
            pins.append(pin)
            if net_name:
                net_members.setdefault(net_name, []).append(
                    {
                        "componentId": component_id,
                        "reference": reference,
                        "pin": number,
                    }
                )
        for lead in pinout.get("leads", []):
            for number in lead.get("padNumbers", []):
                actual = [p["net"] for p in pins if p["number"] == str(number)]
                if actual and lead.get("netName") and lead["netName"] not in actual:
                    warnings.append(
                        f"{reference} pin {number}: stale pinout net ignored; "
                        "using PCB pad net."
                    )
        source = _source_reference(root, src_root, type_name)
        symbol_id, symbol_path = _symbol_reference(root, src_root, type_name)
        symbol: dict[str, Any] = {}
        try:
            from atopile.server.domains.schematic_symbols import load_schematic_symbol

            if symbol_id:
                symbol = load_schematic_symbol(root, symbol_id, symbol_path=symbol_path)
        except (OSError, ValueError) as exc:
            warnings.append(f"{reference}: could not load symbol: {exc}")
        symbol_numbers = {str(p.get("number")) for p in symbol.get("pins", [])}
        missing_pins = {p["number"] for p in pins} - symbol_numbers
        if not symbol.get("primitives") or missing_pins:
            if missing_pins and symbol.get("primitives"):
                warnings.append(
                    f"{reference}: symbol lacks PCB pins "
                    f"{', '.join(sorted(missing_pins))}; using pin box."
                )
            symbol = _fallback_symbol(pins, symbol_id)
        else:
            symbol["missing"] = symbol.get("status") == "missing"
        warnings.extend(
            f"{reference}: {warning}" for warning in symbol.get("warnings", [])
        )
        components.append(
            {
                "id": component_id,
                "reference": reference,
                "value": _property(fp, "Value")
                or str(part.get("value") or part.get("mpn") or ""),
                "atoAddress": _property(fp, "atopile_address")
                or str(pinout.get("atoAddress", "")),
                "source": source,
                "symbol": symbol,
                "pins": pins,
            }
        )
    components.sort(key=lambda c: c["reference"])
    result = {
        "version": 1,
        "projectRoot": str(root),
        "target": target,
        "layoutPath": str(layout_path),
        "connectivityKind": "logical_pad_net_assignments",
        "components": components,
        "nets": [
            {"id": name, "name": name, "members": members}
            for name, members in sorted(net_members.items())
        ],
        "warnings": list(dict.fromkeys(warnings)),
    }
    result["revision"] = hashlib.sha256(
        json.dumps(result, sort_keys=True).encode()
    ).hexdigest()[:16]
    return SchematicData.model_validate(result).model_dump(by_alias=True)


def component_source(data: dict[str, Any], component_id: str) -> dict[str, Any]:
    component = next((c for c in data["components"] if c["id"] == component_id), None)
    if component is None or component["source"] is None:
        raise ValueError("No project source declaration was found for this component")
    source = component["source"]
    # Recheck at the moment of opening, including symlink changes since reading.
    path = _within(Path(data["projectRoot"]).resolve(), Path(source["path"]))
    if not path.is_file():
        raise ValueError("Component source file no longer exists")
    return {"path": str(path), "line": max(1, int(source["line"]))}


def schematic_selection(
    data: dict[str, Any], *, component_id: str = "", net_name: str = ""
) -> dict[str, Any]:
    """Viewer decoration IDs derived only from the current board's terminals."""
    if component_id:
        component = next(
            (c for c in data["components"] if c["id"] == component_id), None
        )
        if component is None:
            raise ValueError("Unknown schematic component")
        members = [
            {"componentId": component_id, "pin": p["number"]} for p in component["pins"]
        ]
        component_ids = [component_id]
    else:
        net = next((n for n in data["nets"] if n["name"] == net_name), None)
        if net is None:
            raise ValueError("Unknown schematic net")
        members = net["members"]
        component_ids = list(dict.fromkeys(m["componentId"] for m in members))
    pad_ids = list(
        dict.fromkeys(f"fp:{m['componentId']}:pad:{m['pin']}" for m in members)
    )
    return SchematicSelection.model_validate(
        {
            "projectRoot": data["projectRoot"],
            "target": data["target"],
            "layoutPath": data["layoutPath"],
            "componentIds": component_ids,
            "padIds": pad_ids,
            "netName": net_name or None,
        }
    ).model_dump(by_alias=True)

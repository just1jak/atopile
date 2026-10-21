"""Local PCB inspection, placement, and KiCad DRC tools."""

from __future__ import annotations

import asyncio
import json
import math
import shutil
import subprocess
import time
import uuid
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, TypedDict

import sexpdata
from atopile.model.pcb_transaction import (
    commit_pcb_bytes,
    finish_board_edit,
    pcb_write_lock,
)

from atopile.agent.scope import Scope
from atopile.agent.tools.registry import tool
from atopile.config import ProjectConfig
from faebryk.libs.kicad.fileformats import Property, kicad


class LayoutArgs(TypedDict, total=False):
    path: str
    target: str
    max_components: int
    max_nets: int
    net: str
    max_pads: int
    max_items: int


class PositionOptions(LayoutArgs, total=False):
    rotation_deg: float
    layer: str


class PositionArgs(PositionOptions):
    address: str


class SetPositionArgs(PositionArgs):
    x_mm: float
    y_mm: float


class AddSegmentArgs(LayoutArgs):
    net: str
    start_x_mm: float
    start_y_mm: float
    end_x_mm: float
    end_y_mm: float
    width_mm: float
    layer: str


class AddViaArgs(LayoutArgs):
    net: str
    x_mm: float
    y_mm: float
    diameter_mm: float
    drill_mm: float


class DeleteCopperArgs(LayoutArgs):
    uuid: str


def resolve_layout_target(project_root: Path, requested: str | None) -> str:
    config = ProjectConfig.from_path(project_root)
    if config is None:
        raise ValueError("No ato.yaml found; specify the PCB path")
    if requested:
        if requested not in config.builds:
            raise ValueError(f"Unknown build target: {requested}")
        return requested
    if "default" in config.builds:
        return "default"
    if len(config.builds) == 1:
        return next(iter(config.builds))
    raise ValueError(
        "Select a build target for this project: " + ", ".join(sorted(config.builds))
    )


def _requested_layout_target(args: LayoutArgs, scope: Scope) -> str | None:
    explicit = str(args.get("target") or "").strip()
    return explicit or (scope.selected_target or "").strip() or None


def _layout_path(args: LayoutArgs, scope: Scope) -> Path:
    if args.get("path"):
        path = scope.resolve(args["path"])
    else:
        config = ProjectConfig.from_path(scope.project_root)
        if config is None:
            raise ValueError("No ato.yaml found; specify the PCB path")
        target = resolve_layout_target(
            scope.project_root,
            _requested_layout_target(args, scope),
        )
        path = scope.resolve(str(config.builds[target].paths.layout))
    if not path.is_file() or path.suffix.lower() != ".kicad_pcb":
        raise ValueError(f"KiCad PCB does not exist: {path}")
    return path


def _load(path: Path) -> Any:
    # Parse text, avoiding the path cache when an editor changed the board.
    return kicad.loads(kicad.pcb.PcbFile, path.read_text(encoding="utf-8"))


def _property(footprint: Any, name: str) -> str:
    return Property.try_get_property(footprint.propertys, name) or ""


def _raw_locked_footprints(text: str) -> set[str]:
    """Read footprint locks the bundled native parser does not preserve."""
    locked = set()
    for item in sexpdata.loads(text)[1:]:
        if not isinstance(item, list) or str(item[0]) != "footprint":
            continue
        uuid = ""
        is_locked = False
        for field in item[2:]:
            if isinstance(field, sexpdata.Symbol) and str(field) == "locked":
                is_locked = True
            elif isinstance(field, list) and field:
                if str(field[0]) == "uuid":
                    uuid = str(field[1])
                elif str(field[0]) == "locked":
                    is_locked = len(field) == 1 or str(field[1]) in {"yes", "true"}
        if is_locked:
            locked.add(uuid)
    return locked


def _component(footprint: Any) -> dict[str, Any]:
    return {
        "reference": _property(footprint, "Reference"),
        "address": _property(footprint, "atopile_address"),
        "value": _property(footprint, "Value"),
        "x_mm": float(footprint.at.x),
        "y_mm": float(footprint.at.y),
        "rotation_deg": float(footprint.at.r or 0),
        "layer": footprint.layer,
        "locked": bool(getattr(footprint, "locked", False))
        or any(t.text == "FBRK:notouch" for t in footprint.fp_texts),
    }


def _find_component(pcb: Any, address: str) -> Any:
    query = address.strip().casefold()
    if not query:
        raise ValueError("Component address or reference is required")
    matches = [
        fp
        for fp in pcb.footprints
        if query
        in {
            _property(fp, "Reference").casefold(),
            _property(fp, "atopile_address").casefold(),
        }
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one exact reference/address match for {address!r}; "
            f"found {len(matches)}. Use layout_get_summary to inspect components."
        )
    return matches[0]


def _netlist(pcb: Any) -> dict[str, list[dict[str, str]]]:
    nets: dict[str, list[dict[str, str]]] = {}
    for footprint in pcb.footprints:
        for pad in footprint.pads:
            if pad.net and pad.net.name:
                nets.setdefault(pad.net.name, []).append(
                    {
                        "reference": _property(footprint, "Reference"),
                        "address": _property(footprint, "atopile_address"),
                        "pad": str(pad.name),
                    }
                )
    return dict(sorted(nets.items()))


@tool(
    "Inspect the local KiCad board: components, positions, "
    "track/via counts, and net names. "
    "Use path or the project's build target. This does not certify routing or DRC.",
    label="Inspected PCB",
)
async def layout_get_summary(args: LayoutArgs, scope: Scope) -> dict[str, Any]:
    path = _layout_path(args, scope)
    pcb = (await asyncio.to_thread(_load, path)).kicad_pcb
    components = [_component(fp) for fp in pcb.footprints]
    raw_locks = _raw_locked_footprints(path.read_text(encoding="utf-8"))
    for footprint, component in zip(pcb.footprints, components):
        component["locked"] = component["locked"] or footprint.uuid in raw_locks
    nets = _netlist(pcb)
    component_limit = max(1, min(500, int(args.get("max_components", 100))))
    net_limit = max(1, min(500, int(args.get("max_nets", 100))))
    return {
        "target": resolve_layout_target(
            scope.project_root, _requested_layout_target(args, scope)
        )
        if not args.get("path")
        else _requested_layout_target(args, scope),
        "layout_path": str(path),
        "component_count": len(components),
        "components": components[:component_limit],
        "components_truncated": len(components) > component_limit,
        "net_count": len(nets),
        "net_names": list(nets)[:net_limit],
        "nets_truncated": len(nets) > net_limit,
        "track_count": len(pcb.segments) + len(pcb.arcs),
        "via_count": len(pcb.vias),
        "zone_count": len(pcb.zones),
    }


@tool(
    "Read logical connectivity from local PCB pad net assignments, "
    "optionally for one exact net name. This describes intended pad connections; "
    "run layout_run_drc to check unrouted connections.",
    label="Read net connectivity",
)
async def layout_get_netlist(args: LayoutArgs, scope: Scope) -> dict[str, Any]:
    path = _layout_path(args, scope)
    pcb = (await asyncio.to_thread(_load, path)).kicad_pcb
    nets = _netlist(pcb)
    query = args.get("net")
    if query:
        if query not in nets:
            raise ValueError(f"Unknown net name: {query}")
        nets = {query: nets[query]}
    net_limit = max(1, min(500, int(args.get("max_nets", 100))))
    pad_limit = max(1, min(500, int(args.get("max_pads", 100))))
    return {
        "layout_path": str(path),
        "connectivity_kind": "logical_pad_net_assignments",
        "net_count": len(nets),
        "nets": [
            {
                "name": name,
                "pad_count": len(pads),
                "pads": pads[:pad_limit],
                "pads_truncated": len(pads) > pad_limit,
            }
            for name, pads in list(nets.items())[:net_limit]
        ],
        "nets_truncated": len(nets) > net_limit,
    }


@tool(
    "Get a footprint's local PCB position by exact reference or atopile address.",
    label="Read placement",
)
async def layout_get_component_position(
    args: PositionArgs, scope: Scope
) -> dict[str, Any]:
    path = _layout_path(args, scope)
    pcb = (await asyncio.to_thread(_load, path)).kicad_pcb
    return {
        "layout_path": str(path),
        "component": _component(_find_component(pcb, args["address"])),
    }


def _set_position(args: SetPositionArgs, scope: Scope) -> dict[str, Any]:
    from faebryk.exporters.pcb.kicad.transformer import PCB_Transformer

    path = _layout_path(args, scope)
    with pcb_write_lock(path):
        original = path.read_bytes()
        raw_locks = _raw_locked_footprints(original.decode("utf-8"))
        pcb_file = kicad.loads(kicad.pcb.PcbFile, original.decode("utf-8"))
        if raw_locks and not getattr(pcb_file, "preserves_unknown_fields", False):
            raise ValueError(
                "Board contains locked KiCad footprints. Edit this board in KiCad; "
                "the bundled parser does not preserve native footprint locks."
            )
        footprint = _find_component(pcb_file.kicad_pcb, args["address"])
        before = _component(footprint)
        if (
            footprint.uuid in raw_locks
            or before["locked"]
            or any(t.text == "FBRK:notouch" for t in footprint.fp_texts)
        ):
            raise ValueError("Component is locked or marked FBRK:notouch")
        x, y = _finite(args["x_mm"], "x_mm"), _finite(args["y_mm"], "y_mm")
        rotation = _finite(
            args.get("rotation_deg", before["rotation_deg"]), "rotation_deg"
        )
        layer = args.get("layer", footprint.layer)
        if layer not in {"F.Cu", "B.Cu"}:
            raise ValueError("Footprint layer must be F.Cu or B.Cu")
        PCB_Transformer.move_fp(
            footprint, kicad.pcb.Xyr(x=x, y=y, r=rotation % 360), layer
        )
        updated = kicad.dumps(pcb_file)
        backup = commit_pcb_bytes(path, original, updated)
        return {
            "updated": True,
            "layout_path": str(path),
            "backup_path": str(backup) if backup else None,
            "before": before,
            "after": _component(footprint),
            "routing_recomputed": False,
            "drc_checked": False,
            "zone_fill_needs_refresh": True,
        }


@tool(
    "Move/rotate/flip one footprint in the local KiCad PCB, preserving "
    "nets and tracks and saving a backup. Requires exact reference/address "
    "and absolute x_mm/y_mm. Locked components are refused. "
    "Existing routes are not recomputed; inspect and run layout_run_drc afterwards.",
    label="Updated placement",
)
async def layout_set_component_position(
    args: SetPositionArgs, scope: Scope
) -> dict[str, Any]:
    return await finish_board_edit(asyncio.to_thread(_set_position, args, scope))


def _copper_layers(pcb: Any) -> list[str]:
    # Canonical layer.name is electrical identity; alias is presentation only.
    return list(
        dict.fromkeys(layer.name for layer in pcb.layers if layer.name.endswith(".Cu"))
    )


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _outline_bounds(pcb: Any) -> dict[str, float]:
    """Conservative axis-aligned outline bounds; native DRC checks real clearance."""
    points: list[tuple[float, float]] = []
    for name in ("gr_lines", "gr_arcs", "gr_rects", "gr_circles", "gr_polys"):
        for geo in getattr(pcb, name, []):
            if getattr(geo, "layer", None) != "Edge.Cuts":
                continue
            if name == "gr_circles":
                radius = math.hypot(geo.end.x - geo.center.x, geo.end.y - geo.center.y)
                points.extend(
                    [
                        (geo.center.x - radius, geo.center.y - radius),
                        (geo.center.x + radius, geo.center.y + radius),
                    ]
                )
            elif name == "gr_polys":
                points.extend((p.x, p.y) for p in geo.pts.xys)
            else:
                points.extend(
                    (getattr(geo, key).x, getattr(geo, key).y)
                    for key in ("start", "mid", "end")
                    if hasattr(geo, key)
                )
    if not points or not all(math.isfinite(v) for p in points for v in p):
        raise ValueError("An Edge.Cuts outline is required for bounded manual routing")
    xs, ys = zip(*points)
    result = {
        "min_x_mm": min(xs),
        "max_x_mm": max(xs),
        "min_y_mm": min(ys),
        "max_y_mm": max(ys),
    }
    if min(xs) >= max(xs) or min(ys) >= max(ys):
        raise ValueError("The PCB outline does not have usable two-dimensional bounds")
    return result


def _check_points(pcb: Any, points: list[tuple[float, float]], margin: float) -> None:
    bounds = _outline_bounds(pcb)
    for x, y in points:
        if not (
            bounds["min_x_mm"] + margin <= x <= bounds["max_x_mm"] - margin
            and bounds["min_y_mm"] + margin <= y <= bounds["max_y_mm"] - margin
        ):
            raise ValueError("Copper lies outside the PCB outline bounding box")


def _native_net(pcb: Any, name: str) -> int:
    matches = [net.number for net in pcb.nets if net.name == name and net.number > 0]
    if len(matches) != 1:
        raise ValueError(f"Expected one existing assigned net named {name!r}")
    return matches[0]


def _raw_copper(text: str) -> list[list]:
    return [
        item
        for item in sexpdata.loads(text)[1:]
        if isinstance(item, list) and item and str(item[0]) in {"segment", "arc", "via"}
    ]


def _raw_uuid(item: list) -> str:
    return next(
        (
            str(field[1])
            for field in item
            if isinstance(field, list) and len(field) > 1 and str(field[0]) == "uuid"
        ),
        "",
    )


def _raw_is_locked(item: list) -> bool:
    return any(
        (isinstance(field, sexpdata.Symbol) and str(field) == "locked")
        or (
            isinstance(field, list)
            and field
            and str(field[0]) == "locked"
            and (len(field) == 1 or str(field[1]) in {"yes", "true"})
        )
        for field in item
    )


def _new_copper_uuid(original: str) -> str:
    value = str(uuid.uuid4())

    def identifiers(node: Any):
        if isinstance(node, list):
            if len(node) > 1 and str(node[0]) == "uuid":
                yield str(node[1])
            for child in node:
                yield from identifiers(child)

    if value in set(identifiers(sexpdata.loads(original))):
        raise RuntimeError("Generated copper UUID already exists; retry the operation")
    return value


def _route_item(
    item: Any, kind: str, nets: dict[int, str], locked: set[str]
) -> dict[str, Any]:
    result = {
        "uuid": str(item.uuid or ""),
        "kind": kind,
        "net": nets.get(item.net, ""),
        "net_id": item.net,
        "locked": bool(getattr(item, "locked", False)) or str(item.uuid) in locked,
    }
    if kind == "via":
        result.update(
            x_mm=item.at.x,
            y_mm=item.at.y,
            diameter_mm=item.size,
            drill_mm=item.drill,
            layers=list(item.layers),
        )
    else:
        result.update(
            start_x_mm=item.start.x,
            start_y_mm=item.start.y,
            end_x_mm=item.end.x,
            end_y_mm=item.end.y,
            width_mm=item.width,
            layer=item.layer,
        )
        if kind == "arc":
            result.update(mid_x_mm=item.mid.x, mid_y_mm=item.mid.y)
    return result


def _route_pads(pcb: Any, query: str | None) -> list[dict[str, Any]]:
    """World-coordinate electrical endpoints, including rotated footprints."""
    result = []
    copper = _copper_layers(pcb)
    for footprint in pcb.footprints:
        angle = math.radians(float(footprint.at.r or 0))
        cosine, sine = math.cos(angle), math.sin(angle)
        for pad in footprint.pads:
            if not pad.net or not pad.net.name or (query and pad.net.name != query):
                continue
            x = footprint.at.x + pad.at.x * cosine + pad.at.y * sine
            y = footprint.at.y - pad.at.x * sine + pad.at.y * cosine
            layers = [
                layer
                for layer in copper
                if any(
                    fnmatchcase(layer, rule)
                    or (rule == "F&B.Cu" and layer in {"F.Cu", "B.Cu"})
                    for rule in pad.layers
                )
            ]
            result.append(
                {
                    "reference": _property(footprint, "Reference"),
                    "address": _property(footprint, "atopile_address"),
                    "pad": str(pad.name),
                    "uuid": str(pad.uuid or ""),
                    "footprint_uuid": str(footprint.uuid or ""),
                    "net": pad.net.name,
                    "net_id": pad.net.number,
                    "x_mm": x,
                    "y_mm": y,
                    "copper_layers": layers,
                    "width_mm": pad.size.w,
                    "height_mm": pad.size.h or pad.size.w,
                }
            )
    return result


@tool(
    "Read existing local copper segments, arcs and vias, exact UUIDs, nets and "
    "canonical copper layer names and pad endpoints in global mm coordinates. "
    "Optionally filter one exact net. "
    "Geometry is not a DRC certificate.",
    label="Inspected routing",
)
async def layout_get_routes(args: LayoutArgs, scope: Scope) -> dict[str, Any]:
    path = _layout_path(args, scope)
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    pcb_file = await asyncio.to_thread(kicad.loads, kicad.pcb.PcbFile, text)
    pcb = pcb_file.kicad_pcb
    nets = {net.number: net.name or "" for net in pcb.nets}
    locked = {_raw_uuid(item) for item in _raw_copper(text) if _raw_is_locked(item)}
    query = args.get("net")
    if query:
        _native_net(pcb, query)
    items = [
        _route_item(item, kind, nets, locked)
        for kind, collection in (
            ("segment", pcb.segments),
            ("arc", pcb.arcs),
            ("via", pcb.vias),
        )
        for item in collection
        if not query or nets.get(item.net) == query
    ]
    limit = max(1, min(1000, int(args.get("max_items", 200))))
    pads = _route_pads(pcb, query)
    pad_limit = max(1, min(1000, int(args.get("max_pads", 200))))
    try:
        bounds = _outline_bounds(pcb)
    except ValueError:
        bounds = None
    return {
        "layout_path": str(path),
        "copper_layers": _copper_layers(pcb),
        "outline_bounds": bounds,
        "item_count": len(items),
        "items": items[:limit],
        "items_truncated": len(items) > limit,
        "pad_count": len(pads),
        "pads": pads[:pad_limit],
        "pads_truncated": len(pads) > pad_limit,
        "drc_checked": False,
    }


def _edit_copper(args: LayoutArgs, scope: Scope, operation: str) -> dict[str, Any]:
    path = _layout_path(args, scope)
    with pcb_write_lock(path):
        original = path.read_bytes()
        text = original.decode("utf-8")
        pcb_file = kicad.loads(kicad.pcb.PcbFile, text)
        pcb = pcb_file.kicad_pcb
        if not getattr(pcb_file, "preserves_unknown_fields", False) and (
            _raw_locked_footprints(text)
            or any(_raw_is_locked(item) for item in _raw_copper(text))
        ):
            raise ValueError(
                "This parser cannot preserve unrelated native locked items"
            )
        if operation == "segment":
            start = (
                _finite(args["start_x_mm"], "start_x_mm"),
                _finite(args["start_y_mm"], "start_y_mm"),
            )
            end = (
                _finite(args["end_x_mm"], "end_x_mm"),
                _finite(args["end_y_mm"], "end_y_mm"),
            )
            width = _finite(args["width_mm"], "width_mm")
            if not 0.05 <= width <= 10 or math.dist(start, end) < 1e-6:
                raise ValueError(
                    "Track width must be 0.05–10 mm and endpoints must differ"
                )
            layer = args["layer"]
            if layer not in _copper_layers(pcb):
                raise ValueError("Use an existing canonical copper layer, such as F.Cu")
            net = _native_net(pcb, args["net"])
            _check_points(pcb, [start, end], width / 2)
            item_id = _new_copper_uuid(text)
            item = kicad.pcb.Segment(
                start=kicad.pcb.Xy(x=start[0], y=start[1]),
                end=kicad.pcb.Xy(x=end[0], y=end[1]),
                width=width,
                layer=layer,
                net=net,
                uuid=item_id,
            )
            pcb.segments = [*pcb.segments, item]
        elif operation == "via":
            point = (_finite(args["x_mm"], "x_mm"), _finite(args["y_mm"], "y_mm"))
            diameter, drill = (
                _finite(args["diameter_mm"], "diameter_mm"),
                _finite(args["drill_mm"], "drill_mm"),
            )
            if not 0.1 <= drill < diameter <= 10:
                raise ValueError(
                    "Through-via drill must be at least 0.1 mm and smaller "
                    "than diameter (max 10 mm)"
                )
            if not {"F.Cu", "B.Cu"} <= set(_copper_layers(pcb)):
                raise ValueError("Through vias require existing F.Cu and B.Cu layers")
            net = _native_net(pcb, args["net"])
            _check_points(pcb, [point], diameter / 2)
            item_id = _new_copper_uuid(text)
            item = kicad.pcb.Via(
                at=kicad.pcb.Xy(x=point[0], y=point[1]),
                size=diameter,
                drill=drill,
                layers=["F.Cu", "B.Cu"],
                net=net,
                remove_unused_layers=None,
                keep_end_layers=None,
                zone_layer_connections=[],
                padstack=None,
                teardrops=None,
                tenting=None,
                free=None,
                locked=None,
                uuid=item_id,
            )
            pcb.vias = [*pcb.vias, item]
        elif operation == "delete":
            item_id = args["uuid"]
            try:
                uuid.UUID(item_id)
            except ValueError, TypeError, AttributeError:
                raise ValueError(
                    "Copper UUID must exactly match layout_get_routes output"
                ) from None
            matches = [
                (name, item)
                for name in ("segments", "arcs", "vias")
                for item in getattr(pcb, name)
                if str(item.uuid) == item_id
            ]
            if len(matches) != 1:
                raise ValueError("Expected one exact existing segment, arc or via UUID")
            if any(
                _raw_uuid(item) == item_id and _raw_is_locked(item)
                for item in _raw_copper(text)
            ):
                raise ValueError("Requested copper item is locked")
            name, item = matches[0]
            if getattr(item, "locked", False):
                raise ValueError("Requested copper item is locked")
            if any(
                item_id in [str(member) for member in group.members]
                for group in getattr(pcb, "groups", [])
            ):
                raise ValueError(
                    "Requested copper belongs to a group; "
                    "edit its membership in KiCad first"
                )
            setattr(
                pcb,
                name,
                [other for other in getattr(pcb, name) if str(other.uuid) != item_id],
            )
        else:
            raise ValueError("Unsupported copper operation")
        backup = commit_pcb_bytes(path, original, kicad.dumps(pcb_file))
        return {
            "updated": True,
            "layout_path": str(path),
            "uuid": item_id,
            "operation": operation,
            "backup_path": str(backup) if backup else None,
            "drc_checked": False,
            "clearance_checked": False,
            "routing_complete": False,
            "zone_fill_needs_refresh": True,
        }


@tool(
    "Add one straight copper segment on an exact existing net and "
    "canonical copper layer. "
    "Coordinates/width in mm; must fit outline bounds. Saves a backup atomically. "
    "Manual primitive only: run layout_run_drc afterwards; "
    "no autorouting or clearance guarantee.",
    label="Added copper segment",
)
async def layout_add_track_segment(
    args: AddSegmentArgs, scope: Scope
) -> dict[str, Any]:
    return await finish_board_edit(
        asyncio.to_thread(_edit_copper, args, scope, "segment")
    )


@tool(
    "Add one through via from F.Cu to B.Cu on an exact existing net, in mm. "
    "Drill must be smaller than diameter; must fit outline bounds. Saves a backup. "
    "Run layout_run_drc afterwards; no autorouting or clearance guarantee.",
    label="Added through via",
)
async def layout_add_via(args: AddViaArgs, scope: Scope) -> dict[str, Any]:
    return await finish_board_edit(asyncio.to_thread(_edit_copper, args, scope, "via"))


@tool(
    "Delete one existing unlocked segment, arc or via using the exact UUID from "
    "layout_get_routes. Footprints, pads, zones and grouped items are refused. "
    "Saves a backup; run layout_run_drc afterwards.",
    label="Removed copper item",
)
async def layout_delete_copper(args: DeleteCopperArgs, scope: Scope) -> dict[str, Any]:
    return await finish_board_edit(
        asyncio.to_thread(_edit_copper, args, scope, "delete")
    )


def _kicad_cli() -> str:
    executable = shutil.which("kicad-cli")
    if executable:
        return executable
    mac_path = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    if mac_path.is_file():
        return str(mac_path)
    raise RuntimeError(
        "KiCad CLI is required for local DRC; install KiCad or add kicad-cli to PATH"
    )


def _run_drc(args: LayoutArgs, scope: Scope) -> dict[str, Any]:
    path = _layout_path(args, scope)
    executable = _kicad_cli()
    output_dir = scope.resolve(".local-agent/drc")
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / f"{path.stem}.{time.time_ns()}.json"
    result = subprocess.run(
        [
            executable,
            "pcb",
            "drc",
            "--format",
            "json",
            "--severity-all",
            "--refill-zones",
            "--output",
            str(report),
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0 or not report.exists():
        raise RuntimeError(
            f"KiCad DRC failed ({result.returncode}): {result.stderr[-1500:]}"
        )
    data = json.loads(report.read_text())
    groups = {
        key: data.get(key, [])
        for key in ("violations", "unconnected_items", "schematic_parity")
    }
    findings = [
        {"category": key, **item} for key, items in groups.items() for item in items
    ]
    return {
        "success": True,
        "layout_path": str(path),
        "report_path": str(report),
        "clean": len(findings) == 0,
        "finding_count": len(findings),
        "violation_count": len(groups["violations"]),
        "unconnected_count": len(groups["unconnected_items"]),
        "findings": findings[:100],
        "findings_truncated": len(findings) > 100,
        "zones_refilled_for_check": True,
        "board_saved": False,
    }


@tool(
    "Run local KiCad PCB DRC and return violations/unconnected counts "
    "and a saved report.",
    label="Checked PCB DRC",
)
async def layout_run_drc(args: LayoutArgs, scope: Scope) -> dict[str, Any]:
    return await asyncio.to_thread(_run_drc, args, scope)

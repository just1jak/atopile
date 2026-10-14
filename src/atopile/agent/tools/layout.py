"""Local PCB inspection, placement, and KiCad DRC tools."""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from threading import RLock
from typing import Any, TypedDict

import sexpdata

from atopile.agent.scope import Scope
from atopile.agent.tools.registry import tool
from atopile.config import ProjectConfig
from faebryk.libs.kicad.fileformats import Property, kicad

_placement_lock = RLock()


class LayoutArgs(TypedDict, total=False):
    path: str
    target: str
    max_components: int
    max_nets: int
    net: str
    max_pads: int


class PositionOptions(LayoutArgs, total=False):
    rotation_deg: float
    layer: str


class PositionArgs(PositionOptions):
    address: str


class SetPositionArgs(PositionArgs):
    x_mm: float
    y_mm: float


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
    with _placement_lock:
        original = path.read_bytes()
        if _raw_locked_footprints(original.decode("utf-8")):
            raise ValueError(
                "Board contains locked KiCad footprints. Edit this board in KiCad; "
                "the bundled parser does not preserve native footprint locks."
            )
        pcb_file = kicad.loads(kicad.pcb.PcbFile, original.decode("utf-8"))
        footprint = _find_component(pcb_file.kicad_pcb, args["address"])
        before = _component(footprint)
        if before["locked"] or any(
            t.text == "FBRK:notouch" for t in footprint.fp_texts
        ):
            raise ValueError("Component is locked or marked FBRK:notouch")
        x, y = float(args["x_mm"]), float(args["y_mm"])
        rotation = float(args.get("rotation_deg", before["rotation_deg"]))
        if not all(math.isfinite(value) for value in (x, y, rotation)):
            raise ValueError("Placement coordinates and rotation must be finite")
        layer = args.get("layer", footprint.layer)
        if layer not in {"F.Cu", "B.Cu"}:
            raise ValueError("Footprint layer must be F.Cu or B.Cu")
        PCB_Transformer.move_fp(
            footprint, kicad.pcb.Xyr(x=x, y=y, r=rotation % 360), layer
        )
        updated = kicad.dumps(pcb_file)
        if path.read_bytes() != original:
            raise RuntimeError("PCB changed in the editor; inspect again before moving")
        # A second *.kicad_pcb in this directory makes target discovery
        # ambiguous. Keep a byte-for-byte backup with a non-layout suffix.
        backup = path.with_name(f"{path.name}.local-agent-{time.time_ns()}.bak")
        backup.write_bytes(original)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".local-layout-",
            delete=False,
        ) as temp:
            temp.write(updated)
            temporary = Path(temp.name)
        try:
            os.chmod(temporary, path.stat().st_mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "updated": True,
            "layout_path": str(path),
            "backup_path": str(backup),
            "before": before,
            "after": _component(footprint),
            "routing_recomputed": False,
            "drc_checked": False,
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
    worker = asyncio.create_task(asyncio.to_thread(_set_position, args, scope))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        # Threaded edits cannot be cancelled. Do not acknowledge Stop while an
        # atomic board edit can still commit, even if Stop is requested again.
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not worker.cancelled():
            worker.exception()  # Consume failures; cancellation remains the outcome.
        raise


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
    }


@tool(
    "Run local KiCad PCB DRC and return violations/unconnected counts "
    "and a saved report.",
    label="Checked PCB DRC",
)
async def layout_run_drc(args: LayoutArgs, scope: Scope) -> dict[str, Any]:
    return await asyncio.to_thread(_run_drc, args, scope)

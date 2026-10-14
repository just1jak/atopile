"""Exercise PCB tools against real parsed KiCad fixtures and mocked DRC."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from atopile.agent.scope import Scope, ScopeError
from atopile.agent.tools import create_registry, layout
from faebryk.libs.kicad.fileformats import kicad

FIXTURE = Path("examples/esp32_minimal/layouts/esp32_minimal/esp32_minimal.kicad_pcb")


@pytest.fixture
def board_scope(tmp_path):
    destination = tmp_path / "board.kicad_pcb"
    shutil.copyfile(FIXTURE, destination)
    return destination, Scope(allowed_roots=[tmp_path])


def test_summary_and_netlist_report_real_pad_assignments(board_scope):
    path, scope = board_scope
    summary = asyncio.run(layout.layout_get_summary({"path": str(path)}, scope))
    netlist = asyncio.run(layout.layout_get_netlist({"path": str(path)}, scope))
    assert summary["component_count"] >= 10
    assert summary["net_count"] > 0
    assert netlist["connectivity_kind"] == "logical_pad_net_assignments"
    assert netlist["net_count"] == summary["net_count"]
    first = netlist["nets"][0]
    assert first["pad_count"] > 0
    assert first["pads"][0]["reference"]
    filtered = asyncio.run(
        layout.layout_get_netlist({"path": str(path), "net": first["name"]}, scope)
    )
    assert filtered["net_count"] == 1
    assert filtered["nets"][0] == first


def test_move_saves_backup_and_preserves_nets_other_components_and_routes(board_scope):
    path, scope = board_scope
    original = path.read_bytes()
    pcb_before = layout._load(path).kicad_pcb
    nets_before = layout._netlist(pcb_before)
    components_before = [layout._component(fp) for fp in pcb_before.footprints]
    chosen = components_before[0]
    result = asyncio.run(
        layout.layout_set_component_position(
            {
                "path": str(path),
                "address": chosen["reference"],
                "x_mm": chosen["x_mm"] + 5,
                "y_mm": chosen["y_mm"] - 3,
                "rotation_deg": 90,
            },
            scope,
        )
    )
    assert Path(result["backup_path"]).read_bytes() == original
    assert result["after"]["x_mm"] == pytest.approx(chosen["x_mm"] + 5)
    assert result["after"]["y_mm"] == pytest.approx(chosen["y_mm"] - 3)
    assert result["after"]["rotation_deg"] == 90
    assert result["routing_recomputed"] is False
    assert result["drc_checked"] is False
    pcb_after = layout._load(path).kicad_pcb
    assert layout._netlist(pcb_after) == nets_before
    assert [layout._component(fp) for fp in pcb_after.footprints][
        1:
    ] == components_before[1:]

    def tracks(pcb):
        return [
            (s.start.x, s.start.y, s.end.x, s.end.y, s.width, s.layer, s.net)
            for s in pcb.segments
        ]

    assert tracks(pcb_after) == tracks(pcb_before)


def test_get_placement_reloads_external_changes(board_scope):
    path, scope = board_scope
    pcb_file = layout._load(path)
    component = layout._component(pcb_file.kicad_pcb.footprints[0])
    args = {
        "path": str(path),
        "address": component["address"] or component["reference"],
    }
    assert (
        asyncio.run(layout.layout_get_component_position(args, scope))["component"][
            "x_mm"
        ]
        == component["x_mm"]
    )
    pcb_file.kicad_pcb.footprints[0].at.x += 7
    kicad.dumps(pcb_file, path)
    assert (
        asyncio.run(layout.layout_get_component_position(args, scope))["component"][
            "x_mm"
        ]
        == component["x_mm"] + 7
    )


def test_scope_rejects_outside_board_and_symlink(board_scope, tmp_path):
    path, scope = board_scope
    outside = tmp_path.parent / "outside-board.kicad_pcb"
    with pytest.raises(ScopeError):
        asyncio.run(layout.layout_get_summary({"path": str(outside)}, scope))
    link = path.parent / "outside-link.kicad_pcb"
    link.symlink_to(outside)
    with pytest.raises(ScopeError):
        asyncio.run(layout.layout_get_summary({"path": str(link)}, scope))


def test_nonfinite_move_rejected_before_mutation(board_scope):
    path, scope = board_scope
    original = path.read_bytes()
    reference = layout._component(layout._load(path).kicad_pcb.footprints[0])[
        "reference"
    ]
    with pytest.raises(ValueError, match="finite"):
        asyncio.run(
            layout.layout_set_component_position(
                {
                    "path": str(path),
                    "address": reference,
                    "x_mm": float("nan"),
                    "y_mm": 1.0,
                },
                scope,
            )
        )
    assert path.read_bytes() == original
    assert not list(path.parent.glob("*.bak.kicad_pcb"))


def test_locked_move_rejected(board_scope):
    path, scope = board_scope
    chosen = layout._load(path).kicad_pcb.footprints[0]
    text = path.read_text()
    # Native footprint locks are not represented in the bundled parser model.
    start = text.index('(footprint "')
    header_end = text.index("\n", start)
    text = text[:header_end] + "\n\t\t(locked yes)" + text[header_end:]
    path.write_text(text)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="locked"):
        asyncio.run(
            layout.layout_set_component_position(
                {
                    "path": str(path),
                    "address": layout._component(chosen)["reference"],
                    "x_mm": 1.0,
                    "y_mm": 2.0,
                },
                scope,
            )
        )
    assert path.read_bytes() == original


def test_drc_reports_violations_and_unconnected_items(board_scope, monkeypatch):
    path, scope = board_scope
    monkeypatch.setattr(layout, "_kicad_cli", lambda: "/test/kicad-cli")

    def fake_drc(command, **kwargs):
        assert command[:3] == ["/test/kicad-cli", "pcb", "drc"]
        report = Path(command[command.index("--output") + 1])
        report.write_text(
            json.dumps(
                {
                    "violations": [{"severity": "error", "type": "clearance"}],
                    "unconnected_items": [
                        {"severity": "error", "type": "unconnected_items"}
                    ],
                }
            )
        )
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(layout.subprocess, "run", fake_drc)
    report = asyncio.run(layout.layout_run_drc({"path": str(path)}, scope))
    assert report["clean"] is False
    assert report["violation_count"] == 1
    assert report["unconnected_count"] == 1
    assert report["finding_count"] == 2
    assert Path(report["report_path"]).is_relative_to(scope.project_root)


def test_drc_missing_command_does_not_claim_success(board_scope, monkeypatch):
    path, scope = board_scope
    monkeypatch.setattr(layout.shutil, "which", lambda *args: None)
    monkeypatch.setattr(layout.Path, "is_file", lambda self: self == path)
    with pytest.raises(RuntimeError, match="KiCad CLI"):
        asyncio.run(layout.layout_run_drc({"path": str(path)}, scope))


def test_layout_tools_registered_with_required_placement_arguments():
    definitions = {item["name"]: item for item in create_registry().definitions()}
    assert set(definitions) >= {
        "layout_get_summary",
        "layout_get_netlist",
        "layout_get_component_position",
        "layout_set_component_position",
        "layout_run_drc",
    }
    schema = definitions["layout_set_component_position"]["parameters"]
    assert set(schema["required"]) == {"address", "x_mm", "y_mm"}
    assert schema["properties"]["x_mm"]["type"] == "number"

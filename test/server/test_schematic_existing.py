"""Explicit native schematic selection, hierarchy confinement and preservation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import sexpdata

from atopile.server.domains import schematic_export as exporter


@pytest.fixture
def native_project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "ato.yaml").write_text(
        "requires-atopile: ^0.15.9\npaths:\n  src: ./\n"
        "builds:\n  v240:\n    entry: main.ato:Scanner\n"
    )
    directory = root / "schematic"
    directory.mkdir()
    (directory / "main.kicad_sch").write_text(
        '(kicad_sch (sheet (property "Sheetfile" "child.kicad_sch")))'
    )
    (directory / "child.kicad_sch").write_text("(kicad_sch)")
    (root / ".atopile-local.json").write_text(
        json.dumps({"schematics": {"v240": "schematic/main.kicad_sch"}})
    )
    return root


@pytest.fixture
def native_result(monkeypatch):
    native = sexpdata.loads(
        "(export (components (comp (ref R1)) (comp (ref J1))) "
        "(nets (net (name power) (node (ref R1) (pin 1)) "
        "(node (ref J1) (pin 1))) "
        '(net (name "unconnected-(J1-Pad2)") (node (ref J1) (pin 2)))))'
    )
    monkeypatch.setattr(exporter, "_native_netlist", lambda _: native)

    def no_projection(*_args):
        pytest.fail("An existing native schematic must not require the PCB projection")

    monkeypatch.setattr(exporter, "get_schematic_data", no_projection)
    return native


def _snapshot(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_existing_native_uses_target_mapping_without_pcb_or_project_writes(
    native_project, native_result
):
    before = _snapshot(native_project)
    result = exporter.export_schematic(native_project, "v240")
    assert result["path"] == str(native_project / "schematic/main.kicad_sch")
    assert result["relativePath"] == "schematic/main.kicad_sch"
    assert result["reused"] is True
    assert result["componentCount"] == 2
    assert result["netCount"] == 1
    assert any("not compared" in warning for warning in result["warnings"])
    assert _snapshot(native_project) == before
    assert not (native_project / "build").exists()


def test_revision_tracks_child_content_and_allows_repeated_sheet_instances(
    native_project, native_result
):
    main = native_project / "schematic/main.kicad_sch"
    main.write_text(
        '(kicad_sch (sheet (property "Sheetfile" "child.kicad_sch")) '
        '(sheet (property "Sheetfile" "child.kicad_sch")))'
    )
    first = exporter.export_schematic(native_project, "v240")
    assert (
        exporter.export_schematic(native_project, "v240")["revision"]
        == first["revision"]
    )
    (main.parent / "child.kicad_sch").write_text('(kicad_sch (generator "edited"))')
    assert (
        exporter.export_schematic(native_project, "v240")["revision"]
        != first["revision"]
    )


@pytest.mark.parametrize(
    "mapping",
    [
        "/tmp/outside.kicad_sch",
        "../outside.kicad_sch",
        "${KIPRJMOD}/a.kicad_sch",
        "file:///a.kicad_sch",
        "a\\b.kicad_sch",
        None,
    ],
)
def test_invalid_mapping_fails_before_native_or_projection(
    native_project, native_result, monkeypatch, mapping
):
    (native_project / ".atopile-local.json").write_text(
        json.dumps({"schematics": {"v240": mapping}})
    )
    monkeypatch.setattr(
        exporter, "_native_netlist", lambda _: pytest.fail("Must reject before KiCad")
    )
    with pytest.raises(ValueError):
        exporter.export_schematic(native_project, "v240")


@pytest.mark.parametrize("contents", ["{", "[]", '{"schematics": []}'])
def test_malformed_project_mapping_fails_closed(
    native_project, native_result, contents
):
    (native_project / ".atopile-local.json").write_text(contents)
    with pytest.raises(ValueError, match=".atopile-local.json"):
        exporter.export_schematic(native_project, "v240")


@pytest.mark.parametrize("escape", ["../../outside.kicad_sch", "linked.kicad_sch"])
def test_child_sheet_escape_including_symlink_is_rejected(
    native_project, native_result, monkeypatch, escape
):
    outside = native_project.parent / "outside.kicad_sch"
    outside.write_text("(kicad_sch)")
    directory = native_project / "schematic"
    (directory / "linked.kicad_sch").symlink_to(outside)
    (directory / "main.kicad_sch").write_text(
        '(kicad_sch (sheet (property "Sheetfile" ' + json.dumps(escape) + ")))"
    )
    monkeypatch.setattr(
        exporter, "_native_netlist", lambda _: pytest.fail("Must reject before KiCad")
    )
    with pytest.raises(ValueError, match="escapes"):
        exporter.export_schematic(native_project, "v240")
    assert outside.read_text() == "(kicad_sch)"


def test_config_symlink_cannot_read_outside_project(native_project, native_result):
    config = native_project / ".atopile-local.json"
    outside = native_project.parent / "outside.json"
    outside.write_bytes(config.read_bytes())
    config.unlink()
    config.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        exporter.export_schematic(native_project, "v240")


def test_cycle_missing_child_and_sheet_limits_fail_before_native(
    native_project, native_result, monkeypatch
):
    child = native_project / "schematic/child.kicad_sch"
    child.write_text('(kicad_sch (sheet (property "Sheetfile" "main.kicad_sch")))')
    with pytest.raises(ValueError, match="cycle"):
        exporter.export_schematic(native_project, "v240")
    child.unlink()
    with pytest.raises(ValueError, match="regular project files"):
        exporter.export_schematic(native_project, "v240")
    child.write_text("(kicad_sch)")
    monkeypatch.setattr(exporter, "MAX_HIERARCHY_FILES", 1)
    with pytest.raises(ValueError, match="sheet limit"):
        exporter.export_schematic(native_project, "v240")
    monkeypatch.setattr(exporter, "MAX_HIERARCHY_FILES", 512)
    monkeypatch.setattr(exporter, "MAX_SCHEMATIC_BYTES", 8)
    with pytest.raises(ValueError, match="size limit"):
        exporter.export_schematic(native_project, "v240")


def test_force_new_bypasses_mapping_and_missing_target_mapping_keeps_generator(
    native_project, monkeypatch
):
    def generation(*_args):
        raise RuntimeError("Original generator called")

    monkeypatch.setattr(exporter, "get_schematic_data", generation)
    (native_project / ".atopile-local.json").write_text("malformed")
    with pytest.raises(RuntimeError, match="Original generator called"):
        exporter.export_schematic(native_project, "v240", force_new=True)
    (native_project / ".atopile-local.json").write_text('{"schematics": {}}')
    with pytest.raises(RuntimeError, match="Original generator called"):
        exporter.export_schematic(native_project, "v240")


def test_native_existing_output_is_temporary_and_timeout_does_not_change_project(
    native_project, monkeypatch
):
    before = _snapshot(native_project)
    monkeypatch.setattr(exporter, "_find_cli", lambda: "/native/kicad-cli")

    def timeout(command, **kwargs):
        destination = Path(command[command.index("--output") + 1])
        assert not destination.is_relative_to(native_project)
        assert kwargs["timeout"] <= 60
        assert "PYTHONPATH" not in kwargs["env"]
        assert "OPENAI_API_KEY" not in kwargs["env"]
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(exporter.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        exporter.export_schematic(native_project, "v240")
    assert _snapshot(native_project) == before

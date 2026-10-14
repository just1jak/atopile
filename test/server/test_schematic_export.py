"""Native KiCad connectivity proof and preservation/confinement regressions."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import sexpdata

from atopile.server.domains import schematic_export as exporter
from atopile.server.domains.schematic import get_schematic_data
from atopile.server.domains.schematic_symbols import _children, _field
from faebryk.libs.kicad.fileformats import kicad

EXPECTED_NETS = {
    "2": {("D1", "2"), ("R1", "2")},
    "hv": {("J1", "1"), ("R1", "1")},
    "lv": {("D1", "1"), ("J1", "2")},
}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "circuit"
    shutil.copytree(
        "examples/offline-indicator",
        root,
        ignore=shutil.ignore_patterns("schematic", "*.kicad_prl", "__pycache__"),
    )
    return root


@pytest.fixture
def native_cli():
    try:
        return exporter._find_cli()
    except RuntimeError:
        pytest.skip("Native KiCad CLI is not installed")


def _directory(root):
    return root / "build/builds/default/schematic"


def _skip_native(monkeypatch):
    # File lifecycle tests do not repeat native CLI work. The tests below prove
    # actual parsing/connectivity with the installed KiCad executable separately.
    monkeypatch.setattr(exporter, "verify_native_connectivity", lambda *_: {})


def _capture_native(monkeypatch):
    results = []
    original = exporter.verify_native_connectivity

    def verify(*args):
        result = original(*args)
        results.append(result)
        return result

    monkeypatch.setattr(exporter, "verify_native_connectivity", verify)
    return results


def test_native_kicad_proves_exact_demo_nets_and_export_does_not_touch_pcb(
    project, native_cli, monkeypatch
):
    pcb_path = project / "layouts/default/default.kicad_pcb"
    pcb = kicad.loads(kicad.pcb.PcbFile, pcb_path.read_text())
    pcb.kicad_pcb.footprints[0].at.x = 76.2  # Preserve a real user's placement.
    kicad.dumps(pcb, pcb_path)
    before, modified_at = pcb_path.read_bytes(), pcb_path.stat().st_mtime_ns
    actual = _capture_native(monkeypatch)
    result = exporter.export_schematic(project)
    assert actual == [EXPECTED_NETS]
    assert result["componentCount"] == result["netCount"] == 3
    assert not result["reused"]
    assert result["layoutPath"] == str(pcb_path)
    assert pcb_path.read_bytes() == before
    assert pcb_path.stat().st_mtime_ns == modified_at
    path = Path(result["path"])
    assert path.is_relative_to(project / "build")
    document = sexpdata.loads(path.read_text())
    assert len(_children(_field(document, "lib_symbols"), "symbol")) == 3
    assert len(_children(document, "symbol")) == 3
    assert len(_children(document, "global_label")) == 6
    assert all(
        abs(float(value) / 1.27 - round(float(value) / 1.27)) < 1e-6
        for instance in _children(document, "symbol")
        for value in _field(instance, "at")[1:3]
    )
    for instance in _children(document, "symbol"):
        properties = {str(p[1]): str(p[2]) for p in _children(instance, "property")}
        assert properties["Footprint"]
        assert properties["AtopilePCBFootprintUUID"]
        assert properties["AtopileAddress"]
        assert properties["AtopileSource"].startswith("main.ato:")
        assert properties["AtopilePCB"] == "layouts/default/default.kicad_pcb"
    assert any("does not change PCB links" in warning for warning in result["warnings"])


def test_native_kicad_keeps_unassigned_pcb_pad_unconnected(
    project, native_cli, monkeypatch
):
    pcb_path = project / "layouts/default/default.kicad_pcb"
    pcb = kicad.loads(kicad.pcb.PcbFile, pcb_path.read_text())
    led = next(
        fp
        for fp in pcb.kicad_pcb.footprints
        if any(p.name == "Reference" and p.value == "D1" for p in fp.propertys)
    )
    next(pad for pad in led.pads if pad.name == "1").net = None
    kicad.dumps(pcb, pcb_path)
    actual = _capture_native(monkeypatch)
    result = exporter.export_schematic(project)
    assert actual[0]["lv"] == {("J1", "2")}
    assert ("D1", "1") not in set().union(*actual[0].values())
    document = sexpdata.loads(Path(result["path"]).read_text())
    assert len(_children(document, "no_connect")) == 1


def test_native_kicad_embeds_resolved_inherited_symbol(
    project, native_cli, monkeypatch
):
    path = project / "parts/Local_LED5mm/LED5mm.kicad_sym"
    document = sexpdata.loads(path.read_text())
    base = _children(document, "symbol")[0]
    base[1] = "BaseLED"
    for unit in _children(base, "symbol"):
        unit[1] = str(unit[1]).replace("LED5mm_", "BaseLED_")
    document.append(
        [
            sexpdata.Symbol("symbol"),
            "LED5mm",
            [sexpdata.Symbol("extends"), "BaseLED"],
            [sexpdata.Symbol("property"), "Value", "Inherited LED"],
        ]
    )
    path.write_text(sexpdata.dumps(document))
    actual = _capture_native(monkeypatch)
    result = exporter.export_schematic(project)
    assert actual == [EXPECTED_NETS]
    exported = sexpdata.loads(Path(result["path"]).read_text())
    for symbol in _children(_field(exported, "lib_symbols"), "symbol"):
        assert not _children(symbol, "extends")
    assert "Inherited LED" in Path(result["path"]).read_text()


def test_native_comparison_rejects_a_changed_label(project, native_cli):
    result = exporter.export_schematic(project)
    path = Path(result["path"])
    document = sexpdata.loads(path.read_text())
    _children(document, "global_label")[0][1] = "fabricated"
    path.write_text(sexpdata.dumps(document))
    with pytest.raises(RuntimeError, match="differs from the PCB"):
        exporter.verify_native_connectivity(path, get_schematic_data(project))


def test_reopen_preserves_native_user_edits_and_force_new_preserves_old_export(
    project, monkeypatch
):
    _skip_native(monkeypatch)
    first = exporter.export_schematic(project)
    path = Path(first["path"])
    edited = path.read_text().replace(
        "editable one-way snapshot", "Edited by the user in KiCad"
    )
    path.write_text(edited)
    reused = exporter.export_schematic(project)
    assert reused["path"] == first["path"]
    assert reused["reused"] is True
    assert path.read_text() == edited
    second = exporter.export_schematic(project, force_new=True)
    assert not second["reused"] and second["path"] != first["path"]
    assert path.read_text() == edited
    assert "Edited by the user in KiCad" not in Path(second["path"]).read_text()
    assert exporter.export_schematic(project)["path"] == second["path"]


def test_deleted_snapshot_regenerates_and_failed_new_export_preserves_manifest(
    project, monkeypatch
):
    _skip_native(monkeypatch)
    first = exporter.export_schematic(project)
    Path(first["path"]).unlink()
    regenerated = exporter.export_schematic(project)
    assert regenerated["path"] != first["path"] and not regenerated["reused"]
    manifest = _directory(project) / "latest.json"
    before = manifest.read_bytes()
    previous_file = Path(regenerated["path"]).read_bytes()

    def fail(*_args):
        raise RuntimeError("Native verification failed")

    monkeypatch.setattr(exporter, "verify_native_connectivity", fail)
    with pytest.raises(RuntimeError, match="verification failed"):
        exporter.export_schematic(project, force_new=True)
    assert manifest.read_bytes() == before
    assert Path(regenerated["path"]).read_bytes() == previous_file
    assert len(list(_directory(project).glob("*.kicad_sch"))) == 1


@pytest.mark.parametrize(
    "malformed",
    [
        "{",
        "[]",
        '{"version":true}',
        '{"version":1,"revision":"bad","filename":"x.kicad_sch"}',
    ],
)
def test_invalid_manifest_stops_without_overwriting_existing_export(
    project, monkeypatch, malformed
):
    _skip_native(monkeypatch)
    result = exporter.export_schematic(project)
    previous = Path(result["path"]).read_bytes()
    manifest = _directory(project) / "latest.json"
    manifest.write_text(malformed)
    with pytest.raises(ValueError, match="manifest"):
        exporter.export_schematic(project, force_new=True)
    assert manifest.read_text() == malformed
    assert Path(result["path"]).read_bytes() == previous


@pytest.mark.parametrize(
    "escape", ["../outside.kicad_sch", "/tmp/outside.kicad_sch", "linked.kicad_sch"]
)
def test_manifest_cannot_select_a_file_outside_generated_directory(
    project, tmp_path, monkeypatch, escape
):
    _skip_native(monkeypatch)
    result = exporter.export_schematic(project)
    victim = tmp_path / "outside.kicad_sch"
    victim.write_text("untouched user schematic")
    if escape == "linked.kicad_sch":
        (_directory(project) / escape).symlink_to(victim)
    manifest = _directory(project) / "latest.json"
    manifest.write_text(
        json.dumps({"version": 1, "revision": result["revision"], "filename": escape})
    )
    with pytest.raises(ValueError, match="manifest"):
        exporter.export_schematic(project)
    assert victim.read_text() == "untouched user schematic"


def test_missing_and_multiunit_symbols_stop_before_writing_a_native_snapshot(
    project, monkeypatch
):
    _skip_native(monkeypatch)
    path = project / "parts/Local_LED5mm/LED5mm.kicad_sym"
    original = path.read_text()
    document = sexpdata.loads(original)
    _children(document, "symbol")[0].append(
        [
            sexpdata.Symbol("symbol"),
            "LED5mm_2_1",
            [
                sexpdata.Symbol("circle"),
                [sexpdata.Symbol("center"), 0, 0],
                [sexpdata.Symbol("radius"), 1],
            ],
        ]
    )
    path.write_text(sexpdata.dumps(document))
    with pytest.raises(ValueError, match="multi-unit"):
        exporter.export_schematic(project)
    assert not list(_directory(project).glob("*.kicad_sch"))
    path.unlink()
    with pytest.raises(ValueError, match="real local KiCad symbol"):
        exporter.export_schematic(project)
    assert not list(_directory(project).glob("*.kicad_sch"))


def test_native_timeout_is_bounded_and_does_not_publish_a_manifest(
    project, monkeypatch
):
    monkeypatch.setattr(exporter, "_find_cli", lambda: "/native/kicad-cli")

    def timeout(command, **kwargs):
        assert kwargs["timeout"] <= 60
        assert "PYTHONPATH" not in kwargs["env"]
        assert "PYTHONHOME" not in kwargs["env"]
        assert "OPENAI_API_KEY" not in kwargs["env"]
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setenv("PYTHONHOME", "/wrong/python")
    monkeypatch.setenv("PYTHONPATH", "/wrong/source")
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-never-forward")
    monkeypatch.setattr(exporter.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        exporter.export_schematic(project)
    assert not (_directory(project) / "latest.json").exists()
    assert not list(_directory(project).glob("*.kicad_sch"))

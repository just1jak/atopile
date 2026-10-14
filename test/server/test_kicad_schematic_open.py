"""Native schematic launch must use literal arguments and leave CAD files intact."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from atopile.server.domains import kicad


def schematic(tmp_path):
    path = tmp_path / "A board; $(literal).kicad_sch"
    path.write_text('(kicad_sch (version 20250114) (generator "atopile_local"))')
    return path


def test_macos_prefers_installed_eeschema_bundle(tmp_path, monkeypatch):
    base = tmp_path / "KiCad"
    app = base / "KiCad.app/Contents/Applications/eeschema.app"
    binary = app / "Contents/MacOS/eeschema"
    binary.parent.mkdir(parents=True)
    binary.write_text("test fixture")
    monkeypatch.setattr(kicad.sys, "platform", "darwin")
    monkeypatch.setattr(kicad, "_MACOS_KICAD_ROOTS", (base,))
    monkeypatch.setattr(
        kicad.shutil,
        "which",
        lambda name: pytest.fail("App bundle should be preferred"),
    )
    assert kicad._find_schematic_editor() == (app, True)


def test_mac_open_uses_literal_path_and_reports_existing_matching_files(
    tmp_path, monkeypatch
):
    path = schematic(tmp_path)
    pcb = path.with_suffix(".kicad_pcb")
    pcb.write_bytes(b"preserve this PCB")
    project = path.with_suffix(".kicad_pro")
    project.write_text("{}")
    before = {p: p.read_bytes() for p in (path, pcb, project)}
    app = Path("/Applications/KiCad/eeschema.app")
    monkeypatch.setattr(kicad, "_find_schematic_editor", lambda: (app, True))
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(kicad.subprocess, "run", run)
    result = kicad.launch_schematic(path)
    assert calls[0][0] == ["/usr/bin/open", "-a", str(app), str(path)]
    assert not calls[0][1].get("shell")
    assert result == {
        "status": "launched",
        "schematicPath": str(path),
        "pcbPath": str(pcb),
        "projectPath": str(project),
        "pcbAssociation": "matching_basename",
    }
    assert {p: p.read_bytes() for p in before} == before


def test_missing_schematic_or_wrong_format_does_not_spawn(tmp_path, monkeypatch):
    monkeypatch.setattr(
        kicad, "_find_schematic_editor", lambda: pytest.fail("Must validate first")
    )
    with pytest.raises(ValueError, match=".kicad_sch"):
        kicad.launch_schematic(tmp_path / "board.kicad_pcb")
    with pytest.raises(FileNotFoundError, match="does not exist"):
        kicad.launch_schematic(tmp_path / "missing.kicad_sch")


def test_missing_desktop_app_reports_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setattr(kicad.sys, "platform", "darwin")
    monkeypatch.setattr(kicad, "_MACOS_KICAD_ROOTS", (tmp_path / "not-installed",))
    monkeypatch.setattr(kicad.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError, match="Install the KiCad desktop app"):
        kicad.launch_schematic(schematic(tmp_path))


def test_cli_launch_is_detached_and_has_no_invented_pcb_association(
    tmp_path, monkeypatch
):
    path = schematic(tmp_path)
    monkeypatch.setattr(
        kicad, "_find_schematic_editor", lambda: (Path("/usr/bin/eeschema"), False)
    )
    monkeypatch.setattr(kicad.time, "sleep", lambda seconds: None)
    calls = []

    def popen(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(kicad.subprocess, "Popen", popen)
    result = kicad.launch_schematic(path)
    assert calls[0][0] == ["/usr/bin/eeschema", str(path)]
    assert calls[0][1]["start_new_session"] is True
    assert not calls[0][1].get("shell")
    assert result["pcbPath"] is None and result["projectPath"] is None
    assert result["pcbAssociation"] == "unavailable"


def test_immediate_editor_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(
        kicad, "_find_schematic_editor", lambda: (Path("/usr/bin/eeschema"), False)
    )
    monkeypatch.setattr(kicad.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        kicad.subprocess,
        "Popen",
        lambda *args, **kwargs: SimpleNamespace(poll=lambda: 3),
    )
    with pytest.raises(RuntimeError, match="code 3"):
        kicad.launch_schematic(schematic(tmp_path))


def test_launchservices_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(
        kicad, "_find_schematic_editor", lambda: (Path("/Apps/eeschema.app"), True)
    )
    monkeypatch.setattr(
        kicad.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1)
    )
    with pytest.raises(RuntimeError, match="could not open"):
        kicad.launch_schematic(schematic(tmp_path))


def test_kicad_environment_does_not_inherit_fork_python(tmp_path, monkeypatch):
    venv = str(tmp_path / "venv")
    monkeypatch.setenv("VIRTUAL_ENV", venv)
    monkeypatch.setenv("PYTHONPATH", "/fork/source")
    monkeypatch.setenv("PYTHONHOME", "/fork/python")
    monkeypatch.setenv("PATH", f"{venv}/bin:/usr/bin")
    env = kicad._clean_env_for_kicad()
    assert not {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"}.intersection(env)
    assert env["PATH"] == "/usr/bin"
    assert kicad.os.environ["PYTHONPATH"] == "/fork/source"


def test_async_service_reuses_validated_launch_helper(tmp_path, monkeypatch):
    path = schematic(tmp_path)
    calls = []

    def launch(candidate):
        calls.append(candidate)
        return {"status": "launched"}

    monkeypatch.setattr(kicad, "launch_schematic", launch)
    assert asyncio.run(kicad.KicadService().open_schematic(path)) == {
        "status": "launched"
    }
    assert calls == [path]

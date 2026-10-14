"""The real child interpreter must not fall back to the wheel or project code."""

import json
import subprocess
from pathlib import Path

from atopile.model.module_introspection import _introspection_child_settings


def test_child_imports_fork_and_state_from_a_hostile_project(tmp_path, monkeypatch):
    project = tmp_path / "user-project"
    project.mkdir()
    (project / "src").mkdir()
    for directory in (project, project / "src"):
        for name in ("atopile.py", "hypothesis.py", "sitecustomize.py"):
            (directory / name).write_text(
                "raise RuntimeError('project shadow executed')"
            )
    monkeypatch.setenv("PYTHONPATH", "src")
    monkeypatch.setenv("ATOPILE_LOCAL_DATA_DIR", str(tmp_path / "fork-state"))
    executable, env = _introspection_child_settings()
    result = subprocess.run(
        [
            executable,
            "-P",
            "-c",
            """
import importlib.util, json, os, sys
import atopile
import atopile.model.sqlite as sqlite
from faebryk.libs.paths import get_log_dir
spec = importlib.util.find_spec('hypothesis')
print(json.dumps({'atopile': atopile.__file__, 'sqlite': sqlite.__file__,
                  'state': str(get_log_dir()), 'safe_path': sys.flags.safe_path,
                  'hypothesis': spec.origin if spec else None}))
""",
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    data = json.loads(result.stdout)
    source = Path(__file__).resolve().parents[2] / "src"
    assert Path(data["atopile"]).is_relative_to(source)
    assert Path(data["sqlite"]) == source / "atopile/model/sqlite.py"
    assert data["state"] == str(tmp_path / "fork-state/logs")
    assert data["safe_path"] is True
    assert not data["hypothesis"] or not Path(data["hypothesis"]).is_relative_to(
        project
    )
    assert env["PYTHONPATH"] == str(source)

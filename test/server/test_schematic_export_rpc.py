"""Native schematic generation and launching use the selected workspace scope."""

import asyncio
from types import SimpleNamespace

import pytest

from atopile.server.domains import schematic_export
from atopile.server.ui.websocket import CoreSocket


@pytest.fixture
def rpc(tmp_path, monkeypatch):
    root = str(tmp_path / "project")
    saved = {
        "path": root + "/build/schematic/circuit.kicad_sch",
        "relativePath": "build/schematic/circuit.kicad_sch",
        "projectRoot": root,
        "target": "default",
        "revision": "abc",
        "layoutPath": root + "/layouts/default/default.kicad_pcb",
        "componentCount": 3,
        "netCount": 3,
        "warnings": [],
        "reused": False,
    }
    exports, launches, responses = [], [], []

    def export(project_root, target, *, force_new=False):
        exports.append((project_root, target, force_new))
        return dict(saved)

    monkeypatch.setattr(schematic_export, "export_schematic", export)
    core = CoreSocket.__new__(CoreSocket)
    core._store = SimpleNamespace(get=lambda _: [SimpleNamespace(root=root)])
    core._selected_project_context = lambda: (root, None)
    core._vscode_bridge = SimpleNamespace(handles=lambda _: False)
    core._layout_session = lambda *args: None
    core._diff_session = lambda *args: None

    async def launch(path):
        launches.append(path)
        return {"status": "launched"}

    async def result(*args, **kwargs):
        responses.append(kwargs)

    core._kicad_service = SimpleNamespace(open_schematic=launch)
    core._send_action_result = result

    def dispatch(**payload):
        asyncio.run(core._dispatch(None, {
            "action": "exportSchematic", "requestId": "native", **payload,
        }))
        return responses[-1]

    return SimpleNamespace(
        dispatch=dispatch, exports=exports, launches=launches,
        core=core, root=root, saved=saved,
    )


def test_export_opens_only_the_server_generated_path(rpc):
    response = rpc.dispatch(openInKicad=True, forceNew=True, path="/etc/passwd")
    assert response["ok"] is True
    assert rpc.exports == [(rpc.root, "default", True)]
    assert [str(path) for path in rpc.launches] == [rpc.saved["path"]]
    assert response["result"]["opened"] is True
    assert response["result"]["openError"] is None


def test_export_without_native_launch_returns_openable_file(rpc):
    response = rpc.dispatch()
    assert response["ok"] is True
    assert response["result"]["path"].endswith(".kicad_sch")
    assert response["result"]["opened"] is False
    assert rpc.launches == []


def test_missing_kicad_keeps_successful_export_path(rpc):
    async def missing(_):
        raise FileNotFoundError("Install KiCad to open the schematic")

    rpc.core._kicad_service.open_schematic = missing
    response = rpc.dispatch(openInKicad=True)
    assert response["ok"] is True
    assert response["result"]["path"] == rpc.saved["path"]
    assert response["result"]["opened"] is False
    assert "Install KiCad" in response["result"]["openError"]


@pytest.mark.parametrize("payload", [
    {"projectRoot": "/outside/workspace"},
    {"forceNew": "false"},
    {"openInKicad": "false"},
])
def test_invalid_scope_or_flags_do_not_generate_or_launch(rpc, payload):
    response = rpc.dispatch(**payload)
    assert response["ok"] is False
    assert rpc.exports == []
    assert rpc.launches == []

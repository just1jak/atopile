"""Real scoped PCB reads must ground every local agent turn before inference."""

import asyncio
import json
import shutil
from types import SimpleNamespace

import pytest

from atopile.agent.providers.base import LLMResponse, ModelId, StreamDone, ToolCall
from atopile.agent.scope import Scope
from atopile.agent.session import AgentSession, Done, Thinking, ToolEnd, ToolStart
from atopile.agent.tools import create_registry
from atopile.agent.tools.layout import (
    _load,
    layout_get_netlist,
    layout_get_summary,
    layout_set_component_position,
)
from atopile.agent.tools.registry import ToolDef, ToolRegistry
from atopile.config import ProjectConfig
from atopile.data_models import UiAgentSessionData
from atopile.server.ui.store import Store
from atopile.server.ui.websocket import CoreSocket
from faebryk.libs.kicad.fileformats import kicad


class RecordingProvider:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])
        self.check = lambda kwargs: None

    async def stream(self, **kwargs):
        self.check(kwargs)
        self.calls.append(kwargs)
        response = (
            self.responses.pop(0)
            if self.responses
            else LLMResponse("r", "Read board.", [])
        )
        yield StreamDone(response)

    def snapshot(self):
        return {}

    def abort_pending(self, **kwargs):
        pass


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "1")
    root = tmp_path / "project"
    shutil.copytree("examples/offline-indicator", root)
    return root


def make_session(root, provider=None, registry=None):
    session = AgentSession(
        session_id="board-context-test",
        project_root=root,
        provider=provider or RecordingProvider(),
        model=ModelId.GPT_5_4,
        registry=registry or create_registry(),
        skill_ids=[],
    )

    async def no_title(message):
        return None

    session._generate_title_event = no_title
    return session


async def turn(session, target=None):
    return [
        event
        async for event in session.send_message(
            "Please help with this board.", selected_target=target
        )
    ]


def configure_targets(root, targets):
    source = root / "layouts/default/default.kicad_pcb"
    for name in targets:
        root.joinpath(f"target_{name}.ato").write_text(
            'from "main.ato" import OfflineIndicator\n'
            f"module Target_{name} from OfflineIndicator:\n    pass\n"
        )
    root.joinpath("ato.yaml").write_text(
        "requires-atopile: ^0.15.9\npaths:\n  src: ./\n  layout: ./layouts\nbuilds:\n"
        + "".join(
            f"  {name}:\n    entry: target_{name}.ato:Target_{name}\n"
            for name in targets
        )
    )
    config = ProjectConfig.from_path(root)
    for name in targets:
        destination = config.builds[name].paths.layout
        if destination != source:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    return config


def test_actual_preflight_precedes_provider_and_persists_normal_trace(project):
    provider = RecordingProvider()
    session = make_session(project, provider)
    assert session.ui_state()["board_context"] is None

    async def run():
        events = []

        def check(kwargs):
            assert any(isinstance(event, ToolEnd) for event in events)
            assert session._board_context["status"] == "ready"
            assert session._board_context["component_count"] == 3
            assert '"net_count": 3' in kwargs["instructions"]
            assert "layout_set_component_position" in kwargs["instructions"]
            assert "layout_get_summary" in kwargs["instructions"]

        provider.check = check
        async for event in session.send_message("Help with placement"):
            events.append(event)
            if len(events) == 1:
                assert isinstance(event, Thinking)
                assert session._board_context["status"] == "checking"
                assert not provider.calls
        return events

    events = asyncio.run(run())
    assert isinstance(events[1], ToolStart)
    done = next(e for e in events if isinstance(e, Done))
    assert done.traces[0].name == "layout_get_summary" and done.traces[0].ok
    assert (
        session.snapshot()["messages"][-1]["toolTraces"][0]["result"]["component_count"]
        == 3
    )
    wire = UiAgentSessionData.model_validate(session.ui_state()).model_dump(
        by_alias=True
    )
    assert wire["boardContext"]["netCount"] == 3
    assert wire["boardContext"]["layoutPath"] == str(
        project / "layouts/default/default.kicad_pcb"
    )


def test_actual_read_error_is_unavailable_with_evidence_before_inference(project):
    (project / "layouts/default/default.kicad_pcb").unlink()
    provider = RecordingProvider()
    session = make_session(project, provider)
    events = asyncio.run(turn(session))
    context = session.ui_state()["board_context"]
    assert context["status"] == "unavailable"
    assert "KiCad PCB does not exist" in context["error"]
    trace = next(e.trace for e in events if isinstance(e, ToolEnd))
    assert trace.ok is False and trace.result["error_type"] == "ValueError"
    assert "KiCad PCB does not exist" in provider.calls[0]["instructions"]
    assert session.snapshot()["messages"][-1]["toolTraces"][0]["ok"] is False


def test_nondefault_target_is_used_by_preflight_and_later_implicit_tool(project):
    config = configure_targets(project, ["alpha", "beta"])
    beta = config.builds["beta"].paths.layout
    board = _load(beta)
    board.kicad_pcb.footprints.pop(len(board.kicad_pcb.footprints) - 1)
    kicad.dumps(board, beta)
    provider = RecordingProvider(
        [
            LLMResponse("r1", "", [ToolCall("call", "layout_get_netlist", "{}", {})]),
            LLMResponse("r2", "Read beta.", []),
        ]
    )
    session = make_session(project, provider)
    events = asyncio.run(turn(session, "beta"))
    assert session._board_context["target"] == "beta"
    assert session._board_context["component_count"] == 2
    assert session._board_context["layout_path"] == str(beta)
    traces = next(e for e in events if isinstance(e, Done)).traces
    assert traces[1].name == "layout_get_netlist" and traces[1].ok
    assert traces[1].result["layout_path"] == str(beta)
    output = json.loads(provider.calls[1]["messages"][0]["output"])
    assert output["layout_path"] == str(beta)
    # An explicit tool target still overrides the per-turn default.
    scope = Scope(allowed_roots=[project], selected_target="beta")
    explicit = asyncio.run(layout_get_netlist({"target": "alpha"}, scope))
    assert explicit["layout_path"] == str(config.builds["alpha"].paths.layout)


def test_each_turn_reads_fresh_board_and_clears_previous_error(project):
    session = make_session(project)
    path = project / "layouts/default/default.kicad_pcb"
    original = path.read_bytes()
    path.unlink()
    asyncio.run(turn(session))
    assert session._board_context["status"] == "unavailable"
    path.write_bytes(original)
    events = asyncio.run(turn(session))
    assert session._board_context["status"] == "ready"
    assert "error" not in session._board_context
    first_checked = session._board_context["checked_at"]
    board = _load(path)
    board.kicad_pcb.footprints[0].at.x += 5
    expected_x = float(board.kicad_pcb.footprints[0].at.x)
    kicad.dumps(board, path)
    refreshed = asyncio.run(turn(session))
    assert session._board_context["checked_at"] > first_checked
    trace = next(e.trace for e in refreshed if isinstance(e, ToolEnd))
    assert trace.result["components"][0]["x_mm"] == expected_x
    assert all(e.trace.ok for e in events if isinstance(e, ToolEnd))


def test_blank_target_uses_selected_board_for_read_and_placement(project):
    config = configure_targets(project, ["default", "beta"])
    default = config.builds["default"].paths.layout
    beta = config.builds["beta"].paths.layout
    default_before = default.read_bytes()
    scope = Scope(allowed_roots=[project], selected_target="beta")
    summary = asyncio.run(layout_get_summary({"target": " "}, scope))
    assert summary["target"] == "beta" and summary["layout_path"] == str(beta)
    asyncio.run(
        layout_set_component_position(
            {"target": "", "address": "J1", "x_mm": 70, "y_mm": 70}, scope
        )
    )
    assert default.read_bytes() == default_before
    moved = asyncio.run(layout_get_summary({}, scope))
    assert next(c for c in moved["components"] if c["reference"] == "J1")["x_mm"] == 70


def test_ambiguous_targets_require_selection_and_sole_target_is_safe(project):
    configure_targets(project, ["alpha", "beta"])
    session = make_session(project)
    asyncio.run(turn(session))
    assert session._board_context["status"] == "unavailable"
    assert "Select a build target" in session._board_context["error"]
    asyncio.run(turn(session, "not-a-target"))
    assert "Unknown build target" in session._board_context["error"]
    configure_targets(project, ["beta"])
    asyncio.run(turn(session))
    assert session._board_context["status"] == "ready"
    assert session._board_context["target"] == "beta"


def test_no_preflight_for_hosted_mode_or_registry_without_board_tools(
    project, monkeypatch
):
    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "0")
    session = make_session(project)
    assert not next(e for e in asyncio.run(turn(session)) if isinstance(e, Done)).traces
    assert session.ui_state()["board_context"] is None
    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "1")
    session = make_session(project, registry=ToolRegistry())
    assert not next(e for e in asyncio.run(turn(session)) if isinstance(e, Done)).traces


def test_server_target_isolation_and_actual_turn_propagation(project, tmp_path):
    config = configure_targets(project, ["alpha", "beta"])
    session = make_session(project)
    core = CoreSocket.__new__(CoreSocket)
    other = tmp_path / "different-project"
    core._selected_project_context = lambda: (
        str(other),
        SimpleNamespace(root=str(other), name="foreign"),
    )
    assert core._agent_turn_target(session) is None
    core._selected_project_context = lambda: (
        str(project),
        SimpleNamespace(root=str(project), name="beta"),
    )
    assert core._agent_turn_target(session) == "beta"
    assert core._agent_turn_target(session, ["alpha"]) == "alpha"
    core._run_tasks = {}
    core._agent = SimpleNamespace(save_sessions=lambda: None)
    core._push_agent_state = lambda: None
    progress = []

    async def emit(session, payload, **kwargs):
        progress.append(payload)

    core._emit_agent_progress = emit
    asyncio.run(core._run_agent_turn(session, "Check selected board"))
    assert session._board_context["target"] == "beta"
    assert session._board_context["layout_path"] == str(
        config.builds["beta"].paths.layout
    )
    assert [p["phase"] for p in progress].index("tool_end") < [
        p["phase"] for p in progress
    ].index("done")


def test_board_snapshot_is_bounded_even_with_large_component_metadata(project):
    from atopile.agent.session import _bounded_board_summary

    result = {
        "component_count": 500,
        "net_count": 200,
        "components": [{"reference": "X" * 10000, "value": "a" * 10000}] * 500,
        "net_names": ["long-net" * 10000] * 200,
    }
    bounded = _bounded_board_summary(result)
    assert len(bounded["components"]) == 24 and len(bounded["net_names"]) == 48
    assert len(json.dumps(bounded)) < 24000


def test_cancelled_preflight_does_not_leave_checking_status(project):
    async def run():
        started = asyncio.Event()

        async def blocked_summary(args, scope):
            started.set()
            await asyncio.Event().wait()

        registry = ToolRegistry()
        actual = layout_get_summary._tool_def
        registry.register(
            ToolDef(
                name=actual.name,
                label=actual.label,
                schema=actual.schema,
                handler=blocked_summary,
            )
        )
        provider = RecordingProvider()
        session = make_session(project, provider, registry)
        task = asyncio.create_task(turn(session))
        await asyncio.wait_for(started.wait(), 1)
        assert session._board_context["status"] == "checking"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        session.abort_run(reason="Stopped")
        assert session._board_context["status"] == "unavailable"
        assert "stopped" in session._board_context["error"]
        assert not session.is_running and not provider.calls

    asyncio.run(run())


def test_startup_discovery_restores_history_without_explicit_project_selection(
    project, monkeypatch
):
    from atopile.agent.session import Agent
    from atopile.model.sqlite import AgentSessions
    from atopile.server.ui import sidebar

    monkeypatch.setenv("ATOPILE_AGENT_PROVIDER", "codex")
    row = {
        "session_id": "saved-chat",
        "project_root": str(project),
        "model": "codex-default",
        "provider_state": {},
        "messages": [
            {
                "id": "saved-message",
                "role": "user",
                "content": "Layout this board",
                "pending": False,
            }
        ],
        "checklist": [],
        "active_skills": ["agent"],
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    monkeypatch.setattr(AgentSessions, "init_db", lambda: None)
    monkeypatch.setattr(
        AgentSessions,
        "load_all",
        lambda **kwargs: [row] if kwargs["project_root"] == str(project) else [],
    )

    async def apply(**kwargs):
        kwargs["store"].set("projects", kwargs["project_list"])
        kwargs["store"].set("project_state", kwargs["project_state"])

    monkeypatch.setattr(sidebar, "apply_project_selection", apply)
    core = CoreSocket.__new__(CoreSocket)
    core._project_discovery_lock = asyncio.Lock()
    core._project_selection_lock = asyncio.Lock()
    core._discovery_paths = [project]
    core._store = Store()
    core._agent = Agent()
    core._project_files = None
    core._sync_selected_layout = None
    core._sync_selected_pinout = None
    core._set_layout_data = None

    async def run():
        await core._refresh_discovered_projects()
        restored = core._agent.sessions["saved-chat"]
        assert restored._messages[0]["content"] == "Layout this board"
        state = core._store.get("agent_data")
        assert state.sessions[0].session_id == "saved-chat"
        assert state.sessions[0].board_context is None
        await core._refresh_discovered_projects()
        assert core._agent.sessions["saved-chat"] is restored

    asyncio.run(run())

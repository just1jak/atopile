from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import atopile.model.build_queue as build_queue_module
import atopile.model.sqlite as sqlite_module
from atopile.buildutil import generate_build_id
from atopile.cli import build as cli_build
from atopile.data_models import (
    Build,
    BuildRequest,
    BuildStage,
    BuildStatus,
    ResolvedBuildTarget,
    StageStatus,
)
from atopile.model import builds as builds_domain
from atopile.model.build_queue import BuildQueue
from atopile.model.sqlite import BuildHistory


@pytest.fixture()
def isolated_build_history(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "build_history.db"
    monkeypatch.setattr(sqlite_module, "BUILD_HISTORY_DB", db_path)
    monkeypatch.setattr(build_queue_module, "BUILD_HISTORY_DB", db_path)
    BuildHistory.init_db()
    yield


def _make_build(project_root: Path, name: str) -> Build:
    started_at = 1000.0 + len(name)
    target = ResolvedBuildTarget(root=str(project_root), name=name)
    return Build(
        build_id=generate_build_id(str(project_root), name, started_at),
        name=name,
        project_root=str(project_root),
        target=target,
        status=BuildStatus.QUEUED,
        started_at=started_at,
    )


def _complete_launch(launched: list[str]):
    def _launch(build_or_queue: BuildQueue | Build, build: Build | None = None) -> None:
        build = build_or_queue if isinstance(build_or_queue, Build) else build
        assert build is not None
        launched.append(build.build_id)
        existing = BuildHistory.get(build.build_id)
        assert existing is not None
        building = existing.model_copy(
            update={
                "status": BuildStatus.BUILDING,
                "stages": [
                    BuildStage(
                        name="Compile",
                        stage_id="compile",
                        status=StageStatus.RUNNING,
                    )
                ],
            }
        )
        BuildHistory.set(building)
        BuildHistory.set(
            building.model_copy(
                update={
                    "status": BuildStatus.SUCCESS,
                    "return_code": 0,
                    "stages": [
                        BuildStage(
                            name="Compile",
                            stage_id="compile",
                            status=StageStatus.SUCCESS,
                        )
                    ],
                }
            )
        )

    return _launch


def test_cli_single_build_starts(
    tmp_path: Path, monkeypatch, isolated_build_history
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    build = _make_build(project_root, "default")
    launched: list[str] = []

    monkeypatch.setattr(
        cli_build,
        "BuildPrinter",
        MagicMock(spec=cli_build.BuildPrinter),
    )
    monkeypatch.setattr(BuildQueue, "_launch_build", _complete_launch(launched))

    results = cli_build._run_build_queue([build], jobs=1, verbose=False)

    assert launched == [build.build_id]
    assert results == {build.build_id: 0}


def test_extension_single_build_starts(
    tmp_path: Path, monkeypatch, isolated_build_history
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "ato.yaml").write_text("builds: {}\n", encoding="utf-8")
    target = ResolvedBuildTarget(root=str(project_root), name="default")
    launched: list[str] = []

    monkeypatch.setattr(
        builds_domain._build_queue,
        "_launch_build",
        _complete_launch(launched),
    )
    monkeypatch.setattr(builds_domain._build_queue, "_running", True)

    submitted = builds_domain.handle_start_build(
        BuildRequest(project_root=str(project_root), targets=[target])
    )

    assert launched == [submitted[0].build_id]


def test_cli_multi_build_starts(
    tmp_path: Path, monkeypatch, isolated_build_history
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    builds = [
        _make_build(project_root, "default"),
        _make_build(project_root, "mfg"),
    ]
    launched: list[str] = []

    monkeypatch.setattr(
        cli_build,
        "BuildPrinter",
        MagicMock(spec=cli_build.BuildPrinter),
    )
    monkeypatch.setattr(BuildQueue, "_launch_build", _complete_launch(launched))

    results = cli_build._run_build_queue(builds, jobs=2, verbose=False)

    assert launched == [build.build_id for build in builds]
    assert results == {build.build_id: 0 for build in builds}


def test_extension_multi_build_starts(
    tmp_path: Path, monkeypatch, isolated_build_history
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "ato.yaml").write_text("builds: {}\n", encoding="utf-8")
    targets = [
        ResolvedBuildTarget(root=str(project_root), name="default"),
        ResolvedBuildTarget(root=str(project_root), name="mfg"),
    ]
    launched: list[str] = []

    monkeypatch.setattr(
        builds_domain._build_queue,
        "_launch_build",
        _complete_launch(launched),
    )
    monkeypatch.setattr(builds_domain._build_queue, "_running", True)

    submitted = builds_domain.handle_start_build(
        BuildRequest(project_root=str(project_root), targets=targets)
    )

    assert launched == [build.build_id for build in submitted]


def test_extension_standalone_build_starts(
    tmp_path: Path, monkeypatch, isolated_build_history
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    entry = project_root / "main.ato"
    entry.write_text("component App:\n    pass\n", encoding="utf-8")
    launched: list[str] = []

    monkeypatch.setattr(
        builds_domain._build_queue,
        "_launch_build",
        _complete_launch(launched),
    )
    monkeypatch.setattr(builds_domain._build_queue, "_running", True)

    submitted = builds_domain.handle_start_build(
        BuildRequest(
            project_root=str(project_root),
            entry="main.ato:App",
            standalone=True,
        )
    )

    assert len(submitted) == 1
    assert launched == [submitted[0].build_id]
    assert submitted[0].standalone is True
    assert submitted[0].target.root == str(project_root)
    assert submitted[0].target.entry == "main.ato:App"


@pytest.fixture(autouse=True)
def telemetry_events(monkeypatch):
    from atopile.telemetry.telemetry import Telemetry

    events = []
    dispatcher = MagicMock()
    dispatcher.capture.side_effect = lambda event, thin: events.append(
        (event, thin.extra)
    )
    monkeypatch.setattr(Telemetry, "get", lambda: dispatcher)
    monkeypatch.delenv("ATO_VSCE_PID", raising=False)
    return events


@pytest.mark.parametrize("via_vsce", [False, True])
@pytest.mark.parametrize("return_code", [0, 1])
def test_entry_paths_emit_one_pair_for_multiple_targets(
    tmp_path,
    monkeypatch,
    isolated_build_history,
    telemetry_events,
    via_vsce,
    return_code,
):
    from test.test_build_telemetry import assert_pair

    if via_vsce:
        monkeypatch.setenv("ATO_VSCE_PID", "123")
    project = tmp_path / "project"
    project.mkdir()
    (project / "ato.yaml").write_text("builds: {}\n")
    builds = [_make_build(project, "a"), _make_build(project, "b")]
    contexts = []

    def launch(queue, build):
        contexts.append(queue._telemetry_builds[build.build_id].worker_context())
        queue._result_q.put(
            build_queue_module.BuildCompletedMsg(
                build_id=build.build_id, return_code=return_code, error=None, stages=[]
            )
        )
        queue._apply_results()

    monkeypatch.setattr(BuildQueue, "_launch_build", launch)
    monkeypatch.setattr(
        BuildQueue, "start", lambda self: setattr(self, "_running", True)
    )
    monkeypatch.setattr(cli_build, "BuildPrinter", MagicMock())
    queue = BuildQueue()
    if via_vsce:
        monkeypatch.setattr(builds_domain, "_build_queue", queue)
        builds_domain.handle_start_build(
            BuildRequest(
                project_root=str(project), targets=[build.target for build in builds]
            )
        )
    else:

        def all_projects(**kwargs):
            results = cli_build._run_build_queue(builds, jobs=2, verbose=False)
            if any(results.values()):
                raise cli_build.typer.Exit(1)

        monkeypatch.setattr(cli_build, "_build_all_projects", all_projects)
        if return_code:
            with pytest.raises(cli_build.typer.Exit):
                cli_build.build(all_projects=True)
        else:
            cli_build.build(all_projects=True)
    assert_pair(telemetry_events, "failed" if return_code else "success", via_vsce, 2)
    assert len(contexts) == 2
    assert all(
        context["invocation_id"] == telemetry_events[0][1]["build_invocation_id"]
        for context in contexts
    )
    assert all(bool(context["vsce_pid"]) == via_vsce for context in contexts)


@pytest.mark.parametrize("cancel_kind", ["queued", "running", "shutdown"])
def test_cancellations_emit_terminal_event(
    tmp_path, monkeypatch, isolated_build_history, telemetry_events, cancel_kind
):
    from test.test_build_telemetry import assert_pair

    queue = BuildQueue()
    monkeypatch.setattr(queue, "_running", True)

    def launch(build):
        if cancel_kind != "queued":
            BuildHistory.set(build.model_copy(update={"status": BuildStatus.BUILDING}))
            queue._cancel_flags[build.build_id] = False

    monkeypatch.setattr(queue, "_launch_build", launch)
    build = _make_build(tmp_path, "a")
    queue.submit_builds([build])
    if cancel_kind == "shutdown":
        queue.stop()
    else:
        assert queue.cancel_build(build.build_id)
        if cancel_kind == "running":
            queue._result_q.put(build_queue_module.BuildCancelledMsg(build.build_id))
            queue._apply_results()
    queue._result_q.put(build_queue_module.BuildCancelledMsg(build.build_id))
    queue._apply_results()
    assert_pair(telemetry_events, "cancelled", False, 1)
    assert BuildHistory.get(build.build_id).status == BuildStatus.CANCELLED


@pytest.mark.parametrize("via_vsce", [False, True])
def test_worker_receives_identity_and_origin(
    tmp_path, monkeypatch, isolated_build_history, via_vsce
):
    context = {"invocation_id": "invocation", "vsce_pid": "123" if via_vsce else ""}
    process = MagicMock()
    process.is_alive.return_value = False
    process.exitcode = 0
    mp_ctx = MagicMock()
    mp_ctx.Process.return_value = process
    build = _make_build(tmp_path, "a")
    build_queue_module._run_build(
        build, build_queue_module.queue.Queue(), {}, mp_ctx, telemetry_context=context
    )
    assert mp_ctx.Process.call_args.kwargs["kwargs"]["telemetry_context"] == context
    assert mp_ctx.Process.call_args.kwargs["kwargs"]["build_id"] == build.build_id


def test_cancelled_process_exit_is_not_success(
    tmp_path, monkeypatch, isolated_build_history
):
    build = _make_build(tmp_path, "a")
    process = MagicMock()
    process.is_alive.return_value = False
    process.exitcode = 0
    mp_ctx = MagicMock()
    mp_ctx.Process.return_value = process
    results = build_queue_module.queue.Queue()
    build_queue_module._run_build(build, results, {build.build_id: True}, mp_ctx)
    assert isinstance(results.get_nowait(), build_queue_module.BuildCancelledMsg)


def test_launch_failure_records_failure(
    tmp_path, monkeypatch, isolated_build_history, telemetry_events
):
    from test.test_build_telemetry import assert_pair

    queue = BuildQueue()
    monkeypatch.setattr(queue, "_running", True)

    def fail(build):
        raise OSError("cannot start worker")

    monkeypatch.setattr(queue, "_launch_build", fail)
    with pytest.raises(OSError, match="cannot start worker"):
        queue.submit_builds([_make_build(tmp_path, "a")])
    assert_pair(telemetry_events, "failed", False, 1)
    assert not queue._telemetry_builds


@pytest.mark.parametrize("via_vsce", [True, False])
def test_validation_failure_emits_pair(
    tmp_path, monkeypatch, telemetry_events, via_vsce
):
    from test.test_build_telemetry import assert_pair

    if via_vsce:
        monkeypatch.setenv("ATO_VSCE_PID", "123")
        with pytest.raises(ValueError):
            builds_domain.handle_start_build(BuildRequest(project_root=str(tmp_path)))
    else:

        def fail(**kwargs):
            raise ValueError("invalid project")

        monkeypatch.setattr(cli_build, "_build_all_projects", fail)
        with pytest.raises(ValueError):
            cli_build.build(all_projects=True)
    assert_pair(telemetry_events, "failed", via_vsce, 0)


def test_process_start_failure_reports_failed_result(tmp_path, isolated_build_history):
    build = _make_build(tmp_path, "a")
    mp_ctx = MagicMock()
    process = mp_ctx.Process.return_value
    process.start.side_effect = OSError("worker launch failed")
    process.is_alive.return_value = False
    results = build_queue_module.queue.Queue()
    build_queue_module._run_build(build, results, {}, mp_ctx)
    result = results.get_nowait()
    assert isinstance(result, build_queue_module.BuildCompletedMsg)
    assert result.return_code != 0
    assert result.error == "worker launch failed"

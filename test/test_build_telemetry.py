"""Build invocation counting, isolation, and best-effort delivery."""

import asyncio
import os
from unittest.mock import MagicMock

import pytest

from atopile.telemetry import build as telemetry
from atopile.telemetry.config import TelemetryConfig
from atopile.telemetry.telemetry import Telemetry


@pytest.fixture
def events(monkeypatch):
    events = []
    dispatcher = MagicMock()
    dispatcher.capture.side_effect = lambda event, thin: events.append(
        (event, thin.extra)
    )
    monkeypatch.setattr(Telemetry, "get", lambda: dispatcher)
    return events


def assert_pair(events, outcome, via_vsce, count):
    assert [event for event, _ in events] == ["cli:build_start", "cli:build_end"]
    start, end = [props for _, props in events]
    assert start["build_invocation_id"] == end["build_invocation_id"]
    assert start["via_vsce"] is end["via_vsce"] is via_vsce
    assert start["outcome"] == "started"
    assert end["outcome"] == outcome
    assert end["target_count"] == count
    assert end["duration"] >= start["duration"] >= 0
    assert end["counting_unit"] == "invocation"


@pytest.mark.parametrize("vsce_pid", ["123", ""])
def test_multiple_targets_finish_once_with_original_origin(
    monkeypatch, events, vsce_pid
):
    monkeypatch.setenv("ATO_VSCE_PID", vsce_pid)
    with telemetry.capture_build_invocation() as invocation:
        invocation.add_targets(["a", "b"])
        with telemetry.capture_build_invocation() as nested:
            assert nested is invocation
    assert len(events) == 1
    monkeypatch.setenv("ATO_VSCE_PID", "changed")
    invocation.complete("a", "success")
    assert len(events) == 1
    invocation.complete("b", "success")
    invocation.complete("b", "failed")
    invocation.close()
    assert_pair(events, "success", bool(vsce_pid), 2)


@pytest.mark.parametrize(
    "outcomes,expected",
    [
        (["failed", "success"], "failed"),
        (["cancelled", "success"], "cancelled"),
        (["cancelled", "failed"], "failed"),
    ],
)
def test_target_outcomes_aggregate(events, outcomes, expected, monkeypatch):
    monkeypatch.delenv("ATO_VSCE_PID", raising=False)
    with telemetry.capture_build_invocation() as invocation:
        invocation.add_targets(["a", "b"])
    for build_id, outcome in zip(["a", "b"], outcomes):
        invocation.complete(build_id, outcome)
    assert_pair(events, expected, False, 2)


@pytest.mark.parametrize(
    "error,outcome",
    [
        (ValueError("invalid"), "failed"),
        (SystemExit(1), "failed"),
        (KeyboardInterrupt(), "cancelled"),
        (asyncio.CancelledError(), "cancelled"),
    ],
)
def test_errors_and_interrupts(events, monkeypatch, error, outcome):
    monkeypatch.delenv("ATO_VSCE_PID", raising=False)
    with pytest.raises(type(error)):
        with telemetry.capture_build_invocation():
            raise error
    assert_pair(events, outcome, False, 0)
    assert telemetry.current_build_invocation() is None


def test_dispatcher_failure_does_not_change_build_result(monkeypatch):
    def broken():
        raise RuntimeError("telemetry unavailable")

    monkeypatch.setattr(Telemetry, "get", broken)
    with telemetry.capture_build_invocation():
        pass
    with pytest.raises(ValueError, match="build failed"):
        with telemetry.capture_build_invocation():
            raise ValueError("build failed")


def test_opt_out_does_not_enqueue(monkeypatch):
    monkeypatch.setattr(
        TelemetryConfig, "load", lambda: TelemetryConfig(telemetry=False)
    )
    dispatcher = Telemetry()
    monkeypatch.setattr(Telemetry, "get", lambda: dispatcher)
    monkeypatch.setattr(dispatcher, "_enqueue", MagicMock())
    with telemetry.capture_build_invocation():
        pass
    dispatcher._enqueue.assert_not_called()
    assert dispatcher._worker is None


@pytest.mark.parametrize("pid", ["123", ""])
def test_worker_context_overrides_stale_environment(monkeypatch, pid):
    monkeypatch.setenv("ATO_VSCE_PID", "stale")
    monkeypatch.setenv("ATO_BUILD_INVOCATION_ID", "old")
    telemetry.apply_worker_context({"invocation_id": "shared-id", "vsce_pid": pid})
    assert os.environ["ATO_BUILD_INVOCATION_ID"] == "shared-id"
    assert os.environ.get("ATO_VSCE_PID", "") == pid


def test_cli_exit_preserves_cancelled_outcome(events, monkeypatch):
    from click.exceptions import Exit

    monkeypatch.delenv("ATO_VSCE_PID", raising=False)
    with pytest.raises(Exit):
        with telemetry.capture_build_invocation() as invocation:
            invocation.add_targets(["target"])
            invocation.complete("target", "cancelled")
            raise Exit(1)
    assert_pair(events, "cancelled", False, 1)


def _worker_origin(context, connection):
    telemetry.apply_worker_context(context)
    connection.send(
        (os.environ["ATO_BUILD_INVOCATION_ID"], os.environ.get("ATO_VSCE_PID", ""))
    )
    connection.close()


@pytest.mark.parametrize("pid", ["123", ""])
def test_spawned_worker_retains_context(monkeypatch, pid):
    import multiprocessing

    monkeypatch.setenv("ATO_VSCE_PID", "stale")
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_worker_origin,
        args=({"invocation_id": "shared-id", "vsce_pid": pid}, child),
    )
    process.start()
    child.close()
    try:
        assert parent.poll(15), "worker did not report telemetry context"
        assert parent.recv() == ("shared-id", pid)
        process.join(15)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        parent.close()


def test_worker_origin_loader_does_not_cache_forkserver_origin(monkeypatch):
    from atopile.telemetry.properties import PropertyLoaders

    monkeypatch.setenv("ATO_VSCE_PID", "stale")
    monkeypatch.setenv("ATO_BUILD_INVOCATION_ID", "old")
    assert PropertyLoaders.via_vsce() is True
    telemetry.apply_worker_context({"invocation_id": "cli", "vsce_pid": ""})
    assert PropertyLoaders.via_vsce() is False


def test_delivery_enriches_version_without_changing_origin_or_duration(
    monkeypatch, events
):
    import importlib.metadata

    from atopile.telemetry.properties import TelemetryProperties, ThinProperties

    monkeypatch.delenv("ATO_VSCE_PID", raising=False)
    with telemetry.capture_build_invocation():
        pass
    monkeypatch.setenv("ATO_VSCE_PID", "different-origin-at-delivery")
    terminal = events[-1][1]
    delivered = TelemetryProperties(thin=ThinProperties(extra=terminal)).dump()
    assert delivered["atopile_version"] == importlib.metadata.version("atopile")
    assert delivered["via_vsce"] is False
    assert delivered["duration"] == terminal["duration"]


def test_network_delivery_failure_cannot_break_build(monkeypatch):
    from atopile.telemetry import telemetry as dispatcher_module

    client = MagicMock()
    client.capture.side_effect = OSError("offline")
    monkeypatch.setattr(dispatcher_module, "TelemetryClient", lambda: client)
    monkeypatch.setattr(dispatcher_module, "_logged_in_identity", lambda: None)
    monkeypatch.setattr(
        TelemetryConfig, "load", lambda: TelemetryConfig(telemetry=True)
    )
    dispatcher = Telemetry()
    monkeypatch.setattr(Telemetry, "get", lambda: dispatcher)
    with telemetry.capture_build_invocation():
        pass
    dispatcher.flush()
    assert client.capture.call_count == 2
    assert dispatcher._queue.empty()

"""Stop must not finish while a threaded PCB edit can still write."""

from __future__ import annotations

import asyncio
import threading

import pytest

from atopile.agent.scope import Scope
from atopile.agent.tools import layout


def test_placement_wrapper_preserves_result_and_arguments(monkeypatch):
    args = {"address": "J1", "x_mm": 10, "y_mm": 20}
    scope = Scope()
    expected = {"updated": True, "after": {"x_mm": 10}}

    def edit(received_args, received_scope):
        assert received_args is args
        assert received_scope is scope
        return expected

    monkeypatch.setattr(layout, "_set_position", edit)
    assert asyncio.run(layout.layout_set_component_position(args, scope)) is expected


def test_placement_wrapper_propagates_worker_error(monkeypatch):
    def edit(args, scope):
        raise ValueError("Board changed before commit")

    monkeypatch.setattr(layout, "_set_position", edit)
    with pytest.raises(ValueError, match="Board changed before commit"):
        asyncio.run(layout.layout_set_component_position({}, Scope()))


@pytest.mark.parametrize("worker_error", [False, True])
def test_repeated_stop_waits_for_thread_completion(monkeypatch, worker_error):
    async def scenario():
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        release = threading.Event()
        finished = threading.Event()
        commits = []

        def edit(args, scope):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(5), "Test did not release the board edit"
            commits.append("committed")
            finished.set()
            if worker_error:
                raise RuntimeError("Edit worker failed after commit")
            return {"updated": True}

        monkeypatch.setattr(layout, "_set_position", edit)
        task = asyncio.create_task(layout.layout_set_component_position({}, Scope()))
        try:
            await asyncio.wait_for(started.wait(), 2)
            task.cancel("first stop")
            await asyncio.sleep(0)
            assert not task.done()
            assert not finished.is_set()
            assert commits == []

            task.cancel("second stop")
            await asyncio.sleep(0)
            assert not task.done()
            assert not finished.is_set()

            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            assert finished.is_set()
            assert commits == ["committed"]
            # The wrapper waited for the worker to return, so no write remains
            # that could run after its caller acknowledges cancellation.
            assert task.done() and task.cancelled()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())

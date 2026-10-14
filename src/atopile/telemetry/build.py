"""One parent-owned event pair per build invocation, across all its targets."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

from click.exceptions import Exit

from atopile.telemetry.properties import ThinProperties
from atopile.telemetry.telemetry import Telemetry

log = logging.getLogger(__name__)
Outcome = Literal["success", "failed", "cancelled"]
_current: ContextVar[BuildInvocation | None] = ContextVar(
    "build_invocation", default=None
)


class BuildInvocation:
    def __init__(self) -> None:
        self.id = str(uuid.uuid4())
        self.vsce_pid = os.environ.get("ATO_VSCE_PID", "")
        self.started_at = time.perf_counter()
        self._lock = threading.Lock()
        self._pending: set[str] = set()
        self._target_count = 0
        self._outcome: Outcome = "success"
        self._closed = False
        self._finished = False
        self._emit("cli:build_start", "started")

    def _emit(self, event: str, outcome: str) -> None:
        # Freeze duration and attribution now, not on the delivery thread. Use
        # the existing dispatcher for version/identity enrichment and opt-out.
        try:
            Telemetry.get().capture(
                event,
                ThinProperties(
                    extra={
                        "build_invocation_id": self.id,
                        "counting_unit": "invocation",
                        "via_vsce": bool(self.vsce_pid),
                        "outcome": outcome,
                        "duration": time.perf_counter() - self.started_at,
                        "target_count": self._target_count,
                    }
                ),
            )
        except Exception:
            log.debug("Failed to capture build telemetry", exc_info=True)

    def add_targets(self, build_ids: list[str]) -> None:
        with self._lock:
            self._pending.update(build_ids)
            self._target_count += len(build_ids)

    def _merge_outcome(self, outcome: Outcome) -> None:
        if outcome == "failed" or self._outcome == "success":
            self._outcome = outcome

    def complete(self, build_id: str, outcome: Outcome) -> None:
        with self._lock:
            if build_id not in self._pending:
                return
            self._pending.remove(build_id)
            self._merge_outcome(outcome)
            self._finish_if_ready()

    def close(self, outcome: Outcome = "success") -> None:
        with self._lock:
            self._closed = True
            self._merge_outcome(outcome)
            if outcome != "success":
                # Covers validation/launch errors and interrupted CLI calls.
                self._pending.clear()
            self._finish_if_ready()

    def close_exit(self, code: int | str | None) -> None:
        # The CLI reports cancelled targets with exit code 1 as well. Preserve
        # their recorded outcome instead of converting cancellation to failure.
        with self._lock:
            recorded_failure = self._outcome != "success"
        self.close("success" if not code or recorded_failure else "failed")

    def _finish_if_ready(self) -> None:
        if self._closed and not self._pending and not self._finished:
            self._finished = True
            self._emit("cli:build_end", self._outcome)

    def worker_context(self) -> dict[str, str]:
        return {"invocation_id": self.id, "vsce_pid": self.vsce_pid}


def apply_worker_context(context: dict[str, str]) -> None:
    """Override stale forkserver environment, including a previously set origin."""
    os.environ["ATO_BUILD_INVOCATION_ID"] = context["invocation_id"]
    if context["vsce_pid"]:
        os.environ["ATO_VSCE_PID"] = context["vsce_pid"]
    else:
        os.environ.pop("ATO_VSCE_PID", None)


def current_build_invocation() -> BuildInvocation | None:
    return _current.get()


@contextmanager
def capture_build_invocation():
    # Nested orchestration (CLI -> queue submission) shares one counting unit.
    if _current.get() is not None:
        yield _current.get()
        return
    invocation = BuildInvocation()
    token = _current.set(invocation)
    try:
        yield invocation
    except KeyboardInterrupt, asyncio.CancelledError:
        invocation.close("cancelled")
        raise
    except (SystemExit, Exit) as exc:
        invocation.close_exit(
            exc.code if isinstance(exc, SystemExit) else exc.exit_code
        )
        raise
    except BaseException:
        invocation.close("failed")
        raise
    else:
        invocation.close()
    finally:
        _current.reset(token)

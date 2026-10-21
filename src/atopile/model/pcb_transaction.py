"""Serialize local PCB writers and commit without overwriting external edits."""

from __future__ import annotations

import asyncio
import hashlib
import os
import stat
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_locks_guard = threading.Lock()
_locks: dict[Path, threading.RLock] = {}
_held = threading.local()


@contextmanager
def pcb_write_lock(path: Path):
    """One cooperating writer per board across threads and local core processes."""
    path = path.resolve()
    with _locks_guard:
        lock = _locks.setdefault(path, threading.RLock())
    with lock:
        held = getattr(_held, "paths", set())
        if path in held:
            yield
            return
        # Lock files stay outside project directories and are never removed while
        # held; unlinking a flock file would permit two different locked inodes.
        state = os.environ.get("ATOPILE_LOCAL_DATA_DIR")
        root = (
            Path(state).expanduser().resolve() / "pcb-locks"
            if state
            else Path(tempfile.gettempdir()) / "atopile-local-pcb-locks"
        )
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = hashlib.sha256(os.fsencode(path)).hexdigest() + ".lock"
        with (root / name).open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                handle.write(b"\0")
                handle.flush()

                def acquire():
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

                def release():
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                def acquire():
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                def release():
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

            deadline = time.monotonic() + 15
            while True:
                try:
                    acquire()
                    break
                except BlockingIOError, PermissionError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Another local process is editing this PCB")
                    time.sleep(0.05)
            _held.paths = held | {path}
            try:
                yield
            finally:
                _held.paths = held
                release()


def commit_pcb_bytes(path: Path, original: bytes, updated: bytes | str) -> Path | None:
    """Back up exact original bytes, then atomically replace an unchanged board."""
    if isinstance(updated, str):
        updated = updated.encode("utf-8")
    with pcb_write_lock(path):
        if path.is_symlink() or not path.is_file() or path.read_bytes() != original:
            raise RuntimeError(
                "PCB changed in the editor; inspect again before editing"
            )
        if updated == original:
            return None
        mode = stat.S_IMODE(path.stat().st_mode)
        backup = path.with_name(
            f"{path.name}.local-agent-{time.time_ns()}-{uuid.uuid4().hex[:8]}.bak"
        )
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(original)
            output.flush()
            os.fsync(output.fileno())
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=".local-layout-", delete=False
            ) as output:
                temporary = Path(output.name)
                output.write(updated)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(mode)
            # Recheck after preparing the replacement, not just before rendering.
            if path.is_symlink() or path.read_bytes() != original:
                raise RuntimeError(
                    "PCB changed in the editor; inspect again before editing"
                )
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return backup


async def finish_board_edit(awaitable: Any) -> Any:
    """Stop waits for an in-flight edit, so it cannot write after acknowledging Stop."""
    worker = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not worker.cancelled():
            worker.exception()
        raise

"""Prevent concurrent startup or temporary SQLite errors from deleting logs."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from atopile.model import sqlite as storage

_WORKER = """
import sys
import time
from pathlib import Path
from atopile.model.sqlite import _get_init_connection, LOG_VER

db, markers, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
(markers / (name + '.ready')).touch()
with _get_init_connection(db) as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS startup_markers (name TEXT PRIMARY KEY)')
    conn.execute('INSERT INTO startup_markers VALUES (?)', (name,))
    (markers / (name + '.entered')).touch()
    if name == 'first':
        deadline = time.monotonic() + 15
        while not (markers / 'release').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('Test did not release initial schema transaction')
            time.sleep(.01)
    conn.execute('PRAGMA user_version = ' + str(LOG_VER))
"""


def _await_marker(path: Path, process: subprocess.Popen, timeout: float = 15):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(f"Worker exited before {path.name}: {stdout}\n{stderr}")
        if time.monotonic() >= deadline:
            pytest.fail(f"Worker did not reach {path.name}")
        time.sleep(0.02)


def test_two_process_initializers_wait_and_keep_both_committed_rows(tmp_path):
    """Hold user_version=0 while a second process tries to initialize.

    The previous code mistook that in-progress database for a stale schema,
    unlinked it, and lost the first process's data (or crashed its commit).
    """
    db = tmp_path / "logs" / "startup.db"
    markers = tmp_path / "markers"
    markers.mkdir()
    env = dict(os.environ, ATOPILE_LOCAL_DATA_DIR=str(tmp_path / "isolated-state"))
    processes = []
    try:
        first = subprocess.Popen(
            [sys.executable, "-c", _WORKER, str(db), str(markers), "first"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(first)
        _await_marker(markers / "first.entered", first)
        second = subprocess.Popen(
            [sys.executable, "-c", _WORKER, str(db), str(markers), "second"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append(second)
        _await_marker(markers / "second.ready", second)
        time.sleep(0.25)
        assert not (markers / "second.entered").exists()
        (markers / "release").touch()
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, f"{stdout}\n{stderr}"
        with sqlite3.connect(db) as connection:
            assert connection.execute(
                "SELECT name FROM startup_markers ORDER BY name"
            ).fetchall() == [("first",), ("second",)]
            assert (
                connection.execute("PRAGMA user_version").fetchone()[0]
                == storage.LOG_VER
            )
        assert list(tmp_path.glob(".*-sqlite-*.lock"))
        assert not list(db.parent.glob("*.lock"))
    finally:
        (markers / "release").touch()
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)


@pytest.mark.parametrize(
    "code",
    [
        sqlite3.SQLITE_BUSY,
        sqlite3.SQLITE_LOCKED,
        sqlite3.SQLITE_IOERR,
        sqlite3.SQLITE_CANTOPEN,
        0,
    ],
)
def test_temporary_database_errors_never_delete_storage(tmp_path, monkeypatch, code):
    db = tmp_path / "logs.db"
    db.write_bytes(b"keep the database")
    error = sqlite3.OperationalError("temporary startup error")
    error.sqlite_errorcode = code

    def fail_connection(*args, **kwargs):
        raise error

    monkeypatch.setattr(storage.sqlite3, "connect", fail_connection)
    monkeypatch.setattr(
        storage,
        "delete_log_storage",
        lambda *args: pytest.fail("deleted DB on temporary error"),
    )
    with pytest.raises(sqlite3.OperationalError):
        storage._reset_log_storage_if_schema_mismatched(db)
    assert db.read_bytes() == b"keep the database"


def test_actual_corruption_can_be_reset(tmp_path, monkeypatch):
    db = tmp_path / "broken.db"
    db.write_bytes(b"This is not a SQLite database")
    monkeypatch.setattr(storage, "get_log_dir", lambda: tmp_path / "logs")
    storage._reset_log_storage_if_schema_mismatched(db)
    assert not db.exists()


def test_normal_matching_schema_preserves_rows(tmp_path):
    db = tmp_path / "logs" / "valid.db"
    with storage._get_init_connection(db) as conn:
        conn.execute("CREATE TABLE marker (message TEXT)")
        conn.execute("INSERT INTO marker VALUES ('preserved')")
        conn.execute(f"PRAGMA user_version = {storage.LOG_VER}")
    with storage._get_init_connection(db) as conn:
        assert conn.execute("SELECT message FROM marker").fetchall() == [("preserved",)]

import base64
import json
import threading
import uuid
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

import pytest

from atopile.telemetry import telemetry
from atopile.telemetry.client import PH_API_HOST, TelemetryClient
from atopile.telemetry.config import TelemetryConfig
from atopile.telemetry.properties import PropertyLoaders, _normalize_git_remote_url


def _access_token(subject: str, email: str | None = None) -> str:
    claims = {"sub": subject}
    if email:
        claims["email"] = email
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


@pytest.mark.parametrize(
    ("git_remote",),
    [
        ("https://github.com/atopile/atopile.git",),
        ("git@github.com:atopile/atopile.git",),
    ],
)
def test_normalize_git_remote_url(git_remote):
    assert _normalize_git_remote_url(git_remote) == "github.com/atopile/atopile"


def test_capture_event():
    @telemetry.capture(
        "test_start",
        "test_end",
        {"test_property": "test_value"},
    )
    def test_capture_event():
        pass

    test_capture_event()


def test_capture_exception():
    try:
        raise Exception("test_exception")
    except Exception as e:
        telemetry.capture_exception(e, {"test_property": "test_value"})


def test_telemetry_worker_starts_lazily(monkeypatch):
    monkeypatch.setattr(telemetry.atexit, "register", lambda _: None)
    monkeypatch.setattr(
        telemetry.TelemetryConfig,
        "load",
        lambda: TelemetryConfig(telemetry=True, id=uuid.uuid4()),
    )
    monkeypatch.setattr(
        telemetry,
        "TelemetryProperties",
        lambda thin: type("FakeTelemetryProperties", (), {"dump": lambda self: {}})(),
    )
    processed = threading.Event()

    class FakeClient:
        def capture(self, *args, **kwargs):
            processed.set()

        def capture_exception(self, *args, **kwargs):
            processed.set()

        def close(self):
            pass

    monkeypatch.setattr(telemetry, "TelemetryClient", FakeClient)

    t = telemetry.Telemetry()
    assert t._worker is None

    t.capture("test_event", telemetry.ThinProperties(extra={"x": 1}))

    assert processed.wait(timeout=1.0)
    assert t._worker is not None
    t.flush()


def test_telemetry_sends_logged_in_user_id(monkeypatch):
    installation_id = uuid.uuid4()
    sent: dict[str, object] = {}
    processed = threading.Event()

    monkeypatch.setattr(telemetry.atexit, "register", lambda _: None)
    monkeypatch.setattr(
        telemetry.TelemetryConfig,
        "load",
        lambda: TelemetryConfig(telemetry=True, id=installation_id),
    )
    monkeypatch.setattr(
        telemetry,
        "TelemetryProperties",
        lambda thin: type(
            "FakeTelemetryProperties",
            (),
            {"dump": lambda self: {"email": "spoofed@example.com"}},
        )(),
    )
    monkeypatch.setattr(
        telemetry,
        "get_auth_token",
        lambda: _access_token("user_logged_in", "user@example.com"),
    )

    class FakeClient:
        def capture(self, *args, **kwargs):
            sent.update(kwargs)
            processed.set()

        def capture_exception(self, *args, **kwargs):
            sent.update(kwargs)
            processed.set()

        def close(self):
            pass

    monkeypatch.setattr(telemetry, "TelemetryClient", FakeClient)

    t = telemetry.Telemetry()
    t.capture("test_event", telemetry.ThinProperties(extra={"x": 1}))

    assert processed.wait(timeout=1.0)
    assert sent["distinct_id"] == "user_logged_in"
    assert sent["properties"]["email"] == "user@example.com"
    t.flush()


def test_telemetry_reads_email_from_stored_session(monkeypatch):
    user = type(
        "StoredUser",
        (),
        {"id": "user_logged_in", "email": "stored@example.com"},
    )()
    session = type("StoredSession", (), {"user": user})()
    monkeypatch.setattr(
        telemetry, "get_auth_token", lambda: _access_token("user_logged_in")
    )
    monkeypatch.setattr(telemetry, "load_stored_session", lambda: session)

    assert telemetry._logged_in_identity() == (
        "user_logged_in",
        "stored@example.com",
    )


def test_telemetry_uses_anonymous_id_when_signed_out(monkeypatch):
    installation_id = uuid.uuid4()
    monkeypatch.setattr(telemetry, "get_auth_token", lambda: None)

    assert telemetry._logged_in_user_id() is None

    monkeypatch.setattr(telemetry.atexit, "register", lambda _: None)
    monkeypatch.setattr(
        telemetry.TelemetryConfig,
        "load",
        lambda: TelemetryConfig(telemetry=True, id=installation_id),
    )
    t = telemetry.Telemetry()
    t._ensure_worker_started = MagicMock()
    t.capture("test_event", telemetry.ThinProperties(extra={"x": 1}))

    queued = t._queue.get_nowait()
    assert queued.distinct_id == installation_id
    assert queued.email is None


def test_telemetry_sends_git_email_when_signed_out(monkeypatch):
    installation_id = uuid.uuid4()
    sent: dict[str, object] = {}
    processed = threading.Event()

    monkeypatch.setattr(telemetry.atexit, "register", lambda _: None)
    monkeypatch.setattr(
        telemetry.TelemetryConfig,
        "load",
        lambda: TelemetryConfig(telemetry=True, id=installation_id),
    )
    monkeypatch.setattr(telemetry, "get_auth_token", lambda: None)
    monkeypatch.setattr(telemetry.PropertyLoaders, "email", lambda: "git@example.com")
    monkeypatch.setattr(
        telemetry,
        "TelemetryProperties",
        lambda thin: type(
            "FakeTelemetryProperties",
            (),
            {"dump": lambda self: {"email": "spoofed@example.com"}},
        )(),
    )

    class FakeClient:
        def capture(self, *args, **kwargs):
            sent.update(kwargs)
            processed.set()

        def capture_exception(self, *args, **kwargs):
            sent.update(kwargs)
            processed.set()

        def close(self):
            pass

    monkeypatch.setattr(telemetry, "TelemetryClient", FakeClient)

    t = telemetry.Telemetry()
    t.capture("test_event", telemetry.ThinProperties(extra={"x": 1}))

    assert processed.wait(timeout=1.0)
    assert sent["distinct_id"] == installation_id
    assert sent["properties"]["email"] == "git@example.com"
    t.flush()


def test_telemetry_client_uses_local_service_url(monkeypatch):
    monkeypatch.setenv("ATO_SERVICES_TELEMETRY_URL", "http://127.0.0.1:4318/")
    with patch("atopile.telemetry.client.http_client") as http_client:
        client = TelemetryClient()
        assert client._url == "http://127.0.0.1:4318/capture/"
        client.close()
    assert http_client.call_count == 1

    monkeypatch.delenv("ATO_SERVICES_TELEMETRY_URL")
    with patch("atopile.telemetry.client.http_client"):
        client = TelemetryClient()
    assert client._url == f"{PH_API_HOST}/capture/"


def test_flush_without_started_worker_is_noop(monkeypatch):
    monkeypatch.setattr(telemetry.atexit, "register", lambda _: None)
    monkeypatch.setattr(
        telemetry.TelemetryConfig,
        "load",
        lambda: TelemetryConfig(telemetry=True, id=uuid.uuid4()),
    )

    t = telemetry.Telemetry()

    assert t._worker is None
    t.flush()
    assert t._shutdown.is_set()


def test_capture_degrades_when_worker_start_fails(monkeypatch):
    monkeypatch.setattr(telemetry.atexit, "register", lambda _: None)
    monkeypatch.setattr(
        telemetry.TelemetryConfig,
        "load",
        lambda: TelemetryConfig(telemetry=True, id=uuid.uuid4()),
    )

    t = telemetry.Telemetry()
    monkeypatch.setattr(
        t,
        "_ensure_worker_started",
        lambda: (_ for _ in ()).throw(RuntimeError("thread start failed")),
    )

    t.capture("test_event", telemetry.ThinProperties(extra={"x": 1}))

    assert t._worker is None


# ── install_method detection tests ────────────────────


def _clear_install_method_cache():
    PropertyLoaders.install_method.cache.clear()


def _mock_dist(path_str, direct_url_json=None):
    """Create a mock distribution with a given path and optional direct_url.json."""
    dist = MagicMock()
    dist._path = PurePosixPath(path_str)
    dist.read_text = lambda name: direct_url_json if name == "direct_url.json" else None
    return dist


def test_install_method_playground(monkeypatch):
    _clear_install_method_cache()
    monkeypatch.setenv("ATO_PLAYGROUND", "1")
    monkeypatch.delenv("ATO_VIA_DOCKER", raising=False)
    assert PropertyLoaders.install_method() == "playground"


def test_install_method_docker(monkeypatch):
    _clear_install_method_cache()
    monkeypatch.delenv("ATO_PLAYGROUND", raising=False)
    monkeypatch.setenv("ATO_VIA_DOCKER", "1")
    assert PropertyLoaders.install_method() == "docker"


def test_install_method_dev(monkeypatch):
    _clear_install_method_cache()
    monkeypatch.delenv("ATO_VIA_DOCKER", raising=False)
    monkeypatch.delenv("ATO_PLAYGROUND", raising=False)
    dist = _mock_dist(
        "/home/user/code/atopile/.venv/lib/python3.14/site-packages/atopile-0.14.dist-info",
        '{"url":"file:///home/user/code/atopile","dir_info":{"editable":true}}',
    )
    with patch("importlib.metadata.distribution", return_value=dist):
        assert PropertyLoaders.install_method() == "dev"


def test_install_method_vsce_managed(monkeypatch):
    _clear_install_method_cache()
    monkeypatch.delenv("ATO_VIA_DOCKER", raising=False)
    monkeypatch.delenv("ATO_PLAYGROUND", raising=False)
    dist = _mock_dist(
        "/home/user/.vscode-server/data/User/globalStorage/atopile.atopile/uv/cache/atopile-0.14.dist-info",
    )
    with patch("importlib.metadata.distribution", return_value=dist):
        assert PropertyLoaders.install_method() == "vsce-managed"


def test_install_method_uv_tool(monkeypatch):
    _clear_install_method_cache()
    monkeypatch.delenv("ATO_VIA_DOCKER", raising=False)
    monkeypatch.delenv("ATO_PLAYGROUND", raising=False)
    dist = _mock_dist(
        "/home/user/.local/share/uv/tools/atopile/lib/python3.14/site-packages/atopile-0.14.dist-info",
    )
    with patch("importlib.metadata.distribution", return_value=dist):
        assert PropertyLoaders.install_method() == "uv-tool"


def test_install_method_brew(monkeypatch):
    _clear_install_method_cache()
    monkeypatch.delenv("ATO_VIA_DOCKER", raising=False)
    monkeypatch.delenv("ATO_PLAYGROUND", raising=False)
    dist = _mock_dist(
        "/opt/homebrew/Cellar/atopile/0.14/lib/python3.14/site-packages/atopile-0.14.dist-info",
    )
    with patch("importlib.metadata.distribution", return_value=dist):
        assert PropertyLoaders.install_method() == "brew"


def test_install_method_pipx(monkeypatch):
    _clear_install_method_cache()
    monkeypatch.delenv("ATO_VIA_DOCKER", raising=False)
    monkeypatch.delenv("ATO_PLAYGROUND", raising=False)
    dist = _mock_dist(
        "/home/user/.local/pipx/venvs/atopile/lib/python3.14/site-packages/atopile-0.14.dist-info",
    )
    with patch("importlib.metadata.distribution", return_value=dist):
        assert PropertyLoaders.install_method() == "pipx"


def test_install_method_pip_fallback(monkeypatch):
    _clear_install_method_cache()
    monkeypatch.delenv("ATO_VIA_DOCKER", raising=False)
    monkeypatch.delenv("ATO_PLAYGROUND", raising=False)
    dist = _mock_dist(
        "/home/user/myproject/.venv/lib/python3.14/site-packages/atopile-0.14.dist-info",
    )
    with patch("importlib.metadata.distribution", return_value=dist):
        assert PropertyLoaders.install_method() == "pip"


def test_install_method_vsce_managed_appdata(monkeypatch):
    """Test VSCE detection with a Windows-style AppData path (forward slashes)."""
    _clear_install_method_cache()
    monkeypatch.delenv("ATO_VIA_DOCKER", raising=False)
    monkeypatch.delenv("ATO_PLAYGROUND", raising=False)
    dist = _mock_dist(
        "C:/Users/user/AppData/Roaming/Code/User/globalStorage/atopile.atopile/uv/cache/atopile-0.14.dist-info",
    )
    with patch("importlib.metadata.distribution", return_value=dist):
        assert PropertyLoaders.install_method() == "vsce-managed"

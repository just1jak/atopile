from types import SimpleNamespace

import pytest

from atopile.cli import motd


class _Response:
    def __init__(self, message: str):
        self._message = message

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"message": self._message}


@pytest.fixture(autouse=True)
def reset_motd() -> None:
    motd._shown = False


def test_motd_is_logged_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls = 0

    def get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Response("Please migrate")

    monkeypatch.setattr(
        motd,
        "config",
        SimpleNamespace(
            project=SimpleNamespace(
                services=SimpleNamespace(
                    components=SimpleNamespace(url="http://legacy.example.com")
                )
            )
        ),
    )
    monkeypatch.setattr(motd.httpx, "get", get)

    with caplog.at_level("WARNING"):
        motd.maybe_show_motd()
        motd.maybe_show_motd()

    assert calls == 1
    assert "Please migrate" in caplog.text


def test_motd_failure_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        motd,
        "config",
        SimpleNamespace(
            project=SimpleNamespace(
                services=SimpleNamespace(
                    components=SimpleNamespace(url="http://legacy.example.com")
                )
            )
        ),
    )
    monkeypatch.setattr(
        motd.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")),
    )

    motd.maybe_show_motd()

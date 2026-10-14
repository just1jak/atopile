import pytest

from atopile.errors import UserException
from faebryk.libs.picker.api import api


def test_picker_requires_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "get_auth_token", lambda: None)

    with pytest.raises(UserException, match="ato auth login"):
        _ = api.ApiClient()._cfg


def test_picker_uses_login_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "get_auth_token", lambda: "clerk-access-token")

    client = api.ApiClient()

    assert client._cfg.api_key == "clerk-access-token"
    assert client._headers["Authorization"] == "Bearer clerk-access-token"

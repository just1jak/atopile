"""Direct provider routing and persistence tests; no live AI requests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from atopile.agent import gateway
from atopile.agent.local_config import (
    direct_config,
    local_mode_enabled,
    public_local_config,
)
from atopile.agent.providers import make_provider
from atopile.agent.providers.anthropic import AnthropicProvider, _build_payload
from atopile.agent.providers.base import ModelId
from atopile.agent.providers.openai import OpenAIProvider
from atopile.agent.session import Agent
from atopile.agent.skills import load_skill
from atopile.agent.tools.websearch import _exa_search
from atopile.auth import runtime as auth_runtime
from atopile.auth import session as auth_session


@pytest.fixture(autouse=True)
def isolated_ai_environment(monkeypatch):
    for name in (
        "ATOPILE_LOCAL_MODE",
        "ATOPILE_AGENT_PROVIDER",
        "ATOPILE_AGENT_MODEL",
        "ATOPILE_AGENT_BASE_URL",
        "ATOPILE_AGENT_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ATOPILE_AGENT_OPENAI_API_KEY",
        "ATOPILE_AGENT_ANTHROPIC_API_KEY",
        "EXA_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    # These tests cover direct API routing; Codex is the product default.
    monkeypatch.setenv("ATOPILE_AGENT_PROVIDER", "openai")
    gateway._direct_openai_clients.clear()
    gateway._direct_anthropic_clients.clear()
    gateway._openai_clients.clear()
    gateway._anthropic_clients.clear()


def test_default_missing_key_never_falls_back_to_hosted(monkeypatch):
    assert local_mode_enabled()
    monkeypatch.setattr(gateway, "get_auth_token", lambda: pytest.fail("hosted lookup"))
    with pytest.raises(RuntimeError, match="your own AI key"):
        gateway.openai_client()


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_direct_clients_use_own_key_and_url_without_bearer(monkeypatch, provider):
    monkeypatch.setenv("ATOPILE_AGENT_PROVIDER", provider)
    monkeypatch.setenv("ATOPILE_AGENT_API_KEY", "test-direct-key")
    monkeypatch.setenv("ATOPILE_AGENT_BASE_URL", "https://inference.example/v1")
    monkeypatch.setattr(gateway, "get_auth_token", lambda: pytest.fail("hosted lookup"))
    calls = []
    marker = object()

    def fake_client(**kwargs):
        calls.append(kwargs)
        return marker

    monkeypatch.setattr(
        gateway,
        "AsyncOpenAI" if provider == "openai" else "AsyncAnthropic",
        fake_client,
    )
    create = gateway.openai_client if provider == "openai" else gateway.anthropic_client
    assert create() is marker
    assert create() is marker
    assert calls == [
        {
            "api_key": "test-direct-key",
            "base_url": "https://inference.example/v1",
            "timeout": 120.0,
        }
    ]


def test_hosted_mode_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "0")
    monkeypatch.setattr(gateway, "get_auth_token", lambda: "test-hosted-token")
    calls = []
    monkeypatch.setattr(
        gateway, "AsyncOpenAI", lambda **kwargs: calls.append(kwargs) or object()
    )
    gateway.openai_client()
    assert calls[0]["base_url"] == gateway.OPENAI_BASE_URL
    assert calls[0]["api_key"] == "gateway"
    assert calls[0]["default_headers"] == {"Authorization": "Bearer test-hosted-token"}


def test_loopback_can_use_no_key_and_status_does_not_claim_key(monkeypatch):
    monkeypatch.setenv("ATOPILE_AGENT_BASE_URL", "http://127.0.0.1:1234/v1")
    assert direct_config().client_key() == "local-no-key"
    assert public_local_config()["keyConfigured"] is False
    assert public_local_config()["ready"] is True


def test_status_and_config_repr_redact_credentials(monkeypatch):
    monkeypatch.setenv("ATOPILE_AGENT_API_KEY", "secret-test-value")
    assert "secret-test-value" not in repr(direct_config())
    assert "secret-test-value" not in repr(public_local_config())


def test_vendor_fallback_key_is_not_reused_for_other_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    assert direct_config("openai").api_key is None
    assert direct_config("anthropic").api_key == "test-anthropic"


@pytest.mark.parametrize(
    "url",
    [
        "https://gateway.atopile.io/openai/v1",
        "https://user:secret@inference.example/v1",
        "https://inference.example/v1?api_key=secret",
        "file:///tmp/model",
    ],
)
def test_unsafe_or_hosted_local_endpoint_rejected(monkeypatch, url):
    monkeypatch.setenv("ATOPILE_AGENT_BASE_URL", url)
    with pytest.raises(ValueError):
        direct_config()


def test_custom_model_routes_to_configured_provider(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ATOPILE_AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ATOPILE_AGENT_MODEL", "my-custom-model:latest")
    agent = Agent()
    session = agent.create_session(tmp_path)
    assert session.model.value == "my-custom-model:latest"
    assert isinstance(session._provider, AnthropicProvider)
    payload = _build_payload(
        model=session.model,
        instructions="",
        messages=[],
        tools=None,
        max_output_tokens=128,
    )
    assert payload["model"] == "my-custom-model:latest"
    assert "thinking" not in payload
    assert "extra_headers" not in payload


def test_direct_openai_factory_and_model_override(monkeypatch):
    monkeypatch.setenv("ATOPILE_AGENT_MODEL", "local/model:8b")
    provider = make_provider(ModelId.CLAUDE_OPUS_4_7)
    assert isinstance(provider, OpenAIProvider)
    assert provider.model.value == "local/model:8b"


def test_local_title_generation_makes_no_provider_calls(monkeypatch, tmp_path: Path):
    agent = Agent()
    session = agent.create_session(tmp_path)
    monkeypatch.setattr(
        OpenAIProvider, "complete", lambda **kwargs: pytest.fail("hidden title request")
    )
    assert (
        asyncio.run(agent.generate_title("Build a motor controller"))
        == "Build a motor controller"
    )
    assert (
        asyncio.run(session.generate_title("Build a motor controller"))
        == "Build a motor controller"
    )


def test_hosted_saved_response_chain_is_discarded_in_local_mode(tmp_path: Path):
    agent = Agent()
    session = agent.create_session(tmp_path)
    row = session.snapshot()
    row["provider_state"] = {
        "provider": "openai",
        "last_response_id": "hosted-response",
    }
    restored = agent._restore_session(row)
    assert restored._provider._last_response_id is None


def test_local_chain_only_restored_for_same_endpoint(monkeypatch, tmp_path: Path):
    agent = Agent()
    session = agent.create_session(tmp_path)
    session._provider._last_response_id = "local-response"
    row = session.snapshot()
    assert agent._restore_session(row)._provider._last_response_id == "local-response"
    monkeypatch.setenv("ATOPILE_AGENT_BASE_URL", "https://other-inference.example/v1")
    assert agent._restore_session(row)._provider._last_response_id is None


def test_local_chain_is_not_reused_with_different_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("ATOPILE_AGENT_API_KEY", "first-account-test")
    agent = Agent()
    session = agent.create_session(tmp_path)
    session._provider._last_response_id = "first-account-response"
    row = session.snapshot()
    assert "first-account-test" not in repr(row)
    monkeypatch.setenv("ATOPILE_AGENT_API_KEY", "second-account-test")
    assert agent._restore_session(row)._provider._last_response_id is None


def test_fresh_local_auth_never_reads_upstream_keychain_or_refreshes(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(auth_session, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(
        auth_session.keyring, "get_keyring", lambda: pytest.fail("upstream keychain")
    )
    monkeypatch.setattr(
        auth_session, "refresh_session", lambda *args: pytest.fail("upstream refresh")
    )
    (tmp_path / auth_session.FILE_SESSION_NAME).write_text("existing-upstream-session")
    auth_runtime.set_auth_token(None)
    assert auth_session._storage_backend() == "file"
    assert auth_session._file_session_path().name == "local_clerk_oauth_session.json"
    assert auth_session.get_valid_stored_session() is None
    assert auth_runtime.get_auth_token() is None


def test_fork_auth_remains_isolated_when_hosted_ai_is_opted_in(monkeypatch, tmp_path):
    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "0")
    monkeypatch.setenv("ATOPILE_LOCAL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(auth_session, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(
        auth_session.keyring, "get_keyring", lambda: pytest.fail("upstream keychain")
    )
    assert auth_session._storage_backend() == "file"
    assert auth_session.KEYRING_SERVICE_NAME != "atopile.clerkOauth"
    assert auth_session._file_session_path().name == "local_clerk_oauth_session.json"


def test_local_search_without_own_key_never_uses_gateway(monkeypatch):
    monkeypatch.setattr(gateway, "http_headers", lambda: pytest.fail("hosted lookup"))
    with pytest.raises(RuntimeError, match="EXA_API_KEY"):
        _exa_search(query="resistor datasheet", num_results=1)


def test_default_skills_are_packaged_and_path_traversal_rejected():
    assert "Core Behavior" in load_skill("agent")
    assert len(load_skill("ato-language")) > 1000
    with pytest.raises(ValueError):
        load_skill("../session")

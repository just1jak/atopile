"""Verify direct routing with the actual SDKs and intercepted HTTP transport."""
import json

import httpx2 as sdk_httpx
import pytest

from atopile.agent import gateway
from atopile.agent.providers.anthropic import AnthropicProvider
from atopile.agent.providers.base import ModelId
from atopile.agent.providers.openai import OpenAIProvider


@pytest.mark.asyncio
@pytest.mark.parametrize("vendor", ["openai", "anthropic"])
async def test_actual_sdk_calls_only_configured_endpoint(monkeypatch, vendor):
    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "1")
    monkeypatch.setenv("ATOPILE_AGENT_PROVIDER", vendor)
    monkeypatch.setenv("ATOPILE_AGENT_MODEL", "local-test-model")
    monkeypatch.setenv("ATOPILE_AGENT_API_KEY", "fake-test-key")
    monkeypatch.setenv("ATOPILE_AGENT_BASE_URL", "https://local-provider.example/v1" if vendor == "openai" else "https://local-provider.example")
    monkeypatch.setattr(gateway, "get_auth_token", lambda: pytest.fail("Atopile auth was consulted"))
    gateway._direct_openai_clients.clear()
    gateway._direct_anthropic_clients.clear()
    if vendor == "openai":
        provider = OpenAIProvider(ModelId("local-test-model"))
        endpoint = "https://local-provider.example/v1/responses"
        payload = {
            "id": "resp_local", "object": "response", "created_at": 0,
            "status": "completed", "model": "local-test-model",
            "output": [{"id": "msg_local", "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "Local endpoint works", "annotations": []}]}],
            "tools": [], "parallel_tool_calls": True,
            "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5, "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
        }
    else:
        provider = AnthropicProvider(ModelId("local-test-model"))
        endpoint = "https://local-provider.example/v1/messages"
        payload = {"id": "msg_local", "type": "message", "role": "assistant", "model": "local-test-model", "content": [{"type": "text", "text": "Local endpoint works"}], "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 2, "output_tokens": 3}}
    requests = []

    def transport(request):
        assert str(request.url) == endpoint
        requests.append(request)
        return sdk_httpx.Response(200, json=payload)

    factory_name = "AsyncOpenAI" if vendor == "openai" else "AsyncAnthropic"
    real_factory = getattr(gateway, factory_name)
    monkeypatch.setattr(gateway, factory_name, lambda **kwargs: real_factory(
        http_client=sdk_httpx.AsyncClient(transport=sdk_httpx.MockTransport(transport)), **kwargs))
    response = await provider.complete(messages=[{"role": "user", "content": "Test direct circuit assistant"}], instructions="Use local circuit tools.")
    assert response.text == "Local endpoint works"
    assert len(requests) == 1
    request = requests[0]
    assert json.loads(request.content)["model"] == "local-test-model"
    if vendor == "openai":
        assert request.headers["authorization"] == "Bearer fake-test-key"
    else:
        assert request.headers["x-api-key"] == "fake-test-key"
    clients = gateway._direct_openai_clients if vendor == "openai" else gateway._direct_anthropic_clients
    for client in clients.values():
        await client.close()
    clients.clear()

# ruff: noqa: F401
"""Providers subpackage — LLM provider abstraction."""

from atopile.agent.local_config import (
    configured_model,
    configured_provider,
    local_mode_enabled,
)
from atopile.agent.providers.anthropic import AnthropicProvider
from atopile.agent.providers.codex import CodexProvider
from atopile.agent.providers.base import (
    LLMProvider,
    LLMResponse,
    ModelId,
    StreamDone,
    StreamEvent,
    StreamTextDelta,
    StreamToolCallDelta,
    StreamToolCallStart,
    TokenUsage,
    ToolCall,
)
from atopile.agent.providers.openai import OpenAIProvider


def resolve_model(model: ModelId) -> ModelId:
    """The local settings take precedence over the legacy fixed UI picker."""
    if local_mode_enabled():
        return ModelId(configured_model())
    if model not in list(ModelId):
        raise ValueError("Custom models require local mode")
    return model


def make_provider(model: ModelId, *, timeout: float = 120.0) -> LLMProvider:
    """Construct the right provider for ``model``."""
    model = resolve_model(model)
    kind = configured_provider() if local_mode_enabled() else model.provider_kind
    if kind == "codex":
        return CodexProvider(model=model, timeout=timeout)
    if kind == "anthropic":
        return AnthropicProvider(model=model, timeout=timeout)
    return OpenAIProvider(model=model, timeout=timeout)

"""Direct AI configuration for the local fork; hosted access is opt-in."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

ProviderKind = Literal["openai", "anthropic", "codex"]


def local_mode_enabled() -> bool:
    """Default to direct providers, even if no credentials have been set."""
    return os.getenv("ATOPILE_LOCAL_MODE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def configured_provider() -> ProviderKind:
    value = os.getenv("ATOPILE_AGENT_PROVIDER", "codex").strip().lower()
    if value not in {"openai", "anthropic", "codex"}:
        raise ValueError("ATOPILE_AGENT_PROVIDER must be codex, openai or anthropic")
    return value  # type: ignore[return-value]


def configured_model() -> str:
    value = os.getenv("ATOPILE_AGENT_MODEL", "").strip()
    if value:
        return value
    if configured_provider() == "codex":
        return "codex-default"
    return "claude-sonnet-4-6" if configured_provider() == "anthropic" else "gpt-5.4"


@dataclass(frozen=True)
class DirectProviderConfig:
    provider: ProviderKind
    model: str
    base_url: str
    api_key: str | None = field(repr=False)

    @property
    def is_loopback(self) -> bool:
        return urlsplit(self.base_url).hostname in {"localhost", "127.0.0.1", "::1"}

    def client_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.is_loopback:
            # SDKs insist on a key even when a local inference server does not.
            return "local-no-key"
        env_name = (
            "OPENAI_API_KEY" if self.provider == "openai" else "ANTHROPIC_API_KEY"
        )
        raise RuntimeError(
            f"Configure your own AI key in Atopile Local settings, "
            f"ATOPILE_AGENT_API_KEY, or {env_name}. "
            "Local mode does not use atopile sign-in or credits."
        )

    @property
    def credential_id(self) -> str:
        """Identify saved provider state without storing the credential itself."""
        return hashlib.sha256((self.api_key or "local-no-key").encode()).hexdigest()


def direct_config(provider: ProviderKind | None = None) -> DirectProviderConfig:
    selected = provider or configured_provider()
    if selected == "codex":
        raise ValueError(
            "Codex uses its native ChatGPT login, not direct API credentials."
        )
    default_url = (
        "https://api.openai.com/v1"
        if selected == "openai"
        else "https://api.anthropic.com"
    )
    base_url = os.getenv("ATOPILE_AGENT_BASE_URL", "").strip() or default_url
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("ATOPILE_AGENT_BASE_URL must be an http or https API URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            "AI base URL must not contain credentials, a query, or a fragment"
        )
    if parsed.hostname == "gateway.atopile.io":
        raise ValueError(
            "Local mode cannot use the atopile gateway. Configure a direct provider "
            "URL, or explicitly opt into hosted mode with ATOPILE_LOCAL_MODE=0."
        )
    # A secret for one vendor must never be used for another vendor's fallback.
    standard_key = "OPENAI_API_KEY" if selected == "openai" else "ANTHROPIC_API_KEY"
    vendor_key = f"ATOPILE_AGENT_{selected.upper()}_API_KEY"
    api_key = (
        os.getenv("ATOPILE_AGENT_API_KEY")
        or os.getenv(vendor_key)
        or os.getenv(standard_key)
        or None
    )
    return DirectProviderConfig(
        selected, configured_model(), base_url.rstrip("/"), api_key
    )


def public_local_config() -> dict[str, object]:
    """Safe metadata for UI consumers; contains no credential values."""
    if configured_provider() == "codex":
        return {
            "local": local_mode_enabled(),
            "provider": "codex",
            "model": configured_model(),
            "baseURL": "",
            "keyConfigured": False,
            "ready": True,
        }
    config = direct_config()
    return {
        "local": local_mode_enabled(),
        "provider": config.provider,
        "model": config.model,
        "baseURL": config.base_url,
        "keyConfigured": bool(config.api_key),
        "ready": bool(config.api_key) or config.is_loopback,
    }


def local_title(message: str) -> str:
    """Generate a useful title without a hidden utility-model request."""
    title = " ".join(message.split())
    return title[:77].rstrip() + "..." if len(title) > 80 else title or "New circuit"

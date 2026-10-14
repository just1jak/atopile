"""Best-effort migration message from the pre-0.16 compatibility service."""

from __future__ import annotations

import logging
import os

import httpx

from atopile.config import config

logger = logging.getLogger(__name__)

_shown = False


def maybe_show_motd() -> None:
    """Log the compatibility service's MOTD at most once per process.

    The message is advisory for 0.15.8. Network or response failures must not
    prevent an otherwise valid command from running.
    """
    if os.getenv("ATOPILE_LOCAL_MODE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return

    global _shown
    if _shown:
        return
    _shown = True

    try:
        url = config.project.services.components.url.rstrip("/") + "/v0/motd"
        response = httpx.get(
            url,
            headers={"User-Agent": "atopile/0.15.8"},
            timeout=3.0,
        )
        response.raise_for_status()
        message = response.json().get("message")
        if isinstance(message, str) and message.strip():
            logger.warning("%s", message.strip())
    except Exception:
        logger.debug("Legacy compatibility MOTD unavailable", exc_info=True)

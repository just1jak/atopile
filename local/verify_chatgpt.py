"""Optional live smoke test. Uses a small amount of the signed-in ChatGPT plan."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    from atopile.agent.providers import make_provider, resolve_model
    from atopile.agent.providers.base import ModelId
    from atopile.agent.session import AgentSession, Done
    from atopile.agent.tools.layout import layout_get_netlist
    from atopile.agent.tools.registry import ToolRegistry

    if os.environ.get("ATOPILE_AGENT_PROVIDER", "codex") != "codex":
        raise RuntimeError("This check requires the ChatGPT (Codex) provider")
    registry = ToolRegistry()
    registry.register(layout_get_netlist._tool_def)
    model = resolve_model(ModelId.GPT_5_4)
    provider = make_provider(model)
    session = AgentSession(
        session_id="chatgpt-connection-verification",
        project_root=ROOT / "examples/offline-indicator",
        provider=provider,
        model=model,
        registry=registry,
        skill_ids=[],
        max_tool_loops=4,
        max_turn_seconds=120,
    )
    try:
        result = None
        async with asyncio.timeout(180):
            async for event in session.send_message(
                "Read the demo PCB using layout_get_netlist with target default. "
                "Report its net names and the unique component references from "
                "that tool's actual result in one sentence. Do not edit anything."
            ):
                if isinstance(event, Done):
                    result = event
        if result is None or not result.text or not result.traces:
            raise AssertionError("ChatGPT did not complete a circuit tool round trip")
        trace = result.traces[0]
        if trace.name != "layout_get_netlist" or not trace.ok:
            raise AssertionError("The local net tool failed")
        print(json.dumps({
            "provider": "codex",
            "auth": "native ChatGPT login; no API key",
            "circuit_tool_round_trip": "passed",
            "tool": trace.name,
            "tool_result": trace.result,
            "answer": result.text,
            "tokens": vars(result.usage),
        }, indent=2))
    finally:
        await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())

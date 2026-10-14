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
    from atopile.agent.tools import create_registry

    if os.environ.get("ATOPILE_AGENT_PROVIDER", "codex") != "codex":
        raise RuntimeError("This check requires the ChatGPT (Codex) provider")
    # Exercise production discovery: a one-tool catalog bypasses the bridge
    # that current Codex models use for the complete agent registry.
    registry = create_registry()
    execute = registry.execute
    blocked = []
    allowed = {"layout_get_summary", "layout_get_netlist"}

    async def read_only_execute(name, args, scope):
        if name not in allowed:
            blocked.append(name)
            raise RuntimeError("This diagnostic only allows summary and netlist reads")
        return await execute(name, args, scope)

    registry.execute = read_only_execute
    model = resolve_model(ModelId("codex-default"))
    provider = make_provider(model)
    session = AgentSession(
        session_id="chatgpt-connection-verification",
        project_root=ROOT / "examples/offline-indicator",
        provider=provider,
        model=model,
        registry=registry,
        skill_ids=["agent", "ato-language"],
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
        trace = next((t for t in result.traces if t.name == "layout_get_netlist"), None)
        if trace is None or not trace.ok or blocked:
            raise AssertionError("The local net tool failed")
        print(json.dumps({
            "provider": "codex",
            "auth": "native ChatGPT login; no API key",
            "circuit_tool_round_trip": "passed",
            "full_production_tool_catalog": True,
            "tool": trace.name,
            "tool_result": trace.result,
            "answer": result.text,
            "tokens": vars(result.usage),
        }, indent=2))
    finally:
        await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())

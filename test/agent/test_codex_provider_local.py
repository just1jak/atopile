"""Deterministic protocol tests; no login, model requests, or credentials used."""

import asyncio
import json
from pathlib import Path

import pytest

from atopile.agent.providers.base import ModelId, StreamDone
from atopile.agent.providers.codex import (
    CodexProvider,
    codex_environment,
    tool_catalog_fingerprint,
    migration_history,
    MIGRATION_HISTORY_CHARS,
    MIGRATION_MESSAGE_CHARS,
)

TOOL = {
    "type": "function",
    "name": "layout_get_netlist",
    "description": "Read nets",
    "parameters": {"type": "object"},
}


def test_app_server_keeps_dynamic_tool_bridge_running_without_native_access(
    monkeypatch,
):
    """A real model discovers this registry via exec, before any tool/call RPC."""
    import json
    from types import SimpleNamespace
    from atopile.agent.providers import codex

    async def scenario():
        captured = []
        stderr = asyncio.StreamReader()
        stderr.feed_eof()

        async def spawn(*args, **kwargs):
            captured.extend(args)
            return SimpleNamespace(returncode=0, stderr=stderr)

        monkeypatch.setattr(codex, "codex_executable", lambda: "codex")
        monkeypatch.setattr(codex.asyncio, "create_subprocess_exec", spawn)
        server = codex.StdioAppServer()
        try:
            await server.start()
            config = dict(
                value.split("=", 1)
                for index, value in enumerate(captured)
                if index and captured[index - 1] == "-c"
            )
            assert json.loads(config["features.code_mode_host"]) is True
            assert json.loads(config["features.code_mode"]) is False
            assert json.loads(config["features.shell_tool"]) is False
            assert json.loads(config["features.unified_exec"]) is False
            assert json.loads(config["features.apps"]) is False
            assert json.loads(config["features.plugins"]) is False
            assert json.loads(config["features.browser_use"]) is False
            assert json.loads(config["forced_login_method"]) == "chatgpt"
        finally:
            await server.close()

    asyncio.run(scenario())


class FakeServer:
    def __init__(self, account="chatgpt", mcp_status="disabled"):
        self.queue = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.account = account
        self.mcp_status = mcp_status
        self.turns = 0

    async def start(self):
        pass

    async def close(self):
        self.closed = True

    async def read(self):
        return await self.queue.get()

    async def emit(self, method, params, request_id=None):
        message = {"method": method, "params": params}
        if request_id is not None:
            message["id"] = request_id
        await self.queue.put(message)

    async def usage(self, total):
        await self.emit(
            "thread/tokenUsage/updated",
            {
                "threadId": "thread-1",
                "tokenUsage": {
                    "total": {
                        "inputTokens": total - 10,
                        "outputTokens": 10,
                        "totalTokens": total,
                    },
                    "last": {"inputTokens": 5, "outputTokens": 1, "totalTokens": 6},
                },
            },
        )

    async def send(self, message):
        self.sent.append(message)
        method = message.get("method")
        if method == "initialized":
            return
        if method is None:
            if message.get("id") == 77 and message.get("result", {}).get("success"):
                await self.usage(162)
                await self.emit(
                    "item/agentMessage/delta",
                    {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "delta": "Three nets.",
                    },
                )
                await self.emit(
                    "turn/completed",
                    {
                        "threadId": "thread-1",
                        "turn": {"id": "turn-1", "status": "completed"},
                    },
                )
            return
        result = {}
        if method == "account/read":
            result = {"account": {"type": self.account}}
        elif method == "mcpServerStatus/list":
            scoped = message["params"].get("threadId")
            result = {
                "data": [
                    {
                        "name": "user-server",
                        "runtimeStatus": self.mcp_status if scoped else "ready",
                        "tools": {},
                        "resources": [],
                        "resourceTemplates": [],
                    }
                ]
            }
        elif method in {"thread/start", "thread/resume"}:
            result = {"thread": {"id": "thread-1"}}
            if method == "thread/resume":
                self.turns = 1
        elif method == "turn/start":
            self.turns += 1
            result = {"turn": {"id": f"turn-{self.turns}"}}
        await self.queue.put({"id": message["id"], "result": result})
        if method == "turn/start":
            if self.turns == 1:
                await self.usage(110)
                await self.emit(
                    "item/tool/call",
                    {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "callId": "call-1",
                        "tool": "layout_get_netlist",
                        "arguments": {"target": "default"},
                    },
                    77,
                )
            else:
                # Delayed old completion must not terminate a later turn.
                await self.emit(
                    "turn/completed",
                    {
                        "threadId": "thread-1",
                        "turn": {"id": "turn-1", "status": "interrupted"},
                    },
                )
                await self.usage(200)
                await self.emit(
                    "item/agentMessage/delta",
                    {
                        "threadId": "thread-1",
                        "turnId": f"turn-{self.turns}",
                        "delta": "I remember the nets.",
                    },
                )
                await self.emit(
                    "turn/completed",
                    {
                        "threadId": "thread-1",
                        "turn": {"id": f"turn-{self.turns}", "status": "completed"},
                    },
                )
        elif method == "turn/interrupt":
            await self.emit(
                "turn/completed",
                {
                    "threadId": "thread-1",
                    "turn": {
                        "id": message["params"]["turnId"],
                        "status": "interrupted",
                    },
                },
            )


@pytest.fixture(autouse=True)
def local_mode(monkeypatch):
    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "1")
    monkeypatch.setenv("ATOPILE_AGENT_PROVIDER", "codex")
    monkeypatch.delenv("ATOPILE_AGENT_MODEL", raising=False)


def make(server):
    provider = CodexProvider(
        ModelId("codex-default"), timeout=1, transport_factory=lambda: server
    )
    provider.bind_project(Path.cwd())
    return provider


def test_saved_restored_chat_keeps_its_native_conversation_before_first_turn():
    provider = make(FakeServer())
    provider.restore({"provider": "codex", "thread_id": "saved-conversation"})
    assert provider.snapshot()["thread_id"] == "saved-conversation"


def test_busy_window_resume_keeps_conversation_for_retry():
    class BusyServer(FakeServer):
        async def send(self, message):
            if message.get("method") == "thread/resume":
                self.sent.append(message)
                await self.queue.put(
                    {
                        "id": message["id"],
                        "error": {
                            "message": "thread saved-conversation already has an active writer"
                        },
                    }
                )
                return
            await super().send(message)

    async def scenario():
        server = BusyServer()
        provider = make(server)
        provider.restore(
            {
                "provider": "codex",
                "thread_id": "saved-conversation",
                "tool_catalog_fingerprint": tool_catalog_fingerprint([TOOL]),
            }
        )
        try:
            with pytest.raises(RuntimeError, match="another Atopile Local window"):
                await run(provider, [{"role": "user", "content": "Read the board"}])
            assert provider.snapshot()["thread_id"] == "saved-conversation"
            assert not any(m.get("method") == "thread/start" for m in server.sent)
        finally:
            await provider.aclose()

    asyncio.run(scenario())


async def run(provider, messages, instructions="Read circuit nets"):
    events = [
        event
        async for event in provider.stream(
            messages=messages, instructions=instructions, tools=[TOOL]
        )
    ]
    return next(event.response for event in events if isinstance(event, StreamDone))


def test_scoped_tools_resume_same_turn_updated_skills_and_incremental_usage():
    async def scenario():
        server = FakeServer()
        provider = make(server)
        try:
            first = await run(provider, [{"role": "user", "content": "Read the nets"}])
            assert first.tool_calls[0].name == "layout_get_netlist"
            assert first.usage.total_tokens == 110
            final = await run(
                provider,
                [
                    {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": '{"nets":3}',
                    }
                ],
                "Newly loaded trusted circuit skill",
            )
            assert final.text == "Three nets."
            assert final.usage.total_tokens == 52
            reply = next(message for message in server.sent if message.get("id") == 77)
            assert (
                "Newly loaded trusted circuit skill"
                in reply["result"]["contentItems"][0]["text"]
            )
            followup = await run(
                provider, [{"role": "user", "content": "Remember them?"}]
            )
            assert followup.text == "I remember the nets."
            assert followup.usage.total_tokens == 38
            starts = [
                message
                for message in server.sent
                if message.get("method") == "thread/start"
            ]
            assert len(starts) == 1
            assert "model" not in starts[0]["params"]
            assert starts[0]["params"]["environments"] == []
            assert (
                starts[0]["params"]["config"]["mcp_servers"]["user-server"]["enabled"]
                is False
            )
            assert not any(
                message.get("method") == "config/read" for message in server.sent
            )
        finally:
            await provider.aclose()
        assert server.closed

    asyncio.run(scenario())


def test_api_key_login_rejected_before_thread_or_model_start():
    async def scenario():
        server = FakeServer(account="apiKey")
        provider = make(server)
        with pytest.raises(RuntimeError, match="ChatGPT sign-in"):
            await run(provider, [{"role": "user", "content": "Read nets"}])
        assert not any(
            message.get("method") in {"thread/start", "turn/start"}
            for message in server.sent
        )
        assert server.closed

    asyncio.run(scenario())


def test_starting_mcp_catalog_refused_even_before_tools_arrive():
    async def scenario():
        server = FakeServer(mcp_status="starting")
        provider = make(server)
        try:
            for _ in range(2):
                with pytest.raises(RuntimeError, match="MCP tools"):
                    await run(provider, [{"role": "user", "content": "Read nets"}])
            assert not any(
                message.get("method") == "turn/start" for message in server.sent
            )
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_reset_captures_old_turn_and_cancels_pending_dynamic_request():
    async def scenario():
        server = FakeServer()
        provider = make(server)
        try:
            await run(provider, [{"role": "user", "content": "Read nets"}])
            provider.reset_chain()
            await provider._cancel_task
            interrupt = next(
                message
                for message in server.sent
                if message.get("method") == "turn/interrupt"
            )
            assert interrupt["params"] == {"threadId": "thread-1", "turnId": "turn-1"}
            reply = next(message for message in server.sent if message.get("id") == 77)
            assert reply["result"]["success"] is False
            assert not provider._pending
            assert provider._thread_id is None
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_native_environment_keeps_login_location_but_excludes_api_credentials(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-forward")
    monkeypatch.setenv("CODEX_API_KEY", "must-not-forward")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "must-not-forward")
    monkeypatch.setenv("ATOPILE_AGENT_API_KEY", "must-not-forward")
    env = codex_environment()
    assert (
        not {
            "OPENAI_API_KEY",
            "CODEX_API_KEY",
            "CODEX_ACCESS_TOKEN",
            "ATOPILE_AGENT_API_KEY",
        }
        & env.keys()
    )
    assert "HOME" in env


def test_resume_restores_cumulative_usage_baseline():
    async def scenario():
        server = FakeServer()
        provider = make(server)
        provider.restore(
            {
                "provider": "codex",
                "thread_id": "thread-1",
                "tool_catalog_fingerprint": tool_catalog_fingerprint([TOOL]),
                "native_usage": {
                    "input_tokens": 152,
                    "output_tokens": 10,
                    "total_tokens": 162,
                },
            }
        )
        try:
            response = await run(provider, [{"role": "user", "content": "Continue"}])
            assert response.usage.total_tokens == 38
            assert any(
                message.get("method") == "thread/resume" for message in server.sent
            )
            assert not any(
                message.get("method") == "thread/start" for message in server.sent
            )
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_model_change_waits_for_old_turn_interrupt_before_new_thread():
    async def scenario():
        server = FakeServer()
        provider = make(server)
        try:
            await run(provider, [{"role": "user", "content": "Read nets"}])
            events = [
                event
                async for event in provider.stream(
                    messages=[{"role": "user", "content": "Continue"}],
                    instructions="Read nets",
                    tools=[TOOL],
                    model=ModelId("gpt-6.1-sol"),
                )
            ]
            assert any(isinstance(event, StreamDone) for event in events)
            methods = [message.get("method") for message in server.sent]
            assert methods.count("thread/start") == 2
            assert methods.index("turn/interrupt") < len(methods) - 1 - methods[
                ::-1
            ].index("thread/start")
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_cancellation_wakes_active_stream_without_concurrent_pipe_reads():
    class WaitingServer(FakeServer):
        async def send(self, message):
            if message.get("method") == "turn/start":
                self.sent.append(message)
                await self.queue.put(
                    {"id": message["id"], "result": {"turn": {"id": "waiting-turn"}}}
                )
                return
            await super().send(message)

    async def scenario():
        server = WaitingServer()
        provider = make(server)
        task = asyncio.create_task(run(provider, [{"role": "user", "content": "Wait"}]))
        try:
            async with asyncio.timeout(1):
                while provider._turn_id is None:
                    await asyncio.sleep(0)
                provider.abort_pending()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert not provider._pending
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_session_loop_limit_cancels_unexecuted_native_tool_request():
    from atopile.agent.session import AgentSession, Done
    from atopile.agent.tools.registry import ToolDef, ToolRegistry

    async def scenario():
        server = FakeServer()
        provider = make(server)
        executions = []

        async def read_nets(args, scope):
            executions.append(args)
            return {"nets": 3}

        registry = ToolRegistry()
        registry.register(ToolDef("layout_get_netlist", "Read nets", TOOL, read_nets))
        session = AgentSession(
            session_id="limit-test",
            project_root=Path.cwd(),
            provider=provider,
            model=ModelId("codex-default"),
            registry=registry,
            skill_ids=[],
            max_tool_loops=0,
        )
        try:
            events = [event async for event in session.send_message("Read nets")]
            await provider._cancel_task
            assert any(isinstance(event, Done) for event in events)
            assert executions == []
            assert not session.is_running
            assert not provider._pending
            reply = next(message for message in server.sent if message.get("id") == 77)
            assert reply["result"]["success"] is False
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_catalog_fingerprint_covers_schema_and_description_but_not_order():
    other = {**TOOL, "name": "layout_get_routes"}
    assert tool_catalog_fingerprint([TOOL, other]) == tool_catalog_fingerprint(
        [other, TOOL]
    )
    assert tool_catalog_fingerprint([TOOL]) != tool_catalog_fingerprint([other])
    assert tool_catalog_fingerprint([TOOL]) != tool_catalog_fingerprint(
        [{**TOOL, "description": "Changed behavior"}]
    )
    assert tool_catalog_fingerprint([TOOL]) != tool_catalog_fingerprint(
        [{**TOOL, "parameters": {"type": "object", "required": ["target"]}}]
    )


@pytest.mark.parametrize("saved_fingerprint", [None, "sha256:v1:old-catalog"])
@pytest.mark.parametrize(
    "new_tool",
    [
        "layout_get_routes",
        "layout_add_track_segment",
        "layout_add_via",
        "layout_delete_copper",
    ],
)
def test_old_catalog_starts_current_tools_and_preserves_old_thread(
    saved_fingerprint, new_tool
):
    class CurrentCatalogServer(FakeServer):
        async def emit(self, method, params, request_id=None):
            if method == "item/tool/call":
                params = {**params, "tool": new_tool}
            await super().emit(method, params, request_id)

    async def scenario():
        server = CurrentCatalogServer()
        provider = make(server)
        state = {"provider": "codex", "thread_id": "original-native-thread"}
        if saved_fingerprint is not None:
            state["tool_catalog_fingerprint"] = saved_fingerprint
        provider.restore(state)
        provider.set_display_history(
            [
                {"role": "user", "content": "Preserve the OBD connector position."},
                {
                    "role": "assistant",
                    "content": "Understood; first inspect the current board.",
                    "toolTraces": [{"result": "OLD_RAW_BOARD_DATA"}],
                    "reasoning": "PRIVATE_REASONING",
                },
                {"role": "tool", "content": "OLD_TOOL_RESULT"},
            ]
        )
        tools = [TOOL, {**TOOL, "name": new_tool}]
        try:
            events = [
                event
                async for event in provider.stream(
                    messages=[{"role": "user", "content": "Read routes now"}],
                    instructions="Use current board preflight",
                    tools=tools,
                )
            ]
            response = next(e.response for e in events if isinstance(e, StreamDone))
            assert response.tool_calls[0].name == new_tool
            starts = [m for m in server.sent if m.get("method") == "thread/start"]
            assert len(starts) == 1
            assert {s["name"] for s in starts[0]["params"]["dynamicTools"]} == {
                TOOL["name"],
                new_tool,
            }
            assert not any(
                m.get("method")
                in {"thread/resume", "thread/archive", "thread/delete", "thread/fork"}
                for m in server.sent
            )
            turn = next(m for m in server.sent if m.get("method") == "turn/start")
            text = turn["params"]["input"][0]["text"]
            assert "Preserve the OBD connector position." in text
            assert (
                "untrusted background" in text
                and "Refresh project, target and board facts" in text
            )
            assert (
                "OLD_RAW_BOARD_DATA" not in text
                and "OLD_TOOL_RESULT" not in text
                and "PRIVATE_REASONING" not in text
            )
            assert text.count("Read routes now") == 1
            saved = provider.snapshot()
            assert saved["previous_thread_ids"] == ["original-native-thread"]
            assert saved["thread_id"] == "thread-1"
            assert saved["tool_catalog_fingerprint"] == tool_catalog_fingerprint(tools)
            assert saved["migration_seed_pending"] is False
            # Following tool replies and user turns do not replay the seed.
            await provider.complete(
                messages=[
                    {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": "fresh result",
                    }
                ],
                instructions="Use current board preflight",
                tools=tools,
            )
            await provider.complete(
                messages=[{"role": "user", "content": "Continue"}],
                instructions="Use current board preflight",
                tools=tools,
            )
            turns = [m for m in server.sent if m.get("method") == "turn/start"]
            assert len(turns) == 2
            assert (
                "Historical display conversation"
                not in turns[1]["params"]["input"][0]["text"]
            )
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_same_catalog_resumes_without_history_seed_or_unsupported_parameters():
    async def scenario():
        server = FakeServer()
        provider = make(server)
        provider.restore(
            {
                "provider": "codex",
                "thread_id": "thread-1",
                "tool_catalog_fingerprint": tool_catalog_fingerprint([TOOL]),
                "previous_thread_ids": ["older-thread"],
            }
        )
        provider.set_display_history([{"role": "user", "content": "OLD_DISPLAY_TEXT"}])
        try:
            await run(provider, [{"role": "user", "content": "Continue"}])
            resume = next(m for m in server.sent if m.get("method") == "thread/resume")
            assert resume["params"]["threadId"] == "thread-1"
            assert "dynamicTools" not in resume["params"]
            assert not any(m.get("method") == "thread/start" for m in server.sent)
            turn = next(m for m in server.sent if m.get("method") == "turn/start")
            assert "OLD_DISPLAY_TEXT" not in turn["params"]["input"][0]["text"]
            assert provider.snapshot()["previous_thread_ids"] == ["older-thread"]
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_migration_display_seed_is_bounded_and_ignores_nontext_payloads():
    messages = [
        {"role": "user", "content": f"turn-{i} " + "\u0001" * 3000} for i in range(50)
    ]
    messages += [
        {"role": "tool", "content": "RAW_TOOL_RESULT"},
        {"role": "assistant", "content": "UNFINISHED", "pending": True},
        {"role": "user", "content": {"not": "display text"}},
    ]
    result = migration_history(messages)
    assert len(result) <= MIGRATION_HISTORY_CHARS
    history = json.loads(result)
    assert 1 <= len(history) <= 12
    assert all(len(item["content"]) <= MIGRATION_MESSAGE_CHARS for item in history)
    assert all(set(item) == {"role", "content"} for item in history)
    assert "[truncated]" in result
    assert (
        "turn-49" in result
        and "RAW_TOOL_RESULT" not in result
        and "UNFINISHED" not in result
    )


def test_session_excludes_active_user_and_pending_assistant_from_migration_seed():
    from types import SimpleNamespace
    from atopile.agent.session import AgentSession
    from atopile.agent.tools.registry import ToolRegistry

    async def scenario():
        provider = make(FakeServer())
        session = AgentSession(
            session_id="migration-history",
            project_root=Path.cwd(),
            provider=provider,
            model=ModelId("codex-default"),
            registry=ToolRegistry(),
            skill_ids=[],
            messages=[
                {"role": "user", "content": "Completed user turn"},
                {"role": "assistant", "content": "Completed assistant turn"},
            ],
        )
        session._start_run("CURRENT_USER_MUST_NOT_BE_SEEDED")

        async def stream(**kwargs):
            if False:
                yield None

        provider.stream = stream
        async for _ in session._stream_model(
            [{"role": "user", "content": "CURRENT_USER_MUST_NOT_BE_SEEDED"}],
            SimpleNamespace(build_instructions=lambda: "Current instructions"),
        ):
            pass
        assert "Completed user turn" in provider._display_history
        assert "Completed assistant turn" in provider._display_history
        assert "CURRENT_USER_MUST_NOT_BE_SEEDED" not in provider._display_history

    asyncio.run(scenario())


def test_migrated_snapshot_resumes_and_delivers_pending_history_once():
    async def scenario():
        first = make(FakeServer())
        first.restore({"provider": "codex", "thread_id": "original-thread"})
        try:
            await first._ensure_thread("Current instructions", [TOOL])
            state = first.snapshot()
            assert state["migration_seed_pending"] is True
        finally:
            await first.aclose()
        server = FakeServer()
        restored = make(server)
        restored.restore(state)
        restored.set_display_history(
            [{"role": "user", "content": "Useful earlier constraints"}]
        )
        try:
            await run(
                restored,
                [{"role": "user", "content": "Continue"}],
                "Current instructions",
            )
            assert any(m.get("method") == "thread/resume" for m in server.sent)
            assert not any(m.get("method") == "thread/start" for m in server.sent)
            turn = next(m for m in server.sent if m.get("method") == "turn/start")
            text = turn["params"]["input"][0]["text"]
            assert (
                "Useful earlier constraints" in text
                and "bounded, partial excerpt" in text
            )
            assert restored.snapshot()["migration_seed_pending"] is False
            assert restored.snapshot()["previous_thread_ids"] == ["original-thread"]
        finally:
            await restored.aclose()

    asyncio.run(scenario())


def test_old_native_thread_metadata_is_bounded_without_remote_deletion():
    provider = make(FakeServer())
    provider.restore(
        {
            "provider": "codex",
            "thread_id": "current",
            "previous_thread_ids": [f"old-{i}" for i in range(80)],
        }
    )
    assert provider.snapshot()["previous_thread_ids"] == [
        f"old-{i}" for i in range(48, 80)
    ]


def test_failed_catalog_migration_keeps_original_native_thread_for_retry():
    class StartFailure(FakeServer):
        async def send(self, message):
            if message.get("method") == "thread/start":
                self.sent.append(message)
                await self.queue.put(
                    {
                        "id": message["id"],
                        "error": {"message": "temporary start failure"},
                    }
                )
                return
            await super().send(message)

    async def scenario():
        server = StartFailure()
        provider = make(server)
        provider.restore(
            {"provider": "codex", "thread_id": "preserve-this-native-thread"}
        )
        try:
            with pytest.raises(RuntimeError, match="temporary start failure"):
                await run(provider, [{"role": "user", "content": "Continue"}])
            assert provider.snapshot()["thread_id"] == "preserve-this-native-thread"
            assert not any(
                m.get("method") in {"thread/archive", "thread/delete", "thread/resume"}
                for m in server.sent
            )
        finally:
            await provider.aclose()

    asyncio.run(scenario())


def test_catalog_change_waits_for_active_tool_result_before_migrating():
    async def scenario():
        server = FakeServer()
        provider = make(server)
        expanded = [TOOL, {**TOOL, "name": "layout_get_routes"}]
        try:
            await run(provider, [{"role": "user", "content": "Read nets"}])
            await provider.complete(
                messages=[
                    {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": "fresh nets",
                    }
                ],
                instructions="Read circuit nets",
                tools=expanded,
            )
            assert sum(m.get("method") == "thread/start" for m in server.sent) == 1
            assert not any(m.get("method") == "turn/interrupt" for m in server.sent)
            await provider.complete(
                messages=[{"role": "user", "content": "Read routes"}],
                instructions="Read circuit nets",
                tools=expanded,
            )
            starts = [m for m in server.sent if m.get("method") == "thread/start"]
            assert len(starts) == 2
            assert "layout_get_routes" in {
                spec["name"] for spec in starts[1]["params"]["dynamicTools"]
            }
        finally:
            await provider.aclose()

    asyncio.run(scenario())

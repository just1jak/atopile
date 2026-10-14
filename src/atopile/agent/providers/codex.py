"""Local Codex app-server bridge using its native ChatGPT sign-in.

The app server pauses at a dynamic tool request. We expose that request to the
existing Atopile runner and return its scoped result on the next stream call.
No OAuth credentials are read, copied, or supplied by this module.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from collections import deque
from pathlib import Path
from typing import Any, AsyncIterator

from atopile.agent.providers.base import (
    LLMResponse,
    ModelId,
    StreamDone,
    StreamEvent,
    StreamReasoningDelta,
    StreamTextDelta,
    TokenUsage,
    ToolCall,
)

DEFAULT_MODEL = "codex-default"
DISABLED_FEATURES = (
    "shell_tool",
    "unified_exec",
    "shell_snapshot",
    "apps",
    "plugins",
    "remote_plugin",
    "hooks",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "computer_use",
    "multi_agent",
    "multi_agent_v2",
    "code_mode",
    "view_image",
    "image_generation",
    "workspace_dependencies",
    "skill_search",
    "skill_mcp_dependency_install",
    "goals",
    "sleep_tool",
)


def codex_executable() -> str:
    explicit = os.getenv("ATOPILE_AGENT_CODEX_PATH", "").strip()
    if explicit:
        if not Path(explicit).is_file() or not os.access(explicit, os.X_OK):
            raise RuntimeError(
                "Configured Codex executable is missing or not executable."
            )
        return explicit
    found = shutil.which("codex")
    if found:
        return found
    for candidate in (
        "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
        "/Applications/Codex.app/Contents/Resources/codex",
    ):
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError(
        "Set the Codex executable in AI settings, then sign in with ChatGPT."
    )


def codex_environment() -> dict[str, str]:
    """Preserve native login location, exclude alternate billing credentials."""
    blocked = {
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "OPENAI_ACCESS_TOKEN",
        "ATOPILE_AGENT_API_KEY",
        "ATOPILE_AGENT_OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
        "AZURE_OPENAI_API_KEY",
    }
    return {key: value for key, value in os.environ.items() if key not in blocked}


def dynamic_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result = []
    for tool in tools or []:
        if tool.get("type") != "function" or not isinstance(tool.get("name"), str):
            raise ValueError("Codex accepts only named Atopile function tools.")
        result.append(
            {
                "type": "function",
                "name": tool["name"],
                "description": tool.get("description", ""),
                "inputSchema": tool.get("parameters", {"type": "object"}),
            }
        )
    return result


class StdioAppServer:
    def __init__(self) -> None:
        self.process: asyncio.subprocess.Process | None = None
        self.stderr: deque[str] = deque(maxlen=16)
        self._stderr_task: asyncio.Task | None = None

    async def start(self) -> None:
        args = [codex_executable(), "app-server", "--listen", "stdio://"]
        overrides = {
            "forced_login_method": "chatgpt",
            "model_provider": "openai",
            "web_search": "disabled",
            "mcp_servers": {},
            "notify": [],
            "analytics.enabled": False,
            "agents.enabled": False,
            "features.skip_host_skill_discovery": True,
            # Current Codex models discover/call client dynamic tools through
            # this JavaScript bridge. Disabling it hides a working PCB registry
            # behind an internal "code-mode host is disabled" tool error.
            # Native shell, file, MCP and browser access remain disabled/scoped.
            "features.code_mode_host": True,
            "project_doc_max_bytes": 0,
        }
        overrides.update(
            {f"features.{feature}": False for feature in DISABLED_FEATURES}
        )
        for key, value in overrides.items():
            args += ["-c", f"{key}={json.dumps(value)}"]
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=codex_environment(),
            limit=4 * 1024 * 1024,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        assert self.process and self.process.stderr
        while line := await self.process.stderr.readline():
            # Bounded diagnostic buffer, never printed or sent to a webview.
            self.stderr.append(line.decode("utf8", "replace")[:1024])

    async def send(self, message: dict[str, Any]) -> None:
        if (
            not self.process
            or self.process.returncode is not None
            or not self.process.stdin
        ):
            raise RuntimeError("Codex app-server is no longer running. Retry the chat.")
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        await self.process.stdin.drain()

    async def read(self) -> dict[str, Any]:
        assert self.process and self.process.stdout
        line = await self.process.stdout.readline()
        if not line:
            raise RuntimeError(
                "Codex app-server closed its connection. Check Codex sign-in and retry."
            )
        try:
            message = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            raise RuntimeError("Codex app-server returned invalid JSON.") from exc
        if not isinstance(message, dict):
            raise RuntimeError("Codex app-server returned an invalid protocol message.")
        return message

    async def close(self) -> None:
        process, self.process = self.process, None
        if process and process.returncode is None:
            if process.stdin:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), 2)
            except asyncio.TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 1)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        if self._stderr_task:
            self._stderr_task.cancel()
            await asyncio.gather(self._stderr_task, return_exceptions=True)
            self._stderr_task = None

    def __del__(self) -> None:
        if self.process and self.process.returncode is None:
            try:
                self.process.kill()
            except ProcessLookupError, RuntimeError:
                pass


class CodexProvider:
    provider_kind = "codex"

    def __init__(
        self,
        model: ModelId,
        *,
        timeout: float = 120.0,
        transport_factory=StdioAppServer,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._transport_factory = transport_factory
        self._server: Any = None
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1024)
        self._responses: dict[str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._ignored_turns: set[str] = set()
        self._last_instructions: str | None = None
        self._usage_reported = TokenUsage()
        self._request_sequence = 0
        self._thread_id: str | None = None
        self._thread_validated = False
        self._turn_id: str | None = None
        self._resume_thread_id: str | None = None
        self._pending: dict[str, Any] = {}
        self._project_root: Path | None = None
        self._tool_names: set[str] = set()
        self._usage_total = TokenUsage()
        self._cancel_task: asyncio.Task | None = None

    def bind_project(self, root: Path) -> None:
        self._project_root = root.resolve()

    @property
    def model(self) -> ModelId:
        return self._model

    @model.setter
    def model(self, value: ModelId) -> None:
        if value != self._model:
            self.reset_chain()
        self._model = value

    async def _read_messages(self) -> None:
        try:
            while True:
                message = await self._server.read()
                request_id = message.get("id")
                if "method" not in message and request_id in self._responses:
                    future = self._responses[request_id]
                    if not future.done():
                        future.set_result(message)
                else:
                    await self._events.put(message)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            for future in self._responses.values():
                if not future.done():
                    future.set_exception(
                        RuntimeError("Codex app-server connection ended.")
                    )
            await self._events.put(
                {"method": "__connection_error", "params": {"message": str(exc)}}
            )

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_sequence += 1
        request_id = f"atopile-{self._request_sequence}"
        future = asyncio.get_running_loop().create_future()
        self._responses[request_id] = future
        try:
            await self._server.send(
                {"id": request_id, "method": method, "params": params}
            )
            message = await asyncio.wait_for(future, self._timeout)
            if "error" in message:
                error = message["error"]
                detail = (
                    error.get("message", "request failed")
                    if isinstance(error, dict)
                    else "request failed"
                )
                if method == "thread/resume" and "already has an active writer" in detail:
                    raise RuntimeError(
                        "This chat is open in another Atopile Local window. "
                        "Reload or close that window, then retry here."
                    )
                raise RuntimeError(f"Codex {method}: {detail}")
            result = message.get("result", {})
            if not isinstance(result, dict):
                raise RuntimeError(f"Codex {method} returned an invalid result.")
            return result
        finally:
            self._responses.pop(request_id, None)

    def _drain_events(self) -> None:
        while not self._events.empty():
            self._events.get_nowait()

    def _usage_delta(self) -> TokenUsage:
        fields = (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "reasoning_tokens",
            "cached_input_tokens",
        )
        result = TokenUsage(
            **{
                field: max(
                    0,
                    getattr(self._usage_total, field)
                    - getattr(self._usage_reported, field),
                )
                for field in fields
            }
        )
        self._usage_reported = TokenUsage(
            **{field: getattr(self._usage_total, field) for field in fields}
        )
        return result

    async def _ensure_thread(
        self, instructions: str, tools: list[dict[str, Any]] | None
    ) -> None:
        if self._thread_id and self._server and self._thread_validated:
            return
        if not self._project_root:
            raise RuntimeError(
                "Codex must be attached to the selected Atopile project."
            )
        if not self._server:
            self._server = self._transport_factory()
            try:
                await self._server.start()
                self._reader_task = asyncio.create_task(self._read_messages())
                await self._rpc(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": "atopile_local",
                            "title": "Atopile Local",
                            "version": "0.3.1",
                        },
                        "capabilities": {"experimentalApi": True},
                    },
                )
                await self._server.send({"method": "initialized", "params": {}})
                account = await self._rpc("account/read", {"refreshToken": False})
                if (
                    not isinstance(account.get("account"), dict)
                    or account["account"].get("type") != "chatgpt"
                ):
                    raise RuntimeError(
                        "Codex needs a ChatGPT sign-in. Use Connect ChatGPT. "
                        "API-key accounts are not used."
                    )
            except BaseException:
                await self.aclose()
                raise
        # Metadata-only discovery: never fetch full credential-bearing config.
        mcp_names = {"node_repl", "computer-use"}
        cursor = None
        while True:
            inventory = await self._rpc(
                "mcpServerStatus/list", {"detail": "toolsAndAuthOnly", "cursor": cursor}
            )
            mcp_names.update(
                entry["name"]
                for entry in inventory.get("data", [])
                if isinstance(entry, dict) and isinstance(entry.get("name"), str)
            )
            cursor = inventory.get("nextCursor")
            if not cursor:
                break
        config = {
            "mcp_servers": {
                name: {"command": sys.executable, "enabled": False}
                for name in mcp_names
            }
        }
        specs = dynamic_tools(tools)
        self._tool_names = {tool["name"] for tool in specs}
        params: dict[str, Any] = {
            "cwd": str(self._project_root),
            "modelProvider": "openai",
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "environments": [],
            "config": config,
            "baseInstructions": instructions,
            "developerInstructions": (
                "Use only the supplied Atopile function tools. "
                "All project reads and changes must pass through those tools. "
                "Do not use native shell, file-edit, MCP, browser, or account tools."
            ),
        }
        if self._model.value != DEFAULT_MODEL:
            params["model"] = self._model.value
        if self._resume_thread_id:
            params["threadId"] = self._resume_thread_id
            started = await self._rpc("thread/resume", params)
            self._resume_thread_id = None
        else:
            self._usage_total = TokenUsage()
            self._usage_reported = TokenUsage()
            params["dynamicTools"] = specs
            started = await self._rpc("thread/start", params)
        self._last_instructions = instructions
        thread = started.get("thread", {})
        self._thread_validated = False
        self._thread_id = thread.get("id")
        if not isinstance(self._thread_id, str):
            raise RuntimeError("Codex did not create a valid thread.")
        cursor = None
        while True:
            inventory = await self._rpc(
                "mcpServerStatus/list",
                {
                    "threadId": self._thread_id,
                    "detail": "toolsAndAuthOnly",
                    "cursor": cursor,
                },
            )
            if any(
                entry.get("tools")
                or entry.get("resources")
                or entry.get("resourceTemplates")
                or entry.get("runtimeStatus") != "disabled"
                or entry.get("toolsError")
                for entry in inventory.get("data", [])
            ):
                await self.aclose()
                raise RuntimeError(
                    "Codex still exposes inherited MCP tools. No inference was started."
                )
            cursor = inventory.get("nextCursor")
            if not cursor:
                break
        self._thread_validated = True

    async def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        instructions: str,
        tools: list[dict[str, Any]] | None = None,
        model: ModelId | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        if self._cancel_task:
            await self._cancel_task
            self._cancel_task = None
        if model is not None:
            self.model = model
        if self._cancel_task:
            await self._cancel_task
            self._cancel_task = None
        try:
            await self._ensure_thread(instructions, tools)
            if self._pending and not any(
                message.get("type") == "function_call_output" for message in messages
            ):
                await self._interrupt()
            instructions_changed = instructions != self._last_instructions
            user_messages = []
            for message in messages:
                if message.get("type") == "function_call_output":
                    call_id = str(message.get("call_id", ""))
                    if call_id not in self._pending:
                        raise RuntimeError(
                            "Codex tool result does not match its pending request."
                        )
                    request_id = self._pending.pop(call_id)
                    output = message.get("output", "")
                    text = output if isinstance(output, str) else json.dumps(output)
                    if instructions_changed:
                        text += (
                            "\n\nTrusted Atopile host instructions have changed:\n"
                            + instructions
                        )
                        self._last_instructions = instructions
                        instructions_changed = False
                    await self._server.send(
                        {
                            "id": request_id,
                            "result": {
                                "success": True,
                                "contentItems": [{"type": "inputText", "text": text}],
                            },
                        }
                    )
                elif message.get("role") == "user":
                    user_messages.append(str(message.get("content", "")))
            if not self._turn_id:
                if not user_messages:
                    raise RuntimeError("Start a Codex turn with a user message.")
                if instructions_changed:
                    user_messages.insert(
                        0,
                        "Trusted Atopile host instructions for this turn:\n"
                        + instructions,
                    )
                    self._last_instructions = instructions
                started = await self._rpc(
                    "turn/start",
                    {
                        "threadId": self._thread_id,
                        "input": [{"type": "text", "text": "\n\n".join(user_messages)}],
                        "approvalPolicy": "never",
                        "environments": [],
                        "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
                    },
                )
                self._turn_id = started.get("turn", {}).get("id")
            elif user_messages:
                await self._rpc(
                    "turn/steer",
                    {
                        "threadId": self._thread_id,
                        "expectedTurnId": self._turn_id,
                        "input": [{"type": "text", "text": "\n\n".join(user_messages)}],
                    },
                )
            stream_turn_id = self._turn_id
            text = ""
            reasoning = ""
            while True:
                event = await asyncio.wait_for(self._events.get(), self._timeout)
                method, params = event.get("method"), event.get("params", {})
                if not isinstance(params, dict):
                    raise RuntimeError("Codex returned invalid event parameters.")
                if method == "__interrupted" and params.get("turnId") == stream_turn_id:
                    raise asyncio.CancelledError()
                event_turn = params.get("turnId") or (
                    params.get("turn", {}).get("id")
                    if isinstance(params.get("turn"), dict)
                    else None
                )
                if event_turn in self._ignored_turns or (
                    event_turn is not None
                    and self._turn_id is not None
                    and event_turn != self._turn_id
                ):
                    continue
                if method == "__connection_error":
                    raise RuntimeError(params.get("message", "Codex connection ended."))
                if params.get("threadId") not in {None, self._thread_id}:
                    continue
                if method == "item/tool/call" and "id" in event:
                    name, arguments = params.get("tool"), params.get("arguments")
                    if name not in self._tool_names or not isinstance(arguments, dict):
                        await self._server.send(
                            {
                                "id": event["id"],
                                "result": {
                                    "success": False,
                                    "contentItems": [
                                        {
                                            "type": "inputText",
                                            "text": "Invalid Atopile tool.",
                                        }
                                    ],
                                },
                            }
                        )
                        raise RuntimeError(
                            "Codex requested an unknown scoped Atopile tool."
                        )
                    call_id = str(params.get("callId", ""))
                    self._pending[call_id] = event["id"]
                    yield StreamDone(
                        LLMResponse(
                            self._turn_id,
                            text,
                            [ToolCall(call_id, name, json.dumps(arguments), arguments)],
                            "requires_tool",
                            usage=self._usage_delta(),
                            reasoning=reasoning,
                        )
                    )
                    return
                if "id" in event and method:
                    # Approval, user-input, auth-token, and other server requests
                    # are not delegated to the circuit model or silently accepted.
                    await self._server.send(
                        {
                            "id": event["id"],
                            "error": {
                                "code": -32601,
                                "message": "Only Atopile tools are available.",
                            },
                        }
                    )
                    raise RuntimeError(
                        "Codex requested an unsupported native operation. Turn stopped."
                    )
                if method == "item/agentMessage/delta":
                    delta = str(params.get("delta", ""))
                    text += delta
                    yield StreamTextDelta(delta)
                elif method in {
                    "item/reasoning/summaryTextDelta",
                    "item/reasoning/textDelta",
                }:
                    delta = str(params.get("delta", ""))
                    reasoning += delta
                    yield StreamReasoningDelta(delta)
                elif method == "item/started" and params.get("item", {}).get(
                    "type"
                ) in {
                    "commandExecution",
                    "fileChange",
                    "mcpToolCall",
                    "webSearch",
                    "imageGeneration",
                }:
                    raise RuntimeError(
                        "Codex attempted a native tool outside Atopile. Turn stopped."
                    )
                elif method == "thread/tokenUsage/updated":
                    usage = params.get("tokenUsage", {}).get("total", {})
                    self._usage_total = TokenUsage(
                        input_tokens=int(usage.get("inputTokens", 0)),
                        output_tokens=int(usage.get("outputTokens", 0)),
                        total_tokens=int(usage.get("totalTokens", 0)),
                        reasoning_tokens=int(usage.get("reasoningOutputTokens", 0)),
                        cached_input_tokens=int(usage.get("cachedInputTokens", 0)),
                    )
                elif method == "turn/completed":
                    turn = params.get("turn", {})
                    self._turn_id = None
                    if turn.get("status") != "completed":
                        error = turn.get("error") or {}
                        detail = error.get("message", "Check your Codex usage limits.")
                        raise RuntimeError(
                            f"Codex turn {turn.get('status', 'failed')}: {detail}"
                        )
                    yield StreamDone(
                        LLMResponse(
                            turn.get("id"),
                            text,
                            [],
                            "completed",
                            usage=self._usage_delta(),
                            reasoning=reasoning,
                        )
                    )
                    return
        except BaseException:
            await self._interrupt()
            raise

    async def complete(self, **kwargs) -> LLMResponse:
        response = None
        async for event in self.stream(**kwargs):
            if isinstance(event, StreamDone):
                response = event.response
        assert response is not None
        return response

    async def _interrupt(
        self, thread_id: str | None = None, turn_id: str | None = None
    ) -> None:
        thread_id, turn_id = thread_id or self._thread_id, turn_id or self._turn_id
        if turn_id:
            self._ignored_turns.add(turn_id)
        if self._server and turn_id and thread_id:
            try:
                for request_id in list(self._pending.values()):
                    await self._server.send(
                        {
                            "id": request_id,
                            "result": {
                                "success": False,
                                "contentItems": [
                                    {
                                        "type": "inputText",
                                        "text": "The user cancelled this tool.",
                                    }
                                ],
                            },
                        }
                    )
                await self._rpc(
                    "turn/interrupt", {"threadId": thread_id, "turnId": turn_id}
                )
            except Exception:
                await self.aclose()
        self._turn_id = None
        self._pending.clear()
        self._drain_events()
        if turn_id:
            await self._events.put(
                {
                    "method": "__interrupted",
                    "params": {"threadId": thread_id, "turnId": turn_id},
                }
            )

    def abort_pending(self, *, reason: str = "Interrupted") -> None:
        if (
            self._server
            and self._turn_id
            and not (self._cancel_task and not self._cancel_task.done())
        ):
            # Capture IDs now: reset_chain may change thread_id before scheduling.
            self._cancel_task = asyncio.create_task(
                self._interrupt(self._thread_id, self._turn_id)
            )

    def reset_chain(self) -> None:
        self.abort_pending()
        self._thread_id = None
        self._thread_validated = False
        self._resume_thread_id = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "local": True,
            "provider": "codex",
            "model": self._model.value,
            # Saving all restored sessions before their first turn must retain
            # their conversation IDs, including after a temporary resume error.
            "thread_id": self._thread_id or self._resume_thread_id,
            "native_usage": vars(self._usage_total).copy(),
        }

    def restore(self, state: dict[str, Any]) -> None:
        if state.get("provider") == "codex" and isinstance(state.get("thread_id"), str):
            self._resume_thread_id = state["thread_id"]
            usage = state.get("native_usage", {})
            if isinstance(usage, dict):
                valid = {
                    field: int(usage.get(field, 0)) for field in vars(TokenUsage())
                }
                self._usage_total = TokenUsage(**valid)
                self._usage_reported = TokenUsage(**valid)

    async def add_searchable_document(self, filename: str, content: bytes) -> None:
        # Datasheets are read through Atopile's document tools. No API uploads.
        return

    async def aclose(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
            self._reader_task = None
        server, self._server = self._server, None
        if server:
            await server.close()
        self._thread_id = None
        self._thread_validated = False
        self._turn_id = None
        self._pending.clear()
        self._drain_events()

"""Exercise the real core server and project discovery without an account."""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]


async def check(port: int) -> None:
    async with websockets.connect(f"ws://127.0.0.1:{port}/atopile-ui") as ws:
        await ws.send(json.dumps({"type": "action", "action": "authStatus", "sessionId": "local-smoke", "requestId": "auth"}))
        response = json.loads(await asyncio.wait_for(ws.recv(), 10))
        assert response["ok"] and response["result"]["isAuthenticated"] is False, response
        await ws.send(json.dumps({"type": "subscribe", "sessionId": "local-smoke", "keys": ["projects"]}))
        await ws.recv()
        await ws.send(json.dumps({"type": "action", "action": "discoverProjects", "sessionId": "local-smoke", "paths": [str(ROOT / "examples/offline-indicator")]}))
        for _ in range(20):
            response = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if response.get("key") == "projects" and "offline-indicator" in json.dumps(response):
                print("PASS: local core server, WebSocket RPC, no-account startup, and project discovery")
                return
        raise AssertionError("Demo project did not appear in server state")


def main() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, ATOPILE_CORE_SERVER_PORT=str(port), ATOPILE_LOCAL_MODE="1")
    with tempfile.TemporaryFile(mode="w+") as log:
        proc = subprocess.Popen([str(ROOT / "bin/ato-local"), "serve", "core"], env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                log.seek(0)
                output = log.read()
                if "ATOPILE_SERVER_READY" in output:
                    asyncio.run(check(port))
                    return
                if proc.poll() is not None:
                    raise RuntimeError(output)
                time.sleep(0.2)
            raise TimeoutError("Local core server did not start")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    main()

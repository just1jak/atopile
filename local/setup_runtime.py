#!/usr/bin/env python3
"""Install the pinned native wheel, then run the fork's Python source over it.

This avoids building Zig locally. No global Python packages are changed.
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPILER_VERSION = "0.15.9"


def main():
    uv = shutil.which("uv")
    if not uv:
        candidates = [
            Path.home() / "Library/Application Support/Code/User/globalStorage/atopile.atopile/uv/uv",
            Path.home() / ".local/bin/uv",
        ]
        uv = next((str(p) for p in candidates if p.is_file()), None)
    if not uv:
        raise SystemExit("Install uv from https://docs.astral.sh/uv/getting-started/installation/ then run this again.")
    env = dict(os.environ)
    env.setdefault("UV_CACHE_DIR", str(ROOT / ".runtime-cache"))
    env.setdefault("UV_PYTHON_INSTALL_DIR", str(ROOT / ".python"))
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        subprocess.run([uv, "venv", "--python", "3.14", str(ROOT / ".venv")], env=env, check=True)
    subprocess.run([uv, "pip", "install", "--python", str(python), "--requirement", str(ROOT / "local/runtime-lock.txt")], env=env, check=True)
    launcher = ROOT / "bin/ato-local"
    launcher.chmod(0o755)
    print("Runtime ready:", launcher)
    print("Select this executable in the extension's atopileLocal.ato setting.")


if __name__ == "__main__":
    main()

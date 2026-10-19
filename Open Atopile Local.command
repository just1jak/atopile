#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/python3 - "$ROOT" "$@" <<'PY'
import json
import os
from pathlib import Path
import sys

source = Path(sys.argv[1])
pointer = Path.home() / "Library/Application Support/Code/User/globalStorage/local-atopile.atopile-local/runtime.json"
try:
    ato = Path(json.loads(pointer.read_text())["ato"])
    launch = ato.parent.parent / "local/launch.py"
    if not ato.is_absolute() or ato.name != "ato-local" or ato.parent.name != "bin" or not ato.is_file() or not launch.is_file():
        raise ValueError("Invalid runtime location")
except (OSError, ValueError, KeyError, TypeError):
    raise SystemExit("Atopile Local's engine is unavailable. Install it with local/install_local_runtime.py first.")
args = sys.argv[2:] or [str(source / "Atopile Local.code-workspace")]
os.execv(sys.executable, [sys.executable, str(launch), *args])
PY

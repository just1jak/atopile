"""Open the local example or a supplied project in VS Code."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def registered_root():
    if sys.platform == "darwin":
        user_dir = Path.home() / "Library/Application Support/Code/User"
    elif os.name == "nt":
        user_dir = Path(os.environ["APPDATA"]) / "Code/User"
    else:
        user_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Code/User"
    pointer = user_dir / "globalStorage/local-atopile.atopile-local/runtime.json"
    if not pointer.exists():
        return None
    try:
        ato = Path(json.loads(pointer.read_text())["ato"])
        runtime = ato.parent.parent
        if not ato.is_absolute() or ato.name != "ato-local" or ato.parent.name != "bin" or not ato.is_file() or not (runtime / "local/launch.py").is_file():
            raise ValueError("Invalid runtime location")
        return runtime.resolve()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit("The registered Atopile Local engine is unavailable. Reinstall it with local/install_local_runtime.py.") from error


def main():
    parser = argparse.ArgumentParser(description="Open Atopile Local in VS Code.")
    parser.add_argument("project", nargs="?", help="Optional existing circuit project directory")
    args = parser.parse_args()
    target = Path(args.project).expanduser().resolve() if args.project else ROOT / "Atopile Local.code-workspace"
    if not target.exists():
        raise SystemExit("Project does not exist: " + str(target))
    runtime = registered_root()
    if runtime and runtime != ROOT:
        subprocess.run([sys.executable, str(runtime / "local/launch.py"), str(target)], check=True)
        return
    spec = importlib.util.spec_from_file_location("local_installer", ROOT / "local/install_extension.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    code = installer.find_code()
    if not (ROOT / ".venv/bin/python").is_file():
        raise SystemExit("Set up this source folder first: python3 local/setup_runtime.py")
    installed = subprocess.run([code, "--list-extensions", "--show-versions"], capture_output=True, text=True, check=True)
    version = json.loads((ROOT / "src/vscode-atopile/package.json").read_text())["version"]
    if installer.EXTENSION_ID + "@" + version not in installed.stdout.splitlines():
        raise SystemExit("Install Atopile Local first: python3 local/install_extension.py")
    if runtime is None:
        installer.register_runtime()
    subprocess.run([code, "--new-window", str(target)], check=True)
    print("Opened Atopile Local. Select Inspect → Schematic after the project builds.")


if __name__ == "__main__":
    main()

"""Open the local example or a supplied project in VS Code."""
import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Open Atopile Local in VS Code.")
    parser.add_argument("project", nargs="?", help="Optional existing circuit project directory")
    args = parser.parse_args()
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
    installer.register_runtime()
    target = Path(args.project).expanduser().resolve() if args.project else ROOT / "Atopile Local.code-workspace"
    if not target.exists():
        raise SystemExit("Project does not exist: " + str(target))
    subprocess.run([code, "--new-window", str(target)], check=True)
    print("Opened Atopile Local. Select Inspect → Schematic after the project builds.")


if __name__ == "__main__":
    main()

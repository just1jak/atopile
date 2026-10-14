"""Install the built VSIX and register its fork-specific runtime location."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ID = "local-atopile.atopile-local"


def main():
    code = shutil.which("code")
    if not code and sys.platform == "darwin":
        candidate = Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code")
        if candidate.is_file():
            code = str(candidate)
    if not code:
        raise SystemExit("Enable the VS Code 'code' command, then run this again.")
    version = json.loads((ROOT / "src/vscode-atopile/package.json").read_text())["version"]
    vsix = ROOT.parent / f"atopile-local-{version}.vsix"
    if not vsix.is_file():
        raise SystemExit(f"Build or place {vsix.name} next to this source folder.")
    if not (ROOT / ".venv/bin/python").is_file():
        raise SystemExit("Run python3 local/setup_runtime.py first.")
    subprocess.run([code, "--install-extension", str(vsix), "--force"], check=True)
    if sys.platform == "darwin":
        user_dir = Path.home() / "Library/Application Support/Code/User"
    elif os.name == "nt":
        user_dir = Path(os.environ["APPDATA"]) / "Code/User"
    else:
        user_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Code/User"
    storage = user_dir / "globalStorage" / EXTENSION_ID
    storage.mkdir(parents=True, exist_ok=True)
    location = storage / "runtime.json"
    location.write_text(json.dumps({"ato": str(ROOT / "bin/ato-local")}, indent=2) + "\n")
    print("Installed Atopile Local; reload a VS Code window to activate it.")
    print("ChatGPT connection command: Atopile Local: Connect ChatGPT")


if __name__ == "__main__":
    main()

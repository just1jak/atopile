"""Install the built VSIX and register its fork-specific runtime location."""
import json
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ID = "local-atopile.atopile-local"


def find_code():
    code = shutil.which("code")
    if not code and sys.platform == "darwin":
        candidate = Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code")
        if candidate.is_file():
            code = str(candidate)
    if not code:
        raise SystemExit("Enable the VS Code 'code' command, then run this again.")
    return code


def download_extension(version):
    name = f"atopile-local-{version}.vsix"
    base = f"https://github.com/just1jak/atopile/releases/download/local-v{version}/"
    with urllib.request.urlopen(base + "SHA256SUMS.txt", timeout=60) as response:
        checksums = response.read(64 * 1024).decode("utf-8")
    expected = next((line.split()[0] for line in checksums.splitlines() if line.split() and line.split()[-1].lstrip("*") == name), None)
    if not expected or len(expected) != 64:
        raise SystemExit("The release has no checksum for the extension.")
    temporary = None
    try:
        digest = hashlib.sha256()
        size = 0
        with tempfile.NamedTemporaryFile(dir=ROOT.parent, prefix=".atopile-local-", delete=False) as output:
            temporary = Path(output.name)
            with urllib.request.urlopen(base + name, timeout=60) as response:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > 100 * 1024 * 1024:
                        raise SystemExit("The extension download exceeds the expected size.")
                    digest.update(block)
                    output.write(block)
        if digest.hexdigest() != expected:
            raise SystemExit("Extension checksum mismatch; nothing was installed.")
        target = ROOT.parent / name
        temporary.replace(target)
        return target
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def register_runtime():
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
    return location


def main():
    parser = argparse.ArgumentParser(description="Install Atopile Local in VS Code.")
    parser.add_argument("--download", action="store_true", help="Download this version from the GitHub release and verify its SHA-256")
    parser.add_argument("--vsix", type=Path, help="Use a specific local extension package")
    args = parser.parse_args()
    code = find_code()
    version = json.loads((ROOT / "src/vscode-atopile/package.json").read_text())["version"]
    vsix = args.vsix or ROOT.parent / f"atopile-local-{version}.vsix"
    if args.download:
        vsix = download_extension(version)
    if not vsix.is_file():
        raise SystemExit(f"Build or place {vsix.name} next to this source folder, or use --download.")
    if not (ROOT / ".venv/bin/python").is_file():
        raise SystemExit("Run python3 local/setup_runtime.py first.")
    subprocess.run([code, "--install-extension", str(vsix), "--force"], check=True)
    register_runtime()
    print("Installed Atopile Local; reload a VS Code window to activate it.")
    print("ChatGPT connection command: Atopile Local: Connect ChatGPT")


if __name__ == "__main__":
    main()

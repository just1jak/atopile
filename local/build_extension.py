"""Rebuild the local extension with Bun and the pinned Python runtime."""
import os
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    bun = shutil.which("bun")
    if not bun:
        tools = ROOT / ".build-tools"
        subprocess.run(["npm", "install", "--prefix", str(tools), "--cache", str(tools / "npm-cache"), "bun@1.3.0"], check=True)
        bun = str(tools / "node_modules/.bin/bun")
    env = dict(os.environ)
    env.update({"PUPPETEER_SKIP_DOWNLOAD": "1", "BUN_INSTALL_CACHE_DIR": str(ROOT / ".build-cache"), "ATOPILE_LOCAL_PYTHON": str(ROOT / ".venv/bin/python"), "ATOPILE_LOCAL_DATA_DIR": str(ROOT / ".state"), "FBRK_TELEMETRY": "0"})
    env["PATH"] = str(Path(bun).parent) + os.pathsep + env["PATH"]
    extension = ROOT / "src/vscode-atopile"
    for folder in [extension, ROOT / "src/ui/webview", ROOT / "src/atopile/layout_server/frontend"]:
        subprocess.run([bun, "install", "--frozen-lockfile"], cwd=folder, env=env, check=True)
    subprocess.run([bun, "run", "build"], cwd=extension, env=env, check=True)
    subprocess.run([bun, "run", "build"], cwd=ROOT / "src/atopile/layout_server/frontend", env=env, check=True)
    version = json.loads((extension / "package.json").read_text())["version"]
    target = ROOT.parent / f"atopile-local-{version}.vsix"
    subprocess.run(["node", str(extension / "node_modules/@vscode/vsce/vsce"), "package", "--allow-missing-repository", "--no-dependencies", "--out", str(target)], cwd=extension, env=env, check=True)
    print("Extension built:", target)


if __name__ == "__main__":
    main()

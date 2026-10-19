#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Install a verified release outside cloud storage, then hand it to VS Code."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile


class InstallError(RuntimeError):
    pass


MARKER = ".atopile-local-install.json"
ROOT = "atopile-local"
REQUIRED = {
    "local/setup_runtime.py", "local/runtime-lock.txt", "bin/ato-local",
    "src/vscode-atopile/package.json",
}
MANAGED = {".git", ".venv", ".python", ".state", ".runtime-cache", MARKER}


def default_paths() -> tuple[Path, Path]:
    home = Path.home()
    if sys.platform == "darwin":
        app_data = home / "Library/Application Support"
        data, code = app_data / "Atopile Local", app_data / "Code/User"
    elif os.name == "nt":
        data = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "Atopile Local"
        code = Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Code/User"
    else:
        data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "atopile-local"
        code = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "Code/User"
    return data, code / "globalStorage/local-atopile.atopile-local/runtime.json"


def no_symlinks(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise InstallError(f"Refusing symbolic link: {item}")


def atomic_write(path: Path, data: bytes, mode: int = 0o600, *, exclusive: bool = False) -> None:
    no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(mode)
        if exclusive:
            os.link(temp, path)  # Never replace an existing user file.
        else:
            os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode()


def verify_checksum(archive: Path, checksum_file: Path, stream) -> str:
    matches = []
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if match and match[2] == archive.name:
            matches.append(match[1].lower())
    if len(matches) != 1:
        raise InstallError("Checksum file must contain exactly one SHA256 entry for this archive.")
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    if digest.hexdigest() != matches[0]:
        raise InstallError("Archive SHA256 does not match the release checksum.")
    stream.seek(0)
    return matches[0]


def inspect_archive(zipped: zipfile.ZipFile) -> tuple[str, list]:
    files, seen, total = [], set(), 0
    for info in zipped.infolist():
        name = info.filename.rstrip("/")
        parts = name.split("/")
        unsafe = (
            not name or "\\" in name or parts[0] != ROOT
            or any(ord(char) < 32 for char in info.orig_filename)
            or any(p in ("", ".", "..") or ":" in p or p[-1:] in (".", " ") for p in parts)
            or any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p) for p in parts)
        )
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if unsafe or kind not in (0, stat.S_IFDIR, stat.S_IFREG) or info.flag_bits & 1:
            raise InstallError("Archive contains an unsafe path, link, or special file.")
        key = name.casefold()
        if key in seen:
            raise InstallError("Archive contains duplicate or case-colliding paths.")
        seen.add(key)
        if len(parts) == 1:
            if not info.is_dir():
                raise InstallError("Archive root must be an atopile-local directory.")
            continue
        if parts[1] in MANAGED or any(p == ".env" for p in parts):
            raise InstallError("Release archive must not contain runtime state or credentials.")
        total += info.file_size
        if total > 1024 ** 3 or info.file_size > 128 * 1024 ** 2 or len(seen) > 100_000:
            raise InstallError("Archive exceeds installation size limits.")
        files.append((info, Path(*PurePosixPath(*parts[1:]).parts)))
    names = {str(path).replace(os.sep, "/") for info, path in files if not info.is_dir()}
    if not REQUIRED <= names:
        raise InstallError("Release archive is missing required runtime source files.")
    try:
        package = json.loads(zipped.read(f"{ROOT}/src/vscode-atopile/package.json"))
    except ValueError as error:
        raise InstallError("Archive package metadata is not valid JSON.") from error
    if not isinstance(package, dict):
        raise InstallError("Archive package metadata must be a JSON object.")
    version = package.get("version", "")
    valid_version = isinstance(version, str) and re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", version
    )
    if (package.get("name"), package.get("publisher")) != ("atopile-local", "local-atopile") or not valid_version:
        raise InstallError("Archive has an invalid Atopile Local package identity or version.")
    return version, files


def install(archive: Path, checksum_file: Path, *, data_root: Path | None = None, pointer: Path | None = None) -> Path:
    archive, checksum_file = Path(archive), Path(checksum_file)
    default_root, default_pointer = default_paths()
    data_root = Path(data_root or default_root).absolute()
    pointer = Path(pointer or default_pointer).absolute()
    no_symlinks(data_root)
    no_symlinks(pointer)
    original = pointer.read_bytes() if pointer.exists() else None
    try:
        config = json.loads(original) if original is not None else {}
    except ValueError as error:
        raise InstallError("Existing runtime pointer is invalid JSON; it was not changed.") from error
    if not isinstance(config, dict):
        raise InstallError("Existing runtime pointer must be a JSON object; it was not changed.")
    with archive.open("rb") as stream:
        digest = verify_checksum(archive, checksum_file, stream)
        with zipfile.ZipFile(stream) as zipped:
            version, files = inspect_archive(zipped)
            target = data_root / f"runtime-{version}"
            no_symlinks(target)
            identity = {"installer": ROOT, "archive_sha256": digest, "version": version}
            ready = False
            if target.exists():
                marker_path = target / MARKER
                no_symlinks(marker_path)
                try:
                    marker = json.loads(marker_path.read_text())
                except (OSError, ValueError) as error:
                    raise InstallError("Existing runtime directory is not owned by this installer.") from error
                if not isinstance(marker, dict) or any(marker.get(k) != v for k, v in identity.items()) or marker.get("state") not in ("partial", "ready"):
                    raise InstallError("Existing runtime belongs to another archive; it was not changed.")
                ready = marker["state"] == "ready"
            else:
                target.mkdir(mode=0o700, parents=True)
                atomic_write(target / MARKER, json_bytes({**identity, "state": "partial"}), exclusive=True)
            # Resume only this verified archive; never overwrite edited or foreign source.
            for info, relative in files:
                destination = target / relative
                no_symlinks(destination)
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                content = zipped.read(info)
                if destination.exists():
                    if not destination.is_file() or destination.read_bytes() != content:
                        raise InstallError(f"Existing source was modified; refusing to overwrite {relative}.")
                else:
                    mode = (info.external_attr >> 16) & 0o777
                    atomic_write(destination, content, mode or 0o644, exclusive=True)
            atomic_write(target / MARKER, json_bytes({**identity, "state": "partial"}))
    # Do not let an old environment redirect uv/Python or carry AI credentials.
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("PYTHON", "UV_", "ATOPILE_", "FBRK_", "OPENAI_", "ANTHROPIC_", "CODEX_"))
        and key not in {"VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "__PYVENV_LAUNCHER__"}
        and not key.endswith(("_API_KEY", "_TOKEN", "_SECRET", "_SECRET_ACCESS_KEY"))
    }
    env.update(UV_CACHE_DIR=str(target / ".runtime-cache"), UV_PYTHON_INSTALL_DIR=str(target / ".python"), ATOPILE_LOCAL_DATA_DIR=str(target / ".state"), ATOPILE_LOCAL_MODE="1", FBRK_TELEMETRY="0", MPLCONFIGDIR=str(target / ".state/matplotlib"))
    try:
        if not ready:
            subprocess.run([sys.executable, str(target / "local/setup_runtime.py")], cwd=target, env=env, check=True, timeout=1800)
        subprocess.run([str(target / "bin/ato-local"), "self-check"], cwd=target, env=env, check=True, timeout=60, capture_output=True, text=True)
    except (subprocess.SubprocessError, OSError) as error:
        raise InstallError("Runtime setup or health check failed; the previous runtime pointer is unchanged. Retry with the same archive to resume.") from error
    atomic_write(target / MARKER, json_bytes({**identity, "state": "ready"}))
    no_symlinks(pointer)
    if (pointer.read_bytes() if pointer.exists() else None) != original:
        raise InstallError("Runtime pointer changed during installation; it was not replaced.")
    backup = pointer.with_suffix(".previous.json")
    if original is not None and not backup.exists():
        atomic_write(backup, original, exclusive=True)
    config["ato"] = str(target / "bin/ato-local")
    atomic_write(pointer, json_bytes(config))
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--checksum-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        target = install(args.archive, args.checksum_file)
    except (InstallError, OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        return 1
    print(f"Atopile Local is ready at {target}. Reload VS Code to use it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

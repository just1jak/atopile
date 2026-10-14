"""KiCad lifecycle service — launch, focus, and readiness polling."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from atopile.logging import get_logger

log = get_logger(__name__)

_MACOS_KICAD_ROOTS = (
    Path("/Applications/KiCad"),
    Path.home() / "Applications/KiCad",
)


def _clean_env_for_kicad() -> dict[str, str]:
    """Keep the fork's Python runtime out of KiCad's internal scripting.

    KiCad's internal Python scripting breaks when our venv is active,
    so we remove VIRTUAL_ENV and its bin dir from PATH.
    """
    env = dict(os.environ)
    venv = env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    if venv:
        path_dirs = env.get("PATH", "").split(os.pathsep)
        venv_bins = [
            os.path.join(venv, "bin"),  # Linux / macOS
            os.path.join(venv, "Scripts"),  # Windows
        ]
        env["PATH"] = os.pathsep.join(d for d in path_dirs if d not in venv_bins)
    return env


def _find_schematic_editor() -> tuple[Path, bool]:
    """Return (editor path, is_macos_app), preferring KiCad's installed bundle."""
    if sys.platform == "darwin":
        for base in _MACOS_KICAD_ROOTS:
            preferred = base / "KiCad.app/Contents/Applications/eeschema.app"
            candidates = [preferred, base / "eeschema.app"]
            if base.is_dir():
                candidates.extend(sorted(base.glob("**/[Ee]eschema.app")))
            for app in candidates:
                if app.is_dir() and (app / "Contents/MacOS/eeschema").is_file():
                    return app, True
    name = "eeschema.exe" if sys.platform == "win32" else "eeschema"
    executable = shutil.which(name)
    if executable:
        return Path(executable), False
    raise FileNotFoundError(
        "KiCad Schematic Editor (Eeschema) was not found. "
        "Install the KiCad desktop app, or put eeschema on PATH."
    )


def launch_schematic(schematic_path: Path) -> dict[str, Any]:
    """Open a saved native schematic without writing it or the matching PCB.

    Callers must first confine the export path to the selected project. Matching
    sibling filenames describe KiCad's project association, not verified UUID
    linkage or successful cross-probing. Missing desktop apps raise an actionable
    error so an exported file can still be offered for manual opening.
    """
    path = schematic_path.expanduser().resolve()
    if path.suffix.lower() != ".kicad_sch":
        raise ValueError("Select an existing .kicad_sch schematic file")
    if not path.is_file():
        raise FileNotFoundError(f"KiCad schematic does not exist: {path}")
    editor, is_app = _find_schematic_editor()
    env = _clean_env_for_kicad()
    if is_app:
        # LaunchServices supplies the application bundle environment and focuses
        # an existing Eeschema instance. Paths are separate literal arguments.
        completed = subprocess.run(
            ["/usr/bin/open", "-a", str(editor), str(path)],
            capture_output=True,
            env=env,
            timeout=15,
        )
        if completed.returncode:
            raise RuntimeError(
                "KiCad Schematic Editor could not open the schematic "
                f"(exit code {completed.returncode})"
            )
    else:
        process = subprocess.Popen(
            [str(editor), str(path)],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        time.sleep(0.5)
        return_code = process.poll()
        if return_code is not None and return_code != 0:
            raise RuntimeError(
                f"KiCad Schematic Editor exited immediately with code {return_code}"
            )
    pcb = path.with_suffix(".kicad_pcb")
    project = path.with_suffix(".kicad_pro")
    return {
        "status": "launched",
        "schematicPath": str(path),
        "pcbPath": str(pcb) if pcb.is_file() else None,
        "projectPath": str(project) if project.is_file() else None,
        "pcbAssociation": "matching_basename" if pcb.is_file() else "unavailable",
    }


def _launch_pcbnew(pcb_path: Path | None) -> None:
    """Spawn pcbnew as a detached subprocess.

    Raises on immediate spawn failure (binary not found, permission denied).
    """
    from faebryk.libs.kicad.paths import find_pcbnew

    exe = find_pcbnew()
    args = [str(exe)]
    if pcb_path is not None:
        args.append(str(pcb_path))

    log.info("Launching pcbnew: %s", args)
    proc = subprocess.Popen(
        args,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_clean_env_for_kicad(),
    )

    # Brief sleep to catch immediate crashes (binary missing, permission denied).
    import time

    time.sleep(0.5)
    rc = proc.poll()
    if rc is not None and rc != 0:
        raise RuntimeError(f"pcbnew exited immediately with code {rc}")


def _focus_pcbnew() -> None:
    """Best-effort attempt to focus the already-running pcbnew window."""
    try:
        platform = sys.platform
        if platform == "darwin":
            subprocess.run(
                ["osascript", "-e", 'tell application "pcbnew" to activate'],
                capture_output=True,
            )
        elif platform == "win32":
            log.debug("Window focus not implemented on Windows")
        else:
            # Linux (X11 only) — wmctrl may not be installed
            result = subprocess.run(
                ["wmctrl", "-a", "pcbnew"],
                capture_output=True,
            )
            if result.returncode != 0:
                log.warning("Failed to focus pcbnew (wmctrl): %s", result.stderr)
    except Exception:
        log.warning("Failed to focus pcbnew", exc_info=True)


class KicadService:
    """Business logic for KiCad launch/focus orchestration."""

    async def open_schematic(self, schematic_path: Path) -> dict[str, Any]:
        """Open an already exported, project-scoped native KiCad schematic."""
        return await asyncio.to_thread(launch_schematic, schematic_path)

    async def open_kicad(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Check if KiCad is running; focus it or launch + poll for readiness.

        Returns ``{"status": "focused"}`` or ``{"status": "launched"}``.
        Raises on failure.
        """
        from faebryk.libs.kicad.ipc import opened_in_pcbnew

        target = msg.get("target") or {}
        pcb_path_str = str(target.get("pcbPath") or "")
        # pcb_path=None is intentional: kipy's opened_in_pcbnew(None) checks
        # whether *any* KiCad instance is running, which is fine when no
        # specific PCB path is configured for the target.
        pcb_path = Path(pcb_path_str) if pcb_path_str else None

        try:
            already_running = await asyncio.to_thread(opened_in_pcbnew, pcb_path)
        except Exception:
            # Socket exists but KiCad not ready — treat as not running
            already_running = False
        log.info(
            "openKicad: already_running=%s pcb_path=%s",
            already_running,
            pcb_path,
        )

        if already_running:
            await asyncio.to_thread(_focus_pcbnew)
            return {"status": "focused"}

        log.info("openKicad: launching pcbnew directly")
        await asyncio.to_thread(_launch_pcbnew, pcb_path)

        # Poll until pcbnew IPC is responsive (20 × 500ms = 10s)
        ready = False
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                ready = await asyncio.to_thread(opened_in_pcbnew, pcb_path)
                if ready:
                    break
            except Exception:
                # KiCad socket exists but not ready yet — keep polling
                pass

        if not ready:
            raise RuntimeError(
                "KiCad was launched but did not become responsive within 10 s"
            )

        return {"status": "launched"}

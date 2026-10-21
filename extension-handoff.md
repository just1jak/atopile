# Atopile Local source handoff

This checkpoint preserves extension/backend work made after published branch commit `416e37a05a97171db920fcdd25cabcdd6fd37f4d` (the local-runtime installer fix). It does not contain authentication state, private API keys, installed runtimes, or a newly published extension release.

## Versions and status

- Extension identity: `local-atopile.atopile-local`, package version **0.4.1**. The original Mac has that package installed. This checkpoint additionally includes later source changes; a fresh VSIX from this exact checkpoint has **not** been built or installed.
- Native compiler: **atopile 0.15.9** wheel, with this repository's Python source overlay. Do not replace it with the older public upstream source or silently upgrade its wheel.
- Verified backend environment: Apple Silicon macOS, **Python 3.14.6**, **pytest 9.1.1**, and **KiCad 10.0.7**. Native acceptance tests currently discover KiCad at its standard macOS application paths; other operating systems were not validated.
- Extension build helper installs **Bun 1.3.0** when Bun is unavailable. JavaScript dependency versions are locked in the three tracked `bun.lock` files. Node.js/npm and VS Code **1.105+** are required for the documented packaging workflow.
- ChatGPT access uses the installed Codex CLI's native `app-server` authentication. Sign in on the new computer using Codex, or **Atopile Local: Connect ChatGPT**. No account state transfers with Git. API providers use the new computer's VS Code SecretStorage.

## Recovered changes

The canonical source and its Git metadata had many iCloud-offloaded files. This checkpoint was recovered against the fresh remote clone without replacing newer remote installer fixes.

| Source | Files restored |
| --- | --- |
| Healthy installed private engine | `src/atopile/agent/providers/codex.py`, `agent/session.py`, `agent/skills/agent/SKILL.md`, `agent/tools/layout.py`, `model/pcb_transaction.py`, `server/domains/layout.py`, `layout_pcb_manager.py`, `schematic_export.py`, and `src/faebryk/libs/kicad/fileformats.py` |
| Local 0.4.1 build source | `src/vscode-atopile/package.json`, `src/vscode-atopile/src/extension.ts`, and `src/ui/webview/panel-schematic/NativeSchematicPanel.tsx` |
| Resident canonical source / saved test overlay | `test/agent/test_codex_provider_local.py`, `test/agent/test_local_routing.py`, `test/libs/kicad/test_kicad10_compat.py`, and `test/server/test_schematic_existing.py` |

The remote `local/install_local_runtime.py` and `local/launch.py` fixes were preserved. The extension source includes a bounded **180-second core startup window**, while the generic process timeout remains unchanged.

The KiCad 10 adapter applies scoped source-span edits and retains unsupported settings and metadata. It supports existing-footprint placement/rotation, checked simple flips, and track/arc/via updates or deletion plus new straight tracks/through-vias. It rejects unsupported settings, zone/net membership, new-footprint changes, ambiguous flips, locked objects, and `FBRK:notouch` edits. Atomic commit/stale-file guards and backups protect both chat tools and UI save/undo. These are manual routing tools, not an extension-integrated autorouter.

Codex catalog migration keeps old native conversations available while starting a current tool catalog and carrying bounded display history. Tests exercise cancellation, pending tool replies, catalog changes, credential filtering, and native-tool isolation without real model calls.

Saved native schematics can be mapped explicitly through `.atopile-local.json`. Their project-contained hierarchy is validated, read using KiCad, and opened without generation or overwriting existing source. The UI distinguishes saved native files from generated snapshots.

## Continue from source on another computer

Keep this checkout on a fully local disk outside iCloud, OneDrive, or other automatic offload folders. Install VS Code, Node.js/npm, uv, and KiCad separately. Install or sign into a compatible Codex CLI if ChatGPT assistance is wanted.

From the checked-out checkpoint root:

```sh
python3 local/setup_runtime.py
python3 local/build_extension.py
python3 local/install_extension.py
python3 local/launch.py
```

The setup helper recreates `.venv` and the pinned native dependencies. The build helper installs locked JavaScript dependencies, generates protocol types, rebuilds host/webviews/layout assets, and writes `atopile-local-0.4.1.vsix` beside the checkout. The installer registers this checkout's `bin/ato-local` in the new computer's fork-specific VS Code storage. Alternatively set **Atopile Local → Ato** to that absolute launcher path.

Do not use `local/install_extension.py --download` or install an older release source archive to reproduce this newer source checkpoint: those fetch released artifacts. Do not copy an old computer's absolute `runtime.json` pointer or `.venv`; regenerate them locally.

The tracked assets needed for rebuild are present: OCCT WebAssembly, model-viewer JavaScript, logos, decoder notices, and locked dependencies. The Draco decoder and Three.js license are copied from the installed dependency during build. Generated `dist/`, `webview-dist/`, layout bundles, `.vsix`, `node_modules`, `.venv`, `.python`, `.state`, and caches are intentionally not source-controlled.

## Fresh checkpoint validation

**114 passed in 14.71 seconds** on 2026-10-20 using the recovered source and existing pinned private Python environment. Four marker-registration warnings came from running this isolated subset with an empty pytest configuration; no test failed. This command used local fake provider transports and native temporary-board acceptance checks; it made no model requests and did not modify the scanner project.

After setting up a local runtime, the equivalent command from this repository root is:

```sh
PYTHONPATH="$PWD/src" \
ATOPILE_LOCAL_DATA_DIR="$PWD/.state/checkpoint-tests" \
FBRK_TELEMETRY=0 ZIG_NORECOMPILE=1 PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -P -m pytest -c /dev/null -p no:cacheprovider -q \
    test/agent/test_codex_provider_local.py \
    test/libs/kicad/test_kicad10_compat.py \
    test/agent/test_local_routing.py \
    test/server/test_schematic_existing.py
```

`git diff --check` passed for recovered extension/source/test changes. The full frontend dependency install, TypeScript checks, complete compiler suite, GUI workflow, and new VSIX package were not rerun as part of the transfer checkpoint. Prior installed-package behavior is separate from this fresh source validation. No physical hardware test was performed.

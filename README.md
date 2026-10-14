# Atopile Local 0.3.1

A local VS Code continuation of atopile 0.15.9 with a KiCad-symbol schematic
viewer, ChatGPT through Codex or your own AI provider, local component imports,
and net/placement/DRC tools. This is an independent
fork, not an official atopile release.

## Start on this Mac

On this Mac, double-click **Open Atopile Local.command** beside the source
folder. It opens the included circuit in VS Code. Select the build target and
choose **Inspect → Schematic**. Other inspection views remain available beside it.

For a new installation, install the supplied `atopile-local-0.3.1.vsix` and open the supplied
`Atopile Local.code-workspace`. The provided installer registers the runtime
for other VS Code workspaces too. ChatGPT (Codex) is the default AI provider.
Run **Atopile Local: Connect ChatGPT** to reuse your local Codex sign-in or start
Codex's browser sign-in. No separate API key is needed. Your ChatGPT plan's
Codex usage limits apply; this does not grant unlimited usage or add credits.

The connection uses the official local `codex app-server` interface. Codex owns
sign-in, credential storage, and renewal. Atopile Local does not copy account
tokens into its settings or webviews. It requires ChatGPT authentication and
will not silently switch to API billing. The compiler and circuit tools still
run locally; prompts and tool results go to OpenAI for AI assistance.

Use **Atopile Local: Configure AI Provider** to select a separate OpenAI-compatible
or Anthropic provider instead, then **Atopile Local: Set AI API Key** to store that
provider's key in VS Code. Optional `atopileLocal.agent.codexPath` selects a Codex
executable; leave it blank for automatic discovery. A blank model uses Codex's
default model when ChatGPT is selected.

The compiler, parts, and viewers work without AI. API providers require their
own key; a loopback model server may omit a key. OpenAI-compatible
endpoints must implement the Responses API, streaming, and tool calls. Datasheet
file search also requires Files/Vector Stores support. A Chat Completions-only
server is not supported by this release. Leave the endpoint blank for the
selected provider's default; custom Anthropic endpoints use the API origin
rather than an OpenAI-style `/v1` suffix. Your provider's prices/limits apply.

## Portable setup

Requires VS Code 1.105+, uv, and KiCad for native layout/DRC. ChatGPT assistance
also requires a Codex CLI with app-server dynamic tools and a ChatGPT plan that
includes Codex access. Tested on Apple
Silicon macOS with Python 3.14.6 and KiCad 10.0.7. The launcher is POSIX (macOS
and Linux); Windows launcher packaging is not included.

```sh
python3 local/setup_runtime.py
python3 local/install_extension.py --download
python3 local/launch.py
```

Download the source and extension from the
[GitHub release](https://github.com/just1jak/atopile/releases/tag/local-v0.3.1),
or clone the fork's `feature/atopile-local` branch. `--download` fetches the
matching extension release and verifies its SHA-256 before installation. If
the VSIX is already beside the source folder, omit `--download`.
To open another existing project, use `python3 local/launch.py /path/to/project`.

```sh
git clone --branch feature/atopile-local https://github.com/just1jak/atopile.git
cd atopile
```

The native compiler is the pinned atopile 0.15.9 wheel. Modified Python source
runs over that wheel, avoiding a local Zig rebuild. The wrapper uses safe
Python import precedence and stores fork state in `.state/`; it disables atopile
telemetry and migration-notice requests. The runtime handoff goes in this fork's
own VS Code global storage and does not alter official atopile settings.

## Local design workflow

```sh
bin/ato-local build examples/offline-indicator --target default
bin/ato-local create part-from-kicad --help
bin/ato-local create part-from-pinout --help
```

Open the **Atopile Local** activity-bar view to build, browse components and
nets, inspect pinouts, and open the PCB/3D viewers. The independent agent can
edit project files, build and debug circuits, read logical nets, inspect or
change placements (with backups), and run KiCad DRC.

## Board access in chat

The chat identifies itself as **Atopile Local** and shows its configured AI
provider. Before each message, the host checks the session's selected PCB with
the local inspection tool. **Board last read** reports the checked target,
part count, and net count. A failed check shows the actual error.

The agent can read placement and logical nets, move components with backups,
and run KiCad DRC. Placement changes preserve existing tracks but do not reroute
them. Ask it to inspect the board first, state any fixed connector positions
and board dimensions, and review DRC after moving parts.

Version 0.3.1 fixes Codex tool discovery for the full production tool catalog.
After updating, reload the VS Code window so the backend and tool bridge restart.
Existing chat history is retained.

## Schematic viewer

After building, open **Inspect → Schematic**, or run **Atopile Local: Open Panel**
and select **Schematic**. The canvas reads the PCB's actual pad-net assignments
and uses local KiCad symbol artwork. Select a net to highlight its wires and
connected pins. Select a component to inspect its pins and values, jump to its
source declaration, or open the PCB with the matching footprint highlighted.
The selected net can also be highlighted in the PCB view.

The schematic refreshes after builds and project/target changes. Pan, zoom,
fit-to-view, and net search are available. Missing artwork is marked explicitly
and displayed as a pin box. Symbol availability does not invent connections.
Power/data Trees remain separate views and may be empty for generic parts.

This version is a read-only schematic projection, not a schematic editor or
`.kicad_sch` exporter. Its wiring describes logical connections; it does not
represent physical PCB trace routes or replace electrical validation. Only
the included small demo has been tested end to end.

The routed offline indicator has three local components, three nets, and a
32 x 18 mm outline. Its layout is a specific hand-authored recipe. Generic
local parts are included in the JSON BOM; unsourced parts are excluded from the
JLCPCB assembly CSV. See `examples/offline-indicator/README.md`.

## Service boundaries

Local builds with locally imported parts do not need atopile sign-in. Automatic
online component selection still uses atopile's service and requires sign-in.
DeepPCB automatic placement/routing remains hosted and is labeled in the UI;
no general local autorouter is included. Web search uses your own `EXA_API_KEY`.
Manual local layout and local agent placement/DRC do not use those services.
Native footprint locks cannot be safely round-tripped by the bundled parser,
so the placement tool refuses boards containing them.

## Rebuild and verify

```sh
python3 local/build_extension.py
PYTHONPATH=$PWD/src ATOPILE_LOCAL_DATA_DIR=$PWD/.state FBRK_TELEMETRY=0 \
  .venv/bin/python -m pytest test/agent test/libs/test_kicad_part_import.py \
  test/exporters/pcb/kicad/test_pcb_transformer.py -q
.venv/bin/python local/verify_backend.py
python3 local/verify_offline.py
```

The verification record is `local/VERIFICATION.json`; demo connectivity and DRC
reports are under `examples/offline-indicator/`. No physical hardware test was
performed. Only the included small example was exercised end
to end; passing DRC does not verify electrical behavior or supplier suitability.

## Source and licenses

Based on the public PyPI atopile 0.15.9 source distribution, SHA-256
`681cc1e123646dd133de31b631aedaf4eaac88682613b4f82d1da4b3ef8b4e8e`.
Upstream MIT notices are retained; local import work retains the Axiovel MIT
attribution in `local/IMPORTER_ATTRIBUTION.md`. Bundled 3D decoders include their
Apache-2.0 notices and Three.js MIT license. The original README is preserved
at `local/UPSTREAM_README.md`. The three standard KiCad demo symbols retain
their CC-BY-SA 4.0 library license and exception in
`examples/offline-indicator/assets/KICAD-SYMBOLS-LICENSE.md`.

Codex-managed ChatGPT authentication is documented for local/open-source apps.
This integration is for local use; a hosted or commercial service needs its own
supported sign-in integration. See [OpenAI's app-server documentation](https://learn.chatgpt.com/docs/app-server).

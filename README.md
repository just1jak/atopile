# Atopile Local 0.4.1 source checkpoint

**Moving to another computer? Start with [CONTINUE-HERE.md](CONTINUE-HERE.md).**
It covers this source checkpoint and the unfinished integrated-SD scanner PCB.

A local VS Code continuation of atopile 0.15.9 with native KiCad schematic
export, ChatGPT through Codex or your own AI provider, local component imports,
and net/placement/DRC tools. This is an independent
fork, not an official atopile release.

This checkpoint preserves the 0.4.1 source and subsequent local KiCad 10
editing, Codex tool-catalog, and startup fixes. The installed extension on the
original Mac reports 0.4.1; this newer source checkpoint has not been packaged
as a new release. Its focused backend checks passed **114 tests**. See
[extension-handoff.md](extension-handoff.md) for exact recovery and rebuild steps.

## Start on this Mac

On this Mac, double-click **Open Atopile Local.command** beside the source
folder. It opens the included circuit in VS Code. Select the build target and
choose **Inspect → Schematic**. Other inspection views remain available beside it.

For this checkpoint, rebuild and install from the checked-out source using the
steps in `extension-handoff.md`. An older downloaded release archive installs
that release's source rather than these later changes. The installer registers
the runtime for other VS Code workspaces too. ChatGPT (Codex) is the default AI provider.
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

Requires VS Code 1.105+, uv, and KiCad for native schematic export, layout and DRC. ChatGPT assistance
also requires a Codex CLI with app-server dynamic tools and a ChatGPT plan that
includes Codex access. Tested on Apple
Silicon macOS with Python 3.14.6 and KiCad 10.0.7. The `.command` launcher is
for macOS; Linux can use `python3 local/launch.py`. Windows launcher packaging
is not included.

Keep the engine outside iCloud, OneDrive, and other folders that automatically
offload files. The current fork includes a verified installer that puts it in
local application storage (on macOS, `~/Library/Application Support/Atopile Local`).
Download the release source ZIP, `SHA256SUMS.txt`, and VSIX, then run this from
the fork checkout:

```sh
python3 local/install_local_runtime.py \
  --archive /path/to/atopile-local-source.zip \
  --checksum-file /path/to/SHA256SUMS.txt
python3 local/launch.py
```

Download the source and extension from the
[GitHub release](https://github.com/just1jak/atopile/releases/tag/local-v0.4.0),
or clone the fork's `feature/atopile-local` branch for the installer. Before
launching, install the VSIX using VS Code's **Extensions: Install from VSIX**
command. The installer verifies the archive, installs pinned dependencies,
and checks startup before changing VS Code's runtime location. Failed setup
keeps the previous location; retrying the same archive resumes setup.
To open another existing project, use `python3 local/launch.py /path/to/project`.

```sh
git clone --branch feature/atopile-local https://github.com/just1jak/atopile.git
cd atopile
```

For this source checkpoint, use a fully local checkout, run
`python3 local/setup_runtime.py`, rebuild with `python3 local/build_extension.py`,
then install using `python3 local/install_extension.py`. Do not use `--download`
when you intend to run the checkpoint source and its rebuilt UI.

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
change placements (with backups), add or delete copper, and run KiCad DRC.

## Board access in chat

The chat identifies itself as **Atopile Local** and shows its configured AI
provider. Before each message, the host checks the session's selected PCB with
the local inspection tool. **Board last read** reports the checked target,
part count, and net count. A failed check shows the actual error.

The agent can read placement and logical nets, move or rotate unlocked
components, add straight track segments and through-vias, delete copper by
UUID, and run KiCad DRC. Placement changes preserve existing tracks but do not
reroute them. Copper tools require explicit net, canonical copper layer, and
geometry; creating a segment does not prove its clearance or complete routing.
Ask it to inspect the board first, state any fixed connector positions and
board dimensions, and review native DRC after edits.

KiCad 10 edits preserve unsupported source fields and unrelated native locks.
Locked targets and `FBRK:notouch` geometry are protected. The scoped editor
supports placement and copper changes; settings, net membership, zone changes,
new footprints, and complex flips remain native KiCad work. Stale external
changes are rejected instead of overwritten, and successful edits create
backups. Save edits in KiCad before switching editors.

Version 0.3.1 fixes Codex tool discovery for the full production tool catalog.
After updating, reload the VS Code window so the backend and tool bridge restart.
Existing chat history is retained.

## Schematics in KiCad

After building, open **Inspect → Schematic** and choose **Open in KiCad**.
If the project has a native schematic, explicitly map it to the build target
in `.atopile-local.json`:

```json
{"schematics": {"v240": "elec/schematic/ChryslerScanner_V240.kicad_sch"}}
```

Normal opening preserves that file and all child sheets. Paths must remain
inside the selected project; the hierarchy is validated before native KiCad
reads it. The app does not guess which existing schematic belongs to a target.

For projects without a mapping, Atopile Local saves a real `.kicad_sch` file, with embedded KiCad symbols and
nets taken from the PCB's actual pad assignments, then opens KiCad's Schematic
Editor. KiCad must be installed: each new snapshot is checked using its native
netlist exporter. The saved file remains available if the editor cannot launch.

The panel shows the saved file's location. Reopening the same circuit revision
uses the saved file, preserving edits made in KiCad. **Generate new from circuit**
creates a separate snapshot and opens it; it never overwrites an earlier file.
Exports live under the selected target's build output in a `schematic` folder.
Keep a copy outside `build/` before cleaning build artifacts.

This is a code-to-schematic export: edits in KiCad do not update `.ato` source.
The existing PCB is left in place. Source and PCB footprint identifiers are
included as symbol properties, but native KiCad PCB cross-probing/relinking is
not established by this export. Missing symbols, unsupported multi-unit parts,
and ambiguous pin mappings stop export with a specific error. This initial
exporter supports up to 256 components per snapshot.

**Preview connections** opens the optional inline preview with net highlighting
and links to source declarations and the PCB view. Its wiring describes logical
connections rather than physical PCB trace routes. Power/data Trees remain
separate views and may be empty for generic parts.

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
The KiCad 10 source-preserving adapter retains native locks and rejects edits
to locked targets. Unsupported changes stop with an error rather than dropping
unknown native fields.

## Rebuild and verify

```sh
python3 local/build_extension.py
PYTHONPATH=$PWD/src ATOPILE_LOCAL_DATA_DIR=$PWD/.state FBRK_TELEMETRY=0 \
  .venv/bin/python -m pytest test/agent test/libs/test_kicad_part_import.py \
  test/exporters/pcb/kicad/test_pcb_transformer.py -q
.venv/bin/python local/verify_backend.py
python3 local/verify_offline.py
```

The recovered checkpoint passed 114 focused backend tests, including native
KiCad edit/connectivity checks and mocked Codex protocol checks, on 2026-10-20.
The full frontend dependency install, TypeScript checks, and VSIX rebuild were
not repeated for this checkpoint. See `extension-handoff.md` for the exact test
command and the distinction from older release verification.

The earlier verification record is `local/VERIFICATION.json`; demo connectivity and DRC
reports are under `examples/offline-indicator/`. No physical hardware test was
performed. Passing DRC does not verify electrical behavior or supplier suitability.

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

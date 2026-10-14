# Offline indicator example

A self-contained, generic 3.3 V LED indicator: a two-pin input connector, a
330 ohm axial resistor, and a 5 mm through-hole LED. All three parts have local
source, symbol, and footprint files. Compilation uses no online component picker.

The layout is a 32 × 18 mm two-layer board with three placed parts and nine
hand-authored track segments. `apply_demo_layout.py` documents this particular
layout recipe; it is not a general autorouter.

From the fork root, run:

```sh
bin/ato-local build examples/offline-indicator --target default
```

The editable PCB is `layouts/default/default.kicad_pcb`. The JSON BOM under
`build/builds/default/` includes all three local parts. The JLCPCB-specific CSV
excludes these parts because no real LCSC selections were supplied.

To regenerate this example's explicit layout after starting from a blank board:

```sh
PYTHONPATH=src .venv/bin/python examples/offline-indicator/apply_demo_layout.py
```

The local importer also supports your own existing KiCad libraries:

```sh
bin/ato-local create part-from-kicad \
  --symbol /path/to/library.kicad_sym --name SymbolName \
  --footprint /path/to/Footprint.kicad_mod \
  --manufacturer Manufacturer --partnumber PartNumber \
  --project-dir /path/to/project
```

For a footprint without an available symbol, `create part-from-pinout` accepts
repeated `--pin NUMBER:NAME` mappings. It creates a box symbol and rejects pins
without corresponding footprint pads. A real LCSC ID can optionally be recorded
with `--supplier-partno C12345`; that is an explicit user selection, not online
qualification or a stock check.

Verification: the local compiler built the design with an IP-network guard;
KiCad DRC reported zero violations and zero unconnected items for the supplied
layout. The generic part dimensions and electrical behavior have not been
physically tested. This is a manual-assembly demonstration, with no claim of
verified supplier stock, part certification, or fabrication readiness. Verify
the actual resistor rating, LED polarity/forward voltage, footprint dimensions,
and connector pinout against the components you plan to use.

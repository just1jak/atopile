# Rev C native validation sources

`verify_safety_revision.py` is the primary portable release guard. Run it with KiCad 10 Python from any working directory; its default project is this source folder’s parent. It reads only bundled source helpers and reference/pre-p1 baselines. It never saves CAD. A release pass requires fresh complete native DRC/ERC/XML, the current PCB hash, exact endpoint/value/rating/hierarchy contracts, frozen physical preservation and full native connectivity. Structural-only mode cannot authorize release.

After editing, refill/save zones deliberately, export a fresh native XML and all-severity ERC/DRC including track checks and schematic parity, then run the verifier. CAD checks do not establish automotive or thermal qualification. See ../reference/rev-c-safety-contract.md. Historical source scripts and historical-pre-rev-c reports are retained for provenance; their hardcoded older counts and acceptance hashes must not be used to certify Rev C.

`package_rev_c.py --output /absolute/path/to/new-package` regenerates local fabrication/project exports only after those checks and the final adversarial review pass. Run it with KiCad Python. The output directory and ZIP names must be new. It does not upload, order or commit anything.

Current accepted contract: 277 electrical parts, 23 old-value changes, 15 original endpoint changes, 162 connected nets, 40 NC pins, 168 hierarchy ports and 55 original safety copper removals plus two unlocked C61 branch segments. Only C61 moves: top side at (193,127) mm, 90 degrees. Every other original placement remains fixed. GPIO13/pad20 ACT_LED is dedicated software health heartbeat; GPIO2/pad22 is original NC. Speculative C31/R106/IO0/SD routing exceptions were rejected and are not accepted contracts. The final55 removal manifest is reference/pre-p1/allowed-copper-removals-final55.json.

The strict verifier also invokes verify_c61_top.py, which binds the exact pre-move PCB hash and permits only C61’s declared transform, four tracks, two processed vias and the two removed tracks.

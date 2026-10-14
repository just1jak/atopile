# Local KiCad importer attribution

The local KiCad symbol/footprint and pinout importer is adapted from
[Axiovel-tech/atopile](https://github.com/Axiovel-tech/atopile/tree/AV-dev-1.0),
branch `AV-dev-1.0`, commit `b8f1143b203496add0675573967f52acbd48c553`.

Adapted files:

- `src/faebryk/libs/kicad_part_import.py`
- `src/faebryk/libs/kicad/sexp_tools.py`
- The `part-from-kicad` and `part-from-pinout` commands in
  `src/atopile/cli/create.py`

This port adds explicit local supplier identity, pin/pad consistency checks,
quoted-name handling, and focused regression tests. The circular-silkscreen
bounding fix and offline indicator assets/layout recipe are local additions.
The demo CAD assets are original, generic examples; no external KiCad library
assets or component inventory records are bundled with that example.

The original source is MIT licensed. Its SPDX notices and the project's MIT
license are retained. The applicable license text follows.

MIT License

Copyright (c) 2024 atopile

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

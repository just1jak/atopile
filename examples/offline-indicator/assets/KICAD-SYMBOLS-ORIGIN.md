# KiCad symbol artwork

The demo's resistor, LED, and connector symbols are derived from the KiCad
community symbol libraries included with KiCad 10.0.7 for macOS:

| Demo file | Original library symbol |
| --- | --- |
| `Resistor330R.kicad_sym` | `Device:R_US` |
| `LED5mm.kicad_sym` | `Device:LED` |
| `Input2.kicad_sym` | `Connector_Generic:Conn_01x02` |

The upstream libraries are maintained at
<https://gitlab.com/kicad/libraries/kicad-symbols> by the KiCad community.
They use CC-BY-SA 4.0 with the KiCad libraries exception; see the accompanying
`KICAD-SYMBOLS-LICENSE.md`. This attribution and license apply to both the
copies here and the corresponding copies in `../parts/Local_*/`.

Changes: renamed symbol and unit names and the Value property to match the
local demo parts, converted pin-number visibility syntax, and serialized through
the bundled parser for compatibility. Electrical pin numbers and artwork were
preserved. The physical footprints are the existing local demo footprints.

The extension's source code retains its separate MIT license.

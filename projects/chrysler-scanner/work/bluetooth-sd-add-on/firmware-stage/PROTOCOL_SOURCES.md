# Protocol and decoder provenance

Retrieved 2026-10-20 from the scanner author's public repository. The code is
licensed under GPL version 3; the upstream license is included in `LICENSE`.
Selected broadcast conversion formulas and CRC behavior were adapted from
ChryslerScanner by Laszlo Daniel (`laszlodaniel`). This is a narrow C++ port with
additional strict bounds/checks, not a copy of the whole desktop client.

## Current V2 wire protocol

[Official V2 API, pinned commit bfc3451ba7962f681186dc9efee03068e9c92687](https://github.com/laszlodaniel/ChryslerScanner/blob/bfc3451ba7962f681186dc9efee03068e9c92687/Documentation/ChryslerScanner_V2_API_Reference.md)

* Sections 2–3: NUS UUIDs, MTU recommendation, sync `3D`, big-endian length,
  routing direction/bus/command, additive checksum including sync. Length includes
  routing and mode but excludes sync, length word, and checksum; total = length+4.
* Section 6: handshake payload is the 15-byte ASCII `CHRYSLERSCANNER`; Status is
  exactly 45 bytes with big-endian counters and current bus settings.
* Section 7: settings are echoed and saved in NVS. Internal Settings command 3,
  mode 2 enables CCD; mode 6 enables PCI; bit 7 is enable. SCI mode 3 additionally
  chooses target/polarity/pin routing/baud, so is deliberately not generated here.
* Section 10.1: an enabled bus pushes RX command 7 asynchronously. The first four
  payload bytes are scanner-uptime milliseconds; the remaining raw message includes
  its bus checksum/CRC. Modes 1/2 mean low/high-speed RX (high speed is SCI only).

The current published API is the wire authority. The old experimental Python
script starts its outbound checksum at byte 1, unlike the current API and the
historical GUI serializer (which include byte 0). It is not used as a wire template.
Current V2 ESP32 source/desktop client are not fully published; actual installed
firmware and BLE throughput must be validated on hardware before readiness claims.
No mandatory advertising name, client concurrency, authentication, or an explicit
"receive-only safety mode" is documented. Enabling a bus is not a hardware TX lock;
this logger's outbound control allowlist prevents its own vehicle transmissions.

Saved reference: `research/ChryslerScanner_V2_API_Reference.md`
SHA-256 `228a156b9bc43a0e909d112cea8274b1106b5567d9ff631110777c64243bf375`.

## Concrete passive decoder subset

The last public GUI source before the December 2023 codebase change is commit
`8e632c7a1144873db60d0614810417855c54a059` (2023-07-08). Later main-tree GUI folders
contain packaged binaries and assembly metadata rather than these decoder files.

| Bus / first ID byte | Exact raw length including checksum | Selected conversion | Pinned source |
|---|---:|---|---|
| PCI `10` | 7 | engine BE16 bytes1–2 ×0.25 rpm; speed BE16 bytes3–4 ×0.0049 mph, converted to km/h; MAP byte5 kPa | [PCI.cs lines103–117](https://github.com/laszlodaniel/ChryslerScanner/blob/8e632c7a1144873db60d0614810417855c54a059/GUI/ChryslerScanner/PCI.cs#L103-L117) |
| PCI `C0` | 6 | battery byte1 ×0.0625 V; oil byte2 ×0.5 psi; coolant byte3−40 C; ambient byte4−40 C | [PCI.cs lines903–915](https://github.com/laszlodaniel/ChryslerScanner/blob/8e632c7a1144873db60d0614810417855c54a059/GUI/ChryslerScanner/PCI.cs#L903-L915) |
| CCD `0C` | 6 | battery byte1 ×0.125 V; oil byte2 ×0.5 psi; coolant byte3−64 C; ambient byte4−64 C | [CCD.cs lines198–210](https://github.com/laszlodaniel/ChryslerScanner/blob/8e632c7a1144873db60d0614810417855c54a059/GUI/ChryslerScanner/CCD.cs#L198-L210) |
| CCD `24` | 4 | byte2 km/h (byte1 is the separate mph value) | [CCD.cs lines410–418](https://github.com/laszlodaniel/ChryslerScanner/blob/8e632c7a1144873db60d0614810417855c54a059/GUI/ChryslerScanner/CCD.cs#L410-L418) |
| CCD `E4` | 4 | byte1 ×32 rpm; byte2 ×0.1217 ×0.4911542 psi, converted to kPa | [CCD.cs lines2573–2582](https://github.com/laszlodaniel/ChryslerScanner/blob/8e632c7a1144873db60d0614810417855c54a059/GUI/ChryslerScanner/CCD.cs#L2573-L2582) |

Oil pressure uses upstream psi→kPa factor `6.894757`; PCI speed uses mph→km/h
factor `1.609344`. Values remain unrounded in the library. The upstream GUI accepts
minimum lengths; this port intentionally requires the exact listed broadcast shape.

The [upstream Util.cs checksum/CRC functions](https://github.com/laszlodaniel/ChryslerScanner/blob/8e632c7a1144873db60d0614810417855c54a059/GUI/ChryslerScanner/Helpers/Util.cs#L239-L283)
establish additive CCD checksum and CRC-8/SAE-J1850 (polynomial `1D`, initial `FF`,
final xor `FF`, no reflection). This port additionally verifies the bus checksum
before producing any selected value. Outer frame checksums are checked first.

These are Chrysler broadcast definitions from historical upstream software.
Availability and accuracy on early-2004 automatic Cummins CM848B/15235133AJ or any
other specific vehicle are **not bench verified**. There are no generic CAN/OBD PID
substitutions. Unknown broadcasts and all SCI data remain raw. SCI sensor pages
in upstream source depend on controller/year, prior requests, speed, and session
state; interpreting them without that context is deliberately excluded.

Reference SHA-256:

* `CCD.cs`: `3705641e3e7441cbc6c7f5ff235cb9eb6ef9203abfe912acf8ddd03c799966ca`
* `PCI.cs`: `d9bca179c9b1494f766ec137842747688a4bdce43fa6cbb19769ae96a94b4343`
* `Helpers-Util.cs`: `bba2b3a2689fbf3bd8470f03b829767d84c3bcecfc2c8102d2ebd0e12b154682`

`research/` is development evidence, not required by firmware. Preserve this
attribution and `LICENSE` when integrating the portable source.

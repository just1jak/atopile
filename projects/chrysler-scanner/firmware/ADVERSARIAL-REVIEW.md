# Firmware adversarial review: 0.1.1

Date: 2026-11-06. Scope: safety controls and passive USB/SD capture for the
accepted Rev C native board. Reviewed by an independent reviewer agent, followed
by fixes, regression tests and a revised-source pass. No hardware was flashed or
measured. The fabrication release remains unchanged.

## Findings and fixes

| ID | Severity | Finding | Resolution and regression coverage |
| --- | --- | --- | --- |
| FW-01 | P1 | Stop status advertised idle before SD flush/close; slow mount/open also left an unsafe idle window | `StorageGate` request/claim/busy publication uses one lock. Busy spans mount/open through close/unmount. Completion is published last, including errors. Client waits for its ACK and a newly queried requested=0/busy=0/logging=0/error=0 status. Tests cover both mount/stop interleavings, every stop cleanup failure stage, stale pre-ACK status and slow mount/close responses. |
| FW-02 | P2 | UART overflow/read loss could accept a checksum-valid suffix as a full frame | `Burst` quarantines unknown prefixes at startup, reconfiguration and gaps until a trustworthy timeout. Read deficits return without using that suspect event's timeout. Tests feed checksum-valid suffixes after gaps and overlength input. |
| FW-03 | P2 | IDF queues timeout data before error events; default interrupts omit frame errors | Capture ISR and consumer share core 1; frame-error interrupts are explicit. Static bounded `BurstBatch` completions are revoked on errors, then published only after the event batch is checked. Full-check/pop is atomic against the same-core producer. RX/error interrupts are masked during ring/event reset. Tests cover DATA(timeout) then FRAME_ERR, read deficits, quarantine and recovery. |
| FW-04 | P2 | SCI logs omitted selected OBD pin and baud | Protocol revision 2, raw mode 0x92 embeds physical pin and baud index in every SCI record. Raw SCI payload limit is 254 bytes to preserve the 266-byte maximum packet. C++ serialization and Python recording/replay tests distinguish identical bytes captured on different routes/speeds. |
| FW-05 | P2 | Coalesced GPIO IRQs could be treated as valid PCI pulses | Same-level samples and non-increasing timestamps reset VPW decoding and count a discontinuity. Tests reject these intervals; physical IRQ timing remains a bench gate. |
| FW-06 | P2 | Plausible truncated packet headers could hide valid replies indefinitely | Host and device parsers expire stalled heads, scan later syncs for complete validated packets and discard incomplete remnants. Tests cover a complete response/command behind a false long header on a quiet link. |
| FW-07 | P2 | Modification times did not prove that packaged source matched compiled code | `tools/build.py` cleans the target, snapshots declared input hashes before/after a successful build and records image/config hashes. Export validates the stamp with non-removable checks. Tests reject source edits with backdated mtimes, edits during the build window and changed image bytes. |

All seven findings are closed in the revised source. The independent final pass
identified **no remaining P1/P2 software findings within the passive bench-prototype
scope**, conditional on the final clean build and checks passing. The accompanying
`evidence/validation.json` records the checked source and image hashes and results.

Dedicated GPIO13 ownership, worker fault latching, expander safe masks/order,
package-pin guard and rejection of active vehicle commands remain intact. Stop
requests remain permitted in a fault state; start and SCI configuration require
ready/nonfaulted operation. No active diagnostic/programming path was added.

## Remaining qualifications

This source review is not vehicle approval. Reset-state bias/termination loading,
actual TX passive voltages, UART/PCI timing under load, GPIO edge-capture latency,
watchdog release, SD card latency/power loss and supply/thermal behavior still
require the measurements in `VALIDATION.md`. CRC and source review cannot prove
physical waveform integrity or filesystem survival during power loss.

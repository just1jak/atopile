# Portable Chrysler Scanner V2 protocol and broadcast decoders

C++17 with no Arduino, BLE, SD, operating-system, or third-party library dependency.
See `include/chrysler/protocol.hpp`; link `src/protocol.cpp` into the logger firmware.
`SOURCES.md` records the exact upstream sources and compatibility limits.

## Integration

1. Restrict the connection to the configured scanner address, discover the NUS service,
   subscribe to its notification characteristic, and negotiate the local BLE MTU.
   The official API does not specify an advertising name or bonding/PIN scheme.
2. Use `build_read_request` for Handshake, HardwareFirmwareInfo, and Status. Feed all
   incoming chunks to one `StreamParser` for that connection. Require the exact V2
   handshake before sending configuration. Retain the firmware identity in metadata.
3. Read fresh Status and, for explicitly requested CCD/PCI buses that are disabled,
   call `build_receive_enable_request`. This sets only enable bit 7 and preserves
   other bits. Wait for the echoed settings response, then read Status again and
   require the enable bit. Settings persist in scanner NVS, so do not write them
   repeatedly. No vehicle Message TX, diagnostic polling, reset, bootloader, emulator,
   file, or voltage commands are exposed by this library.
4. A valid message on an enabled bus is pushed automatically. The API has no separate
   receive-start command. If no packets arrive, report an enabled-but-idle bus; do not
   claim that the vehicle is connected or that recording is capturing traffic.
5. Call `decode_receive` for automotive packets and `decode_metrics` with the explicit
   configured profile. Raw frames are preserved even for unknown modes/messages.

SCI raw RX is understood for both PCM/TCM and low/high speed, but this library does
not change SCI enable/baud/polarity/routing/target. That setup needs an exact vehicle
profile and deliberate configuration; generic SCI settings are unsafe to infer.

`UpstreamBroadcast2023` is an explicit set of historical upstream client formulas,
not a claim of validation on a particular vehicle. A product configuration should
name that profile openly when selected. The API's `None` value is available for raw
capture and must not be substituted silently for a requested decoded-values mode.

## Capture and gaps

BLE notifications can split a frame anywhere or contain several frames. Preserve
notification chunks in the transport journal before parsing, then keep each Packet
event's original `frame.raw` in the packet journal. Rejecting a checksum never erases
the original bytes from the transport journal. `ParseEvent.bytes` supplies evidence
for rejected/pending data; resynchronization diagnostics can overlap those bytes.

Call `notify_loss(observed_drop_count)` for every known input queue/transport gap;
zero means an unknown drop count. It clears any partial frame to avoid joining data
across the gap. Call `finish()` on disconnect/stop or an explicit partial-frame idle
deadline. A truncated frame is reported before clearing. A corrupt plausible length
can delay resynchronization until enough bytes or that deadline; framing is not
cryptographic authentication. Callbacks are synchronous and must enqueue quickly;
do not recursively call the parser from a callback.

The parser holds at most the configured maximum packet size (default 4096; a local
defensive bound, not a documented V2 wire maximum). The format's absolute maximum
is 65539. The source API mentions a 1024-byte buffer for some operations, not a
general maximum for every response. Rejects and local truncations are explicit.

Scanner timestamps are unsigned 32-bit milliseconds since boot, big-endian. Preserve
them unchanged; they wrap after about 49.7 days. Reconnect/reset/wrap need distinct
session events. Raw frames have no scanner sequence number: do not infer a precise
number of lost vehicle messages from BLE delivery or a time gap. Status RX counters
can support a separately qualified loss estimate, with wrap/reset handled.

## Host validation

```sh
c++ -std=c++17 -Wall -Wextra -Wpedantic -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -I include src/protocol.cpp tests/protocol_test.cpp -o protocol_test
./protocol_test
```

Alternatively use CMake/CTest. Test packets are synthetic protocol vectors, not
vehicle captures. Tests exercise official literal framing/handshake bytes, every
split boundary, coalesced frames, corruption/resync, bounded input, truncation and
known gaps, endianness, strict lengths, safe control allowlists, checksum rejection,
explicit profile selection, and source-based selected-value formulas.

No firmware was flashed, no scanner connected, and no vehicle traffic transmitted.

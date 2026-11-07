# Rev C passive firmware, 0.2.0

First board-specific source port for the accepted ESP32-PICO-V3-02 scanner.
This is a bench-development image: software checks do not establish physical
safety, lossless capture, electrical compatibility or vehicle qualification.
No board has been flashed or tested by this work. CAD and fabrication packages
are unchanged. See [SOURCES.md](SOURCES.md) for upstream reuse and licensing.

## Implemented scope

- Dedicated health-task GPIO13 pulses, staged startup, checked AW9523 setup,
  periodic register verification and latched faults requiring reboot.
- Fixed passive TX levels: CCD GPIO7 HIGH, SCI GPIO4 HIGH, PCI GPIO27 LOW.
  Vehicle UART TX signals are not connected to those pads. Only USB UART0 has
  a transmit call. All expander TX/VBB/VPP bits stay LOW; SCI receive selection
  permits only disconnected, OBD7 or OBD15. RX7 bias remains off.
- CCD UART receive at 7812 baud with 10-bit idle delimiting; valid additive
  checksum frames and explicitly marked raw bursts.
- Receive-only PCI VPW edge decoding with original symbol windows and CRC.
  It assumes comparator inversion (GPIO LOW means active); verify this on bench.
  Overflow discards the partial decoder state instead of splicing across a gap.
- SCI raw receive, optionally selecting OBD7 or OBD15 at 976, 7812, 62500 or
  125000 baud. No automatic ECU requests, wakeup, bootstrap or programming.
- USB at 250000 baud, bounded queues, packet validation and explicit drop counts.
- SPI microSD at a conservative 4 MHz, unique non-overwriting files, periodic
  sync, 64 MiB rotation, stop/drain/close, card-removal/error handling, and CRC
  recovery/export. No automatic formatting, timezone or invented UTC clock.

Active commands, GPIO13 LED settings, raw expander/debug writes, reset commands,
voltage reporting, CAN, OTA, diagnostic decoders and the full original GUI
API are not implemented in this image. ADC reporting waits for calibration.
The modern desktop and React Native clients are in [../apps](../apps/README.md).
The old WinForms application is not compatible with these extensions.

## Safety behavior and limits

The hardware safety contract in `../current/reference/rev-c-safety-contract.md`
controls. Before the first heartbeat, all four workers must have run and voted.
The control worker waits 300 ms after the first permit, writes safe latches,
GPIO mode, push-pull and directions, and reads back the expected register image.
Only then does it declare acquisition ready. Initialization failures, register
mismatch, failed workers and missed safety scheduling latch a fault. No automatic
permit recovery occurs; USB status remains available after a running fault.

The safety task raises a 1 ms pulse every 10 ms using task delays. It alone owns
GPIO13 after initial safe-low setup. A safety scheduling gap over 20 ms faults
instead of resuming pulses. Control, acquisition and USB votes expire after
40 ms; the storage vote expires after 2 s to accommodate bounded card operations.
Votes are renewed by the actual worker, never an independent timer. A wedged SD
operation can therefore take up to its 2 s lease plus scheduling and hardware
timeout to remove permit. Once edges stop, the hardware's separately specified
nominal 65.536 ms timeout / qualified 70 ms budget applies. Do not confuse that
hardware timeout with total fault-detection latency. Measure both on hardware.

The current hardware has **active-low CCD bias/termination** at P1_7. Firmware
uses P1=0x80 when disconnected, not all-zero P1. With AD0/AD1 grounded, AW9523
reset defaults can enable that bias network before initialization and after
watchdog reset. Software cannot guarantee a high-impedance attachment during
those intervals. Check reset/power-off loading and transitions on a simulated
bus before connecting a vehicle. Fixed MCU TX levels also require physical
measurement; a source-level passive policy is not electrical qualification.

SCI routing is serialized with verification, disconnects before changing baud,
flushes old UART state and verifies the selected receive-only mask. Selection
acknowledges queue acceptance; poll status for the applied route. A fault requires
reboot. Package identity is checked read-only before configuring the special
PICO pins. There are no application eFuse writes. BLE bond storage writes are restricted
to physical commissioning with acquisition inhibited; subscriptions are volatile.

## Build and software checks

Use Python plus PlatformIO Core 6.1.19 (`requirements.txt`). From this directory:

```powershell
python -m pip install -r requirements.txt
python tools/check_board.py
python -m unittest discover -s tests -p test_tools.py -v
python tools/build.py
```

The custom board manifest specifies 8 MB flash, DIO/40 MHz, ESP32 revision 3
minimum and explicit GPIO routing. ESP-IDF 5.5.0 and espressif32 6.12.0 are pinned.
PSRAM is intentionally unused in this first image; its internal pins are reserved.
One factory partition is used; no OTA partitions. BLE bonds are stored in NVS.
Build images are under `.pio/build/rev_c_passive/`. The wrapper performs a clean
build, rejects input edits during the build and binds declared source, SDK config
and image hashes. Export requires this verified build stamp; file timestamps are
not trusted. Build does not flash a board.

Portable C++ core tests can use a host C++17 compiler:

```powershell
clang++ -std=c++17 -Wall -Wextra -Werror -Iinclude tests/test_core.cpp -o test_core.exe
./test_core.exe
```

Tests cover worker expiry/re-arm denial, exhaustive command allowlisting, malformed
packet resynchronization/fuzz, synthetic VPW symbols/CRC and journal CRC. Python
tests also cover false-header expiry, SCI provenance, stale status and slow SD
stop completion, and source/image hash tampering with backdated edits. C++ tests
exercise startup/gap quarantine, DATA-before-error notification batches, receive
source changes, PCI discontinuities and both mount/stop interleavings. Board checks bind
17 MCU assignments and 18 expander nets to the accepted native PCB hash.
These tests do not exercise FreeRTOS, physical I2C/UART/SPI, actual storage timing
or real vehicle waveforms. See `VALIDATION.md` for performed checks and bench gates.

## Passive capture operation

After the bench gates, power the board and connect USB. Substitute its COM port:

```powershell
python tools/scanner.py caps --port COM7
python tools/scanner.py status --port COM7
python tools/scanner.py monitor --port COM7 --seconds 60
python tools/scanner.py start --port COM7
python tools/scanner.py status --port COM7
python tools/scanner.py stop --port COM7
```

Logging starts OFF at boot. A debounced short press/release of SW3 toggles requested logging;
the USB start/stop command provides the same request. Use a preformatted FAT card.
Wait for status `logging=1` after starting. The stop client waits for its own
acknowledgement, then polls until `requested=0`, `sd_busy=0`, `logging=0` and
`sd_error=0`. Only that completed stop permits card removal. `sd_busy` covers
mount/open as well as recording and close/unmount. An acknowledgement alone is
not a completed flush. GPIO13 is a health indication and never indicates recording.
The device does not auto-start logging merely because a card is inserted.

For raw SCI capture only:

```powershell
python tools/scanner.py sci --port COM7 --route 1 --speed 1
python tools/scanner.py sci --port COM7 --route 0
```

Route 1 selects OBD7, route 2 OBD15; route 0 disconnects both. No bias is enabled.
SCI burst delimiting is 100 UART bit times; it is not a decoded diagnostic frame.
Each SCI record carries the physical OBD pin and baud index, so changes remain
identifiable offline. The unknown first burst after startup, a route change or
a known UART gap is discarded through the next idle delimiter. Capture UART
ISRs run on the acquisition core; timeout-completed bursts are held until the
driver event batch has been checked for framing/break/overflow errors.
Check idle polarity and baud against the specific bench target before trusting
the bytes. Defaults are non-inverted UART RX.

Copy a recording from the card and recover/export without altering it:

```powershell
python tools/scanner.py recover RC12345678.cbr > recording.jsonl
```

Recovery reports skipped/corrupt bytes and only calls a file clean when its final
CRC-valid record is `session_clean_stop` with no skipped bytes or sequence gaps. CRC/flush cannot
guarantee FAT filesystem survival after abrupt power loss. UTC is unknown.
Each file's record sequence resets to zero. USB uses the original wrapping
32-bit millisecond timestamp; the journal also stores 64-bit monotonic microseconds.
UART timestamps are assigned when a burst is processed, not exact start-bit
hardware timestamps. PCI timestamps derive from captured SOF edges.

## Protocol extensions

Original `0x3d` sync, big-endian length and additive checksum are retained.
Protocol revision 3 retains revision-2 SCI provenance and SD busy status, and adds
authenticated BLE, control ownership and USB-only passkey retrieval. Only
these host routes are accepted:

| Route | Mode | Payload | Result |
| --- | --- | --- | --- |
| 0x01 | 0 | empty | Original handshake string |
| 0x04 | 0x7f | empty | JSON capability response, route 0x85 |
| 0x04 | 0x80 | empty | JSON status, route 0x85 |
| 0x04 | 0x81 | one byte 0/1 | Request SD stop/start; echo acceptance |
| 0x04 | 0x82 | route 0–2, speed index 0–3 | Queue passive SCI receive selection |
| 0x04 | 0x83 | one byte 0/1 | Release/acquire control lease |
| 0x04 | 0x84 | empty, USB only | Commissioning passkey and remaining seconds |

Status `rx` order is CCD/PCI/SCI. `lost` order is USB capture/response queue,
SD queue/discards, PCI edge queue/discontinuities, UART gaps/discarded bursts.
`reject` and `parse` count rejected commands and malformed parser events. `baud`
reports applied SCI baud. These counters are
different units and must not be added as a total number of lost bus messages.
USB is an unacknowledged serial stream: an unplugged host does not stop standalone
logging and cannot be counted as a host-delivery success or failure by this image.

Complete checksum-valid CCD/PCI frames use legacy receive mode 1. Mode 0x80 OR
flags denotes raw/error data (raw=2, truncated=4, UART-error=8; reserved flags are
not all currently emitted). SCI mode **0x92** has a four-byte timestamp followed
by physical OBD pin (7/15), baud index (0–3), then up to 254 raw UART bytes.
SD type-2 records contain the
exact USB frame; type-4 records contain lifecycle metadata. Capture queues are
bounded: 64 USB frames, 128 SD frames, 512 PCI edges. Long SD stalls can lose
frames even before the 2 s safety deadline; counters expose this limitation.

## BLE commissioning and simultaneous hosts

BLE uses Nordic UART Service UUIDs with authenticated, encrypted Secure Connections
and a six-digit passkey. No unauthenticated vehicle data or control is exposed.
Stop SD recording first, then hold SW3 for three seconds. This opens a 90-second
pairing window and deliberately latches acquisition/heartbeat OFF until reboot.
Read the passkey in the USB desktop Device page, pair from the mobile development
build, then reboot/reconnect. Never commission during a recording. Bond changes
and flash persistence are prohibited outside this inhibited window. A reconnecting
client must subscribe again; CCCD changes are not written to flash during capture.

USB and BLE can monitor concurrently. Mutations use a ten-second owner lease;
status polling renews the current owner's lease. Release control before handing
it to another client. USB stop preempts the lease so a connected USB operator can
stop and close SD storage. Disconnecting a host does not stop standalone SD.
BLE notification and RX queues are bounded; `ble_lost` reports transport drops,
not successful phone delivery. BLE capture has no end-to-end acknowledgements.
Notifications and security/connection transitions run on the NimBLE host context.

Software compilation is complete; secure pairing/reconnect, radio coexistence,
flash timing during commissioning and sustained USB/BLE/SD capture need bench
validation. Phone background execution is not a guaranteed recorder; use board SD.

## Rev D CAN diagnostics

The separate `rev_d_can` target adds passive CAN capture and USB-only read-only
OBD diagnostics. Build and bench procedures are in the [Rev D project](../rev-d/README.md).
Rev C remains the default PlatformIO target.

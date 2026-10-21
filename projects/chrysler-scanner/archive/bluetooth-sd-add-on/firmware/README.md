# Chrysler Bluetooth-to-SD logger firmware

Standalone prototype for the **Seeed XIAO ESP32-S3 base module** on the companion
carrier. It receives Chrysler Scanner V2 Bluetooth LE notifications, saves original
transport bytes and validated scanner packets, and writes selected passive values.
No computer is needed after firmware and card configuration are installed.

This deliverable contains source and host acceptance tests; see `validation.json`
for the actual embedded build result. It is not a bench-tested automotive product.
No hardware has been flashed by this build. The module's stated operating
range is -20 to +65 °C; this is not qualification for a hot vehicle interior.
Use regulated **USB 5 V only**, the specified external antenna, and the carrier's
separate SD regulator. Never connect raw vehicle 12 V or vehicle data wires here.

## Hardware contract

| Function | XIAO pin / ESP32 GPIO |
|---|---|
| microSD SCK | D8 / 7 |
| microSD MISO | D9 / 8 |
| microSD MOSI | D10 / 9 |
| microSD CS | D1 / 2 |
| Button to ground | D0 / 1, active low |
| External status LED | D3 / 4, active high |

This is not the Sense/Plus onboard-card pinout. No RTC, card-detect switch, battery,
power-hold circuit, or vehicle electrical connection is included.

## Prepare and use

1. Format a card FAT32. Copy [card/logger.cfg](card/logger.cfg) to its root.
2. Set `scanner_address` to the scanner's exact BLE address; choose its real public
   or random address type. The all-zero example deliberately refuses to start.
3. Choose the named decoder profile and selected IDs. The supplied example enables
   `upstream_broadcast_2023`. Formulas come from the upstream 2023 GUI and apply only
   to the listed passive CCD/PCI broadcast IDs; this does not prove compatibility
   with a particular Cummins or another vehicle. See [provenance](PROTOCOL_SOURCES.md).
   For intentional raw-only recording, set `decoder_profile=none` and `selected=`.
4. Insert the card before power-on. The default starts recording automatically and
   reconnects to that scanner. Exact NUS UUIDs plus the V2 handshake are verified.
5. Press and release the button to stop. **Wait for the solid LED** before removing
   the card or USB power. A second press starts a fresh session. Configuration is
   read at boot; stop, power off, change the card, and reboot to change settings.

LED: solid = files closed / safe software stop; regular half-second blink = receive
paths confirmed; double blink = recording but scanner not ready; rapid blink =
stopping; triple blink = error, no safe-stop promise. An idle/ready LED does not
prove that the vehicle is sending data. There is no card hot-swap support.

The firmware subscribes to Nordic UART notifications and sends only an allowlist
of scanner-internal handshake/status/info reads and CCD/PCI **receive-enable**
settings. Receive settings preserve other existing bits and persist in scanner
NVS. SCI is captured raw if the scanner was correctly configured separately; this
logger never guesses SCI baud/route settings. There is no vehicle transmit,
diagnostic polling, bootstrap voltage, flashing, emulator, or arbitrary command
interface. Other clients/scanner firmware remain outside this logger's control.
BLE MAC/handshake checks identify the intended service; they are not cryptographic
authentication. No guessed PIN or automatic insecure passkey acceptance is added.

## Card data and timing

Each recording creates a new `/logs/S000001` directory without overwriting older
sessions. It contains `configuration.txt`, `raw_0001.bin`, `selected_0001.csv`, and,
after a successful stop, `summary.txt` and `closed.ok`. Data files rotate together
when the raw journal approaches 64 MiB. The maximum is 9,999 parts per session.

`raw_*.bin` records original BLE chunks (including corrupt/noise bytes), complete
valid scanner frames, parser errors, and lifecycle/status events. Chunk and frame
records overlap intentionally; do not count both as separate vehicle messages.
The exact binary layout is in [capture_format.hpp](include/capture_format.hpp).
Each record has a magic, length, sequence, monotonic/optional UTC timestamp,
cumulative dropped-chunk count, and CRC32. A power-loss tail can be recognized;
card/controller caches and FAT corruption still require hardware power-loss tests.

CSV fields are `host_us,utc_us,scanner_ms,bus,profile,metric,value,unit`. `host_us`
is 64-bit logger uptime; `scanner_ms` is scanner uptime and can wrap after ~49.7 days
or reset on scanner reboot. By default `utc_us=0`: there is no wall clock. Optional
`utc_epoch_at_boot` means Unix seconds at this exact logger boot and must be updated
for each boot. No build-time date or old card timestamp is presented as real time.

64 fixed notification blocks buffer SD latency. Known queue loss resets partial
framing, so bytes across a gap are never spliced. Counters include dropped chunks
and bytes, parse errors, connection attempts, decoded rows, unsupported messages,
and scanner RX/TX counts. The scanner protocol has no continuous per-message
sequence, so these counters cannot prove zero radio/scanner loss. Unsupported and
invalid messages remain raw; guessed values are never filled into the CSV.

## Reproduce the build

Pinned inputs: PlatformIO Core 6.1.18, `espressif32` 6.12.0, Arduino ESP32 core
2.0.17 (PlatformIO package `framework-arduinoespressif32` 3.20017.241212),
NimBLE-Arduino 2.5.1, board `seeed_xiao_esp32s3`, C++17. A Mac/Linux host needs
Python 3, network access for these public packages, and several GB free disk.

Run `sh tools/test_host.sh` for sanitizer-enabled host acceptance tests. Run
`sh tools/build.sh` to compile. Build tooling is isolated under a temporary directory
unless `LOGGER_BUILD_TOOLS`/`PLATFORMIO_CORE_DIR` are explicitly supplied. No command
in either script opens a serial device or flashes hardware. The generated `dist/`
bundle includes actual build-derived offsets, images, versions, and SHA-256 hashes.

Flashing is a separate manual step after the hardware is assembled and checked.
Use generated flash arguments for this **ESP32-S3**; do not assume classic ESP32
bootloader offsets. The firmware never modifies the Chrysler scanner's firmware.

## Validation still required

Bench-check regulator startup/current, card detect/write errors, antenna/RF link,
BLE handshake/reconnect, every LED/button state, SD stalls/overflow, and repeated
power-loss recovery. Confirm raw reception before trusting a selected metric.
Validate each decoder against known values on the actual vehicle. A clean software
stop cannot guarantee data survival if power is removed before the solid LED.

GPLv3 source and decoder attribution are included; see [LICENSE](LICENSE).

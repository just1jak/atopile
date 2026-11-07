# Rev C passive port validation

Date: 2026-11-06. Scope: 0.2.0 safety/passive USB/SD/BLE implementation, separate
from the frozen fabrication release. No physical board, vehicle or SD card has
been exercised. No firmware was flashed. No fabrication package was regenerated.

## Software evidence

- Native board hash and firmware mappings: `tools/check_board.py` checks the
  accepted PCB SHA-256, 17 MCU mappings, 18 expander nets and passive source guards.
- C++17 host core tests: expander startup/readback and I2C failure injection;
  receive disconnect/configure/connect ordering and invalid masks; health vote
  expiry and permanent fault latch; exhaustive route/mode policy and payload
  ranges; malformed framing and 100,000 pseudorandom input bytes; synthetic
  VPW frames, CRC reference vector, malformed/overlength symbols; journal CRC
  and maximum frame bounds. Assertions remain enabled in the host build.
- Python recovery/client/build tests: nine tests covering truncated records at every
  byte boundary, torn close records, corruption resynchronization, missing whole
  records, unchanged source recordings, framing and random noise, parser expiry,
  per-record SCI source, stale-status/slow-mount stop completion, and hash-bound
  build rejection of changed sources/backdated edits and altered images.
- Embedded target: PlatformIO Core 6.1.19, espressif32 6.12.0, ESP-IDF 5.5.0,
  Xtensa GCC 14.2.0+20241119, custom PICO-V3-02 board manifest, 8 MB DIO/40 MHz,
  minimum chip revision 3, PSRAM off, 1000 Hz FreeRTOS, console/normal bootloader
  logging off. Application compilation uses warnings as errors.

The exported development bundle's `manifest.json` binds the actual source and
bootloader/partition/application image hashes. Its included build log records
the final compile outcome and memory figures. Static RAM figures exclude the
runtime queues, task stacks and driver allocations; measure heap and stack
high-water marks on the board.

The independent adversarial source review applies to the earlier 0.1.1 image.
The BLE/app extension has since received an [independent adversarial review](../apps/ADVERSARIAL-REVIEW.md), followed by fixes and fresh software checks.
The earlier 0.1.1 review and revised-source pass accompany
these software checks; see `ADVERSARIAL-REVIEW.md`. This is not a hardware safety
certification. The full original GUI,
voltage calibration, active diagnostics and programming remain future
milestones. Existing frozen hardware reports still describe the fabrication
checkpoint, when firmware was deferred.

## Required bench gates before vehicle connection

1. Confirm the assembled MCU ordering code, flash geometry, board revision and
   complete hardware safety/assembly checks. Save the existing firmware before
   any deliberate flash operation; this work did not perform one.
2. With a current-limited supply and simulated loads, scope CCD TX, SCI TX,
   PCI TX, all expander TX/VBB/VPP outputs and OBD pins through boot, reset,
   wrong-package rejection, brownout and software faults. Verify the physical
   passive levels and lack of programming voltages. Confirm GPIO15 CS stays
   inactive through boot and power transitions.
3. Measure GPIO13 pulse spacing/width, AW_RESET_N release and watchdog timeout.
   Suspend each required worker and then the safety task; exercise frozen-high
   and frozen-low GPIO13. Verify no automatic re-arm. Control/acquisition/USB
   leases are 40 ms; SD has a 2 s operation lease. The external 70 ms budget
   starts at the last valid edge, not at the beginning of an SD stall.
4. Measure the active-low CCD bias/termination load during reset and startup,
   after initialization and after a watchdog fault. The firmware disables it
   when running, but reset defaults cannot be made high impedance by software.
   Resolve any unacceptable loading before attaching a vehicle.
5. Apply known CCD frames with back-to-back data and near-boundary idle gaps.
   Verify the UART-only idle method replaces the unavailable old GPIO23 ISR.
   Compare every byte/checksum against a logic analyzer, including UART errors
   and FIFO/queue overflow. UART timestamps are burst-processing timestamps.
6. Apply known PCI VPW frames with CRC errors, noise, all pulse boundaries and
   IFR. Confirm actual comparator inversion, SOF timestamps, IRQ latency and
   resynchronization. Synthetic unit tests do not qualify vehicle timing.
7. Check SCI receiver selection and polarity at all advertised baud rates.
   Scope break-before-make and confirm TX, VBB/VPP and bias never enable.
   SCI output in this image is raw UART bursts, not decoded ECU transactions.
8. Run simultaneous maximum expected bus traffic, USB commands and SD capture.
   Compare captures against an external reference and inspect separate loss
   counters. Test USB unplug/reconnect without disturbing standalone logging.
   UART delivery has no host acknowledgements and cannot report unplugged-host
   frame loss. Measure runtime heap, stack margins and watchdog scheduling.
9. Use named, measured FAT cards. Test initialization, slow writes/fsync,
   card-full, removal, insertion, repeated start/stop, 64 MiB rotation and
   power loss at different record/flush boundaries. Issue stop during mount/open,
   verify `sd_busy` remains asserted, and confirm the client ignores pre-ACK idle
   status. Confirm queued data cannot
   cross distinct session boundaries and recovery never modifies the original.
   A failed card is retried only after removal/reinsertion; a safety fault needs
   reboot. CRC recovery does not guarantee filesystem survival.
10. Measure shared-rail supply droop and temperatures under SD write peaks and
    the declared 9–16 V input range. Complete the remaining hardware contract
    bench gates before relying on any live-vehicle capture.

Record scope traces, bus-generator input, raw output, counter snapshots, exact
card model and image/source hashes. Promote only the measured capabilities;
successful compile and synthetic tests do not close these gates.

## 0.2.0 extension checks and unresolved hardware evidence

The target compiles with Secure Connections only, security level 4, encrypted /
authenticated GATT, and a single BLE connection. Primary review corrected a
connection-handle/security race by sending notifications on the NimBLE host,
restricted bond flash writes to acquisition-inhibited commissioning, fenced SD
start against pairing, separated USB/BLE loss counters, and made USB transmission
nonblocking. C++ lease tests cover expiry and USB stop preemption. These source
checks do not prove pairing or real-time behavior on the board.

Additionally bench-test: pairing denied outside SW3 window; wrong passkey and
unbonded reads/writes; commissioning requires idle SD and reboot; bond persistence
and reconnect without flash writes; notification subscription and disconnect
handle reuse; USB/BLE ownership conflicts, expiry and emergency USB stop; sustained
three-bus traffic plus USB/BLE/SD; phone background/disconnect and dropped queues.
Confirm every fault leaves passive outputs and external permit in the safe state.

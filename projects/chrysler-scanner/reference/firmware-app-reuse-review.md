# Original firmware and app reuse review

Review date: 2026-11-06. Scope: source inspection and mapping to the accepted two-sided Rev C board. No firmware was built, flashed or qualified; no CAD or fabrication package was changed. This is an engineering assessment, not a new independent hardware review.

## Source provenance

The current public upstream tree `4ddc6e5d1c260c87c6139f60079932ffde6e5d9a` contains packaged Windows apps and ESP32 firmware binaries for PICO-D4 and PICO-V3-02, but no corresponding editable current ESP32 firmware or complete Windows app source. Source is recoverable from Git history: commit `257aa0983594c201c7375e010640d4cfa80fc4ff` removed the inspected paths on 2023-12-07. Its parent, `c7229f288e5b3c3be8cb6123bb5958085aa0117c`, is the pinned recovery point used here. The recovered firmware identifies its latest hardware version as `0x2100`; it does not establish equivalence to the current V240 binaries.

Relevant recovered files are under `work/firmware-app-review/upstream-history/`: ESP32 `main.c`, `config.h`, `enums.h`, `platformio.ini`, AW9523 header, and Windows `MainForm.cs`, project file, `SerialService.cs` and `PacketHelper.cs`. This is a partial review snapshot, not a reconstructed buildable project. Existing decoder research is under `work/bluetooth-sd-add-on/protocol-stage/research/`.

Sources: [upstream project](https://github.com/laszlodaniel/ChryslerScanner), [pinned firmware](https://github.com/laszlodaniel/ChryslerScanner/blob/c7229f288e5b3c3be8cb6123bb5958085aa0117c/PlatformIO/ChryslerScanner/src/main.c), [pinned app](https://github.com/laszlodaniel/ChryslerScanner/blob/c7229f288e5b3c3be8cb6123bb5958085aa0117c/GUI/ChryslerScanner/MainForm.cs). Preserve upstream GPL-3.0 attribution and license obligations when reusing code. Separately establish redistribution rights for any external diagnostic databases.

## What is reusable

| Component | Useful starting point | Work before relying on it |
| --- | --- | --- |
| ESP-IDF firmware | CCD/PCI/SCI receive/transmit algorithms, timing logic, checksums, packet framing, UART/I2C scaffolding, diagnostic command handling | Port hardware mapping and safety ownership; measure timing and actual electrical behavior |
| Windows app | Existing WinForms bench UI, packet commands, logging displays, engine/ABS/memory/bootstrap workflows | Update board capabilities and safety controls; validate each supported vehicle/module and operation |
| Decoder classes | CCD, PCI and SCI PCM/TCM interpretation, formulas, DTC and message knowledge | Separate presentation from decoding; add capture fixtures and explicit supported profiles |
| USB protocol | Existing handshake, status, message and error framing | Add firmware/board version and capability negotiation, safe command policy and robust framing |
| Archived BLE-to-SD add-on | Journal format, CRC/sequence concepts, recovery/session logic, passive decoder fixtures | This is a separate ESP32-S3 BLE-client prototype. Replace its hardware mapping and acquisition path for direct on-board logging |

The app is C# Windows Forms targeting .NET Framework 4.8. It can accelerate a Windows bench tool; it is not directly an iOS or macOS app. Its decoders also contain display/table formatting, so extracting a reusable protocol core takes work. A phone app requires a BLE transport and a new platform UI. Desktop and phone should share packet definitions and test captures even if their UI languages differ.

## Board port: mandatory gaps

Current native board/netlist and `current/reference/rev-c-safety-contract.md` control these assignments. Package-specific GPIO mapping is essential: ESP32-PICO-V3-02 is not a generic ESP32 development-board pinout.

| Function | Recovered firmware | Current board / required change |
| --- | --- | --- |
| CCD UART | RX GPIO19, TX GPIO18 | RX1 GPIO8, TX1 GPIO7. GPIO19 is now microSD SCK; old configuration conflicts directly |
| CCD idle/start detection | Dedicated GPIO23 interrupt | GPIO23 is not exposed on this package. Redesign and validate idle/start timing using available receive/timer resources; do not assume the old interrupt can be retained |
| SCI UART | RX GPIO5, TX GPIO4 | Same UART signals, but selector routing differs; audit every expander bit and polarity |
| PCI | RX GPIO14, TX GPIO27 | Retained pins; regression-test timing, polarity and simultaneous logging load |
| USB UART / I2C | RX3/TX1; SDA21/SCL22 | Retained; verify board initialization and host framing |
| Safety heartbeat | GPIO13 activity LED, configurable blink, commonly 5-second interval | Dedicated health task pulses every 10 ms only while required tasks vote healthy. Remove all legacy LED writers and host blink/disable controls |
| MicroSD | No integrated SD implementation in recovered main.c | CS15, MOSI20, SCK19, MISO36, detect38; button37. Respect CS boot-strap level and package GPIO20 mapping |
| Voltage measurement | Battery/bootstrap scale 6.345679; programming scale 12.234567 | Recalculate all channels for Rev C divider/loading/switch behavior (nominal gain about 0.06757), calibrate ADC and protected-input diode correction |

Additional blocking firmware changes:

1. **Safety startup and recovery.** Old `app_main` initializes I2C/expander before starting its LED task. Our expander reset is held by the hardware health permit. Implement the documented startup sequence, then safe latches/configuration before command enable. The old code does select P0 push-pull, but its ordering and control ownership still require adaptation. Test frozen tasks, reset, brownout and session loss.
2. **Selector mapping.** Old configuration names SCI TX7/TX15 and RX6/9/12/14; the current expander nets include TX6/9/12/14, RX7/RX15 and RX7 bias. This is a functional mapping change, not merely renaming GPIOs. Audit P0/P1 bit assignments, inactive polarity, VBB/VPP routes and every raw/debug write. Centralize interlocks; do not expose unvalidated programming commands.
3. **Disable automatic eFuse provisioning.** The recovered `load_settings` can write hardware-version eFuse fields when blank. Remove that automatic action from the port; manufacturing identity needs an explicit reviewed provisioning process.
4. **Build configuration.** Recover the complete source, headers/resources, partition table and SDK configuration. Original PlatformIO configuration pins `espressif32@5.2.0`, `pico32`, ESP-IDF. Establish correct PICO-V3-02 flash/PSRAM and partitions, a reproducible toolchain, and versioned board profiles. A matching package name on an upstream binary does not establish Rev C compatibility.
5. **Concurrent acquisition and storage.** Add bounded queues, timestamps, loss counters, SD batching, card-full/removal/error handling, power-loss recovery and a usable stop/eject operation. Storage or BLE backpressure must never stall safety or bus timing. The archived add-on can inform this; it does not complete integration.

## Host and wireless gaps

The historical packet enum provides USB/CCD/PCM/TCM/PCI buses, not CAN. Retain compatibility where practical and negotiate new capabilities. The old LED command must no longer control GPIO13. Add health/permit, voltage calibration, SD status/session and dropped-frame reporting.

`SerialService` uses System.IO.Ports and a queued worker model. Its unbounded transmit queue, cancellation/reconnect behavior, fixed receive buffer and error reporting need review and tests under malformed/truncated frames, disconnects and sustained capture. Keep acquisition/recording separate from UI refresh.

BLE is unfinished in the inspected firmware: `init_ble()` is commented out and `ble_notify_packet()` is an empty stub. The write handler assumes packet layout too early and needs length/bounds validation, mbuf handling, fragmented/coalesced frame parsing and ownership separation from USB state. NUS UUID definitions are reusable, but this is not a working mobile link. Define fragmentation, reconnect, bounded buffering, command authorization and throughput behavior. Do not transplant the archived relay's exact-MAC selection into an iOS design.

Engine, memory and bootstrap screens show implemented workflow concepts, not demonstrated compatibility with this board or every ECU. Start with passive capture; qualify active commands and programming separately with recovery plans and known target hardware.

## CAN recommendation

**Yes: CAN would broaden appeal for a combined legacy Chrysler tool and CAN logger, provided useful software and documented vehicle coverage ship with it.** This is a product judgment, not measured demand. A transceiver alone does not supply ISO-TP, diagnostic services, module definitions or universal modern-vehicle coverage. Cheap CAN adapters make legacy CCD/PCI/SCI expertise and dependable software the stronger differentiators.

The ESP32 has one Classic CAN/TWAI controller and needs an external transceiver; it cannot process CAN FD. See [Espressif TWAI documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/twai.html) and the [PICO package datasheet](https://documentation.espressif.com/esp32-pico_series_datasheet_en.html).

Our OBD6/14 already serve SCI/programming. A future CAN revision needs protected default-disconnected switching of both lines, break-before-make transitions, hardware mutual exclusion, safe standby and boot/fault review. No permanent vehicle-bus termination. Firmware needs listen-only capture first, filters/timestamps, bus-off handling, logging throughput and then ISO-TP/diagnostic functions appropriate to the advertised scope. CAN FD requires an additional controller or a different MCU platform as well as a suitable transceiver.

Corrected the current CAN note: GPIO5 is already SCI RX, not spare. GPIO39 may be an input candidate, but TX and mode-control allocations remain unresolved. No CAN hardware or pin allocation is approved by this review; see `current/reference/can-upgrade.md`.

Recommendation: complete the present legacy prototype's safe firmware and passive USB/SD logging first. If the aim is a broadly sellable next revision, plan CAN before a production-scale batch, with a defined minimum software feature set. Preserve this fabrication release while evaluating that revision.

## Completion sequence and acceptance evidence

1. Recover complete pinned upstream source and establish a reproducible build without automatic eFuse writes.
2. Implement Rev C pin/selector mapping, health-task ownership, safe startup/recovery, ADC calibration and capability reporting. Bench-test permits and fault cases with active vehicle commands disabled.
3. Validate passive CCD/PCI/SCI USB capture using known waveforms and golden recordings. Check timing and loss under simultaneous traffic.
4. Integrate SD sessions and verify sustained logging, card faults, power interruption and replay against raw capture evidence.
5. Adapt Windows UI and decoders; exercise reconnect, malformed frames and capability restrictions. Add BLE/mobile as a separate validated transport/UI milestone.
6. Qualify active diagnostics and finally programming per supported target. CAN is a separate hardware/software milestone.

No delivery-duration estimate is justified until a complete build and the first timing/safety bench results exist. Native CAD ERC/DRC success does not complete these firmware or vehicle-validation gates.

# iOS and desktop app feasibility

Exploration date: 2026-10-21. No app or firmware was implemented, compiled or flashed for this exploration. No CAD files were changed.

An iOS and desktop companion is feasible with the existing hardware. The best starting point is a shared app for recording review and live monitoring, with Bluetooth LE on iPhone and USB serial plus BLE on desktop. The main uncertainty is the scanner firmware and its protocol compatibility, rather than app screens. Keep the scanner's future SD recorder responsible for continuous capture so a phone disconnect or background suspension does not end the recording.

## What is already available

| Evidence in this repository | What it means for the app |
|---|---|
| `current/reference/integration-handoff.md`: U10 ESP32-PICO-V3-02, integrated SPI microSD, button and card detect | One scanner MCU can capture and store locally. The SD addition does not require a separate BLE relay. |
| `current/reference/final-netlist.xml`: J2 USB-C and U12 CP2102 | Desktop serial is a practical development/debug transport. This USB connection is a UART bridge, not an SD mass-storage interface. Firmware must implement any log download over it. |
| ESP32 radio and existing RF path | BLE is the natural iPhone transport. The SiP also has Wi-Fi capability; an app-accessible Wi-Fi service would require firmware and measurements, not just an app change. See the [Espressif datasheet](https://documentation.espressif.com/esp32-pico_series_datasheet_en.html). |
| CCD, PCI/J1850, SCI hardware | These are the initial bus families. There is no CAN transceiver in the current board; a CAN UI does not create CAN support. |
| `archive/bluetooth-sd-add-on/firmware` | A historical XIAO BLE-to-SD draft contains portable protocol parsing, selected decoders, capture records and host tests. Its board pinout and receive architecture do not match U10. |

The integrated-board firmware remains deferred. Its handoff records that the inspected public V2 scanner folder provided binaries rather than a complete current scanner source project. That is a recorded limitation of that inspection, not proof that compatible source cannot be obtained. Identify the exact installed firmware, source and build process before promising integration or log-control commands. Do not flash the XIAO draft onto this PCB.

## Recommended architecture

Use Flutter for a shared iOS, Windows and macOS UI and application model; add Linux if wanted. Flutter officially supports these mobile/desktop targets, but BLE and serial integration still need platform-specific adapters and physical-device testing. The recommendation is an engineering choice, not a claim that one BLE plugin already solves every platform. See [Flutter platform support](https://docs.flutter.dev/reference/supported-platforms) and [desktop support](https://docs.flutter.dev/resources/faq).

```text
BLE / desktop serial / optional Wi-Fi / imported capture file
                         |
             Transport and stream framing
                         |
      Protocol version, capability and connection state
                         |
       Raw events -> recording store -> replay / export
                         |
       Explicit vehicle decoder profile -> values / charts
```

Keep transport framing, raw records, decoder definitions and session storage separate from widgets. Use bounded queues; render sampled updates while retaining the full supported event stream in storage. A recording page should show actual received frames, drops, parser errors, stale values and disconnects. “Connected” must not mean “recording successfully.” No cloud service or user account is required for the first version.

Alternative: SwiftUI for iOS/macOS plus a separate Windows app gives direct Apple API access but requires two UI implementations. A local web interface over scanner Wi-Fi could be useful later, but adds a firmware network service and does not replace native BLE integration. Start with Flutter unless Apple-only desktop support or another established codebase changes the tradeoff.

## Transport decisions and iOS constraints

| Transport | Initial role | Work required |
|---|---|---|
| BLE GATT | iPhone live data, status and bounded control; optional desktop live data | Confirm actual scanner service, writes, notifications, MTU behavior, fragmentation and reconnect. Measure simultaneous live streaming plus SD recording. |
| USB serial through CP2102 | Desktop bring-up, reliable wired monitoring and future downloads | Confirm port settings and firmware framing; handle drivers, unplug/replug and reset/boot control lines. Do not let port opening unexpectedly toggle reset. |
| Removable microSD | First offline recording workflow | File picker/import, validation, interrupted-session recovery, replay, charts and CSV export. Integrated firmware must first produce a defined format. |
| Wi-Fi | Optional bulk session download or faster streaming | Implement discovery/connection, authentication, download resume, checksums and firmware resource budgeting. No Wi-Fi app API is established by the present CAD. |

Apple supports BLE peripherals through Core Bluetooth; the BLE route does not require making the device a Classic Bluetooth serial accessory. Include a meaningful Bluetooth usage description. Use service discovery and the scanner handshake, then save the OS peripheral identifier and a future firmware-provided device identity. Do not copy the XIAO draft's exact-MAC-address selection into an iOS UI: Core Bluetooth identifies peers using OS-assigned UUIDs. See [Apple Bluetooth](https://developer.apple.com/bluetooth/), [Core Bluetooth](https://developer.apple.com/documentation/corebluetooth) and [peer identifiers](https://developer.apple.com/documentation/CoreBluetooth/CBPeer/identifier).

Background BLE modes allow specific event handling, not unrestricted continuous app execution. Implement reconnect/state restoration as appropriate, but make device-side SD recording independent of app lifecycle. Force-quit, locked-screen, out-of-range and Bluetooth-off cases need explicit tests. See [Apple background processing](https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/CoreBluetoothBackgroundProcessingForIOSApps/PerformingTasksWhileYourAppIsInTheBackground.html).

Do not promise direct CP2102 access from iPhone because the cable fits. Apple's External Accessory framework addresses supported accessory arrangements, not a generic guarantee that arbitrary USB UART bridges work in an ordinary iPhone app. Treat wired iPhone support as a separate feasibility test; BLE is the baseline. See [External Accessory](https://developer.apple.com/documentation/externalaccessory).

Wi-Fi discovery/download would need local-network permission handling, including denied access and direct-IP fallback as appropriate. See [Apple local network privacy](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy). iOS building/signing also needs access to macOS/Xcode and a physical iPhone; the Windows workstation alone cannot complete that toolchain. See [Flutter iOS setup](https://docs.flutter.dev/platform-integration/ios/setup).

## Protocol and firmware work that determines scope

The archived `firmware/PROTOCOL_SOURCES.md` pins the upstream [V2 API reference](https://github.com/laszlodaniel/ChryslerScanner/blob/bfc3451ba7962f681186dc9efee03068e9c92687/Documentation/ChryslerScanner_V2_API_Reference.md). Its saved copy and parser source were inspected locally for this report. It describes Nordic UART Service UUIDs `6E400001/2/3-B5A3-F393-E0A9-E50E24DCCA9E`, `0x3D` framing, a big-endian length, route/command/mode fields, additive checksum and the `CHRYSLERSCANNER` handshake. Notifications are arbitrary chunks of a stream, not complete packets. Preserve raw bytes and reject corrupt frames before decoding values.

Before building live features, prove these against the actual device using golden captures. Confirm whether USB uses the same framing, supported firmware/API versions, maximum packet sizes, client concurrency, command acknowledgements, current bus settings and throughput. No known per-message sequence in the legacy protocol proves lossless radio capture; the app must report observed loss and avoid claims it cannot establish.

New integrated logging needs a versioned contract for:

- Capabilities, unique device ID, firmware/build identity and supported buses.
- Recording start/stop acknowledgements, card health/free space, session state, overflow counters and confirmed file closure.
- Session list/metadata, resumable file transfer, integrity hashes and deletion rules, if downloads are in scope.
- Monotonic timestamps, scanner reboot/wrap events and an explicitly valid host-supplied UTC anchor. The board has no RTC; stale timestamps must not be presented as real time.
- Command ownership when more than one client connects, and device authentication before exposing control or future Wi-Fi services.

The archived `include/capture_format.hpp` defines `CBSDRAW1`/`CBR1` records with record sequence, monotonic/optional UTC timestamps, loss counters and CRC32. It is useful for an importer and fixtures, but it describes the old BLE-relay journal, including overlapping chunk and frame records. Do not count both as distinct vehicle messages or silently declare this the new integrated SD format. Freeze a versioned integrated capture specification first, or deliberately adopt and extend it with documented compatibility.

The existing passive decoder subset is narrow: selected historical CCD/PCI broadcasts. The intended early-2004 automatic Cummins values are not vehicle-validated. Unknown messages and SCI should remain raw until controller-specific definitions and session context are established. Generic OBD-II/CAN PID libraries are not substitutes. Read/clear DTCs, actuator tests, SCI polling, programming voltages and ECU flashing are separate projects after a receive-only monitor works.

Portable code and historical decoder work carry GPL notices. Choose the app's licensing/distribution approach before directly incorporating it, preserve provenance, and include a distribution review in release preparation.

## A practical sequence

| Stage | Deliverable and completion gate |
|---|---|
| 1. Reproducible contract | Locate/build the compatible scanner source; verify the installed API through desktop serial/BLE. Freeze representative valid, corrupt, fragmented and disconnected-session fixtures. This is the main external dependency. |
| 2. Offline app | Shared desktop/iOS shell, recording import, raw frame table, session timeline, replay, explicit decoder profiles, charts and CSV export. Can start using fixtures before firmware work is finished. |
| 3. Live monitor | Desktop serial first, then BLE on physical iPhone and desktop. Prove handshake, reconnect, parsing, drop accounting, stale indicators and bounded memory over long runs. |
| 4. Integrated SD control | Port recording into U10's scanner receive pipeline; implement clean stop, recovery and card errors; expose capability/state commands. Test power loss, SD stalls, radio/SD concurrency and timestamp anchors. |
| 5. Product release | Download/resume if wanted, device association, accessibility, installer/signing, crash recovery, platform lifecycle tests and TestFlight/desktop distribution. Validate the actual target vehicle before advertising its decoded values. |

A file viewer/replay prototype is the smallest useful first build. A reliable live scanner/logger spans firmware, app and hardware validation; screen generation alone does not complete it. Estimate calendar time after Stage 1 identifies source availability and after choosing the desktop targets and first feature set.

## Decisions to make before implementation

1. Desktop target: Windows only initially, or Windows and macOS? Is Linux required?
2. First product: raw logging/replay and live gauges, or also diagnostic commands and fault codes?
3. First vehicle/controller profile: exact Cummins year, engine/TCM identities and bus observations?
4. Are recordings normally removed on SD, downloaded wirelessly, or transferred by USB?
5. Personal use/TestFlight, public App Store, or broader commercial distribution?
6. Is a Mac and physical iPhone available for builds and testing, and can compatible scanner firmware source be obtained?

Recommended first milestone: **offline import/replay plus desktop USB monitoring, then iPhone BLE live view; device-side SD logging remains the recording authority.**

# Chrysler Scanner apps

Modern React/Electron desktop for Windows, macOS and Linux, plus an Expo React
Native app for iOS and Android. Shared TypeScript code implements Rev C passive
protocol 2/3, recording recovery, CSV export and selected historical decoders.
These clients replace the passive capture workflow of the original WinForms app;
full original diagnostic/programming functionality has not been ported.

## Find your app

- **Windows:** extract the ZIP in `desktop/release/` and run Chrysler Scanner.exe.
- **Linux:** the native x86-64 package target is a `.deb`; build on Linux or
  download a successful Linux workflow artifact. Serial access depends on your
  distribution's device permissions.
- **macOS:** the desktop source is shared with Windows/Linux. Build on a Mac or
  download a successful Mac workflow artifact. Test packages are not notarized.
- **Android:** app source is in [mobile/](mobile/README.md). The build workflow
  has a standalone ARM64 test APK job. An APK is available only after that job
  succeeds.
- **iPhone:** same React Native source. Live BLE requires a native build with
  Apple signing/provisioning for physical devices. There is no TestFlight
  release. JavaScript bundles alone are not installable apps.

Repository builds are listed under [GitHub Actions](https://github.com/just1jak/atopile/actions).
Use the artifacts from the run for your commit, rather than older packages.

## Run and build

Install Node 22.13+ and run these commands in this directory:

```sh
npm ci
npm run typecheck
npm test
npm run start:desktop
npm run test:ui
npm run dev:mobile
npm run export:mobile
```

Package desktop on the corresponding OS:

```sh
npm run package --workspace @chrysler/desktop -- --win zip --publish never
npm run package --workspace @chrysler/desktop -- --mac --publish never
npm run package --workspace @chrysler/desktop -- --linux --publish never
```

macOS signing/notarization and distribution certificates are not configured.
Windows ZIP is unsigned. Linux serial access may require dialout group/udev
permissions. Packages use the serialport Node-API prebuilds (native rebuild off).
Verify the native binding when adding platforms or architectures.

Live mobile BLE requires a native build; Expo Go supports offline
recording review only. Use `npx expo run:android` or `npx expo run:ios` from mobile
with the platform SDK installed, or use a successful Android test APK workflow artifact.
iOS native compilation requires macOS/Xcode. No paid cloud build is submitted.
The web preview supports offline import, not live BLE. JavaScript bundles compile
for both iOS and Android; native APK/IPA and physical phone tests remain pending.

## Use

Connect USB at 250000 baud and select the enumerated port. Capability negotiation
rejects incompatible firmware before controls become available. Live monitoring,
computer recording and board SD recording are separate controls. Closing the app
ends the computer recording but does not stop standalone board SD recording.
For SD removal, request Stop and wait for confirmed close/unmount; an acceptance
ACK is not a flush confirmation. Stale/disconnected status never grants removal.

For BLE, use firmware 0.2.0: stop SD first, hold SW3 three seconds, obtain the
six-digit passkey from USB Device / pairing code, and connect/pair from the phone
within 90 seconds. Commissioning intentionally disables acquisition until reboot.
Reboot and reconnect after pairing. Never commission during a recording.
USB and BLE can monitor together; only one transport owns mutations for a renewable
ten-second lease. Release control to hand over; USB Stop can preempt for SD closure.
The mobile app polls only while active. Use board SD for independent recording;
phone background capture is not guaranteed.

Open `.cbr` recordings from board SD or computer capture for CRC recovery and CSV.
Preview tables are bounded, while CSV streams the entire file. Mobile accepts a
single segment up to 70 MiB (board segments rotate at 64 MiB). Raw/error traffic
is retained and labeled. SCI is raw data with source pin/baud, not ECU diagnostics.
Historical Chrysler decoder profile is opt-in: its few broadcast formulas are
vehicle-specific and must be checked against the actual vehicle.

## Validation

Shared tests cover framing, malformed input, capability rejection, checksums,
SCI provenance, torn/corrupt journal recovery, and SD start/close confirmation.
Hidden Electron integration imports 6,000 synthetic CCD/PCI/SCI frames through
real IPC and file dialogs, tests bounded previews, exports every row and loads
the native serialport binding. Mobile web integration imports the same fixture.
Fixtures/screenshots are synthetic, not captured vehicle data.

Desktop packages are tested where platform runners are available. Check the
current review report for which packages actually built and ran.
No USB device, radio, SD card, phone or vehicle has been exercised. See firmware
VALIDATION.md for commissioning, electrical and timing gates. CAD is unchanged.

The `Chrysler companion apps` GitHub workflow builds desktop packages on all
three OS runners, builds an Android ARM64 test APK, and exports mobile JS bundles.
It triggers on app changes on the scanner branch and requires Actions enabled in
the fork. It does not publish to stores or sign a physical iPhone build.

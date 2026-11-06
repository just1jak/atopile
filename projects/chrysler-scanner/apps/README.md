# Chrysler Scanner apps

Modern React/Electron desktop for Windows, macOS and Linux, plus an Expo React
Native app for iOS and Android. Shared TypeScript code implements Rev C passive
protocol 2/3, recording recovery, CSV export and selected historical decoders.
These clients replace the passive capture workflow of the original WinForms app;
full original diagnostic/programming functionality has not been ported.

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

Live mobile BLE requires a native development build; Expo Go supports offline
recording review only. Use `npx expo run:android` or `npx expo run:ios` from mobile
with the platform SDK installed, or your configured Expo development-build service.
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

Windows packaging and local Electron tests are available. Mac/Linux sources and
build targets are implemented but native packages have not been built here.
No USB device, radio, SD card, phone or vehicle has been exercised. See firmware
VALIDATION.md for commissioning, electrical and timing gates. CAD is unchanged.

The manual `Chrysler companion apps` GitHub workflow builds unsigned desktop
packages on all three OS runners and exports mobile JS bundles. It has not been
dispatched as part of this local implementation.

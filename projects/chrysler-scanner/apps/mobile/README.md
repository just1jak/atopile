# Chrysler Scanner mobile

This Expo React Native app is shared by Android and iOS. It can review and
export a scanner recording offline, or connect to Rev C firmware over authenticated
BLE for live passive capture and board microSD controls.

On Android, look for a successful `android-arm64-test-apk` artifact in the
[companion build workflow](https://github.com/just1jak/atopile/actions). This is
a test APK for ARM64 phones, not a Play Store release. For a local build, install
dependencies from the parent directory and run `npx expo run:android` here
with Android Studio / Android SDK available.

On iPhone, run `npx expo run:ios --device` on a Mac with Xcode and signing
configured for the connected device. There is no signed IPA or TestFlight build
in this repository. Expo Go and the web preview can review recordings but cannot
access the app's BLE native module.

See the [companion setup guide](../README.md) for pairing and capture instructions.
For longer recordings or while the phone is in the background, log on the
scanner's microSD.

## Internal TestFlight build

The `production` EAS profile is a store build with automatically incremented
build numbers. From this directory, sign into Expo and use the Apple Developer
team that owns `io.just1jak.chryscanner`:

```sh
npx eas-cli login --browser
npx eas-cli build --platform ios --profile production --auto-submit
```

Use the Apple authentication prompts to configure distribution signing and
select the corresponding App Store Connect app. After Apple processes the
upload, add the build to an internal TestFlight group and add your App Store
Connect user to that group. This path does not publish to the App Store.

For the first BLE test, use Rev C firmware with BLE. With SD stopped, hold
SW3 for three seconds, read the pairing code over USB, and pair from the phone.
Reboot the scanner and reconnect. Confirm live CCD/PCI/SCI data from a bench
source, SD start and confirmed stop, and BLE reconnect without disturbing a
running SD recording.

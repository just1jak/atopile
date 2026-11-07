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

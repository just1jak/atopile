# Reuse and licensing

GPL-3.0-only; see LICENSE. Original project: laszlodaniel/ChryslerScanner at recovered
source revision c7229f288e5b3c3be8cb6123bb5958085aa0117c (before source removal).
The original framing convention and selected passive broadcast formulas are
ported into packages/core. See firmware/SOURCES.md and archive's
bluetooth-sd-add-on/firmware/PROTOCOL_SOURCES.md for earlier provenance research.

Selected formulas cover PCI 0x10/0xc0 and CCD 0x0c/0x24/0xe4 broadcasts; checksum
and expected length are required. These are historical vehicle-specific profiles,
not universal OBD PIDs. Original WinForms forms, active ECU transactions, flash
programming, bootstrap logic and the complete decoder tables are not ported.
React/Electron/Expo UI, transport ownership and recording controls are new.

Dependencies and transitive licenses are recorded in package-lock.json; third-party
packages retain their own licenses. BLE uses the ESP-IDF NimBLE implementation
and Nordic UART Service UUIDs. No claim of Bluetooth product certification is made.

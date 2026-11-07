# Companion apps and BLE: adversarial review

Reviewed baseline: `33ba4ec3`. Separate reviewers inspected the apps and
BLE firmware, including the shared wire protocol and SD control paths.
The design remains passive. CAD and fabrication files were outside this change.

| Area | Failure found | Fix |
| --- | --- | --- |
| BLE command dispatch | Queued data or expired parser input from a disconnected peer could still reach the command handler. | Check the BLE generation at each complete-frame acceptance. A command already accepted may finish; queued input and output from the old generation are discarded. |
| BLE command replies | Streaming capture filled the same queue as status and SD acknowledgements, causing mobile timeouts and miscounting BLE loss as USB loss. | Reserve a separate reply queue, prioritize it between whole frames, tag capture with its peer generation, and keep BLE loss separate. |
| BLE subscription and rebonding | A storage denial could reject unsubscribe after it took effect, or repeatedly retry pairing after a failed bond deletion. | Keep subscription state in memory and only retry after a successful bond deletion. Bond key mutations remain restricted to physical commissioning. |
| Desktop recording | Disconnect during the save dialog could open an empty journal and later mark it clean. Old serial events could reach a replacement connection. | Bind pending saves and serial callbacks to the current connection; drain active writes before a clean quit. |
| Mobile connection | A missing native connection callback could leave the app busy forever. Rapid taps and repeated connect could race native link cleanup. | Bound BLE setup, dispose listeners/links on failure, and serialize connection actions. |
| SD stop | Late status could restore an eject confirmation after disconnect. A physical SW3 restart could invalidate the last observed idle status between polls. | Recheck session identity after asynchronous operations; clear stale or malformed status. Show stop as confirmed at the last check and tell the operator not to restart before removing the card. |
| Recording recovery | A corrupt frame payload could abort the rest of the journal scan. | Skip the malformed record, keep scanning, and distinguish recovery from a clean capture. |
| Desktop source selection | A recording preview could remain in the live tab, confusing file data with incoming traffic. | Separate recording and live views. The three activity traces show counts from retained frames, in 250 ms bins. |

Verification covers the C++ passive policy and BLE command generation, nine
firmware Python checks, board integrity, 14 app regression tests, desktop
integration on a synthetic 6,000-frame journal, and Android/iOS Hermes bundles.
The build workflow has native desktop jobs and an Android ARM64 APK job.
Check a specific workflow run for actual artifacts.

Before relying on this for vehicle capture, bench-test authenticated pairing,
bond reconnect, competing USB/BLE controls, sustained three-bus traffic and
SD stop/removal. These checks used no physical scanner, vehicle or phone.

# SYNTHETIC example — no vehicle capture

These files were generated on a host computer. **No scanner, BLE radio, SD card,
vehicle connection, or real sensor reading was used.** They demonstrate the file
format and evidence-backed decoder formulas, not physical logger readiness or
compatibility with any particular vehicle.

* `raw_0001.bin`: the firmware's `CBSDRAW1` format, with explicit synthetic events,
  three invented BLE chunks, and their two validated complete PCI scanner frames.
  The first frame deliberately crosses a notification boundary.
* `selected_0001.csv`: seven rows produced by the actual C++ protocol/decoder
  library with the explicit `upstream_broadcast_2023` profile.
* `expected.json`: exact frame bytes and independently specified expected values.
* `generate_demo.cpp`: reproducible generator using the portable library and the
  firmware's `capture_format.hpp`. It does not connect to hardware.

Expected values:

| Scanner time | Metric | Value | Unit |
|---:|---|---:|---|
| 1000 ms | engine_rpm | 2000 | rpm |
| 1000 ms | vehicle_speed_kph | 78.857856 | km/h |
| 1000 ms | manifold_absolute_pressure_kpa | 101 | kPa |
| 1010 ms | battery_voltage_v | 14 | V |
| 1010 ms | oil_pressure_kpa | 344.737850 | kPa |
| 1010 ms | coolant_temperature_c | 85 | degC |
| 1010 ms | ambient_temperature_c | 40 | degC |

UTC is unknown (`utc_us=0`). All timestamps and bus data are invented test inputs.
The host times represent completion of each synthetic frame. See the portable
protocol's `SOURCES.md` for pinned formula provenance and vehicle limitations.

Reproduction from the delivered `examples/synthetic` directory:

```sh
c++ -std=c++17 -Wall -Wextra -Wpedantic -Werror \
  -I ../../firmware/include \
  ../../firmware/src/protocol.cpp generate_demo.cpp -o generate_demo
./generate_demo
```

Run only in a scratch directory: the generator recreates its two synthetic output
files. The generated files contain no device address, account data, or credentials.

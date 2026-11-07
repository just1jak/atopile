# Rev D passive CAN design scope

Start with Classic CAN receive-only capture on J1962 pins 6/14. Keep CCD, PCI
and SCI capture. Treat active diagnostics, ISO-TP requests and CAN FD as
separate milestones. The accepted Rev C assembly has no CAN physical layer.

## Netlist and firmware findings

- In the Rev C [released netlist](../current/reference/final-netlist.xml),
  J1.6 is on the legacy branch with Q2.6, R29 and TP14. J1.14 is on the legacy
  branch with Q3.6, R36 and TP16. Both connector conductors need isolation
  before adding CAN. The legacy capacitor, clamp and pull networks must sit
  on the legacy side of the selector, with CAN protection sized separately.
- U10 pad 8 (GPIO39) and pad 22 (GPIO2) are unconnected in the released netlist.
  GPIO39 is a receive candidate and requires external bias if needed.
  GPIO2 is a boot strap, so leave it unallocated until boot and reset
  requirements are reviewed. The pinned ESP-IDF 5.5 on-chip driver validates a
  real output-capable TX GPIO even in listen-only mode. Its TX output need
  not connect to the transceiver in the receive-only design.
- The ESP32 TWAI controller handles Classic CAN. Listen-only mode suppresses
  ACK, error-frame and data transmission. [ESP-IDF TWAI documentation](https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32/api-reference/peripherals/twai.html)

## Circuit direction

Place a two-conductor selector between the connector and the two front ends.
Use independently qualified, normally open legacy and CAN branches and an
all-open reset state. Use a hardware interlock and transition dead time so
both branches cannot close together. Prove that disabling the safety permit
opens both branches and forces CAN standby. Evaluate a single stuck-contact
fault before allowing any programming voltage on a shared pair.

Use a 5 V transceiver with a 3.3 V logic rail and standby, with
TCAN1042HGV as the initial evaluation candidate. Hold TXD recessive with
hardware referenced to VIO and omit a fitted MCU-to-TXD connection in the
passive prototype. Provide CAN-specific low-capacitance protection close to
the connector and route the pair together with short stubs. Vehicle capture
uses no onboard 120 Ω termination. Use removable termination on the bench
when the bench bus needs it. [TI transceiver specifications](https://www.ti.com/product/TCAN1042HGV)

## Bring-up sequence

1. Prototype the receiver on an isolated bench CAN network with separate
   transmitting and acknowledging nodes. Verify the receiver never ACKs or
   drives dominant and check standard and extended IDs at 250 and 500 kbit/s.
2. Choose selector parts from measured legacy programming and vehicle fault
   limits. Close the GPIO assignment and reset/boot analysis, then add the
   circuit and routing in a separate CAD revision.
3. Add capability-gated CAN frames with timestamps, standard/extended ID,
   RTR and payload length to the logging pipeline. Keep legacy recording
   decoding and separate loss counters. Measure queue drops with concurrent
   CAN, legacy capture, BLE and SD writes.
4. Verify reset, unpowered loading, brownout, hot plug, transition and stuck
   faults. Run ERC/DRC and hardware review before making a fabrication package.

This is a design scope and a netlist audit. Selector part choice, GPIO
allocation, CAD, firmware capture and hardware validation are still open.
See [the Rev C CAN upgrade analysis](../current/reference/can-upgrade.md).

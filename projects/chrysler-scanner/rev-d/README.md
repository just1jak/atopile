# Rev D switchable legacy and CAN diagnostics

Open [ChryslerScanner_RevD.kicad_pro](ChryslerScanner_RevD.kicad_pro) in KiCad
10. Sheet 25 is the CAN transceiver, sheet 26 switches OBD pins 6 and 14
between CAN and the retained legacy branches, and sheet 27 gates CAN TX.
The KiCad project includes the routed PCB and a separate diagnostic firmware
target. Hardware qualification is required before connecting to a vehicle.

## Mode control

U26 is an MCP23008 on the existing I2C bus at seven-bit address 0x20. GP0
requests CAN and GP1 requests Legacy. Both request lines have pull-downs.
U27 decodes the requests in hardware and its enable is driven by N_R88_2,
the existing supervised expander reset/permit. That net also resets U26
and cuts the coil return through Q27. Only the normally open contacts of
K1 and K2 are wired to the bus branches.

| Hardware permit | Request GP1:GP0 | OBD pins 6 and 14 |
| --- | --- | --- |
| Low | Any | Both branches open after relay release |
| High | 00 | Both branches open |
| High | 01 | CAN branch only |
| High | 10 | Legacy branch only |
| High | 11 | Both branches open |

The PCB extends the lower edge by 30 mm to make room for the
selector and TX interlock. It retains the four Rev C mounting-hole centers.
Confirm the revised outline and enclosure fit before releasing fabrication.

Each relay has a delayed pickup and quicker turnoff path from the decoder
through its RC network and Schmitt buffer. The firmware must write 00
between modes and wait through the qualified contact release, bounce and
discharge interval before requesting the other mode. Firmware startup
must clear the output latch before configuring the request GPIOs as outputs.
Drop the hardware permit if expander setup, readback or a mode transition
fails. CCD, PCI and SCI receive on pins 7/15 retain their existing wiring.

CAN RXD feeds GPIO39. STB defaults high and is pulled low for CAN capture.
D40 protects the CAN branch. The selector restores physical access to the
legacy branches. Existing firmware continues to inhibit VBB/VPP and active
transmission. A future programming release requires independent isolation
and contact-state safeguards. A coil command or expander readback cannot
prove that a contact opened.

## Active diagnostics and passive default

U26 GP2 is the TX arm request and defaults low through R146. U29 through
U31 require the hardware permit, the raw CAN decode, the delayed CAN relay
command, a low Legacy relay command and the explicit arm. U32 is a buffer
with a high impedance output when the permit is low. R149 then holds the
transceiver TXD high, which is the recessive state. The raw decode disables
TX when leaving CAN even if the delayed CAN relay signal is still high.
On reset, the selector opens both branches. Selecting CAN with GP2 low
gives the passive capture mode and permits TWAI to run in listen-only mode.

U10 GPIO2, pad 22, is the Rev D TWAI TX candidate and connects only to the
buffer input and a 47 kΩ pull-down. This keeps the required low strap for
joint download mode. Verify cold boot and USB download across supplies and
temperatures. Firmware must establish recessive TX before asserting GP2.

Build the firmware with `pio run -e rev_d_can` from the firmware directory.
Use the USB CLI on a terminated bench bus once the board is qualified.

```powershell
python tools/scanner.py can-mode passive --port COM7 --bitrate 500000
python tools/scanner.py can-read pid --port COM7 --pid 0x0c
python tools/scanner.py can-read dtc --port COM7
python tools/scanner.py can-read vin --port COM7
python tools/scanner.py can-mode legacy --port COM7
python tools/scanner.py can-mode open --port COM7
```

The selector starts open. Selecting CAN starts TWAI in listen-only mode.
An explicit USB lease and request are required to arm TX. The diagnostic
window has a 900 ms software budget and returns to listen-only after a reply
or timeout. A controller or ISO-TP fault drops the arm and opens the selector.
The CH340 provides no physical USB disconnect signal to the MCU.
Active mode can send requests, ISO-TP flow control, ACKs, and error frames.
The implementation supports 250/500 kbit/s Classical CAN with standard IDs,
functional read-only OBD requests, and one ISO-TP responder per request.
Desktop and mobile diagnostic controls are outside this firmware target.
Relay timing and isolation still require physical verification.

## Checks and bring-up

KiCad 10 full DRC reports zero violations, unconnected items or schematic
parity issues. The pad connectivity audit finds all 231 ground pads in one
group. The MCU fanout uses a local CAN RX escape on L2. Keep the
filled-and-capped processing specified in the board for vias whose drills
intersect SMD lands.

KiCad 10 all-severity ERC passed with zero violations. The netlist checker
compares every net to Rev C plus the declared changes and evaluates all eight
steady-state permit/request combinations using the normally open relay contacts.
The TX logic check covers 64 combinations of route request, hardware permit,
relay commands and TX arm. Only the fully enabled CAN state allows TX.
The check covers connectivity and the contact model. It does not measure
physical timing, leakage, or behavior under a welded contact.

```powershell
kicad-cli sch erc --severity-all --exit-code-violations ChryslerScanner_RevD.kicad_sch
kicad-cli sch export netlist --format kicadxml -o rev-d-netlist.xml ChryslerScanner_RevD.kicad_sch
python check_netlist.py rev-d-netlist.xml
kicad-cli pcb drc --all-track-errors --schematic-parity --severity-all --refill-zones --exit-code-violations ChryslerScanner_RevD.kicad_pcb
```

Before routing release, verify mechanical land patterns and the relay supply
and permit loading. Measure the minimum pickup delay and maximum release and
bounce including diode flyback, tolerance, temperature, supply sequencing
and rapid changes. Check both poles during MCU reset, missing heartbeat,
brownout and recovery. The relay model does not guarantee opening when a
contact welds or the coil safety transistor shorts. Qualify these cases
before connecting a vehicle or permitting programming voltages. Confirm
CAN signal quality and listen-only capture on a terminated bench bus
with separate transmitting and acknowledging nodes.

Exercise PID, DTC and multi-frame VIN responses on the bench at both bit
rates. Scope TXD and both relay outputs during the request, response, timeout
and bus-off cases. Confirm passive capture contributes no ACK, verify
transmit permit removal on lease release, and measure the time to recessive
TXD after a watchdog fault.

[Relay datasheet](https://components.omron.com/sites/default/files/datasheet_pdf/K106-E1.pdf)
· [I2C expander datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP23008-MCP23S08-Data-Sheet-20001919F.pdf)
· [CAN transceiver datasheet](https://www.ti.com/lit/ds/symlink/tcan1042h-q1.pdf)

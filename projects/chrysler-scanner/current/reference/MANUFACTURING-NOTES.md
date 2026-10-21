# Manufacturing and assembly requirements

These requirements describe the exact checked PCB identified below. They do not constitute a manufacturing order or hardware qualification.

**PCB SHA256:** `f4a5945538dd61389ef7a3937fe1406f76e9dfba2382e11e35fac4b787a8e12a`

The board is 110 × 55 mm with four copper layers and nominal 1.6 mm thickness. Preserve the inner ground reference, antenna keepouts and native geometry. RF/USB impedance targets require review against the actual fabricator stackup.

## Filled and capped vias

Every site in this table requires nonconductive resin fill, copper capping and planarization (VIPPO). Ordinary open or tented drilled vias cannot replace this process. Tenting settings do not replace filling/capping. The actual saved KiCad filling and capping flags were reloaded and checked. All surface-mount pad apertures intersected by drills have these flags.

| Net / nearby pads | X mm | Y mm | Copper / drill mm | Front / rear tenting | UUID |
| --- | ---: | ---: | --- | --- | --- |
| GND / U13.4 | 123.812500 | 141.487500 | 0.60 / 0.30 | tented / tented | 48f683c4-3dd7-526b-8754-f7ab5cfa5510 |
| N_R11_1 / pad-edge escape | 161.173500 | 139.008900 | 0.60 / 0.30 | tented / tented | 7ddf842a-ba60-474b-8b13-336cf6a58587 |
| RX7_BIAS_EN / pad-edge escape | 164.819600 | 141.209800 | 0.60 / 0.30 | tented / tented | 1b841adb-6b3a-49bc-9897-d601d8baf368 |
| RX7_BIAS_EN / pad-edge escape | 165.080800 | 142.313300 | 0.60 / 0.30 | tented / tented | 03df75de-2a49-4b09-8039-39ac565edcfd |
| SDA / pad-edge escape | 165.083900 | 123.549800 | 0.60 / 0.30 | tented / tented | 408794a8-2311-4911-96fa-4296a80d79fc |
| SDA / pad-edge escape | 165.304900 | 117.435800 | 0.60 / 0.30 | tented / tented | 580d523b-68fb-4a45-9dca-eecffe65582f |
| GND / C56.2 | 167.000000 | 133.475000 | 0.60 / 0.30 | tented / tented | 75781361-256c-4837-88cc-ba6fda185725 |
| GND / U19.25 | 168.000000 | 138.250000 | 0.60 / 0.30 | open / tented | 3d2b97c3-78f3-5237-9c46-18156e7f8795 |
| PCI_RX / pad-edge escape | 168.717600 | 121.021600 | 0.60 / 0.30 | tented / tented | 8734c258-e496-4cfc-81fb-21ce9f52b344 |
| PWR_LED / pad-edge escape | 168.883200 | 122.016800 | 0.60 / 0.30 | tented / tented | 2ff00f93-8846-42df-b197-9ada7017060c |
| PWR_LED / pad-edge escape | 169.885400 | 119.044800 | 0.60 / 0.30 | tented / tented | 3fa55b73-e865-4651-ad92-b3a8fac24abe |
| GND / C57.2 | 170.625000 | 134.725000 | 0.60 / 0.30 | tented / tented | b7697e04-db47-561f-9a4e-d233a506b8ac |
| V_BT / pad-edge escape | 170.942500 | 117.112500 | 0.60 / 0.30 | tented / tented | 8cf8242f-4b46-50a7-a351-4b51bd98f7f7 |
| LOG_BUTTON / pad-edge escape | 170.956200 | 132.513500 | 0.60 / 0.30 | tented / tented | 6cdc3d29-ecd2-4b3a-aebc-db851e5df992 |
| GND / C26.2 | 171.450000 | 121.025000 | 0.60 / 0.30 | tented / tented | 68ec5b48-b597-5ec5-b705-5eb74073c7f9 |
| +3.3V / R87.1 | 171.500000 | 139.075000 | 0.60 / 0.30 | tented / tented | f3ed3169-4f94-4c67-96a3-4055a4a6b525 |
| SDA / pad-edge escape | 171.572300 | 133.158400 | 0.60 / 0.30 | tented / tented | 137d9f61-5487-4f6b-b5fe-53a3392d661e |
| TX_LED / pad-edge escape | 171.900000 | 119.375000 | 0.60 / 0.30 | tented / tented | e5be0212-82b3-4107-b93e-da42f058e245 |
| RX7_BIAS_EN / pad-edge escape | 172.500000 | 138.000000 | 0.60 / 0.30 | tented / tented | 3c79c845-4b6d-4c46-8c8a-8b603738c973 |
| GND / U10.49 | 172.787500 | 114.712500 | 0.60 / 0.30 | open / tented | 58fa7355-b3ff-5452-8638-c5bbac75cb55 |
| GND / U10.49 | 172.787500 | 116.512500 | 0.60 / 0.30 | open / tented | 7cf65e96-662f-5743-9633-c54e27543225 |
| PWR_LED / pad-edge escape | 173.076800 | 123.991900 | 0.60 / 0.30 | tented / tented | a20c6ad3-184a-49cf-9e2b-4ffcd9145520 |
| RX15_EN / pad-edge escape | 173.400000 | 138.425000 | 0.60 / 0.30 | tented / tented | 3c1a0180-b98a-4787-9105-2da1707648d9 |
| LOG_BUTTON / pad-edge escape | 174.038000 | 134.993000 | 0.60 / 0.30 | tented / tented | b993e142-812a-4612-8dc5-b1e112396a78 |
| GND / U10.49 | 174.587500 | 114.712500 | 0.60 / 0.30 | open / tented | b4cba1e6-ea24-5a74-bc91-afec95083085 |
| GND / U10.49 | 174.587500 | 116.512500 | 0.60 / 0.30 | open / tented | 8db94462-3d3d-5a36-94f3-aec1d3125488 |
| TX_LED / pad-edge escape | 175.100000 | 130.275000 | 0.60 / 0.30 | tented / tented | de55ceba-41f5-4d3a-bc99-1e36713f60c5 |
| GND / C31.2 | 175.775000 | 120.750000 | 0.60 / 0.30 | tented / tented | ea669069-42ed-59b8-8f2b-a6c53cd3d62f |
| SCL / pad-edge escape | 175.797500 | 134.244200 | 0.60 / 0.30 | tented / tented | 9efcfa21-2d0c-4845-a5c2-a9b68fd1e39d |
| TX_LED / pad-edge escape | 179.600000 | 140.875000 | 0.60 / 0.30 | tented / tented | a8805c5c-c73f-4d21-a8b7-6d61ae7c2945 |
| PWR_LED / pad-edge escape | 179.674200 | 124.034500 | 0.60 / 0.30 | tented / tented | bb810104-d0c2-455d-b8cc-282b90f75d9e |
| PWR_LED / pad-edge escape | 182.533400 | 123.811100 | 0.60 / 0.30 | tented / tented | 40325167-1d86-45a3-836c-c0bfca3ded20 |
| GND / C23.2 | 185.775000 | 115.750000 | 0.60 / 0.30 | tented / tented | 7d5c0199-5627-5888-b109-2cdd12e36f0d |
| GND / U11.2 | 200.050099 | 128.750000 | 0.60 / 0.30 | tented / tented | 9a887a6b-218d-5083-812e-b6f3faba1440 |
| GND / U12.29 | 203.979982 | 114.440018 | 0.60 / 0.30 | open / tented | 054fe1b1-22f7-5290-b500-a7f213f7380a |

## Assembly and prototype checks

Outer ground fills connect surface-mount ground pads solidly; through-hole pads use thermal reliefs. Account for ground copper and exposed-pad vias in the stencil and reflow process.

The microSD socket and its regulator/capacitors are on the underside. Provide card access and at least 7 mm underside clearance; verify enclosure fit against the actual parts.

Prototype checks still include supply droop and peak SD current, shared +5 V capacity, regulator temperature, RF/USB signal integrity and vehicle-interface behavior. The design has no RTC or shutdown hold-up. Firmware remains deferred and the current firmware has not been made to log to this SD socket.

The subsequent schematic reorganization changes only the PCB J1 sheet path.
Current PCB SHA256: `85011cefd33c4d6a623440d91eeb9876282d39dc7fc6a37eb90d50e2a278c36a`.
The geometry and fabrication exports are unchanged from the source hash above.

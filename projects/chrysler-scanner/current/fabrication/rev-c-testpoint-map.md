> Current 2026-10-28 refinement: testpoint identities and geometry are unchanged, and the overall board now requires 246 filled/capped/planarized sites. The 230-site count below records the historical debug-addition checkpoint. Use the current fabrication processing-site JSON and layered verifier.

# Debug access / test points

48 Keystone 5015 micro-miniature SMT loops accept miniature grabbers; four bare 1 mm SPI probe pads avoid a hook on the SPI lines. They are distributed across both board sides to preserve all existing placements. Silkscreen TP numbers match this table and schematic page 24. Use board spacers for underside access. The footprint uses the manufacturer-recommended 3.4 × 1.8 mm solder pad; the optional outline silk is omitted to retain readable labels in dense areas. These are small SMT loops: use lightweight miniature grabbers and avoid pulling on them.

TP1–TP10 cover power, TP11–TP19 the OBD bus lines, TP20–TP31 UART/I²C/PCI logic, TP32–TP35 safety/heartbeat/reset, TP36–TP41 ADC before and after isolation, TP42 card detect, TP43–TP44 CCD logic, TP45–TP48 SPI, and TP49–TP52 local ground clips. N_R88_2 is the expander reset/permit output. ACT_LED is the dedicated health heartbeat, not ordinary activity traffic.

Use high-impedance probes for ADC/logic measurements, not 50 Ω scope termination. Ground clips are GND only; never use a programming rail as a scope ground. Hook hardware is deliberately absent from the RF and USB differential paths. SPI pads have short taps, up to 5 mm; verify signal integrity at the actual configured clock speed during bench qualification.

No previous traces or component placements are removed or moved by this addition. There are 19 new 0.2 mm track segments and three filled/capped vias. 22 existing vias under the new pads require filling, copper capping and planarizing without any change to drill/copper geometry. Total processing sites: 230. Earlier fabrication archives are superseded. The exact additive contract is verified by source/verify_testpoints.py against reference/pre-testpoints.

[Keystone 5015 product and drawing](https://www.keyelco.com/product.cfm/Micro-Miniature/5015/product_id/1353). No manufacturer 3D model is bundled for the new loops; footprint/courtyard clearance is checked, while actual clip and enclosure access remain physical assembly checks.

| TP | Net | Type | Side | X mm | Y mm |
|---|---|---|---|---:|---:|
| TP1 | J1962-16 | 5015 loop | top | 107.809 | 143.591 |
| TP2 | +12V | 5015 loop | bottom | 110.616 | 134.962 |
| TP3 | VBUS | 5015 loop | bottom | 204.071 | 110.500 |
| TP4 | +5V | 5015 loop | top | 130.078 | 117.637 |
| TP5 | +3.3V | 5015 loop | bottom | 159.851 | 131.921 |
| TP6 | SD_3V3 | 5015 loop | bottom | 199.000 | 134.575 |
| TP7 | +7.5V | 5015 loop | bottom | 197.215 | 112.064 |
| TP8 | VBB | 5015 loop | bottom | 138.287 | 126.695 |
| TP9 | VPP | 5015 loop | top | 149.552 | 125.922 |
| TP10 | PCI_VCC | 5015 loop | bottom | 119.460 | 126.075 |
| TP11 | J1962-2 | 5015 loop | bottom | 114.805 | 119.279 |
| TP12 | J1962-3 | 5015 loop | bottom | 119.531 | 116.270 |
| TP13 | J1962-11 | 5015 loop | bottom | 115.283 | 115.201 |
| TP14 | J1962-6 | 5015 loop | bottom | 142.684 | 130.857 |
| TP15 | J1962-12 | 5015 loop | bottom | 118.409 | 138.312 |
| TP16 | J1962-14 | 5015 loop | bottom | 163.011 | 151.992 |
| TP17 | J1962-9 | 5015 loop | top | 140.370 | 142.753 |
| TP18 | J1962-7 | 5015 loop | bottom | 128.849 | 147.519 |
| TP19 | J1962-15 | 5015 loop | bottom | 124.969 | 150.450 |
| TP20 | TX0 | 5015 loop | bottom | 198.550 | 119.325 |
| TP21 | RX0 | 5015 loop | top | 187.465 | 121.131 |
| TP22 | EN | 5015 loop | bottom | 157.240 | 104.841 |
| TP23 | IO0 | 5015 loop | top | 186.572 | 149.672 |
| TP24 | SCL | 5015 loop | bottom | 175.350 | 143.830 |
| TP25 | SDA | 5015 loop | top | 162.834 | 118.639 |
| TP26 | PCI_RX | 5015 loop | bottom | 131.319 | 121.022 |
| TP27 | PCI_TX | 5015 loop | bottom | 161.903 | 125.840 |
| TP28 | RX1 | 5015 loop | bottom | 171.474 | 106.574 |
| TP29 | TX1 | 5015 loop | bottom | 130.941 | 104.405 |
| TP30 | RX2 | 5015 loop | bottom | 136.145 | 146.863 |
| TP31 | TX2 | 5015 loop | bottom | 124.093 | 139.191 |
| TP32 | ACT_LED | 5015 loop | bottom | 183.350 | 122.275 |
| TP33 | HEARTBEAT_VALID | 5015 loop | bottom | 161.812 | 105.050 |
| TP34 | LOGIC_PG | 5015 loop | bottom | 162.512 | 145.750 |
| TP35 | N_R88_2 | 5015 loop | bottom | 152.916 | 126.725 |
| TP36 | V_BA_PRE | 5015 loop | bottom | 144.161 | 113.176 |
| TP37 | V_BA | 5015 loop | bottom | 146.433 | 126.736 |
| TP38 | V_BT_PRE | 5015 loop | bottom | 171.698 | 129.065 |
| TP39 | V_BT | 5015 loop | bottom | 154.277 | 150.585 |
| TP40 | V_PR_PRE | 5015 loop | bottom | 139.302 | 112.885 |
| TP41 | V_PR | 5015 loop | bottom | 167.007 | 130.495 |
| TP42 | SD_DETECT | 5015 loop | top | 195.657 | 139.344 |
| TP43 | CCD+ | 5015 loop | top | 129.750 | 112.825 |
| TP44 | CCD- | 5015 loop | bottom | 121.223 | 111.808 |
| TP45 | SD_CS | Bare pad | bottom | 181.588 | 133.305 |
| TP46 | SD_SCK | Bare pad | top | 191.625 | 139.349 |
| TP47 | SD_MOSI | Bare pad | bottom | 184.425 | 130.999 |
| TP48 | SD_MISO | Bare pad | bottom | 187.516 | 113.395 |
| TP49 | GND | 5015 loop | bottom | 115.250 | 143.000 |
| TP50 | GND | 5015 loop | bottom | 134.375 | 152.250 |
| TP51 | GND | 5015 loop | bottom | 169.275 | 145.250 |
| TP52 | GND | 5015 loop | bottom | 203.980 | 114.440 |

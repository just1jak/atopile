# Rev D assembly BOM: Omron sourcing update

2026-11-07. K1–K4 select **OMRON G6K-2F-Y-TR DC5 BY OMR/C,
JLC/LCSC C231390**. This is a purchasing change to the existing G6K-2F-Y
5 V relay design. PCB, schematic, routing, firmware and the hardened bench
fabrication ZIP are unchanged. This package is for bench quotation and
assembly review; it does not qualify the tool for vehicle use or programming.

## Compatibility decision

The selected part is the monostable, surface-mount, Y-terminal DPDT version.
The `-TR` ordering option is tape packaging. Omron's February 2018 notice
explicitly lists `G6K-2F-Y-TR DC5 BY OMR/C`, internal code G6K3090M, and its
factory-transfer replacement. It describes a factory/lot-marking change,
without a specification change. The subsequent February 2019 notice says
that production instead transfers to Japan and specifications and external
dimensions remain unchanged. The supplier name therefore refers to a
documented Omron ordering variant. It does not establish the date, factory
or condition of the particular stock that will be supplied.

| Check | Result |
| --- | --- |
| Coil and drive | 5 V, nominal 237 ohms / 21.1 mA. Two selected coils draw about 42.2 mA nominal, as before. Positive coil pin 1, switched return pin 8. |
| Contacts | Common pins 3/6, normally open pins 4/5; NC pins 2/7 remain unused. Same 1 A at 30 VDC resistive rating; the existing bounded 28 V envelope remains. |
| PCB lands | All four actual PCB footprints match: 1.8 × 0.8 mm pads, 7.0 mm row spacing, 3.2/2.2/2.2 mm longitudinal intervals. The ordinary non-Y footprint is different and is not an alternate. |
| Body | Nominal 10 × 6.5 × 5.2 mm, same as the existing design. |
| Isolation architecture | K1+K3 remain in series on CAN; K2+K4 remain in series on Legacy. All four packages and their independent stage drivers remain fitted. |
| Default and fault behavior | Unchanged normally open contacts, supervised coil permit, passive CAN default, hardware TX arm gate and nonretriggerable TX timer. |

Manufacturer evidence: [G6K datasheet, ordering/ratings/dimensions](https://components.omron.com/us-en/system/files/2026-05/datasheet_pdf/K106-E1.pdf),
[2018 factory notice, exact `/C` model on page 2](https://www.anglia.com/registration/pcn_ptn/docs/pcn/omr_PCN%20G6K.pdf),
[2019 superseding factory notice](https://media.digikey.com/pdf/PCNs/Omron/Rel-199A.pdf).
Supplier identity: [JLC C231390](https://jlcpcb.com/partdetail/231277-G6K_2F_Y_TR_DC5_BY_OMRC/C231390),
[LCSC C231390](https://www.lcsc.com/product-detail/C231390.html).

Incoming assembly review must confirm the supplied 5 V nonlatching Y part,
lot traceability, pin-1 orientation and solderability. Do not use distributor
typical operate/release numbers as timing guarantees. The existing release,
bounce, diode-flyback, brownout, cold-boot, stuck-contact/driver, CAN signal
quality and hardware TX-timeout bench qualifications remain required.
No wider temperature, 24 V input or automotive qualification is added.

## Files and scope

- `BOM.csv`: all 393 schematic components, including explicit exclusions.
- `JLC-BOM.csv`: 113 purchasing rows / 385 placed components per board.
- `JLC-CPL.csv`: the same 385 references, copied from native KiCad placement
  coordinates, sides and rotations. Coordinates are millimetres, with KiCad's
  upward-positive Y convention. JLC's component preview must be reviewed
  against the board before ordering; no rotation corrections are guessed.
- `selections.json`: inherits the frozen Rev C exact-part ledger and selects
  the 60 Rev D additions. Small passives and AO3400A reuse existing selections.
  D40 and D41/D42 have explicit manufacturer packaging suffixes; U33 is the
  **LTC6993-1**, distinct from the existing **LTC6993-2** at U22.
- `checks.json` / `verify.py`: fresh native-check evidence and the repeatable
  BOM/placement, relay-land and unchanged-release audit.
- `quote-status.md`: quote progress and explicitly limited catalog comparison.

R23/R24 remain DNP. JP1/JP2 and TP45–TP48 remain PCB features, not components
to purchase or assemble. All 48 Keystone 5015 hook testpoints remain fitted.
The Rev C quote-only capacitor, diode and resistor substitutions are not
silently imported. Supplier IDs are carried forward only for identical MPNs;
blank IDs require exact-part matching. Catalog identity does not imply stock
is available to the JLC assembly account.

Use the unchanged `../../outputs/ChryslerScanner-RevD-hardened-bench-fabrication.zip`
for Gerbers: **110 × 96 mm, four layers, 1.6 mm, assembly on both sides**.
The quoted process must fill, copper-cap and planarize all 254 recorded
sites. ENIG and 1 oz inner/outer copper are retained for comparison.
Do not reuse the old 110 × 55 mm Rev C quote as a Rev D assembly total.

## Verification

Fresh KiCad 10 ERC and full DRC with zone refill and schematic parity report
zero violations, unconnected items and parity issues under the unchanged
project settings. The existing netlist checker passes all retained legacy
net contracts, 80 conductor/contact-state cases and 128 TX-permit cases.
The procurement audit verifies all four relay lands, exact BOM/CPL agreement,
254 processed vias and 113 unchanged Rev D release files including the ZIP.
This is a procurement-delta review, not a new independent whole-board review.

From the repository root, after exporting fresh native reports and positions:

```powershell
& 'C:/Program Files/KiCad/10.0/bin/python.exe' projects/chrysler-scanner/rev-d/procurement/verify.py `
  --netlist .build-cache/rev-d-relay-procurement.xml `
  --erc .build-cache/rev-d-relay-erc.json --drc .build-cache/rev-d-relay-drc.json `
  --positions .build-cache/rev-d-relay-positions.csv `
  --report .build-cache/rev-d-procurement-checks.json
```

PCB SHA-256: `2e78fc59cdb673444d1d433c10f06dfd234662e7a467a3b113f6c6cee1294ea0`.
Unchanged bench ZIP SHA-256: `c1663b4b48c9ed3a417d6e2abbae966029568083a504ff6e5e4dc472fdc33b68`.

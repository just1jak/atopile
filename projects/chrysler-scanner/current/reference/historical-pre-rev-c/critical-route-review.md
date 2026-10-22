# Critical routing seed

Use `critical-power-candidate.kicad_pcb` as the input to the remaining router. Its SHA256 is `82c75bbcafb8474820fe86ec497f9660b5a900f2315c6744f6cd3a8a79019ea4`. It builds on the frozen physical correction `f2b5c36611bb8ea9b47a6f21de91bd04ad656ecaa4f75047ede9a9424269604e` without moving any component.

Native KiCad 10 checks with `--all-track-errors --refill-zones` report **0 errors and 0 warnings**. This is a preroute seed: **553 full-board airwires remain** after a native in-memory zone fill. The CLI's list is capped at 499; that list must not be used as the completion count. `critical-route-proof.json` records the native connectivity and preservation assertions.

All 263 footprint blocks are byte-identical to the corrected physical input. Every existing copper segment, via, zone and drawing remains. The seed adds 96 locked track segments and 16 locked tented through vias. The original GND stitch via remains too. No rule exclusions, net changes, footprint changes or project-rule relaxations were introduced.

## USB and radio paths

All intended pad members of `LNA_IN`, `N_R23_1`, `D+`, `D-`, `D+P` and `D-P` belong to their respective connected native copper groups. The four USB nets follow the actual schematic: J2 A6/B6 → U11.1; J2 A7/B7 → U11.3; U11.6 → U12.4; U11.4 → U12.5. U12 is the classic CP2102.

USB primary and downstream paths use F.Cu over the ground reference. Only the short reversible-contact crossover uses B.Cu, with a matching two-via topology on each USB net. The connector contact fanout and the ESD pin fanout are uncoupled sections; the straight downstream trunk uses 0.22 mm traces and 0.15 mm gap. Connector traces use 0.20 mm. Preserve the locked geometry. These are 90 Ω design targets, not a measured or fabricator-qualified impedance. Signal-path length sums in the proof include branches; they are not end-to-end differential delay measurements. Silicon Labs' [USB layout guidance](https://www.silabs.com/documents/public/application-notes/an0046-efm32-usb-hardware-design-guidelines.pdf) supports a continuous reference, short paths and controlled differential geometry; device-specific EFM32 resistor values do not apply to this CP2102 circuit.

RF uses 0.30 mm F.Cu copper with the existing series element and optional shunt pads preserved. Shunt ground stubs join the ground planes through nearby vias outside the antenna reserve. The original all-layer no-via/no-pour antenna region remains at x166.1–179.1, y100–106 mm. New track-only keepouts cover that entire box on B.Cu and both inner layers; two F.Cu boxes leave only a 0.75 mm corridor centered on the locked feed at x171.1 mm. Native export confirms these become five `wire_keepout` polygons, with the original four `via_keepout` polygons retained. The 50 Ω RF goal and antenna tuning require the real fabricated stackup and hardware validation. See [Espressif PCB guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html).

## Power routes and remaining constraints

The four switch-node groups are complete in native connectivity and locked on F.Cu at 0.60 mm: `N_C5_2` (U2), `N_D7_2` (U5), `N_C17_2` (U6), and `N_C21_2` (U7). The three LMR14010 bootstrap connections are locked at 0.25 mm. Local inductor/output-capacitor and filter links use 0.80 mm. Nearby ground-return vias join the ground plane. USB power-switch input/output decoupling is connected locally at 0.50/0.40 mm. Preserve these routes instead of letting a generic router meander the switching nodes. This follows the short-loop principle in TI's [LMR14010A documentation](https://www.ti.com/product/LMR14010A); it is not a thermal or EMI qualification.

`routing-constraints.json` gives explicit starting widths for the remaining rails. In particular, do not consider long 0.25 mm default routes a validated 1 A supply design: review +12 V and +5 V trunks, USB switch/diode paths, and the dedicated SD regulator feed. Short narrow escapes at fine-pitch pads can be necessary; their length must remain limited. Keep In1.Cu as the continuous ground reference and avoid using it for ordinary signal routing. Preserve local In2 ground under the radio and return paths around the power converters.

The VPP programming supply is nominally 20 V and VBB nominally 12 V in the scanner API. Route those away from logic and feedback traces; 0.30 mm is a conservative routing-clearance target where package geometry permits, while the native project's existing intrinsic pad rules remain authoritative. Do not silently change a regulator pin, connector net or component placement to make routing fit.

The remaining router must connect ground pads, dense MCU escapes, bus interfaces and rail branches. It cannot establish current capacity, regulator cooling, antenna match, USB impedance, SD timing or automotive transient survival. The SD LDO's 500 mA rating does not prove the shared upstream power chain can supply every load. Firmware remains deferred.

## Completion checks

After SES import, verify all footprint positions, rotations, sides and UUID paths, since an SES importer may apply placement information. Preserve locked copper and all antenna keepouts. Refill zones natively, require the **uncapped native airwire count to be zero**, and run full native DRC with no errors, warnings or added exclusions. Also compare every pad's net endpoint set with the schematic-derived baseline. The final native result, rather than the autorouter's completion message, determines electrical connectivity.

`critical-routes.json` applies RF/USB to the physical seed; `critical-power-routes.json` applies the power additions to the first candidate. `critical_routes.py` enforces the exact input hash, writes a different output path and marks additions locked. `verify_critical_routes.py` performs the independent native and preservation checks. The source project and physical seed remain unchanged.

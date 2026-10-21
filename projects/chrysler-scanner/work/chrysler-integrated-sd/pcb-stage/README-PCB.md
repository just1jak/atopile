# Integrated main-board SD logger, engineering revision A

This is the **same Chrysler V240 scanner PCB**, expanded previously to110x55mm. It adds18parts on the back; there is no XIAO module, daughterboard, or separate logger PCB. The existing ESP32-PICO-V3-02 remains the controller. Firmware is deferred at the user's request.

The original245footprints, all original footprint/pad UUIDs and physical geometry, connector locations, mounting holes, outline geometry, and original board-zone/keep-out polygons/properties are preserved. Exactly six previously singleton/unused U10 pad nets are reassigned according to the frozen integration manifest. Added parts use the manifest's full native KiCad footprint IDs and the merged schematic's instance paths. Original3D model geometry/transforms remain unchanged; only model pathnames are made portable. H1–H4 retain their existing native attributes and additionally carry the board-only metadata flag, because these mechanical holes intentionally have no schematic symbols; this changes neither geometry nor DRC rules.

## Placement

Board origin is absolute(100,100)mm. J4 is on the back at absolute(190,146)mm, i.e. local(90,46)mm, opening toward the bottom edge. Its courtyard is inside the existing board outline. The card extends about4.7mm beyond that edge; provide a case cutout and finger access. C61 is5.9mm tall, so **allow at least7mm clear space below the board**, plus access to the LOG/STOP button. Existing front-side RESET/BOOT controls remain in place.

U20 and input/output capacitors occupy the back-side area north of J4. R104/R105/R106 are near the corresponding U10 source pads. R104 sits outside the existing antenna-feed drawing/keep-out region; the existing RF keep-outs are unchanged. SW3 is on the back near the bottom edge, left of J4. All existing connector and through-hole projections remain clear of the new component courtyards.

U20 is MCP1825S-3302E/DB: main **+5V** to a dedicated SD_3V3 rail. It does not draw SDcard power from the MCU3.3V rail or directly from USB VBUS. The shared upstream5V power budget, LDO heat-spreading copper/thermal vias, load-transient response, power sequencing, and final current/temperature limits still require completion during routing and bench validation. The500mA device rating is not a proven continuous thermal rating of this unrouted board. C61 is transient decoupling, not safe-shutdown hold-up.

## Verified state and remaining work

The board is **unrouted**: no new tracks or vias are fabricated by this revision. The existing base also has zero tracks/vias. Both retain their original provisional, unfilled plane definitions. Native KiCad10 DRC is run with in-memory zone refill; it does not save/refill the project board on disk.

`pcb-preservation.json` records native before/after preservation checks and source hashes. `drc-baseline.json`, `drc-final.json`, and `drc-comparison.json` show the inherited rule-check baseline and introduced differences. The target is **no newly introduced physical-rule violations**, not a claim that the whole scanner passes DRC. Existing errors: four U12 corner-pad clearances and four J2 pad/NPTH-hole clearances. Existing warnings: one isolated-copper region and one local-footprint-library mismatch. These are unchanged by adding the SD hardware.

The CLI JSON report stops at499 missing connections. Full native connectivity API counts are recorded separately: baseline561airwires and combined607airwires,46additional unrouted connections. New SD nets and their missing connections are registered and included in the native connectivity engine. Schematic/PCB parity is validated after the final schematic merge by the root packager.

No manufacturing outputs are produced for this unrouted engineering board. Routing, complete DRC/ERC resolution, upstream power validation, enclosure clearance, firmware, and physical tests remain before fabrication/use. The original scanner project was neither overwritten nor modified.

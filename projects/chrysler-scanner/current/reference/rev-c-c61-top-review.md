# C61 top-side move review


## 2026-10-22 C61 top-side relocation

User authorized moving C61 to F.Cu at (193,127) mm, orientation 90 degrees. Pin 1 remains SD_3V3 and pin 2 GND. Exactly two obsolete unlocked SD_3V3 branch segments are removed; four 0.5 mm tracks and two 0.6/0.3 mm filled/capped vias are added. All retained copper and other placements are exact. R96 reference text alone is repositioned. Native all-severity ERC, full refill/track/parity DRC, body-overlap and native connectivity checks pass. See rev-c-c61-top-audit.json and source/verify_c61_top.py. This is an implementing-agent adversarial delta review; the prior independent review retains its original provenance. No new independent reviewer is claimed. C61 requires about 5.9 mm top-side component headroom; verify the actual enclosure.

Final PCB SHA-256: `a2cb3d5e82d57b75eb0caab103d6f82529d8543b182aa9fc80e320bfe61c2fd5`. Exact pre-move board is frozen under reference/pre-c61. Native structural checks permit only this single capacitor transform and two C61 copper removals in addition to the existing 55 safety removals. The original pre-P1 baseline is unchanged.

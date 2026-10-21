# Native5 ground stitching fabrication requirements

This is an incomplete engineering work copy. It has six isolated GND pads and five signal connections remaining.
All nine sites below require nonconductive filled, copper capped, planarized via-in-pad (VIPPO) processing. Open vias or tenting alone are not equivalent.
All are through vias with 0.60 mm copper diameter and 0.30 mm drill. The pad and footprint geometry was not changed.
The original front pad mask windows remain. Exposed thermal pad vias are top open / bottom tented; ordinary component pad sites are tented both sides.

| Target | X mm | Y mm | Via UUID |
| --- | ---: | ---: | --- |
| U10.49 | 173.687500 | 115.362500 | 87918af0-1294-525b-97f0-f493c22293c6 |
| U10.49 | 172.787500 | 115.362500 | 3369aeaf-d4a1-5472-b28b-5c869e8d0f87 |
| U10.49 | 174.587500 | 115.362500 | acb91d58-5ff1-55fc-9627-1e082d19c8f0 |
| U19.18,U19.22,U19.24,U19.25,U19.9 | 168.000000 | 137.850000 | 3f620289-6eae-5796-977d-602df49c9a9f |
| U12.29,U12.3 | 203.979982 | 114.440018 | 054fe1b1-22f7-5290-b500-a7f213f7380a |
| C28.2 | 175.775000 | 122.400000 | 0e15f86d-1936-55ef-bb73-836862cbb8a2 |
| R59.2 | 152.075000 | 147.750000 | 0bcb79aa-808e-548b-b188-6a060d332568 |
| U11.2 | 200.050099 | 128.750000 | 9a887a6b-218d-5083-812e-b6f3faba1440 |
| U13.4 | 123.812500 | 141.487500 | 48f683c4-3dd7-526b-8754-f7ab5cfa5510 |

Native DRC: no new violation identities; only the inherited four edge-clearance findings and three dangling copper warnings remain. Schematic parity: zero.
The 150 µm necks and their actual lengths are recorded individually in ground-stitch-proof.json; wider copper is retained elsewhere.

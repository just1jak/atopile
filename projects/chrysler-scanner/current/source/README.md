# Native routing and verification helpers

The PCB and schematic are native KiCad files. Open the project in KiCad 10;
these scripts are not needed to view or edit it. Firmware is deferred.

The included helpers preserve the routing and verification methods used for
this revision. Native helpers require KiCad 10's bundled Python and pcbnew.
The Specctra and independent serialized-board audit helpers require Python and
sexpdata. They are snapshots of the local work pipeline, not a standalone
Atopile regeneration system. CLI arguments and original frozen reference paths
are visible in their source. Some provenance comparisons require the retained
local seed, reference boards, original source manifest and native XML exports.
Those large historical inputs are not duplicated into this portable CAD folder.

The final native DRC, circuit and routing reports in reference identify the
exact checked PCB by SHA256. Rerun KiCad's native DRC with refill and schematic
parity after any edit; the supplied reports apply only to the recorded revision.

The router ran locally with networking denied. No board upload, manufacturing
order, firmware compilation or flashing was performed for this routing task.

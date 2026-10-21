# Local FreeRouting 1.9 checkpoints

`-im 1` enables intermediate GUI-board snapshots. The engine saves after completed
passes, at most once every 30 seconds, into `java.io.tmpdir/freerouting-<inputCRC32>.frb`.
It overwrites that path; it is not a best-result history. Use a dedicated temporary
directory per run, and an input whose optional placement values are ASCII.

Compile the task-local helper against the verified JAR:

```sh
/opt/homebrew/opt/openjdk@17/bin/javac -cp freerouting-1.9.0.jar CheckpointToSes.java
```

Then export a distinct immutable checkpoint without attaching to the live engine:

```sh
/usr/bin/sandbox-exec -f offline.sb /opt/homebrew/opt/openjdk@17/bin/java \
  -Xmx512m -Djava.awt.headless=true -cp freerouting-1.9.0.jar:. \
  CheckpointToSes INPUT.frb NEW_OUTPUT.ses ORIGINAL_INPUT.dsn
```

The helper requires JAR SHA256
`9084a4888937a7f31f857ecc12aa7a37407f51160e4d2892dff9c9bb47ae3102`.
It checks that the source bytes and metadata remain stable while copying, saves
`NEW_OUTPUT.ses.frb`, deserializes that copy, exports through the native engine's
SES writer, and reports engine counts. It never routes or writes the source
checkpoint, DSN, or a native PCB. Outputs must be new paths. A rejected snapshot
copy remains for diagnosis; retry with another output name after the next save.
Java serialization input must be our trusted local engine output, never a
downloaded FRB. Core-only invocation does not initialize the application or its
analytics client; the network-denied sandbox adds a runtime boundary.

**SES contains placement.** Before importing into the exact native seed, run:

```sh
python3 specctra_tools.py sanitize-ses NEW_OUTPUT.ses NEW_NO_PLACEMENT.ses
```

Native KiCad import preserves locked seed copper but replaces unlocked copper.
Never import into an unrelated board. Afterwards assert exact footprint/pad
geometry, all assigned pad nets, preserved critical copper, and run native KiCad
DRC including unconnected items and schematic parity. Engine airwire counts and
native KiCad counts can differ; neither a saved checkpoint nor a successful SES
export proves a completed board.

Actual engine APIs were checked against the pinned JAR's `BoardFrame.save`,
`BoardHandling.save_design_file`, and `SpecctraSesFileWriter.write` bytecode.
The helper's regression tests cover a complete captured checkpoint, refusal to
overwrite outputs, and rejection of an incomplete board graph.

## Bounded ground-only repair

`GroundFanout.java` uses the same pinned core's `RoutingBoard.fanout` on disconnected
GND SMD pins in an immutable copied checkpoint. Its budgets are explicit (maximum
5 seconds per pin and 300 seconds overall), with two passes and no ripup. It keeps
the parsed plane, class, via, and keepout rules. It accepts only exact rational
collinear subdivisions of protected centerlines, with unchanged layer/net/width;
protected vias, areas and pins and every component placement are checked too.
Non-ground net connectivity must not regress. This is a candidate generator, not
a replacement for final native KiCad import/DRC or manufacturing review.

```sh
/opt/homebrew/opt/openjdk@17/bin/javac -cp freerouting-1.9.0.jar:. \
  GroundFanout.java GroundFanoutCoverageTest.java
/usr/bin/sandbox-exec -f offline.sb /opt/homebrew/opt/openjdk@17/bin/java \
  -Xmx512m -Djava.awt.headless=true -cp freerouting-1.9.0.jar:. \
  GroundFanout INPUT.frb NEW_GROUND.ses ORIGINAL_INPUT.dsn 1000 90
```

The current DSN's through-via stack is 0.60 mm copper / 0.30 mm drill, F-to-B,
with via attachment to SMD pad centers disabled (`attach off`). The engine cannot
establish fabrication readiness: inspect any vias near exposed thermal pads,
connector pads and solderable areas after native import. Specify tenting and,
where applicable, filled/capped via-in-pad treatment with the manufacturer rather
than assuming ordinary unfilled vias are suitable for a thermal pad.

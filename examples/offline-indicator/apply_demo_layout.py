"""Apply this example's small hand-authored layout after `ato-local build`.

This is an explicit demo layout recipe, not a general placement/routing engine.
Run using the fork's Python runtime with src on PYTHONPATH.
"""

from pathlib import Path
from uuid import uuid4

from faebryk.libs.kicad.fileformats import kicad


def main():
    path = Path(__file__).parent / "layouts/default/default.kicad_pcb"
    pcb_file = kicad.loads(kicad.pcb.PcbFile, path)
    board = pcb_file.kicad_pcb
    by_name = {fp.name: fp for fp in board.footprints}
    locations = {
        "Local_Input2:Input2": (5.0, 9.0),
        "Local_Resistor330R:Resistor330R": (12.0, 9.0),
        "Local_LED5mm:LED5mm": (25.0, 9.0),
    }
    if set(by_name) != set(locations):
        raise RuntimeError("Build the original three-component example first")
    for name, (x, y) in locations.items():
        by_name[name].at = kicad.pcb.Xyr(x=x, y=y, r=0)

    def net(name, pin):
        pad = next(p for p in by_name[name].pads if p.name == pin)
        if not pad.net:
            raise RuntimeError("Demo pad has no net")
        return pad.net.number

    routes = [
        (net("Local_Input2:Input2", "1"), "F.Cu", [(5, 9), (5, 4), (12, 4), (12, 9)]),
        (
            net("Local_Resistor330R:Resistor330R", "2"),
            "F.Cu",
            [(19.62, 9), (19.62, 6), (27.54, 6), (27.54, 9)],
        ),
        (
            net("Local_Input2:Input2", "2"),
            "B.Cu",
            [(7.54, 9), (7.54, 14), (25, 14), (25, 9)],
        ),
    ]
    board.segments = [
        kicad.pcb.Segment(
            start=kicad.pcb.Xy(x=start[0], y=start[1]),
            end=kicad.pcb.Xy(x=end[0], y=end[1]),
            width=0.3,
            layer=layer,
            net=net_number,
            uuid=str(uuid4()),
        )
        for net_number, layer, points in routes
        for start, end in zip(points, points[1:])
    ]
    board.gr_rects = [rect for rect in board.gr_rects if rect.layer != "Edge.Cuts"] + [
        kicad.pcb.Rect(
            start=kicad.pcb.Xy(x=0, y=0),
            end=kicad.pcb.Xy(x=32, y=18),
            layer="Edge.Cuts",
            layers=[],
            stroke=kicad.pcb.Stroke(width=0.05, type="default"),
            fill="none",
            locked=None,
            solder_mask_margin=None,
            uuid=str(uuid4()),
        )
    ]
    kicad.dumps(pcb_file, path)
    print("Applied 32 x 18 mm demo outline, three placements, and nine track segments")


if __name__ == "__main__":
    main()

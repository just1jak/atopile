"""Local KiCad geometry and confinement regressions; no KiCad process/network."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from atopile.server.domains import schematic_symbols as symbols

DEMO = Path(__file__).parents[2] / "examples" / "offline-indicator"


def _library(root: Path, content: str, filename: str = "Fixture.kicad_sym") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / filename
    path.write_text(f"(kicad_symbol_lib (version 20241229) {content})")
    return path


@pytest.mark.parametrize(
    ("name", "expected_pins", "graphic_type"),
    [
        ("Input2", {"1": "Pin_1", "2": "Pin_2"}, "rect"),
        ("LED5mm", {"1": "K", "2": "A"}, "polyline"),
        ("Resistor330R", {"1": "", "2": ""}, "polyline"),
    ],
)
def test_genuine_demo_symbols_keep_native_graphics_and_pin_mapping(
    name, expected_pins, graphic_type
):
    path = Path("parts") / f"Local_{name}" / f"{name}.kicad_sym"
    result = symbols.load_schematic_symbol(DEMO, name, symbol_path=path)
    assert result["status"] == "loaded", result.get("warnings")
    assert result["missing"] is False
    assert {pin["number"]: pin["name"] for pin in result["pins"]} == expected_pins
    assert any(primitive["type"] == graphic_type for primitive in result["primitives"])
    assert all(pin["electricalType"] == "passive" for pin in result["pins"])
    assert result["bounds"]["width"] > 0
    # The normalized transport is data, never a prebuilt SVG or executable markup.
    assert "<svg" not in json.dumps(result)
    if name == "Resistor330R":
        assert sum(len(p.get("points", [])) for p in result["primitives"]) >= 15
        assert any(
            min(point["x"] for point in primitive["points"])
            < 0
            < max(point["x"] for point in primitive["points"])
            for primitive in result["primitives"]
            if primitive["type"] == "polyline"
        )
        top, bottom = result["pins"]
        assert top["y"] < 0 < bottom["y"]
        assert top["endY"] > top["y"]
        assert bottom["endY"] < bottom["y"]


def test_inheritance_units_common_graphics_and_rotated_pins(tmp_path):
    path = _library(
        tmp_path,
        """
        (symbol "Base" (pin_names (offset 0.5))
          (symbol "Base_0_1"
            (circle (center 1 2) (radius 1) (fill (type background))))
          (symbol "Base_1_1"
            (rectangle (start -1 1) (end 1 -1))
            (pin input line (at 0 5 270) (length 2)
              (name "IN") (number "1")))
          (symbol "Base_2_1"
            (pin output line (at 5 0 180) (length 2)
              (name "OUT") (number "2")))
          (symbol "Base_1_2" (circle (center 50 50) (radius 9))))
        (symbol "Derived" (extends "Base")
          (property "Value" "Derived" (at 0 0 0))
          (symbol "Derived_0_1"
            (text "Native text" (at 3 4 90)
              (effects (font (size 1 2)) (justify left)))))
        """,
    )
    first = symbols.load_schematic_symbol(tmp_path, "Fixture:Derived", symbol_path=path)
    assert first["status"] == "loaded"
    assert first["availableUnits"] == [1, 2]
    assert {pin["number"] for pin in first["pins"]} == {"1"}
    pin = first["pins"][0]
    assert (pin["x"], pin["y"], pin["endX"], pin["endY"], pin["rotation"]) == (
        0,
        -5,
        0,
        -3,
        90,
    )
    assert any(p["type"] == "circle" and p["cy"] == -2 for p in first["primitives"])
    assert not any(p.get("r") == 9 for p in first["primitives"])
    text = next(p for p in first["primitives"] if p.get("text") == "Native text")
    assert (text["x"], text["y"], text["angle"], text["size"], text["anchor"]) == (
        3,
        -4,
        270,
        2,
        "start",
    )
    assert not any(p.get("text") == "Derived" for p in first["primitives"])
    second = symbols.load_schematic_symbol(
        tmp_path, "Derived", symbol_path=path, unit=2
    )
    assert {pin["number"] for pin in second["pins"]} == {"2"}
    assert any(p["type"] == "circle" for p in second["primitives"])
    assert not any(p["type"] == "rect" for p in second["primitives"])
    absent = symbols.load_schematic_symbol(
        tmp_path, "Derived", symbol_path=path, unit=3
    )
    assert absent["status"] == "partial"
    assert "no unit 3" in absent["warning"]


@pytest.mark.parametrize(
    ("start", "mid", "end", "expected_mid_y", "major"),
    [
        ("1 0", "0 1", "-1 0", -1, False),
        ("1 0", "-1 0", "0 1", 0, True),
        ("1 0", "0 -1", "-1 0", 1, False),
    ],
)
def test_arc_sampling_preserves_midpoint_direction_and_major_sweep(
    tmp_path, start, mid, end, expected_mid_y, major
):
    path = _library(
        tmp_path,
        f"""(symbol "Arc" (symbol "Arc_1_1"
        (arc (start {start}) (mid {mid}) (end {end})
          (stroke (width 0.2)) (fill (type none)))))""",
    )
    result = symbols.load_schematic_symbol(tmp_path, "Arc", symbol_path=path)
    assert result["status"] == "loaded", result.get("warning")
    points = result["primitives"][0]["points"]
    assert all(math.hypot(p["x"], p["y"]) == pytest.approx(1) for p in points)
    assert points[0] == {"x": 1, "y": 0}
    assert any(p["y"] == expected_mid_y for p in points)
    if major:
        assert any(p["x"] < -0.9 for p in points)
        assert any(p["y"] > 0.9 for p in points)
        assert len(points) > 50
    else:
        assert len(points) >= 37
        assert (
            all(p["y"] <= 0 for p in points)
            if expected_mid_y < 0
            else all(p["y"] >= 0 for p in points)
        )


def test_cycle_missing_parent_and_missing_symbol_never_make_fake_geometry(tmp_path):
    path = _library(
        tmp_path,
        '(symbol "A" (extends "B")) (symbol "B" (extends "A"))'
        ' (symbol "Orphan" (extends "Gone"))',
    )
    for name, warning in [
        ("A", "Cyclic"),
        ("Orphan", "missing"),
        ("Absent", "No local"),
    ]:
        result = symbols.load_schematic_symbol(tmp_path, name, symbol_path=path)
        assert result["missing"] is True
        assert result["primitives"] == result["pins"] == []
        assert warning in result["warning"]


def test_unsupported_and_degenerate_graphics_warn_without_discarding_valid_geometry(
    tmp_path,
):
    path = _library(
        tmp_path,
        """(symbol "Partial" (symbol "Partial_1_1"
          (circle (center 0 0) (radius 2))
          (bezier (pts (xy 1 2) (xy 3 4)))
          (arc (start 0 0) (mid 1 0) (end 2 0))
          (circle (center nan 0) (radius 1))))""",
    )
    result = symbols.load_schematic_symbol(tmp_path, "Partial", symbol_path=path)
    assert result["status"] == "partial"
    assert len(result["primitives"]) == 1
    assert "bezier" in result["warning"]
    assert "Degenerate" in result["warning"]
    json.dumps(result, allow_nan=False)


def test_hidden_pins_keep_electrical_anchors_without_visible_labels(tmp_path):
    path = _library(
        tmp_path,
        """(symbol "Hidden" (pin_names (hide yes)) (pin_numbers hide)
        (symbol "Hidden_1_1"
          (pin passive line (at 0 0 0) (length 1) (name "NO_LABEL") (number "1"))
          (pin power_in line (at 0 2 90) (length 1) hide
            (name "VCC") (number "2"))))""",
    )
    result = symbols.load_schematic_symbol(tmp_path, "Hidden", symbol_path=path)
    assert len(result["pins"]) == 2
    assert result["pins"][1]["hidden"]
    assert [p["type"] for p in result["primitives"]] == ["line"]


def test_project_discovery_and_explicit_file_cannot_escape_root(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = _library(
        tmp_path / "outside",
        '(symbol "Secret" (symbol "Secret_1_1" (circle (center 0 0) (radius 1))))',
    )
    (project / "Leak.kicad_sym").symlink_to(outside)
    for candidate in [outside, "../outside/Fixture.kicad_sym", "Leak.kicad_sym"]:
        result = symbols.load_schematic_symbol(project, "Secret", symbol_path=candidate)
        assert result["missing"]
        assert "outside" in result["warning"]
        assert result["sourceFile"] is None
    assert symbols.load_schematic_symbol(project, "Secret")["missing"]
    for invalid in ["../Secret", "/etc/passwd", "x\\Secret"]:
        assert symbols.load_schematic_symbol(project, invalid)["missing"]
    # Explicit host-owned library roots are allowed; there is no network lookup.
    trusted = symbols.load_schematic_symbol(
        project, "Secret", library_roots=[outside.parent]
    )
    assert trusted["status"] == "loaded"


def test_source_size_depth_and_discovery_limits_are_enforced(tmp_path, monkeypatch):
    path = _library(tmp_path, '(symbol "Test")')
    monkeypatch.setattr(symbols, "MAX_SOURCE_BYTES", 16)
    assert (
        "size limit"
        in symbols.load_schematic_symbol(tmp_path, "Test", symbol_path=path)["warning"]
    )
    monkeypatch.setattr(symbols, "MAX_SOURCE_BYTES", 10000)
    monkeypatch.setattr(symbols, "MAX_SOURCE_DEPTH", 1)
    assert (
        "complexity limit"
        in symbols.load_schematic_symbol(tmp_path, "Test", symbol_path=path)["warning"]
    )
    monkeypatch.setattr(symbols, "MAX_SOURCE_DEPTH", 64)
    monkeypatch.setattr(symbols, "MAX_DIRECTORY_ENTRIES", 0)
    result = symbols.load_schematic_symbol(tmp_path, "Test")
    assert result["missing"]
    assert "search limit" in result["warning"]


def test_project_asset_library_precedes_extra_installed_library(tmp_path):
    local = tmp_path / "project"
    _library(
        local / "assets",
        '(symbol "Same" (symbol "Same_1_1" (circle (center 0 0) (radius 1))))',
    )
    _library(
        tmp_path / "installed",
        '(symbol "Same" (symbol "Same_1_1" (circle (center 0 0) (radius 9))))',
        filename="Device.kicad_sym",
    )
    result = symbols.load_schematic_symbol(
        local, "Device:Same", library_roots=[tmp_path / "installed"]
    )
    assert result["status"] == "loaded"
    assert result["primitives"][0]["r"] == 1
    assert result["sourceFile"].startswith("assets/")

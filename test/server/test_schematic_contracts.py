"""Producer, generated transport, and webview schematic contracts agree."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from atopile import generate_types
from atopile.server.domains.schematic import get_schematic_data, schematic_selection
from atopile.server.domains.schematic_models import (
    SchematicData,
    SchematicSelection,
    SchematicSymbol,
)

DEMO = Path(__file__).parents[2] / "examples" / "offline-indicator"


def test_real_demo_projection_and_selection_validate_as_canonical_models():
    original = get_schematic_data(DEMO)
    data = SchematicData.model_validate(original)
    payload = data.model_dump(by_alias=True)
    assert payload["connectivityKind"] == "logical_pad_net_assignments"
    assert len(payload["components"]) == len(payload["nets"]) == 3
    assert payload["warnings"] == []
    assert not any("_" in field for field in payload)
    led = next(c for c in payload["components"] if c["reference"] == "D1")
    assert led["symbol"]["sourceFile"].endswith("LED5mm.kicad_sym")
    assert {p["number"]: p["name"] for p in led["symbol"]["pins"]} == {
        "1": "K",
        "2": "A",
    }
    selection = SchematicSelection.model_validate(
        schematic_selection(payload, net_name="lv")
    ).model_dump(by_alias=True)
    assert len(selection["padIds"]) == 2
    assert selection["sequence"] == 0


def test_symbol_metadata_round_trips_and_invalid_graphics_are_rejected():
    original = get_schematic_data(DEMO)["components"][0]["symbol"]
    original["localLibraryRevision"] = "fixture"
    original["primitives"][0]["localGraphicHint"] = "fixture"
    normalized = SchematicSymbol.model_validate(original).model_dump(by_alias=True)
    assert normalized["localLibraryRevision"] == "fixture"
    assert normalized["primitives"][0]["localGraphicHint"] == "fixture"
    for replacement in [
        {"type": "script", "text": "unsupported"},
        {"type": "circle", "cx": float("nan"), "cy": 0, "r": 1},
        {"type": "rect", "x": 0, "y": 0, "width": -1, "height": 1},
    ]:
        hostile = copy.deepcopy(original)
        hostile["primitives"] = [replacement]
        with pytest.raises(ValidationError):
            SchematicSymbol.model_validate(hostile)


def test_generator_discovers_schematic_models_without_changing_legacy_module_api(
    tmp_path, monkeypatch
):
    assert len(generate_types._schema_modules()) == 4
    models = {model.__name__ for model in generate_types.discover_camel_models()}
    assert {
        "SchematicData", "SchematicSymbol", "SchematicSelection",
        "SchematicExportResult",
    } <= models
    output = tmp_path / "generated-types.ts"
    monkeypatch.setattr(generate_types, "OUT", output)
    generate_types.main()
    first = output.read_text()
    generate_types.main()
    assert output.read_text() == first
    assert "export interface SchematicData" in first
    assert "export interface SchematicExportResult" in first
    assert "reused: boolean;" in first
    assert "openError: string | null;" in first
    assert 'connectivityKind: "logical_pad_net_assignments"' in first
    assert "strokeWidth?: number;" in first
    assert "endX: number;" in first
    assert "sequence?: number;" in first
    assert "SchematicLine | SchematicPolyline | SchematicRectangle" in first
    assert "export interface UiAgentData" in first


def test_webview_consumes_generated_schematic_contracts_without_wire_duplicates():
    source_root = Path(__file__).parents[2]
    frontend = (source_root / "src/ui/webview/panel-schematic/types.ts").read_text()
    assert 'from "../../protocol/generated-types"' in frontend
    for name in (
        "SchematicData",
        "SchematicComponent",
        "SchematicNet",
        "SchematicSelection",
    ):
        assert name in frontend
        assert not re.search(rf"\binterface\s+{name}\b", frontend)
    assert 'SchematicSymbol["primitives"][number]' in frontend

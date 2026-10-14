# SPDX-License-Identifier: MIT
"""Offline import contracts: pin identity, local selection, and asset preservation."""

from pathlib import Path

import pytest

from faebryk.libs.ato_part import AtoPart
from faebryk.libs.kicad_part_import import (
    KicadPartImportError,
    import_part_from_kicad,
    import_part_from_pinout,
    load_library_symbol,
    synthesize_symbol_lib_text,
)

ASSETS = Path(__file__).resolve().parents[2] / "examples/offline-indicator/assets"


@pytest.mark.usefixtures("setup_project_config")
def test_local_import_preserves_pins_assets_and_selection(monkeypatch):
    import faebryk.libs.picker.api.api as api

    def no_catalog():
        pytest.fail("A local import attempted to contact the component catalog")

    monkeypatch.setattr(api, "get_api_client", no_catalog)
    part = import_part_from_kicad(
        symbol_lib_path=ASSETS / "LED5mm.kicad_sym",
        footprint_path=ASSETS / "LED5mm.kicad_mod",
        manufacturer="Local",
        partnumber="LED5mm",
    )
    loaded = AtoPart.load(part.path)
    assert loaded.pick_part.supplier.supplier_id == "local"
    assert loaded.pick_part.supplier_partno == "MANUAL-LED5mm"
    assert [pad.name for pad in loaded.fp.footprint.pads] == ["1", "2"]
    source = (part.path / "Local_LED5mm.ato").read_text()
    assert "signal A ~ pin 2" in source
    assert "signal K ~ pin 1" in source


@pytest.mark.usefixtures("setup_project_config")
def test_pinout_requires_matching_footprint_pads():
    with pytest.raises(KicadPartImportError, match="no matching footprint pads: 3"):
        import_part_from_pinout(
            footprint_path=ASSETS / "Input2.kicad_mod",
            pins=[("1", "POS"), ("3", "NEG")],
            manufacturer="Local",
            partnumber="BadInput",
        )


def test_pinout_rejects_duplicate_numbers():
    with pytest.raises(KicadPartImportError, match="unique"):
        synthesize_symbol_lib_text("Bad", [("1", "A"), ("1", "K")])


def test_generated_symbol_escapes_names(tmp_path):
    path = tmp_path / "quoted.kicad_sym"
    path.write_text(synthesize_symbol_lib_text('Part "A"', [("1", 'Pin "one"')]))
    loaded = load_library_symbol(path, 'Part "A"')
    assert loaded.pins == [('Pin "one"', "1")]


@pytest.mark.usefixtures("setup_project_config")
def test_existing_part_requires_explicit_overwrite():
    kwargs = dict(
        footprint_path=ASSETS / "Input2.kicad_mod",
        pins=[("1", "POS"), ("2", "NEG")],
        manufacturer="Local",
        partnumber="Input2",
    )
    part = import_part_from_pinout(**kwargs)
    source = part.path / "Local_Input2.ato"
    before = source.read_bytes()
    with pytest.raises(KicadPartImportError, match="already exists"):
        import_part_from_pinout(**kwargs)
    assert source.read_bytes() == before


def test_circle_only_silkscreen_bbox():
    from faebryk.exporters.pcb.kicad.transformer import PCB_Transformer
    from faebryk.libs.kicad.fileformats import kicad

    fp = kicad.footprint.loads((ASSETS / "LED5mm.kicad_mod").read_text()).footprint
    board_fp = kicad.pcb.Footprint(
        at=kicad.pcb.Xyr(x=0, y=0, r=0),
        **PCB_Transformer._fp_common_fields_dict(object.__new__(PCB_Transformer), fp),
    )
    assert PCB_Transformer.get_footprint_silkscreen_bbox(board_fp) == (
        (-1.23, -2.5),
        (3.77, 2.5),
    )

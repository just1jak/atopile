"""Lossless scoped KiCad 10 edits alongside the pinned editable formats."""

from __future__ import annotations

import copy
import subprocess
import uuid
from pathlib import Path

import pytest
import sexpdata

from faebryk.libs.kicad import fileformats
from faebryk.libs.kicad.fileformats import kicad


def _board(version=20260206, *, tenting="(front yes) (back no)"):
    modern = version == 20260206
    pad_net = '(net "signal")' if modern else '(net 1 "signal")'
    route_net = '(net "signal")' if modern else "(net 1)"
    zone_net = route_net if modern else '(net 1) (net_name "signal")'
    empty_net = "" if modern else '(net 0) (net_name "")'
    table = "" if modern else '(net 0 "") (net 1 "signal")'
    modern_settings = (
        "(covering (front no) (back yes)) (plugging (front yes) (back no)) "
        "(capping yes) (filling no)"
        if modern
        else ""
    )
    return f"""(kicad_pcb (version {version}) (generator test) (generator_version "10.0")
        (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
        (setup (pad_to_mask_clearance 0.05) (tenting {tenting}) {modern_settings})
        {table}
        (footprint "fixture:R" (layer "F.Cu") (at 10 20)
            (uuid "d4e6a2d9-84db-4d95-b002-35174642524b")
            (property "Reference" "R1" (at 0 0) (layer "F.SilkS"))
            (property "Description" "literal (tenting (front yes))" (at 0 1) (layer "F.Fab"))
            (duplicate_pad_numbers_are_jumpers no)
            (pad "1" thru_hole circle (at 0 0) (size 1.7 1.7)
                (drill 1) (layers "*.Cu" "*.Mask") {pad_net}))
        (segment (start 10 20) (end 20 20) (width 0.25) (layer "F.Cu") {route_net})
        (arc (start 20 20) (mid 21 21) (end 22 20) (width 0.25) (layer "F.Cu") {route_net})
        (via (at 20 20) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") {route_net})
        (zone {zone_net} (layer "F.Cu") (hatch edge 0.5)
            (polygon (pts (xy 0 0) (xy 30 0) (xy 30 30))))
        (zone {empty_net} (layers "F.Cu" "B.Cu") (hatch edge 0.5)
            (keepout (tracks not_allowed) (vias not_allowed) (pads not_allowed)
                (copperpour not_allowed) (footprints allowed))
            (polygon (pts (xy 0 0) (xy 2 0) (xy 2 2))))
        (future_preserved_field "opaque data"))"""


def _assert_connectivity(pcb):
    model = pcb.kicad_pcb
    signal = next(net.number for net in model.nets if net.name == "signal")
    assert signal > 0
    assert model.footprints[0].pads[0].net.number == signal
    assert model.footprints[0].pads[0].net.name == "signal"
    assert model.segments[0].net == signal
    assert model.arcs[0].net == signal
    assert model.vias[0].net == signal
    assert model.zones[0].net == signal and model.zones[0].net_name == "signal"
    assert model.zones[1].net == 0 and model.zones[1].net_name == ""


@pytest.mark.parametrize(
    ("tenting", "expected"),
    [
        ("(front yes) (back no)", ["front"]),
        ("(front no) (back yes)", ["back"]),
        ("(front yes) (back yes)", ["front", "back"]),
        ("(front no) (back no)", []),
        ("front back", ["front", "back"]),
    ],
)
def test_kicad10_side_settings_and_complete_source_round_trip(tenting, expected):
    source = _board(tenting=tenting)
    pcb = kicad.loads(kicad.pcb.PcbFile, source)
    assert isinstance(pcb, kicad.pcb.PcbFile)
    assert list(pcb.kicad_pcb.setup.tenting) == expected
    _assert_connectivity(pcb)
    assert kicad.dumps(pcb) == source
    assert sexpdata.loads(kicad.dumps(pcb)) == sexpdata.loads(source)
    reloaded = kicad.loads(kicad.pcb.PcbFile, kicad.dumps(pcb))
    _assert_connectivity(reloaded)
    assert kicad.dumps(reloaded) == source
    assert kicad.type_to_module(pcb) is kicad.pcb


def test_older_tenting_and_numeric_nets_keep_editable_native_behavior():
    pcb = kicad.loads(kicad.pcb.PcbFile, _board(20241229, tenting="front back"))
    _assert_connectivity(pcb)
    assert list(pcb.kicad_pcb.setup.tenting) == ["front", "back"]
    pcb.kicad_pcb.footprints[0].at.x = 15.24
    pcb.kicad_pcb.setup.tenting = ["back"]
    reloaded = kicad.loads(kicad.pcb.PcbFile, kicad.dumps(pcb))
    assert reloaded.kicad_pcb.footprints[0].at.x == 15.24
    assert list(reloaded.kicad_pcb.setup.tenting) == ["back"]
    _assert_connectivity(reloaded)


def test_modified_kicad10_dump_fails_before_creating_destination(tmp_path):
    pcb = kicad.loads(kicad.pcb.PcbFile, _board())
    pcb.kicad_pcb.setup.pad_to_mask_clearance = 0.2
    destination = tmp_path / "uncreated" / "board.kicad_pcb"
    with pytest.raises(ValueError, match="placement and copper routes only"):
        kicad.dumps(pcb, destination)
    assert not destination.parent.exists()


def test_kicad10_copy_keeps_full_source_and_unsupported_edit_guard():
    source = _board()
    original = kicad.loads(kicad.pcb.PcbFile, source)
    copied = kicad.copy(original)
    assert kicad.dumps(copied) == source
    copied.kicad_pcb.setup.tenting = ["back"]
    with pytest.raises(ValueError, match="placement and copper routes only"):
        kicad.dumps(copied)
    assert kicad.dumps(original) == source


def test_failed_edit_does_not_poison_subsequent_path_reads(tmp_path):
    source = _board()
    path = tmp_path / "board.kicad_pcb"
    path.write_text(source)
    first = kicad.loads(kicad.pcb.PcbFile, path)
    first.kicad_pcb.setup.pad_to_mask_clearance = 0.2
    with pytest.raises(ValueError, match="placement and copper routes only"):
        kicad.dumps(first, path)
    second = kicad.loads(kicad.pcb.PcbFile, path)
    assert second is not first
    assert second.kicad_pcb.footprints[0].at.y == 20
    _assert_connectivity(second)
    assert path.read_text() == source
    assert kicad.dumps(second) == source


def test_kicad10_path_round_trip_preserves_crlf_bytes(tmp_path):
    source = _board().replace("\n", "\r\n").encode("utf-8")
    path = tmp_path / "original.kicad_pcb"
    path.write_bytes(source)
    pcb = kicad.loads(kicad.pcb.PcbFile, path)
    assert kicad.dumps(pcb).encode("utf-8") == source
    destination = tmp_path / "copy.kicad_pcb"
    kicad.dumps(pcb, destination)
    assert destination.read_bytes() == source
    assert path.read_bytes() == source


@pytest.mark.parametrize(
    ("original", "malformed"),
    [
        ("(front yes) (back no)", "(front yes) (front no)"),
        ("(front yes) (back no)", "(front maybe) (back no)"),
        ("(front yes) (back no)", "front (back no)"),
        ("(capping yes)", "(capping perhaps)"),
        ('(net "signal")', "(net 7)"),
        ('(net "signal")', '(net 7 "signal")'),
        ("(setup ", "(setup (tenting front) "),
    ],
)
def test_ambiguous_or_malformed_new_syntax_is_rejected(original, malformed):
    with pytest.raises(ValueError, match="KiCad 10"):
        kicad.loads(kicad.pcb.PcbFile, _board().replace(original, malformed))


def test_unknown_future_pcb_version_is_not_reinterpreted_as_supported_kicad10():
    with pytest.raises(ValueError):
        kicad.loads(kicad.pcb.PcbFile, _board().replace("20260206", "20270201"))


def test_schematic_still_uses_its_native_parser():
    source = '(kicad_sch (version 20250114) (generator eeschema) (generator_version "9.0") (uuid "329f2b00-d760-4cc2-b513-97f4be47eb43") (paper "A4"))'
    schematic = kicad.loads(kicad.schematic.SchematicFile, source)
    assert schematic.kicad_sch.generator == "eeschema"
    assert "eeschema" in kicad.dumps(schematic)


def _editable_board(*, unknown_pad=True):
    source = _board()
    for number, kind in enumerate(("segment", "arc", "via"), 1):
        source = source.replace(
            "(" + kind + " ",
            f'({kind} (uuid "{uuid.UUID(int=number)}") ',
            1,
        )
    if unknown_pad:
        source = source.replace(
            '(pad "1" thru_hole circle ',
            '(pad "1" thru_hole circle (future_pad (mode "preserve µΩ")) ',
        )
    return source.replace(
        "(via (uuid ", '(via (future_via (opaque "unchanged")) (uuid '
    )


def _signal(pcb):
    return next(net.number for net in pcb.kicad_pcb.nets if net.name == "signal")


def _segment(pcb, *, identifier=None, net=None):
    return kicad.pcb.Segment(
        start=kicad.pcb.Xy(x=20, y=20),
        end=kicad.pcb.Xy(x=25, y=20),
        width=0.3,
        layer="B.Cu",
        net=_signal(pcb) if net is None else net,
        uuid=identifier or str(uuid.uuid4()),
    )


def test_placement_patches_only_its_source_span_with_unicode_crlf_and_comments():
    source = _editable_board().replace("\n", "\r\n")
    source = source.replace(
        "(footprint ", '; untouched µΩ \\"quote\\" \\\\path\r\n        (footprint ', 1
    )
    pcb = kicad.loads(kicad.pcb.PcbFile, source)
    assert pcb.preserves_unknown_fields is True
    pcb.kicad_pcb.footprints[0].at.x = 15.24
    output = kicad.dumps(pcb)
    prefix, suffix = source.split("(at 10 20)", 1)
    assert output.startswith(prefix) and output.endswith(suffix)
    reloaded = kicad.loads(kicad.pcb.PcbFile, output)
    assert reloaded.kicad_pcb.footprints[0].at.x == 15.24
    assert '(future_pad (mode "preserve µΩ"))' in output
    assert '(future_via (opaque "unchanged"))' in output
    _assert_connectivity(reloaded)


def test_existing_transformer_rotation_preserves_unknown_pad_metadata():
    from faebryk.exporters.pcb.kicad.transformer import PCB_Transformer

    pcb = kicad.loads(kicad.pcb.PcbFile, _editable_board())
    PCB_Transformer.move_fp(
        pcb.kicad_pcb.footprints[0], kicad.pcb.Xyr(x=15.24, y=22.86, r=90), "F.Cu"
    )
    output = kicad.dumps(pcb)
    reloaded = kicad.loads(kicad.pcb.PcbFile, output)
    fp = reloaded.kicad_pcb.footprints[0]
    assert (fp.at.x, fp.at.y, fp.at.r) == (15.24, 22.86, 90)
    assert fp.pads[0].at.r == 90
    assert '(future_pad (mode "preserve µΩ"))' in output
    _assert_connectivity(reloaded)


def test_copper_add_update_delete_uses_native_names_and_preserves_other_fields():
    source = _editable_board()
    pcb = kicad.loads(kicad.pcb.PcbFile, source)
    pcb.kicad_pcb.segments.pop(0)
    added = _segment(pcb)
    pcb.kicad_pcb.segments.append(added)
    pcb.kicad_pcb.arcs[0].width = 0.4
    pcb.kicad_pcb.vias[0].at.x = 22
    output = kicad.dumps(pcb)
    reloaded = kicad.loads(kicad.pcb.PcbFile, output)
    assert reloaded.kicad_pcb.segments[0].uuid == added.uuid
    assert reloaded.kicad_pcb.arcs[0].width == 0.4
    assert reloaded.kicad_pcb.vias[0].at.x == 22
    assert '(future_via (opaque "unchanged"))' in output
    assert "(covering (front no) (back yes))" in output
    assert '(future_pad (mode "preserve µΩ"))' in output
    for node in sexpdata.loads(output):
        if isinstance(node, list) and str(node[0]) in {"segment", "arc", "via"}:
            net = next(
                child
                for child in node
                if isinstance(child, list) and str(child[0]) == "net"
            )
            assert net == [sexpdata.Symbol("net"), "signal"]
    _assert_connectivity(reloaded)


def test_new_via_and_removing_existing_copper_round_trip():
    pcb = kicad.loads(kicad.pcb.PcbFile, _editable_board())
    pcb.kicad_pcb.arcs.pop(0)
    pcb.kicad_pcb.vias.pop(0)
    via = kicad.pcb.Via(
        at=kicad.pcb.Xy(x=25, y=20),
        size=0.8,
        drill=0.4,
        layers=["F.Cu", "B.Cu"],
        net=_signal(pcb),
        uuid=str(uuid.uuid4()),
    )
    pcb.kicad_pcb.vias.append(via)
    reloaded = kicad.loads(kicad.pcb.PcbFile, kicad.dumps(pcb))
    assert not reloaded.kicad_pcb.arcs
    assert len(reloaded.kicad_pcb.vias) == 1
    assert reloaded.kicad_pcb.vias[0].uuid == via.uuid
    assert reloaded.kicad_pcb.vias[0].net == _signal(reloaded)


def test_atomic_path_saves_preserve_mode_and_support_repeated_edits(tmp_path):
    path = tmp_path / "board.kicad_pcb"
    path.write_text(_editable_board())
    path.chmod(0o640)
    pcb = kicad.loads(kicad.pcb.PcbFile, path)
    for x in (15.24, 25.4):
        pcb.kicad_pcb.footprints[0].at.x = x
        kicad.dumps(pcb, path)
        assert kicad.loads(kicad.pcb.PcbFile, path).kicad_pcb.footprints[0].at.x == x
        assert path.stat().st_mode & 0o777 == 0o640


def test_consecutive_add_modify_delete_copper_saves_from_same_loaded_object(tmp_path):
    source = _editable_board()
    path = tmp_path / "board.kicad_pcb"
    path.write_text(source)
    pcb = kicad.loads(kicad.pcb.PcbFile, path)
    pcb.kicad_pcb.segments.append(_segment(pcb))
    via = kicad.copy(pcb.kicad_pcb.vias[0])
    via.uuid = str(uuid.uuid4())
    via.at.x = 25
    pcb.kicad_pcb.vias.append(via)
    kicad.dumps(pcb, path)
    pcb.kicad_pcb.segments[-1].end.x = 30
    pcb.kicad_pcb.vias[-1].drill = 0.5
    kicad.dumps(pcb, path)
    reloaded = kicad.loads(kicad.pcb.PcbFile, path)
    assert reloaded.kicad_pcb.segments[-1].end.x == 30
    assert reloaded.kicad_pcb.vias[-1].drill == 0.5
    pcb.kicad_pcb.segments.pop(-1)
    pcb.kicad_pcb.vias.pop(-1)
    kicad.dumps(pcb, path)
    assert path.read_text() == source


def test_external_change_and_atomic_replace_failure_preserve_existing_file(
    tmp_path, monkeypatch
):
    path = tmp_path / "board.kicad_pcb"
    source = _editable_board()
    path.write_text(source)
    pcb = kicad.loads(kicad.pcb.PcbFile, path)
    pcb.kicad_pcb.footprints[0].at.x = 25.4
    external = source + "\n; native editor saved\n"
    path.write_text(external)
    with pytest.raises(RuntimeError, match="changed on disk"):
        kicad.dumps(pcb, path)
    assert path.read_text() == external
    path.write_text(source)

    def fail_replace(*_args):
        raise OSError("simulated atomic failure")

    monkeypatch.setattr(fileformats.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated atomic failure"):
        kicad.dumps(pcb, path)
    assert path.read_text() == source
    assert list(tmp_path.iterdir()) == [path]


def test_existing_locked_object_cannot_move_but_unrelated_lock_is_preserved():
    source = _editable_board()
    document = sexpdata.loads(source)
    footprint = next(
        node
        for node in document
        if isinstance(node, list) and str(node[0]) == "footprint"
    )
    background = copy.deepcopy(footprint)
    for node in background:
        if isinstance(node, list) and str(node[0]) == "uuid":
            node[1] = str(uuid.uuid4())
        if (
            isinstance(node, list)
            and str(node[0]) == "property"
            and node[1] == "Reference"
        ):
            node[2] = "R2"
    background.append(sexpdata.Symbol("locked"))
    document.append(background)
    source = sexpdata.dumps(document)
    pcb = kicad.loads(kicad.pcb.PcbFile, source)
    pcb.kicad_pcb.footprints[0].at.x = 15
    output = kicad.dumps(pcb)
    assert sexpdata.dumps(background) in output
    pcb.kicad_pcb.footprints[1].at.x = 30
    with pytest.raises(ValueError, match="locked"):
        kicad.dumps(pcb)


def test_flip_rejects_unknown_side_sensitive_pad_metadata():
    pcb = kicad.loads(kicad.pcb.PcbFile, _editable_board())
    pcb.kicad_pcb.footprints[0].layer = "B.Cu"
    with pytest.raises(ValueError, match="flip cannot preserve unsupported future_pad"):
        kicad.dumps(pcb)


def _flip_fixture(*, text_angle=0):
    source = _editable_board(unknown_pad=False)
    document = sexpdata.loads(source)
    footprint = next(
        node
        for node in document
        if isinstance(node, list) and str(node[0]) == "footprint"
    )
    for node in footprint:
        if not isinstance(node, list):
            continue
        if str(node[0]) == "property":
            node.append(sexpdata.loads("(effects (font (size 1 1)))"))
            if node[1] == "Reference":
                next(
                    child
                    for child in node
                    if isinstance(child, list) and str(child[0]) == "at"
                ).append(text_angle)
        if str(node[0]) == "pad":
            node.append(sexpdata.loads("(thermal_bridge_angle 17)"))
    return sexpdata.dumps(document)


def test_supported_flip_matches_native_cardinal_convention_and_preserves_thermal_angle():
    from faebryk.exporters.pcb.kicad.transformer import PCB_Transformer

    pcb = kicad.loads(kicad.pcb.PcbFile, _flip_fixture())
    PCB_Transformer._flip_obj(pcb.kicad_pcb.footprints[0])
    output = kicad.dumps(pcb)
    reloaded = kicad.loads(kicad.pcb.PcbFile, output)
    fp = reloaded.kicad_pcb.footprints[0]
    assert fp.layer == "B.Cu" and fp.at.r == 180
    assert fp.pads[0].at.r == 180
    assert "(thermal_bridge_angle 17)" in output
    assert str(fp.propertys[0].effects.justify.justify1) == "mirror"


def test_noncardinal_transformer_flip_is_rejected_when_text_differs_from_native():
    from faebryk.exporters.pcb.kicad.transformer import PCB_Transformer

    pcb = kicad.loads(kicad.pcb.PcbFile, _flip_fixture(text_angle=65))
    PCB_Transformer._flip_obj(pcb.kicad_pcb.footprints[0])
    with pytest.raises(ValueError, match="unsupported pad or text angle"):
        kicad.dumps(pcb)


@pytest.mark.parametrize("marker", ["locked", "notouch", "locked_copper"])
def test_all_edit_paths_enforce_raw_lock_and_notouch_markers(marker):
    source = _editable_board()
    if marker == "locked":
        source = source.replace(
            '(footprint "fixture:R" ', '(footprint "fixture:R" locked ', 1
        )
    elif marker == "notouch":
        source = source.replace(
            '(pad "1"',
            '(fp_text user "FBRK:notouch" (at 0 0) (layer "F.Fab") (effects (font (size 1 1)))) (pad "1"',
            1,
        )
    else:
        source = source.replace("(segment ", "(segment locked ", 1)
    pcb = kicad.loads(kicad.pcb.PcbFile, source)
    if marker == "locked_copper":
        pcb.kicad_pcb.segments.pop(0)
    else:
        pcb.kicad_pcb.footprints[0].at.x = 15
    with pytest.raises(ValueError, match="locked|notouch"):
        kicad.dumps(pcb)


@pytest.mark.parametrize("identifier", ["via_collision", "invalid"])
def test_added_copper_uuid_cannot_collide_across_types_or_be_malformed(identifier):
    pcb = kicad.loads(kicad.pcb.PcbFile, _editable_board())
    value = (
        pcb.kicad_pcb.vias[0].uuid if identifier == "via_collision" else "not-a-uuid"
    )
    pcb.kicad_pcb.segments.append(_segment(pcb, identifier=value))
    with pytest.raises(ValueError, match="UUID"):
        kicad.dumps(pcb)


@pytest.mark.parametrize(
    "kind",
    [
        "zone",
        "pad_net",
        "new_footprint",
        "unknown_route_net",
        "duplicate_uuid",
        "pad_position",
    ],
)
def test_unsupported_or_ambiguous_edits_fail_closed(kind):
    pcb = kicad.loads(kicad.pcb.PcbFile, _editable_board())
    if kind == "zone":
        pcb.kicad_pcb.zones[0].polygon.pts.xys[0].x = 10
    elif kind == "pad_net":
        pcb.kicad_pcb.footprints[0].pads[0].net.number = 0
    elif kind == "new_footprint":
        footprint = kicad.copy(pcb.kicad_pcb.footprints[0])
        footprint.uuid = str(uuid.uuid4())
        pcb.kicad_pcb.footprints.append(footprint)
    elif kind == "pad_position":
        pcb.kicad_pcb.footprints[0].pads[0].at.x = 2
    else:
        identifier = (
            pcb.kicad_pcb.segments[0].uuid if kind == "duplicate_uuid" else None
        )
        pcb.kicad_pcb.segments.append(
            _segment(
                pcb,
                identifier=identifier,
                net=999 if kind == "unknown_route_net" else None,
            )
        )
    with pytest.raises(ValueError):
        kicad.dumps(pcb)


def test_native_kicad_accepts_edited_copper_and_placement(tmp_path):
    native = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    if not native.is_file():
        pytest.skip("Native KiCad is not installed")
    from atopile.server.domains.kicad import _clean_env_for_kicad

    source = _editable_board(unknown_pad=False)
    source = source.replace('(future_via (opaque "unchanged"))', "")
    source = source.replace('(future_preserved_field "opaque data")', "")
    pcb = kicad.loads(kicad.pcb.PcbFile, source)
    pcb.kicad_pcb.footprints[0].at.x = 15.24
    pcb.kicad_pcb.segments.append(_segment(pcb))
    destination = tmp_path / "edited.kicad_pcb"
    kicad.dumps(pcb, destination)
    output = tmp_path / "edited.d356"
    result = subprocess.run(
        [
            str(native),
            "pcb",
            "export",
            "ipcd356",
            "--output",
            str(output),
            str(destination),
        ],
        cwd=tmp_path,
        env=_clean_env_for_kicad(),
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, (result.stderr or result.stdout)[-500:]
    assert output.is_file()

"""Validate schematic topology against real pad nets, including hostile metadata."""

import asyncio
import json
import shutil
from types import SimpleNamespace

import pytest

from atopile.server.domains import schematic
from atopile.server.ui.websocket import CoreSocket
from faebryk.libs.kicad.fileformats import kicad


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    shutil.copytree("examples/offline-indicator", root)
    return root


def test_real_pad_nets_symbols_source_and_selection(project):
    data = schematic.get_schematic_data(project)
    assert len(data["components"]) == 3
    assert len(data["nets"]) == 3
    refs = {c["reference"]: c for c in data["components"]}
    assert set(refs) == {"D1", "R1", "J1"}
    assert refs["D1"]["source"] == {"path": str(project / "main.ato"), "line": 14}
    for component in data["components"]:
        assert component["symbol"]["missing"] is False
        assert component["symbol"]["primitives"]
        assert {p["number"] for p in component["pins"]} <= {
            str(p["number"]) for p in component["symbol"]["pins"]
        }
    net = next(n for n in data["nets"] if n["name"] == "lv")
    assert {(m["reference"], m["pin"]) for m in net["members"]} == {
        ("D1", "1"),
        ("J1", "2"),
    }
    selection = schematic.schematic_selection(data, net_name="lv")
    assert len(selection["padIds"]) == 2
    assert set(selection["componentIds"]) == {refs["D1"]["id"], refs["J1"]["id"]}
    assert schematic.component_source(data, refs["D1"]["id"])["line"] == 14
    with pytest.raises(ValueError, match="Unknown"):
        schematic.schematic_selection(data, net_name="invented-net")


def test_fresh_pcb_wins_over_stale_pinout_and_revision_changes(project):
    before = schematic.get_schematic_data(project)
    pcb_path = project / "layouts/default/default.kicad_pcb"
    pcb = kicad.loads(kicad.pcb.PcbFile, pcb_path.read_text())
    led = next(
        fp
        for fp in pcb.kicad_pcb.footprints
        if schematic._property(fp, "Reference") == "D1"
    )
    led.pads[0].net.name = "changed-net"
    kicad.dumps(pcb, pcb_path)
    after = schematic.get_schematic_data(project)
    assert after["revision"] != before["revision"]
    assert any(n["name"] == "changed-net" for n in after["nets"])
    assert any("stale pinout net ignored" in warning for warning in after["warnings"])


def test_missing_symbol_is_explicit_pin_box_without_invented_nets(project):
    for path in project.glob("parts/**/*.kicad_sym"):
        path.unlink()
    data = schematic.get_schematic_data(project)
    assert all(c["symbol"]["missing"] for c in data["components"])
    assert all(len(c["pins"]) == 2 for c in data["components"])
    assert len(data["nets"]) == 3
    assert any("pin box" in warning for warning in data["warnings"])


def test_unassigned_pad_stays_unconnected_despite_pinout_metadata(project):
    pcb_path = project / "layouts/default/default.kicad_pcb"
    pcb = kicad.loads(kicad.pcb.PcbFile, pcb_path.read_text())
    led = next(
        fp
        for fp in pcb.kicad_pcb.footprints
        if schematic._property(fp, "Reference") == "D1"
    )
    led.pads[0].net = None
    kicad.dumps(pcb, pcb_path)
    data = schematic.get_schematic_data(project)
    component = next(c for c in data["components"] if c["reference"] == "D1")
    assert next(p for p in component["pins"] if p["number"] == "1")["net"] is None
    ground = next(n for n in data["nets"] if n["name"] == "lv")
    assert [(m["reference"], m["pin"]) for m in ground["members"]] == [("J1", "2")]


def test_artifact_and_source_symlinks_cannot_escape_project(project, tmp_path):
    data = schematic.get_schematic_data(project)
    led = next(c for c in data["components"] if c["reference"] == "D1")
    source = project / "main.ato"
    external = tmp_path / "external.ato"
    external.write_text(source.read_text())
    source.unlink()
    source.symlink_to(external)
    with pytest.raises(ValueError, match="escapes"):
        schematic.component_source(data, led["id"])
    fresh = schematic.get_schematic_data(project)
    assert all(c["source"] is None for c in fresh["components"])
    pinout = project / "build/builds/default/pinout/001_led.json"
    external_json = tmp_path / "external.json"
    external_json.write_text("{}")
    pinout.unlink()
    pinout.symlink_to(external_json)
    with pytest.raises(ValueError, match="escapes"):
        schematic.get_schematic_data(project)


def test_metadata_cannot_invent_electrical_connection(project):
    path = project / "build/builds/default/pinout/001_led.json"
    pinout = json.loads(path.read_text())
    pinout["leads"].append(
        {"leadDesignator": "FAKE", "padNumbers": ["999"], "netName": "fabricated"}
    )
    pinout["typeName"] = "../../external.ato::Fake.x"
    path.write_text(json.dumps(pinout))
    data = schematic.get_schematic_data(project)
    led = next(c for c in data["components"] if c["reference"] == "D1")
    assert led["source"] is None
    assert "999" not in {p["number"] for p in led["pins"]}
    assert "fabricated" not in {n["name"] for n in data["nets"]}


def test_source_jump_prefers_physical_part_over_enclosing_module(project):
    nested = project / "nested.ato"
    nested.write_text("module Block:\n    led = new Local_LED5mm_package\n")
    address = (
        "main.ato::OfflineIndicator.supply|nested.ato::Block.led|"
        "parts/Local_LED5mm/Local_LED5mm.ato::Local_LED5mm_package"
    )
    assert schematic._source_reference(project, project, address) == {
        "path": str(nested),
        "line": 2,
    }


def test_rpc_projection_and_saved_selection(project):
    """Exercise the actual dispatcher without starting auth, servers or builds."""
    core = CoreSocket.__new__(CoreSocket)
    core._schematic_selection = None
    core._subscriptions = {}
    core._store = SimpleNamespace(get=lambda name: [SimpleNamespace(root=str(project))])
    core._selected_project_context = lambda: (str(project), None)
    core._vscode_bridge = SimpleNamespace(handles=lambda action: False)
    core._layout_session = lambda *args: None
    core._diff_session = lambda *args: None
    sent = []

    async def send(*args, **kwargs):
        sent.append(kwargs)

    core._send_action_result = send
    forwarded = []

    async def forward(ws, payload):
        forwarded.append(payload)

    core._send_message = forward
    core._vscode_bridge.forward_request = lambda ws, session, payload: {
        "type": "extension_request",
        **payload,
    }

    async def run():
        await core._dispatch(
            None,
            {"action": "getSchematicData", "requestId": "data", "target": "default"},
        )
        data = sent[-1]["result"]
        assert sent[-1]["ok"] is True
        await core._dispatch(
            None,
            {"action": "schematicSelectNet", "requestId": "select", "netName": "lv"},
        )
        assert sent[-1]["result"]["netName"] == "lv"
        assert sent[-1]["result"]["sequence"] == 1
        await core._dispatch(
            None, {"action": "getSchematicSelection", "requestId": "latest"}
        )
        assert sent[-1]["result"] == core._schematic_selection
        await core._dispatch(
            None,
            {
                "action": "schematicOpenSource",
                "requestId": "source",
                "componentId": data["components"][0]["id"],
                "path": "/etc/passwd",
                "line": 999,
            },
        )
        assert sent[-1]["ok"] is True
        assert forwarded[-1]["action"] == "vscode.openFile"
        assert forwarded[-1]["path"] == str(project / "main.ato")
        assert forwarded[-1]["line"] == 14
        await core._dispatch(
            None,
            {
                "action": "getSchematicData",
                "requestId": "escape",
                "projectRoot": "/tmp",
            },
        )
        assert sent[-1]["ok"] is False
        assert "current workspace" in sent[-1]["error"]
        assert data["layoutPath"].startswith(str(project))

    asyncio.run(run())

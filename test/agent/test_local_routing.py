"""Real KiCad 10 boards, native connectivity/DRC, and scoped mutation failures."""

import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import types
import uuid
from pathlib import Path

import pytest

from atopile.agent.scope import Scope, ScopeError
from atopile.agent.tools import create_registry, layout
from atopile.model import pcb_transaction
from faebryk.libs.kicad.fileformats import kicad

NATIVE_PYTHON = Path(
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9"
)
CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


def native(code, *args):
    env = {
        k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG", "TMPDIR"}
    }
    result = subprocess.run(
        [str(NATIVE_PYTHON), "-I", "-c", code, *map(str, args)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture(scope="session")
def native_board(tmp_path_factory):
    if not NATIVE_PYTHON.is_file() or not CLI.is_file():
        pytest.skip("Installed native KiCad 10 is needed for connectivity acceptance")
    path = tmp_path_factory.mktemp("native-kicad10") / "board.kicad_pcb"
    native(
        """
import pcbnew,sys
b=pcbnew.BOARD()
b.SetLayerName(pcbnew.F_Cu,'Custom top')
def xy(x,y):return pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y))
net=pcbnew.NETINFO_ITEM(b,'TEST',1);b.Add(net)
other=pcbnew.NETINFO_ITEM(b,'OTHER',2);b.Add(other)
for ref,x,y,n in [('J1',5,10,net),('J2',15,10,net),('J3',5,15,other)]:
 f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetValue('testpoint');f.SetPosition(xy(x,y));b.Add(f)
 p=pcbnew.PAD(f);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
 p.SetShape(pcbnew.PAD_SHAPE_CIRCLE);p.SetSize(xy(1,1));p.SetPosition(xy(x,y))
 layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers);p.SetNet(n);f.Add(p)
for start,end in [((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))]:
 s=pcbnew.PCB_SHAPE(b);s.SetShape(pcbnew.SHAPE_T_SEGMENT);s.SetLayer(pcbnew.Edge_Cuts)
 s.SetStart(xy(*start));s.SetEnd(xy(*end));s.SetWidth(pcbnew.FromMM(.05));b.Add(s)
pcbnew.SaveBoard(sys.argv[1],b)
""",
        path,
    )
    return path


@pytest.fixture
def board(native_board, tmp_path, monkeypatch):
    path = tmp_path / "board.kicad_pcb"
    shutil.copyfile(native_board, path)
    monkeypatch.setenv("ATOPILE_LOCAL_DATA_DIR", str(tmp_path / "state"))
    return path, Scope(allowed_roots=[tmp_path])


def call(tool, args, board):
    path, scope = board
    return asyncio.run(tool({"path": str(path), **args}, scope))


def segment(**changes):
    return {
        "net": "TEST",
        "start_x_mm": 5,
        "start_y_mm": 10,
        "end_x_mm": 15,
        "end_y_mm": 10,
        "width_mm": 0.25,
        "layer": "F.Cu",
        **changes,
    }


def drc(board):
    path, _ = board
    before = path.read_bytes()
    result = call(layout.layout_run_drc, {}, board)
    assert path.read_bytes() == before
    assert result["zones_refilled_for_check"] is True and result["board_saved"] is False
    return result


def test_native_connectivity_improves_and_roundtrip_preserves_unknown_setup(board):
    path, _ = board
    before = path.read_bytes()
    native_before = drc(board)
    assert native_before["unconnected_count"] == 1
    result = call(layout.layout_add_track_segment, segment(), board)
    assert Path(result["backup_path"]).read_bytes() == before
    assert result["clearance_checked"] is False and result["routing_complete"] is False
    after = path.read_bytes()
    # A root copper insertion must preserve every existing byte and native setting.
    position = after.find(b"(segment", after.rfind(b"(gr_"))
    assert position >= 0
    assert b"(tenting" in before and b"(covering" in before
    native_after = drc(board)
    assert native_after["unconnected_count"] == 0
    pcb = layout._load(path).kicad_pcb
    assert len(pcb.segments) == 1 and str(pcb.segments[0].uuid) == result["uuid"]
    assert layout._netlist(pcb) == layout._netlist(
        kicad.loads(kicad.pcb.PcbFile, before.decode()).kicad_pcb
    )
    info = json.loads(
        native(
            """
import pcbnew,sys,json
b=pcbnew.LoadBoard(sys.argv[1]);b.BuildConnectivity()
tracks=[(str(t.m_Uuid.AsString()),t.GetNetname(),pcbnew.ToMM(t.GetWidth()))
        for t in b.GetTracks()]
print(json.dumps({'tracks':tracks}))
""",
            path,
        )
    )
    assert info["tracks"] == [[result["uuid"], "TEST", 0.25]]


def test_wrong_net_primitive_is_reported_by_native_drc_not_claimed_safe(board):
    baseline = drc(board)
    # Join pads on different nets. An isolated track touching only TEST pads
    # would be auto-assigned to TEST by KiCad and would not prove a real short.
    call(layout.layout_add_track_segment, segment(end_x_mm=5, end_y_mm=15), board)
    checked = drc(board)
    assert checked["violation_count"] > baseline["violation_count"]
    report = json.loads(Path(checked["report_path"]).read_text())
    assert any(
        "short" in str(item.get("type", "")).lower() for item in report["violations"]
    )


def test_through_via_add_read_delete_and_uuid_guard(board):
    call(layout.layout_add_track_segment, segment(), board)
    original = board[0].read_bytes()
    result = call(
        layout.layout_add_via,
        {"net": "TEST", "x_mm": 10, "y_mm": 10, "diameter_mm": 0.6, "drill_mm": 0.3},
        board,
    )
    routes = call(layout.layout_get_routes, {"net": "TEST"}, board)
    via = next(item for item in routes["items"] if item["kind"] == "via")
    assert via["layers"] == ["F.Cu", "B.Cu"] and via["uuid"] == result["uuid"]
    assert via["diameter_mm"] == 0.6 and via["drill_mm"] == 0.3
    call(layout.layout_delete_copper, {"uuid": via["uuid"]}, board)
    assert not layout._load(board[0]).kicad_pcb.vias
    assert drc(board)["unconnected_count"] == 0
    assert Path(result["backup_path"]).read_bytes() == original
    before = board[0].read_bytes()
    with pytest.raises(ValueError, match="exact existing"):
        call(layout.layout_delete_copper, {"uuid": via["uuid"]}, board)
    assert board[0].read_bytes() == before


def test_native_footprint_move_rotate_flip_preserves_netlist(board):
    path, _ = board
    original = path.read_bytes()
    pcb_file = layout._load(path)
    before = layout._netlist(pcb_file.kicad_pcb)
    result = call(
        layout.layout_set_component_position,
        {"address": "J1", "x_mm": 6, "y_mm": 10, "rotation_deg": 90, "layer": "B.Cu"},
        board,
    )
    assert result["after"]["layer"] == "B.Cu" and result["after"]["rotation_deg"] == 90
    assert Path(result["backup_path"]).read_bytes() == original
    after_file = layout._load(path)
    assert layout._netlist(after_file.kicad_pcb) == before
    inspected = json.loads(
        native(
            """
import pcbnew,sys,json
b=pcbnew.LoadBoard(sys.argv[1])
f=next(f for f in b.GetFootprints() if f.GetReference()=='J1')
print(json.dumps({'x':pcbnew.ToMM(f.GetPosition().x),'y':pcbnew.ToMM(f.GetPosition().y),
                 'angle':f.GetOrientationDegrees(),'back':f.GetLayer()==pcbnew.B_Cu}))
""",
            path,
        )
    )
    assert inspected == {"x": 6, "y": 10, "angle": 90, "back": True}


def test_route_pad_world_coordinates_match_native_rotated_footprint(board):
    path, _ = board
    native(
        """
import pcbnew,sys
b=pcbnew.LoadBoard(sys.argv[1])
f=next(f for f in b.GetFootprints() if f.GetReference()=='J2')
p=next(iter(f.Pads()));p.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(16),pcbnew.FromMM(10)))
f.SetOrientationDegrees(90);pcbnew.SaveBoard(sys.argv[1],b)
""",
        path,
    )
    expected = json.loads(
        native(
            """
import pcbnew,sys,json
b=pcbnew.LoadBoard(sys.argv[1])
f=next(f for f in b.GetFootprints() if f.GetReference()=='J2')
p=next(iter(f.Pads()));print(json.dumps([pcbnew.ToMM(p.GetPosition().x),pcbnew.ToMM(p.GetPosition().y)]))
""",
            path,
        )
    )
    data = call(layout.layout_get_routes, {"net": "TEST"}, board)
    endpoint = next(p for p in data["pads"] if p["reference"] == "J2")
    assert [endpoint["x_mm"], endpoint["y_mm"]] == pytest.approx(expected)
    assert endpoint["copper_layers"] == ["F.Cu"]
    assert data["copper_layers"] == ["F.Cu", "B.Cu"]


@pytest.mark.parametrize(
    "changes",
    [
        {"net": "invented"},
        {"layer": "Custom top"},
        {"layer": "F.SilkS"},
        {"width_mm": 0},
        {"start_x_mm": -1},
        {"end_x_mm": math.inf},
        {"end_x_mm": 5, "end_y_mm": 10},
    ],
)
def test_invalid_route_never_writes_or_creates_backup(board, changes):
    before = board[0].read_bytes()
    with pytest.raises(ValueError):
        call(layout.layout_add_track_segment, segment(**changes), board)
    assert board[0].read_bytes() == before
    assert not list(board[0].parent.glob("*.bak"))


def test_invalid_via_scope_and_non_copper_delete_never_write(board):
    before = board[0].read_bytes()
    with pytest.raises(ValueError):
        call(
            layout.layout_add_via,
            {
                "net": "TEST",
                "x_mm": 10,
                "y_mm": 10,
                "diameter_mm": 0.3,
                "drill_mm": 0.6,
            },
            board,
        )
    footprint_id = str(layout._load(board[0]).kicad_pcb.footprints[0].uuid)
    with pytest.raises(ValueError, match="segment, arc or via"):
        call(layout.layout_delete_copper, {"uuid": footprint_id}, board)
    with pytest.raises(ScopeError):
        call(
            layout.layout_add_track_segment,
            {**segment(), "path": "/etc/private.kicad_pcb"},
            board,
        )
    assert board[0].read_bytes() == before


def test_generated_uuid_collision_is_rejected(board, monkeypatch):
    existing = layout._load(board[0]).kicad_pcb.footprints[0].uuid
    monkeypatch.setattr(layout.uuid, "uuid4", lambda: uuid.UUID(existing))
    before = board[0].read_bytes()
    with pytest.raises(RuntimeError, match="UUID already exists"):
        call(layout.layout_add_track_segment, segment(), board)
    assert board[0].read_bytes() == before


def test_routing_tools_are_in_actual_provider_registry():
    schemas = {entry["name"]: entry for entry in create_registry().definitions()}
    for name in [
        "layout_get_routes",
        "layout_add_track_segment",
        "layout_add_via",
        "layout_delete_copper",
    ]:
        assert name in schemas
    fields = schemas["layout_add_track_segment"]["parameters"]
    assert fields["additionalProperties"] is False
    assert fields["properties"]["start_x_mm"]["type"] == "number"
    assert {"net", "width_mm", "layer", "start_x_mm", "end_x_mm"} <= set(
        fields["required"]
    )


def test_unrelated_native_locks_preserved_and_requested_locked_target_refused(board):
    path, _ = board
    native(
        """
import pcbnew,sys
b=pcbnew.LoadBoard(sys.argv[1])
next(f for f in b.GetFootprints() if f.GetReference()=='J3').SetLocked(True)
pcbnew.SaveBoard(sys.argv[1],b)
""",
        path,
    )
    before = path.read_bytes()
    call(
        layout.layout_set_component_position,
        {"address": "J1", "x_mm": 6, "y_mm": 10},
        board,
    )
    assert b"(locked yes)" in path.read_bytes() or b" locked" in path.read_bytes()
    assert Path(next(path.parent.glob("*.bak"))).read_bytes() == before
    after = path.read_bytes()
    with pytest.raises(ValueError, match="locked"):
        call(
            layout.layout_set_component_position,
            {"address": "J3", "x_mm": 7, "y_mm": 15},
            board,
        )
    assert path.read_bytes() == after
    routed = call(layout.layout_add_track_segment, segment(start_x_mm=6), board)
    native(
        """
import pcbnew,sys
b=pcbnew.LoadBoard(sys.argv[1]);next(iter(b.GetTracks())).SetLocked(True)
pcbnew.SaveBoard(sys.argv[1],b)
""",
        path,
    )
    before = path.read_bytes()
    with pytest.raises(ValueError, match="locked"):
        call(layout.layout_delete_copper, {"uuid": routed["uuid"]}, board)
    assert path.read_bytes() == before


def test_tool_and_ui_edits_preserve_crlf_and_native_unknown_settings(
    board, monkeypatch
):
    from atopile.server.domains import layout as service_module
    from atopile.server.domains.layout_models import MoveCommand, UndoCommand

    path, _ = board
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    original = path.read_bytes()
    setup_start = original.index(b"\t(setup")
    setup_end = original.index(b"\r\n\t(footprint", setup_start)
    setup_bytes = original[setup_start:setup_end]
    call(
        layout.layout_set_component_position,
        {"address": "J1", "x_mm": 6, "y_mm": 10},
        board,
    )
    call(layout.layout_add_track_segment, segment(start_x_mm=6), board)
    assert setup_bytes in path.read_bytes()
    assert b"\n" not in path.read_bytes().replace(b"\r\n", b"")
    service = service_module.LayoutService()
    service.load(path)
    monkeypatch.setattr(service_module, "_reload_pcb_in_kicad", lambda _: None)
    chosen = next(fp for fp in service.manager.get_footprints() if fp.reference == "J2")

    async def edit_and_undo():
        moved = await service.execute_action(
            MoveCommand(command="move", uuids=[chosen.uuid], dx=0, dy=1)
        )
        assert moved.status == "ok"
        assert service.manager.can_undo
        undone = await service.execute_action(UndoCommand(command="undo"))
        assert undone.status == "ok"
        assert service.manager.can_redo

    asyncio.run(edit_and_undo())
    assert setup_bytes in path.read_bytes()
    assert b"\n" not in path.read_bytes().replace(b"\r\n", b"")
    assert drc(board)["unconnected_count"] == 0


def test_ui_composite_failure_restores_model_and_history(board):
    from atopile.server.domains.layout_pcb_manager import (
        Action,
        CompositeAction,
        MoveAction,
        PcbManager,
    )

    manager = PcbManager()
    manager.load(board[0])
    before = kicad.dumps(manager._pcb_file)
    rendered_before = manager.get_render_model().model_dump()
    target = manager.pcb.footprints[0]

    class Failure(Action):
        def execute(self, pcb):
            raise ValueError("later operation refused")

        def undo(self, pcb):
            raise AssertionError("failed operation must never enter history")

    with pytest.raises(ValueError, match="later operation"):
        manager.execute_action(CompositeAction([MoveAction(target, 1, 0), Failure()]))
    assert kicad.dumps(manager._pcb_file) == before
    assert manager.get_render_model().model_dump() == rendered_before
    assert not manager.can_undo and not manager.can_redo
    assert board[0].read_bytes() == before.encode()


def test_failed_undo_restores_model_and_retains_history(board):
    from atopile.server.domains.layout_pcb_manager import Action, MoveAction, PcbManager

    manager = PcbManager()
    manager.load(board[0])
    move = MoveAction(manager.pcb.footprints[0], 1, 0)

    class BadUndo(Action):
        def execute(self, pcb):
            move.execute(pcb)

        def undo(self, pcb):
            move.undo(pcb)
            raise ValueError("undo operation refused")

    manager.execute_action(BadUndo())
    snapshot = kicad.dumps(manager._pcb_file)
    rendered = manager.get_render_model().model_dump()
    with pytest.raises(ValueError, match="undo operation"):
        manager.undo()
    assert kicad.dumps(manager._pcb_file) == snapshot
    assert manager.get_render_model().model_dump() == rendered
    assert manager.can_undo and not manager.can_redo


def test_external_same_path_reload_clears_stale_history_but_identical_reload_keeps_it(
    board,
):
    from atopile.server.domains.layout_pcb_manager import PcbManager

    path, _ = board
    manager = PcbManager()
    manager.load(path)
    chosen = next(fp for fp in manager.get_footprints() if fp.reference == "J1")
    manager.move_footprint(chosen.uuid, 6, 10)
    manager.save()
    assert manager.can_undo
    manager.load(path)
    assert manager.can_undo
    call(layout.layout_add_track_segment, segment(start_x_mm=6), board)
    actual = path.read_bytes()
    manager.load(path)
    assert not manager.can_undo and not manager.can_redo
    assert len(manager.pcb.segments) == 1
    assert path.read_bytes() == actual


def test_existing_arc_uuid_can_be_inspected_and_deleted(board):
    path, _ = board
    native(
        """
import pcbnew,sys
b=pcbnew.LoadBoard(sys.argv[1])
def xy(x,y):return pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y))
a=pcbnew.PCB_ARC(b);a.SetStart(xy(5,5));a.SetMid(xy(10,4));a.SetEnd(xy(15,5))
a.SetWidth(pcbnew.FromMM(.25));a.SetLayer(pcbnew.F_Cu);a.SetNet(b.FindNet('TEST'));b.Add(a)
pcbnew.SaveBoard(sys.argv[1],b)
""",
        path,
    )
    arc = next(
        item
        for item in call(layout.layout_get_routes, {}, board)["items"]
        if item["kind"] == "arc"
    )
    before = path.read_bytes()
    result = call(layout.layout_delete_copper, {"uuid": arc["uuid"]}, board)
    assert not layout._load(path).kicad_pcb.arcs
    assert Path(result["backup_path"]).read_bytes() == before


def test_ui_stale_save_keeps_agent_edit_and_discards_pending_model_history(
    board, monkeypatch
):
    from atopile.server.domains import layout as service_module
    from atopile.server.domains.layout_models import MoveCommand

    path, _ = board
    service = service_module.LayoutService()
    service.load(path)
    monkeypatch.setattr(service_module, "_reload_pcb_in_kicad", lambda _: None)
    chosen = service.manager.get_footprints()[0]
    call(layout.layout_add_track_segment, segment(), board)
    actual = path.read_bytes()
    response = asyncio.run(
        service.execute_action(
            MoveCommand(command="move", uuids=[chosen.uuid], dx=1, dy=0)
        )
    )
    assert response.status == "error" and "changed in the editor" in response.message
    assert path.read_bytes() == actual
    assert len(service.manager.pcb.segments) == 1
    assert not service.manager.can_undo and not service.manager.can_redo
    now = next(fp for fp in service.manager.get_footprints() if fp.uuid == chosen.uuid)
    assert now.x == chosen.x and now.y == chosen.y


def test_ui_failed_atomic_save_restores_disk_model_and_history(board, monkeypatch):
    from atopile.server.domains import layout as service_module
    from atopile.server.domains.layout_models import MoveCommand

    path, _ = board
    service = service_module.LayoutService()
    service.load(path)
    monkeypatch.setattr(service_module, "_reload_pcb_in_kicad", lambda _: None)
    original = path.read_bytes()
    chosen = service.manager.get_footprints()[0]

    def failed_replace(*_):
        raise PermissionError("simulated atomic commit failure")

    monkeypatch.setattr(pcb_transaction.os, "replace", failed_replace)
    response = asyncio.run(
        service.execute_action(
            MoveCommand(command="move", uuids=[chosen.uuid], dx=1, dy=0)
        )
    )
    assert response.status == "error" and "commit failure" in response.message
    assert path.read_bytes() == original
    assert kicad.dumps(service.manager._pcb_file).encode() == original
    assert not service.manager.can_undo and not service.manager.can_redo
    assert not list(path.parent.glob(".local-layout-*"))


def test_external_edit_during_serialization_is_never_overwritten(board, monkeypatch):
    path, _ = board
    original = path.read_bytes()
    external = original + b"\n"
    dump = layout.kicad.dumps

    def race(*args, **kwargs):
        value = dump(*args, **kwargs)
        path.write_bytes(external)
        return value

    monkeypatch.setattr(layout.kicad, "dumps", race)
    with pytest.raises(RuntimeError, match="changed in the editor"):
        call(layout.layout_add_track_segment, segment(), board)
    assert path.read_bytes() == external
    assert not list(path.parent.glob("*.bak"))


def test_commit_checks_again_after_preparing_replacement(tmp_path, monkeypatch):
    path = tmp_path / "board.kicad_pcb"
    path.write_bytes(b"original")
    original_factory = pcb_transaction.tempfile.NamedTemporaryFile

    class RacingTemporary:
        def __enter__(self):
            self.handle = original_factory(mode="wb", dir=tmp_path, delete=False)
            return self.handle.__enter__()

        def __exit__(self, *args):
            self.handle.__exit__(*args)
            path.write_bytes(b"external edit")

    monkeypatch.setattr(
        pcb_transaction.tempfile, "NamedTemporaryFile", lambda **_: RacingTemporary()
    )
    with pytest.raises(RuntimeError, match="changed in the editor"):
        pcb_transaction.commit_pcb_bytes(path, b"original", b"our edit")
    assert path.read_bytes() == b"external edit"


def test_local_file_commit_never_requests_native_kicad_reload(board, monkeypatch):
    from atopile.server.domains import layout as service_module

    calls = []
    ipc = types.ModuleType("faebryk.libs.kicad.ipc")
    ipc.reload_pcb = lambda path: calls.append(path)
    monkeypatch.setitem(sys.modules, "faebryk.libs.kicad.ipc", ipc)
    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "1")
    service_module._reload_pcb_in_kicad(board[0])
    assert calls == []
    # Explicit hosted mode retains upstream behavior; local mode is the default.
    monkeypatch.setenv("ATOPILE_LOCAL_MODE", "0")
    service_module._reload_pcb_in_kicad(board[0])
    assert calls == [board[0]]


def test_ui_stop_waits_until_the_atomic_edit_finishes(board, monkeypatch):
    from atopile.server.domains import layout as service_module
    from atopile.server.domains.layout_models import MoveCommand

    service = service_module.LayoutService()
    service.load(board[0])
    chosen = service.manager.get_footprints()[0]
    original = board[0].read_bytes()
    release = threading.Event()
    real_save = service.manager.save
    monkeypatch.setattr(service_module, "_reload_pcb_in_kicad", lambda _: None)

    async def scenario():
        started = asyncio.Event()
        loop = asyncio.get_running_loop()

        def delayed_save():
            loop.call_soon_threadsafe(started.set)
            assert release.wait(5)
            real_save()

        monkeypatch.setattr(service.manager, "save", delayed_save)
        task = asyncio.create_task(
            service.execute_action(
                MoveCommand(command="move", uuids=[chosen.uuid], dx=1, dy=0)
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and board[0].read_bytes() == original
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            assert board[0].read_bytes() != original
            assert not service._action_lock.locked()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())

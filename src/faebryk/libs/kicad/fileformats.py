import copy
import logging
import math
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Callable,
    Iterable,
    Protocol,
    cast,
    overload,
)

from faebryk.libs.checksum import Checksum
from faebryk.libs.kicad.other_fileformats import (
    UUID,
    C_kicad_config_common,
    C_kicad_drc_report_file,
    C_kicad_model_file,
    C_kicad_project_file,
)
from faebryk.libs.util import compare_dataclasses, find, find_or

logger = logging.getLogger(__name__)


# TODO find complete examples of the fileformats, maybe in the kicad repo


# zig shims


class Named(Protocol):
    name: str


# namespace
class kicad:
    from faebryk.core.zig.gen.sexp import (
        footprint,  # noqa: E402, F401 # type: ignore[import-untyped]
        footprint_v5,  # noqa: E402, F401 # type: ignore[import-untyped]
        fp_lib_table,  # noqa: E402, F401 # type: ignore[import-untyped]
        netlist,  # noqa: E402, F401 # type: ignore[import-untyped]
        pcb,  # noqa: E402, F401 # type: ignore[import-untyped]
        schematic,  # noqa: E402, F401 # type: ignore[import-untyped]
        symbol,  # noqa: E402, F401 # type: ignore[import-untyped]
        symbol_v6,  # noqa: E402, F401 # type: ignore[import-untyped]
    )

    class project:
        ProjectFile = C_kicad_project_file

    class drc:
        DrcFile = C_kicad_drc_report_file

    class model:
        ModelFile = C_kicad_model_file

    class config:
        ConfigFile = C_kicad_config_common

    type types = (
        pcb.PcbFile
        | footprint.FootprintFile
        | fp_lib_table.FpLibTableFile
        | netlist.NetlistFile
        | symbol.SymbolFile
        | schematic.SchematicFile
        | C_kicad_drc_report_file
        | C_kicad_model_file
        | C_kicad_project_file
        | C_kicad_config_common
        | footprint_v5.FootprintFile
        | symbol_v6.SymbolFile
    )

    @staticmethod
    def type_to_module(t: type[types] | types):
        def instance_or_subclass(_t: type | object, target: type):
            return _t is target or type(_t) is target

        if t is _KiCad10Pcb or isinstance(t, _KiCad10Pcb):
            return kicad.pcb
        if instance_or_subclass(t, kicad.pcb.PcbFile):
            return kicad.pcb
        elif instance_or_subclass(t, kicad.footprint.FootprintFile):
            return kicad.footprint
        elif instance_or_subclass(t, kicad.fp_lib_table.FpLibTableFile):
            return kicad.fp_lib_table
        elif instance_or_subclass(t, kicad.netlist.NetlistFile):
            return kicad.netlist
        elif instance_or_subclass(t, kicad.symbol.SymbolFile):
            return kicad.symbol
        elif instance_or_subclass(t, kicad.schematic.SchematicFile):
            return kicad.schematic
        elif instance_or_subclass(t, kicad.footprint_v5.FootprintFile):
            return kicad.footprint_v5
        elif instance_or_subclass(t, kicad.symbol_v6.SymbolFile):
            return kicad.symbol_v6
        elif instance_or_subclass(t, kicad.drc.DrcFile):
            return kicad.drc.DrcFile
        # TODO need to switch to bytes instead of str in sexp load
        # elif instance_or_subclass(t, kicad.model.ModelFile):
        #    return kicad.model.ModelFile
        elif instance_or_subclass(t, kicad.project.ProjectFile):
            return kicad.project.ProjectFile
        elif instance_or_subclass(t, kicad.config.ConfigFile):
            return kicad.config.ConfigFile

        raise ValueError(f"Unsupported type: {t} ({type(t)})")

    @staticmethod
    def loads[T: kicad.types](t: type[T], path_or_sexpstring: Path | str) -> T:
        """
        Attention: object returned is shared, so be careful with mutations!
        """
        path = None
        if isinstance(path_or_sexpstring, Path):
            path = path_or_sexpstring
            if not hasattr(kicad.loads, "cache"):
                kicad.loads.cache = {}
            if path in kicad.loads.cache:
                out = kicad.loads.cache[path]
                assert isinstance(out, t)
                return out
            if t in (kicad.pcb.PcbFile, _KiCad10Pcb):
                with path.open("r", encoding="utf-8", newline="") as source:
                    data = source.read()
            else:
                data = path.read_text(encoding="utf-8")
        else:
            data = path_or_sexpstring

        if t in (kicad.pcb.PcbFile, _KiCad10Pcb):
            out = cast(T, _load_pcb_compatible(data))
        else:
            out = cast(T, kicad.type_to_module(t).loads(data))
        # Compatibility objects must not share unsaved mutations with later reads.
        if path and not isinstance(out, _KiCad10Pcb):
            kicad.loads.cache[path] = out
        return out

    @staticmethod
    def dumps(obj: types, path: Path | None = None):
        if isinstance(obj, _KiCad10Pcb):
            raw = obj.serialize_source()
        else:
            raw = kicad.type_to_module(obj).dumps(
                obj,  # type: ignore
            )

        # TODO should live in zig
        # some files have trailing newlines, some don't
        if isinstance(obj, kicad.footprint.FootprintFile):
            if raw.endswith("\n"):
                raw = raw[: -len("\n")]

        if path is not None:
            if isinstance(obj, _KiCad10Pcb):
                obj.write_source(path, raw)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(raw, encoding="utf-8")
        return raw

    @staticmethod
    def gen_uuid(mark: str = ""):
        import uuid

        # format: d864cebe-263c-4d3f-bbd6-bb51c6d2a608
        value = uuid.uuid4().hex

        suffix = mark.encode().hex()
        if suffix:
            value = value[: -len(suffix)] + suffix

        DASH_IDX = [8, 12, 16, 20]
        formatted = value
        for i, idx in enumerate(DASH_IDX):
            formatted = formatted[: idx + i] + "-" + formatted[idx + i :]

        return UUID(formatted)

    @staticmethod
    def fp_get_base_name(fp: footprint.Footprint | pcb.Footprint) -> str:
        return fp.name.split(":")[-1]

    @staticmethod
    def get[T: Named](obj: Iterable[T], name: str) -> T:
        return find(obj, lambda o: o.name == name)

    @staticmethod
    def try_get[T: Named](
        obj: Iterable[T], name: str, default: T | None = None
    ) -> T | None:
        return find_or(obj, lambda o: o.name == name, default=cast(T, default))

    @staticmethod
    def set[T: Named](
        parent,
        field: str,
        container: list[T],
        value: T,
        index: int | None = None,
        preserve_uuid: bool = True,
    ) -> T:
        uuid = None
        if index is None:
            index = next(
                (i for i, o in enumerate(container) if o.name == value.name), -1
            )
            if index != -1:
                uuid = getattr(container[index], "uuid", None)
        kicad.filter(parent, field, container, lambda o: o.name != value.name)

        if preserve_uuid and hasattr(value, "uuid") and uuid:
            setattr(value, "uuid", uuid)

        return kicad.insert(parent, field, container, value, index=index)

    @staticmethod
    def insert[T](parent, field: str, container: list[T], *value: T, index=-1) -> T:
        obj = getattr(parent, field)
        for i, val in enumerate(value):
            obj.insert(index + i, val)

        return obj[index]

    @staticmethod
    def filter[T](
        parent, field: str, container: list[T], predicate: Callable[[T], bool]
    ):
        obj = getattr(parent, field)

        # Iterate backwards to avoid index shifting issues
        for i in range(len(obj) - 1, -1, -1):
            if not predicate(obj[i]):
                obj.pop(i)

        return obj

    @staticmethod
    def delete[T: Named](parent, field: str, container: list[T], name: str):
        kicad.filter(parent, field, container, lambda o: o.name != name)

    @staticmethod
    def clear_and_set[T](parent, field: str, container: list[T], values: list[T]):
        obj = getattr(parent, field)

        obj.clear()
        for val in values:
            obj.append(val)

    class geo:
        @staticmethod
        def rotate(obj: "kicad.pcb.Xy", center: "kicad.pcb.Xy", angle: float):
            import math

            angle = -angle  # rotate kicad style counter-clockwise

            # Translate point to origin
            translated_x = obj.x - center.x
            translated_y = obj.y - center.y

            # Convert angle to radians
            angle = math.radians(angle)

            # Rotate
            rotated_x = translated_x * math.cos(angle) - translated_y * math.sin(angle)
            rotated_y = translated_x * math.sin(angle) + translated_y * math.cos(angle)

            # Translate back
            new_x = rotated_x + center.x
            new_y = rotated_y + center.y

            return kicad.pcb.Xy(x=new_x, y=new_y)

        @overload
        @staticmethod
        def add(obj: "kicad.pcb.Xy", *other: "kicad.pcb.Xy") -> "kicad.pcb.Xy": ...

        @overload
        @staticmethod
        def add(
            obj: "kicad.pcb.Xyr", *other: "kicad.pcb.Xyr | kicad.pcb.Xy"
        ) -> "kicad.pcb.Xyr": ...

        @staticmethod
        def add(obj, *other):
            x = obj.x
            y = obj.y
            r = getattr(obj, "r", None) or 0
            for o in other:
                x += o.x
                y += o.y
                r += getattr(o, "r", None) or 0
            if hasattr(obj, "r"):
                return kicad.pcb.Xyr(x=x, y=y, r=r)
            else:
                return kicad.pcb.Xy(x=x, y=y)

        @overload
        @staticmethod
        def sub(obj: "kicad.pcb.Xy", *other: "kicad.pcb.Xy") -> "kicad.pcb.Xy": ...

        @overload
        @staticmethod
        def sub(
            obj: "kicad.pcb.Xyr", *other: "kicad.pcb.Xyr | kicad.pcb.Xy"
        ) -> "kicad.pcb.Xyr": ...

        @staticmethod
        def sub(obj, *other):
            x = obj.x
            y = obj.y
            r = getattr(obj, "r", None) or 0
            for o in other:
                x -= o.x
                y -= o.y
                r -= getattr(o, "r", None) or 0
            if hasattr(obj, "r"):
                return kicad.pcb.Xy(x=x, y=y)
            else:
                return kicad.pcb.Xyr(x=x, y=y, r=r)

        @staticmethod
        def neg(obj: "kicad.pcb.Xy") -> "kicad.pcb.Xy":
            return kicad.pcb.Xy(x=-obj.x, y=-obj.y)

        @staticmethod
        def get_layers(obj):
            if obj.layer is not None:
                return [obj.layer]
            if obj.layers is not None:
                return obj.layers
            return []

        @staticmethod
        def apply_to_layers(obj, func: Callable[[str], str]):
            if hasattr(obj, "layer") and obj.layer is not None:
                if isinstance(obj.layer, str):
                    obj.layer = func(obj.layer)
                elif hasattr(obj.layer, "layer"):
                    obj.layer.layer = func(obj.layer.layer)
            if hasattr(obj, "layers") and obj.layers is not None:
                obj.layers = [func(layer) for layer in obj.layers]

    @staticmethod
    @overload
    def convert(
        old: "kicad.footprint_v5.FootprintFile",
    ) -> "kicad.footprint.FootprintFile": ...

    @staticmethod
    @overload
    def convert(
        old: "kicad.symbol_v6.SymbolFile",
    ) -> "kicad.symbol.SymbolFile": ...

    @staticmethod
    def convert(old: Any) -> Any:
        old = kicad.copy(old)
        if isinstance(old, kicad.footprint_v5.FootprintFile):

            def _calc_arc_midpoint(arc: kicad.footprint_v5.Arc):
                start = arc.end
                center = arc.start

                mid = kicad.geo.rotate(start, center, -arc.angle / 2.0)
                end = kicad.geo.rotate(start, center, -arc.angle)

                return {"start": start, "mid": mid, "end": end}

            for k in old.footprint.fp_texts:
                if (name := k.type.capitalize()) in ("Reference", "Value"):
                    Property.set_property(
                        old.footprint,
                        kicad.pcb.Property(
                            name=name,
                            value=k.text,
                            at=k.at,
                            layer=k.layer.layer,
                            uuid=k.uuid or kicad.gen_uuid(),
                            hide=k.hide,
                            effects=k.effects,
                            unlocked=None,
                        ),
                        index=0 if name == "Reference" else 1,
                    )
            texts = [
                t
                for t in old.footprint.fp_texts
                if t.type
                not in (
                    kicad.pcb.E_fp_text_type.REFERENCE,
                    kicad.pcb.E_fp_text_type.VALUE,
                )
            ]
            for t in old.footprint.fp_texts:
                if t.type == kicad.pcb.E_fp_text_type.REFERENCE:
                    # already added it as property
                    continue
                    texts.append(
                        kicad.pcb.FpText(
                            type=kicad.pcb.E_fp_text_type.USER,
                            text=t.text.replace("REF**", "${REFERENCE}"),
                            at=t.at,
                            layer=t.layer,
                            uuid=t.uuid or kicad.gen_uuid(),
                            effects=t.effects,
                            hide=t.hide,
                        )
                    )
                elif not t.uuid:
                    t.uuid = kicad.gen_uuid()

            for p in old.footprint.pads:
                if p.uuid:
                    continue
                p.uuid = kicad.gen_uuid()

            if old.footprint.layer not in [None, "F.Cu"]:
                raise ValueError(
                    f"Invalid library footprint: layer must be F.Cu, got"
                    f" {old.footprint.layer}"
                )

            return kicad.footprint.FootprintFile(
                footprint=kicad.footprint.Footprint(
                    name=old.footprint.name,
                    layer=old.footprint.layer,
                    uuid=old.footprint.uuid or kicad.gen_uuid(),
                    path=old.footprint.path,
                    propertys=old.footprint.propertys,
                    fp_texts=texts,
                    attr=old.footprint.attr,
                    fp_lines=[
                        kicad.pcb.Line(
                            start=line.start,
                            end=line.end,
                            layer=line.layer,
                            layers=[line.layer],
                            solder_mask_margin=None,
                            stroke=kicad.pcb.Stroke(width=line.width, type="solid"),
                            fill=None,
                            locked=False,
                            uuid=kicad.gen_uuid(),
                        )
                        for line in old.footprint.fp_lines
                    ],
                    fp_arcs=[
                        kicad.pcb.Arc(
                            **_calc_arc_midpoint(arc),
                            layer=arc.layer,
                            layers=[],
                            solder_mask_margin=None,
                            stroke=kicad.pcb.Stroke(width=arc.width, type="solid"),
                            fill=None,
                            locked=False,
                            uuid=kicad.gen_uuid(),
                        )
                        for arc in old.footprint.fp_arcs
                    ],
                    fp_circles=[
                        kicad.pcb.Circle(
                            center=circle.center,
                            end=circle.end,
                            layer=circle.layer,
                            layers=[],
                            solder_mask_margin=None,
                            stroke=kicad.pcb.Stroke(width=circle.width, type="solid"),
                            fill=None,
                            locked=False,
                            uuid=kicad.gen_uuid(),
                        )
                        for circle in old.footprint.fp_circles
                    ],
                    fp_rects=[
                        kicad.pcb.Rect(
                            start=rect.start,
                            end=rect.end,
                            layer=rect.layer,
                            layers=[],
                            solder_mask_margin=None,
                            stroke=kicad.pcb.Stroke(width=rect.width, type="solid"),
                            fill=None,
                            locked=False,
                            uuid=kicad.gen_uuid(),
                        )
                        for rect in old.footprint.fp_rects
                    ],
                    fp_poly=old.footprint.fp_poly,
                    pads=old.footprint.pads,
                    models=[
                        kicad.pcb.Model(
                            path=old.footprint.model.path,
                            offset=old.footprint.model.offset
                            or old.footprint.model.at
                            or kicad.pcb.ModelXyz(xyz=kicad.pcb.Xyz(x=0, y=0, z=0)),
                            scale=old.footprint.model.scale,
                            rotate=old.footprint.model.rotate,
                        )
                    ]
                    if old.footprint.model
                    else [],
                    description=old.footprint.description,
                    tags=old.footprint.tags,
                    version=20241229,
                    generator="faebryk_convert",
                    generator_version="v5",
                    tedit=old.footprint.tedit,
                    embedded_fonts=False,
                )
            )
        elif isinstance(old, kicad.symbol_v6.SymbolFile):
            return kicad.symbol.SymbolFile(
                kicad_sym=kicad.symbol.SymbolLib(
                    version=20241229,
                    generator="faebryk_convert",
                    symbols=[
                        kicad.schematic.Symbol(
                            name=symbol.name,
                            power=symbol.power,
                            propertys=symbol.propertys,
                            pin_numbers=symbol.pin_numbers,
                            pin_names=symbol.pin_names,
                            in_bom=symbol.in_bom,
                            on_board=symbol.on_board,
                            symbols=[
                                kicad.schematic.SymbolUnit(
                                    name=sym.name,
                                    polylines=sym.polylines,
                                    circles=[
                                        kicad.schematic.Circle(
                                            center=circle.center,
                                            end=kicad.pcb.Xy(
                                                x=circle.center.x + circle.radius,
                                                y=circle.center.y,
                                            ),
                                            stroke=circle.stroke,
                                            fill=circle.fill,
                                        )
                                        for circle in sym.circles
                                    ],
                                    rectangles=sym.rectangles,
                                    arcs=sym.arcs,
                                    pins=sym.pins,
                                )
                                for sym in symbol.symbols
                            ],
                            convert=symbol.convert,
                        )
                        for symbol in old.kicad_sym.symbols
                    ],
                )
            )
        raise ValueError(f"Unsupported type: {type(old)}")

    @staticmethod
    def compare_without_uuid(old: Any, new: Any):
        return compare_dataclasses(
            before=old,
            after=new,
            skip_keys=("uuid",),
            require_dataclass_type_match=False,
            float_precision=2,
        )

    class KicadStruct(Protocol):
        @staticmethod
        def __field_names__() -> list[str]: ...

    type Primitive = str | list | int | float | bool | tuple | None

    @staticmethod
    def copy[T: KicadStruct | Primitive](old: T) -> T:
        if old is None:
            return old
        if isinstance(old, (str, int, float, bool, tuple)):
            return old
        # Accept both Python lists and pyzig MutableList wrappers
        # pyzig exposes lists as a C-extension type named 'pyzig.MutableList'
        if isinstance(old, list) or (
            type(old).__name__ == "MutableList"
            and type(old).__module__ in ("pyzig", "pyzig_local")
        ):
            return [kicad.copy(item) for item in old]  # type: ignore
        t = type(old)
        copied = {
            name: kicad.copy(getattr(old, name)) for name in old.__field_names__()
        }
        out = t(**copied)
        if isinstance(old, _KiCad10Pcb):
            out._original_source = old._original_source
            out._typed_baseline = old._typed_baseline
            out._native_owner = old
            out._last_written = dict(old._last_written)
        return out

    @staticmethod
    def decompress(data: list[str]) -> bytes:
        from base64 import b64decode

        import zstd

        merged = "".join(str(v) for v in data)
        assert merged.startswith("|") and merged.endswith("|")
        return zstd.decompress(b64decode(merged[1:-1]))

    @staticmethod
    def compress(data: bytes) -> list[str]:
        from base64 import b64encode

        import zstd

        # from kicad:common/embedded_files.cpp
        b64 = b64encode(zstd.compress(data)).decode()
        CHUNK_LEN = 76
        # chunk string to 76 characters
        chunks = [b64[i : i + CHUNK_LEN] for i in range(0, len(b64), CHUNK_LEN)]
        chunks[0] = "|" + chunks[0]
        chunks[-1] = chunks[-1] + "|"
        return chunks


class Property:
    class _Property(Protocol):
        name: str
        value: str
        at: kicad.pcb.Xyr

        # def __init__(self, name: str, value: str): ...

    class _PropertyHolder(Protocol):  # [T: _Property](kicad.KicadStruct):
        propertys: list  # [T]

    class PropertyNotSet(Exception):
        pass

    class checksum:
        @staticmethod
        def _hashable(obj: "Property._PropertyHolder", remove_uuid: bool = True):
            # TODO: only used by ato part for verifying user didnt accidentally modify
            # will fix later when we care about that
            raise NotImplementedError("Not implemented")
            copy = kicad.copy(obj)

            Property.checksum.delete_checksum(copy)
            # TODO: this doesn't work atm
            # out = kicad.dumps(copy)
            out = repr(copy)

            if remove_uuid:
                out = re.sub(r"\(uuid \"[^\"]*\"\)", "", out)

            return out

        @staticmethod
        def set_checksum(
            obj: "Property._PropertyHolder", p_type: type["Property._Property"]
        ):
            Property.checksum.delete_checksum(obj)

            attrs = {
                "name": "checksum",
                "value": Checksum.build(Property.checksum._hashable(obj)),
                "at": kicad.pcb.Xyr(x=0, y=0, r=0),
                "hide": True,
            }
            if p_type is kicad.pcb.Property:
                attrs["layer"] = "F.Cu"
            Property.set_property(
                obj,
                p_type(**attrs),
            )

        @staticmethod
        def verify_checksum(obj: "Property._PropertyHolder"):
            checksum_stated = Property.checksum.get_checksum(obj)
            try:
                Checksum.verify(checksum_stated, Property.checksum._hashable(obj))
            except Checksum.Mismatch:
                # legacy
                Checksum.verify(
                    checksum_stated, Property.checksum._hashable(obj, remove_uuid=False)
                )

        @staticmethod
        def delete_checksum(obj: "Property._PropertyHolder"):
            Property.delete_property(obj, "checksum")

        @staticmethod
        def get_checksum(obj: "Property._PropertyHolder") -> str:
            return Property.get_property(obj.propertys, "checksum")

    @staticmethod
    def get_property_obj[T: _Property](obj: Iterable[T], name: str) -> T:
        for prop in obj:
            if prop.name == name:
                return prop
        raise Property.PropertyNotSet(f"Property `{name}` not set")

    @staticmethod
    def get_property(obj: Iterable[_Property], name: str) -> str:
        out = Property.try_get_property(obj, name)
        if out is None:
            raise Property.PropertyNotSet(f"Property `{name}` not set")
        return out

    @staticmethod
    def delete_property[T: _Property](parent: _PropertyHolder, name: str):
        kicad.delete(parent, "propertys", parent.propertys, name)

    @staticmethod
    def set_property[T: _Property](
        parent: _PropertyHolder, prop: T, index: int | None = None
    ) -> T:
        for p in parent.propertys:
            if p.name == prop.name:
                p.value = prop.value
                return p

        return kicad.set(parent, "propertys", parent.propertys, prop, index=index)

    @staticmethod
    def try_get_property(obj: Iterable[_Property], name: str) -> str | None:
        for prop in obj:
            if prop.name == name:
                return prop.value
        return None

    @staticmethod
    def property_dict(obj: Iterable[_Property]) -> dict[str, str]:
        return {prop.name: prop.value for prop in obj}


class _KiCad10Pcb(kicad.pcb.PcbFile):
    """Native model whose approved edits patch the complete original document."""

    preserves_unknown_fields = True

    def serialize_source(self) -> str:
        current = kicad.pcb.dumps(self)
        if current == self._typed_baseline:
            return self._original_source
        return _patch_kicad10(self._original_source, self._typed_baseline, current)

    def write_source(self, path: Path, raw: str) -> None:
        """Atomically save without replacing an externally changed board."""
        path = Path(path)
        if path.is_symlink():
            raise ValueError("KiCad 10 output must not be a symbolic link")
        resolved = path.resolve()
        expected = self._last_written.get(
            resolved, self._original_source.encode("utf-8")
        )
        if path.exists() and not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("KiCad 10 output must be a regular file")
        previous = path.read_bytes() if path.exists() else None
        if previous is not None and previous != expected:
            raise RuntimeError("PCB changed on disk; reload it before saving")
        mode = stat.S_IMODE(path.stat().st_mode) if previous is not None else 0o644
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(raw.encode("utf-8"))
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, mode)
            if (
                path.is_symlink()
                or (path.read_bytes() if path.exists() else None) != previous
            ):
                raise RuntimeError("PCB changed on disk; reload it before saving")
            os.replace(temporary, path)
            self._last_written[resolved] = raw.encode("utf-8")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _sexp_tag(node):
    return str(node[0]) if isinstance(node, list) and node else ""


def _sexp_groups(node):
    groups = {}
    for child in node:
        if isinstance(child, list) and child:
            groups.setdefault(_sexp_tag(child), []).append(child)
    return groups


def _sexp_identity(node):
    uuids = _sexp_groups(node).get("uuid", [])
    if len(uuids) == 1 and len(uuids[0]) == 2:
        return ("uuid", str(uuids[0][1]))
    if _sexp_tag(node) in {"property", "pad"} and len(node) > 1:
        return (_sexp_tag(node), str(node[1]))
    return None


@dataclass
class _SexpSpan:
    start: int
    end: int
    value: Any
    children: list["_SexpSpan"]

    def groups(self):
        groups = {}
        for child in self.children:
            if isinstance(child.value, list) and child.value:
                groups.setdefault(_sexp_tag(child.value), []).append(child)
        return groups


def _source_spans(source: str) -> _SexpSpan:
    """Locate original Unicode character spans without formatting any source."""
    import sexpdata

    if len(source.encode("utf-8")) > 64 * 1024 * 1024:
        raise ValueError("KiCad 10 editable source exceeds the size limit")
    value = sexpdata.loads(source, nil=None, true=None, false=None)
    position = 0

    def whitespace():
        nonlocal position
        while position < len(source):
            if source[position].isspace():
                position += 1
            elif source[position] == ";":
                end = source.find("\n", position)
                position = len(source) if end == -1 else end + 1
            else:
                break

    def parse(item, depth=0):
        nonlocal position
        if depth > 128:
            raise ValueError("KiCad 10 editable source exceeds its nesting limit")
        whitespace()
        start = position
        children = []
        if position >= len(source):
            raise ValueError("Incomplete KiCad 10 source")
        if source[position] == "(":
            if not isinstance(item, list):
                raise ValueError("Unsupported KiCad 10 source expression")
            position += 1
            for child in item:
                children.append(parse(child, depth + 1))
            whitespace()
            if position >= len(source) or source[position] != ")":
                raise ValueError("Unsupported KiCad 10 source expression")
            position += 1
        elif source[position] == '"':
            position += 1
            while position < len(source) and source[position] != '"':
                position += 2 if source[position] == "\\" else 1
            if position >= len(source):
                raise ValueError("Unterminated KiCad 10 string")
            position += 1
        else:
            while (
                position < len(source)
                and not source[position].isspace()
                and source[position] not in "();"
            ):
                position += 1
            if position == start:
                raise ValueError("Unsupported KiCad 10 source token")
        return _SexpSpan(start, position, item, children)

    root = parse(value)
    whitespace()
    if position != len(source):
        raise ValueError("Unexpected trailing KiCad 10 source")
    return root


_PLACEMENT_FIELDS = {
    "at",
    "start",
    "end",
    "mid",
    "center",
    "xy",
    "layer",
    "layers",
    "justify",
}
_COPPER_FIELDS = {
    "segment": {"start", "end", "width", "layer", "net"},
    "arc": {"start", "mid", "end", "width", "layer", "net"},
    "via": {"at", "size", "drill", "layers", "net"},
}


def _locked_source(node):
    if any(str(atom) == "locked" for atom in node[1:] if not isinstance(atom, list)):
        return True
    for flag in _sexp_groups(node).get("locked", []):
        if len(flag) == 1 or str(flag[1]) in {"yes", "true"}:
            return True
    return False


def _require_known_flip_fields(source: _SexpSpan, baseline):
    """Unknown side-sensitive fields cannot be left on the wrong board side."""
    groups = _sexp_groups(baseline)
    for tag, originals in source.groups().items():
        known = groups.get(tag, [])
        if not known:
            if (
                _sexp_tag(source.value) == "footprint"
                and tag == "duplicate_pad_numbers_are_jumpers"
            ):
                continue
            # Native KiCad 10 Flip preserves this pad-local angle unchanged
            # (checked with asymmetric pads and a nondefault 17-degree angle).
            if _sexp_tag(source.value) == "pad" and tag == "thermal_bridge_angle":
                if (
                    len(originals) == 1
                    and len(originals[0].value) == 2
                    and isinstance(originals[0].value[1], (int, float))
                    and math.isfinite(originals[0].value[1])
                ):
                    continue
            raise ValueError(
                f"KiCad 10 flip cannot preserve unsupported {tag}; flip in native KiCad"
            )
        if len(originals) != len(known):
            raise ValueError(
                "KiCad 10 flip has ambiguous geometry; flip in native KiCad"
            )
        keyed = {_sexp_identity(node): node for node in known}
        for index, original in enumerate(originals):
            identity = _sexp_identity(original.value)
            match = keyed.get(identity) if identity is not None else known[index]
            if match is None:
                raise ValueError(
                    "KiCad 10 flip has ambiguous geometry; flip in native KiCad"
                )
            _require_known_flip_fields(original, match)


def _placement_transform(old, new):
    """Require the footprint's local geometry to follow a rigid placement edit."""
    old_groups, new_groups = _sexp_groups(old), _sexp_groups(new)

    def at(node):
        values = _sexp_groups(node).get("at", [])
        if not values or len(values[0]) < 3:
            raise ValueError("KiCad 10 placement needs explicit object positions")
        value = values[0]
        return (
            float(value[1]),
            float(value[2]),
            float(value[3]) if len(value) > 3 else 0.0,
        )

    flipped = old_groups.get("layer") != new_groups.get("layer")
    before_angle, after_angle = at(old)[2], at(new)[2]
    delta = after_angle - (180 - before_angle if flipped else before_angle)
    for family in ("pad", "property", "fp_text"):
        olds, news = old_groups.get(family, []), new_groups.get(family, [])
        if len(olds) != len(news):
            raise ValueError(
                "KiCad 10 placement cannot add or remove footprint children"
            )
        keyed = {_sexp_identity(node): node for node in news}
        for index, previous in enumerate(olds):
            identity = _sexp_identity(previous)
            current = keyed.get(identity) if identity is not None else news[index]
            if current is None:
                raise ValueError(
                    "KiCad 10 placement requires stable footprint children"
                )
            x, y, angle = at(previous)
            nx, ny, na = at(current)
            expected_y = -y if flipped else y
            if not math.isclose(x, nx, abs_tol=1e-8) or not math.isclose(
                expected_y, ny, abs_tol=1e-8
            ):
                raise ValueError(
                    "KiCad 10 placement cannot independently move pads or labels"
                )
            expected_angle = (180 - angle if flipped else angle) + delta
            period = 360 if family == "pad" else 180
            error = (na - expected_angle + period / 2) % period - period / 2
            if not math.isclose(error, 0, abs_tol=1e-7):
                raise ValueError(
                    "KiCad 10 placement has an unsupported pad or text angle; use native KiCad"
                )
    if flipped and (
        old_groups.get("fp_text_box")
        or any(
            _sexp_groups(pad).get("primitives") or _sexp_groups(pad).get("chamfer")
            for pad in old_groups.get("pad", [])
        )
    ):
        raise ValueError(
            "KiCad 10 flip needs native KiCad for custom pads or text boxes"
        )
    return flipped


def _patch_kicad10(source: str, before: str, after: str) -> str:
    """Patch approved model differences, retaining all other original bytes."""
    import sexpdata

    original = _source_spans(source)
    baseline = sexpdata.loads(before)
    current = sexpdata.loads(after)
    approved = ("footprint", *_COPPER_FIELDS)
    if [node for node in baseline if _sexp_tag(node) not in approved] != [
        node for node in current if _sexp_tag(node) not in approved
    ]:
        raise ValueError(
            "KiCad 10 editing supports placement and copper routes only; board settings, nets, zones and drawings must remain unchanged"
        )
    net_names = {
        node[1]: node[2]
        for node in _sexp_groups(baseline).get("net", [])
        if len(node) == 3
    }
    edits: list[tuple[int, int, str]] = []
    newline = "\r\n" if "\r\n" in source else "\n"

    def uuids(node):
        if not isinstance(node, list):
            return []
        if _sexp_tag(node) == "uuid" and len(node) == 2:
            return [str(node[1])]
        return [value for child in node for value in uuids(child)]

    reserved_uuids = set(uuids(original.value))

    def encoded(node, kind):
        node = copy.deepcopy(node)
        if _sexp_tag(node) == "net":
            if len(node) != 2 or not net_names.get(node[1]):
                raise ValueError("Copper routes must use an existing named net")
            node[1] = net_names[node[1]]
        elif kind in _COPPER_FIELDS:
            for child in node:
                if _sexp_tag(child) == "net":
                    if len(child) != 2 or not net_names.get(child[1]):
                        raise ValueError("Copper routes must use an existing named net")
                    child[1] = net_names[child[1]]
        return sexpdata.dumps(node)

    def unsupported(tag):
        raise ValueError(
            f"KiCad 10 editing cannot safely change {tag}; use native KiCad for this edit"
        )

    def merge(span, old, new, kind, flipped=False):
        if old == new:
            return
        tag = _sexp_tag(old)
        allowed = (
            (_PLACEMENT_FIELDS if flipped else {"at"})
            if kind == "footprint"
            else _COPPER_FIELDS[kind]
        )
        old_atoms = [item for item in old if not isinstance(item, list)]
        new_atoms = [item for item in new if not isinstance(item, list)]
        if old_atoms != new_atoms:
            if tag not in allowed or tag != _sexp_tag(new):
                unsupported(tag)
            if any(isinstance(item, list) for item in span.value[1:]):
                unsupported(tag)
            if tag != "net" and span.value != old_atoms[: len(span.value)]:
                unsupported(tag)
            if kind == "footprint" and flipped:
                if tag in {"start", "end", "mid", "center", "xy"} and (
                    len(old_atoms) != 3
                    or new_atoms[1:] != [old_atoms[1], -old_atoms[2]]
                ):
                    unsupported(tag)
                if tag in {"layer", "layers"}:
                    expected = [
                        old_atoms[0],
                        *[
                            (
                                "B." + value[2:]
                                if value.startswith("F.")
                                else "F." + value[2:]
                                if value.startswith("B.")
                                else value
                            )
                            for value in old_atoms[1:]
                        ],
                    ]
                    if new_atoms != expected:
                        unsupported(tag)
                if tag == "justify":
                    expected = set(old_atoms[1:])
                    mirror = sexpdata.Symbol("mirror")
                    expected.symmetric_difference_update({mirror})
                    if set(new_atoms[1:]) != expected:
                        unsupported(tag)
            edits.append((span.start, span.end, encoded(new, kind)))
            return
        old_groups, new_groups = _sexp_groups(old), _sexp_groups(new)
        source_groups = span.groups()
        for child_tag in dict.fromkeys([*old_groups, *new_groups]):
            olds, news = old_groups.get(child_tag, []), new_groups.get(child_tag, [])
            if olds == news:
                continue
            originals = source_groups.get(child_tag, [])
            if len(olds) <= 1 and len(news) <= 1 and len(originals) <= 1:
                if olds and news and originals:
                    merge(originals[0], olds[0], news[0], kind, flipped)
                elif child_tag in allowed and not any(
                    len(group) > 1 for group in (olds, news, originals)
                ):
                    if originals:
                        edits.append((originals[0].start, originals[0].end, ""))
                    if news:
                        if (
                            kind == "footprint"
                            and child_tag == "justify"
                            and news[0]
                            != [sexpdata.Symbol("justify"), sexpdata.Symbol("mirror")]
                        ):
                            unsupported(child_tag)
                        edits.append(
                            (span.end - 1, span.end - 1, " " + encoded(news[0], kind))
                        )
                else:
                    unsupported(child_tag)
                continue
            if len(olds) != len(news) or len(originals) != len(olds):
                unsupported(child_tag)
            if child_tag == "xy":
                matches = zip(originals, olds, news)
            else:
                old_keys = [_sexp_identity(node) for node in olds]
                new_map = {_sexp_identity(node): node for node in news}
                source_map = {_sexp_identity(node.value): node for node in originals}
                if (
                    None in old_keys
                    or len(set(old_keys)) != len(olds)
                    or set(old_keys) != new_map.keys()
                    or set(old_keys) != source_map.keys()
                ):
                    unsupported(child_tag)
                matches = [
                    (source_map[key], node, new_map[key])
                    for key, node in zip(old_keys, olds)
                ]
            for child_span, old_child, new_child in matches:
                merge(child_span, old_child, new_child, kind, flipped)

    old_groups, new_groups = _sexp_groups(baseline), _sexp_groups(current)
    source_groups = original.groups()
    additions = []
    for kind in approved:
        olds, news = old_groups.get(kind, []), new_groups.get(kind, [])
        if olds == news:
            continue
        old_map = {_sexp_identity(node): node for node in olds}
        new_map = {_sexp_identity(node): node for node in news}
        source_map = {
            _sexp_identity(node.value): node for node in source_groups.get(kind, [])
        }
        if (
            None in old_map
            or None in new_map
            or any(key[0] != "uuid" for key in [*old_map, *new_map])
            or len(old_map) != len(olds)
            or len(new_map) != len(news)
            or set(old_map) != source_map.keys()
        ):
            raise ValueError("KiCad 10 edits require unique, stable object UUIDs")
        if kind == "footprint" and old_map.keys() != new_map.keys():
            unsupported("footprint membership")
        for key, old in old_map.items():
            new = new_map.get(key)
            if old == new:
                continue
            span = source_map[key]
            if _locked_source(span.value):
                raise ValueError("Cannot edit a locked KiCad object")
            if new is None:
                edits.append((span.start, span.end, ""))
                continue
            if kind == "footprint":
                if any(
                    _sexp_tag(node) == "fp_text" and "FBRK:notouch" in node
                    for node in span.value
                    if isinstance(node, list)
                ):
                    raise ValueError("Cannot edit a footprint marked FBRK:notouch")
                old_layer = _sexp_groups(old).get("layer")
                new_layer = _sexp_groups(new).get("layer")
                if old_layer != new_layer:
                    if (
                        not old_layer
                        or not new_layer
                        or {old_layer[0][1], new_layer[0][1]} != {"F.Cu", "B.Cu"}
                    ):
                        unsupported("footprint board side")
                    _require_known_flip_fields(span, old)
                flipped = _placement_transform(old, new)
            else:
                flipped = False
            merge(span, old, new, kind, flipped)
        for key, new in new_map.items():
            if key not in old_map:
                from uuid import UUID as NativeUuid

                new_uuids = uuids(new)
                try:
                    if any(str(NativeUuid(value)) != value for value in new_uuids):
                        raise ValueError
                except ValueError as error:
                    raise ValueError(
                        "New KiCad copper objects require canonical UUIDs"
                    ) from error
                if len(new_uuids) != len(set(new_uuids)) or reserved_uuids.intersection(
                    new_uuids
                ):
                    raise ValueError(
                        "New KiCad copper objects require globally unique UUIDs"
                    )
                reserved_uuids.update(new_uuids)
                additions.append(encoded(new, kind))
    if additions:
        edits.append(
            (
                original.end - 1,
                original.end - 1,
                newline + newline.join(additions) + newline,
            )
        )
    ordered = sorted(edits, key=lambda edit: (edit[0], edit[1]))
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("Overlapping KiCad 10 source edits")
    patched = source
    for start, end, replacement in reversed(ordered):
        patched = patched[:start] + replacement + patched[end:]
    verified = _load_pcb_compatible(patched)
    if sexpdata.loads(kicad.pcb.dumps(verified)) != current:
        raise ValueError("KiCad 10 edit cannot preserve the requested model exactly")
    return patched


def _load_pcb_compatible(data: str) -> kicad.pcb.PcbFile:
    # Adapt only the recognized KiCad 10 PCB format. Older formats keep their
    # native parser, cache and editing behavior without a Python AST round trip.
    if not re.match(r"\A\s*\(kicad_pcb\s+\(version\s+20260206\s*\)", data):
        return kicad.pcb.loads(data)

    import sexpdata

    def tag(node):
        return str(node[0]) if isinstance(node, list) and node else ""

    def children(node, name):
        return [child for child in node if tag(child) == name]

    def field(node, name):
        found = children(node, name)
        if len(found) > 1:
            raise ValueError(f"Ambiguous KiCad 10 {name} field")
        return found[0] if found else None

    try:
        document = sexpdata.loads(data)
    except Exception as error:
        raise ValueError("Invalid KiCad 10 PCB syntax") from error
    if tag(document) != "kicad_pcb":
        raise ValueError("Expected a KiCad 10 PCB document")
    version = field(document, "version")
    if version != [sexpdata.Symbol("version"), 20260206]:
        raise ValueError("Expected the supported KiCad 10 PCB version")

    setup = field(document, "setup")
    if setup is not None:
        for name in ("tenting", "covering", "plugging"):
            setting = field(setup, name)
            if setting is None:
                continue
            if name == "tenting" and all(
                isinstance(value, sexpdata.Symbol) and str(value) in {"front", "back"}
                for value in setting[1:]
            ):
                continue
            sides: dict[str, bool] = {}
            for side in setting[1:]:
                if (
                    not isinstance(side, list)
                    or len(side) != 2
                    or str(side[0]) not in {"front", "back"}
                    or not isinstance(side[1], sexpdata.Symbol)
                    or str(side[1]) not in {"yes", "no"}
                    or str(side[0]) in sides
                ):
                    raise ValueError(f"Invalid KiCad 10 {name} side settings")
                sides[str(side[0])] = str(side[1]) == "yes"
            if name == "tenting":
                setting[:] = [sexpdata.Symbol("tenting")] + [
                    sexpdata.Symbol(side) for side, enabled in sides.items() if enabled
                ]
        for name in ("capping", "filling"):
            setting = field(setup, name)
            if setting is not None and (
                len(setting) != 2
                or not isinstance(setting[1], sexpdata.Symbol)
                or str(setting[1]) not in {"yes", "no"}
            ):
                raise ValueError(f"Invalid KiCad 10 {name} setting")

    # KiCad 10 names nets directly in pads, tracks, vias and zones; the pinned
    # renderer expects a numeric table and numeric references. This table exists
    # only in the viewer model. The complete source remains the serialization.
    references: list[tuple[list, str]] = []
    names: set[str] = set()

    def collect(node, parent=""):
        if not isinstance(node, list):
            return
        if tag(node) in {"pad", "segment", "arc", "via", "zone"}:
            field(node, "net")
        if tag(node) == "net":
            if (
                parent not in {"pad", "segment", "arc", "via", "zone"}
                or len(node) != 2
                or not isinstance(node[1], str)
            ):
                raise ValueError("Ambiguous or unsupported KiCad 10 net reference")
            name = str(node[1])
            if name:
                names.add(name)
            references.append((node, parent))
        for child in node:
            collect(child, tag(node))

    try:
        collect(document)
    except RecursionError as error:
        raise ValueError("KiCad 10 PCB nesting exceeds the parser limit") from error
    numbers = {name: index + 1 for index, name in enumerate(sorted(names))}
    for node, parent in references:
        name = str(node[1])
        number = numbers[name] if name else 0
        node[:] = [sexpdata.Symbol("net"), number]
        if parent == "pad":
            node.append(name)
    for zone in children(document, "zone"):
        net = field(zone, "net")
        number = net[1] if net is not None else 0
        if net is None:
            zone.append([sexpdata.Symbol("net"), 0])
        name = next((name for name, value in numbers.items() if value == number), "")
        if field(zone, "net_name") is not None:
            raise ValueError("Ambiguous KiCad 10 zone net_name field")
        zone.append([sexpdata.Symbol("net_name"), name])
    document.extend(
        [sexpdata.Symbol("net"), number, name] for name, number in numbers.items()
    )
    native = kicad.pcb.loads(sexpdata.dumps(document))
    out = _KiCad10Pcb(kicad_pcb=native.kicad_pcb)
    out._original_source = data
    out._typed_baseline = kicad.pcb.dumps(out)
    out._native_owner = native
    out._last_written = {}
    return out


_DUPLICATE_REF_TEXTS = ("${REFERENCE}", "%R")


def strip_duplicate_ref_texts(
    fp_texts: list[kicad.pcb.FpText],
) -> list[kicad.pcb.FpText]:
    """Remove fp_text entries that duplicate the Reference property.

    EasyEDA/JLCPCB footprints often include both a property "Reference"
    and an fp_text user "${REFERENCE}" or "%R", causing double designators.
    """
    return [t for t in fp_texts if t.text not in _DUPLICATE_REF_TEXTS]

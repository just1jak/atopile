"""Canonical schematic projection contracts, also generated for webviews."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from atopile.data_models import CamelModel

# Defaults are serialized by Python. Marking these fields optional in TypeScript
# also permits minimal read-only fixtures and older cached projection payloads.
_TS_OPTIONAL = {"ts_optional": True}


class SchematicPoint(CamelModel):
    model_config = ConfigDict(allow_inf_nan=False)

    x: float
    y: float


class SchematicBounds(SchematicPoint):
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class SchematicGraphicStyle(CamelModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    stroke_width: float = Field(default=0.254, ge=0, json_schema_extra=_TS_OPTIONAL)
    fill: Literal["none", "background", "outline"] = Field(
        default="none", json_schema_extra=_TS_OPTIONAL
    )


class SchematicLine(SchematicGraphicStyle):
    type: Literal["line"]
    x1: float
    y1: float
    x2: float
    y2: float


class SchematicPolyline(SchematicGraphicStyle):
    type: Literal["polyline"]
    points: list[SchematicPoint]
    closed: bool = Field(default=False, json_schema_extra=_TS_OPTIONAL)


class SchematicRectangle(SchematicGraphicStyle):
    type: Literal["rect"]
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class SchematicCircle(SchematicGraphicStyle):
    type: Literal["circle"]
    cx: float
    cy: float
    r: float = Field(ge=0)


class SchematicText(SchematicGraphicStyle):
    type: Literal["text"]
    x: float
    y: float
    text: str
    size: float = Field(default=1.27, gt=0, json_schema_extra=_TS_OPTIONAL)
    angle: float = Field(default=0, json_schema_extra=_TS_OPTIONAL)
    anchor: Literal["start", "middle", "end"] = Field(
        default="middle", json_schema_extra=_TS_OPTIONAL
    )


SchematicPrimitive = Annotated[
    SchematicLine
    | SchematicPolyline
    | SchematicRectangle
    | SchematicCircle
    | SchematicText,
    Field(discriminator="type"),
]


class SchematicPin(SchematicPoint):
    model_config = ConfigDict(extra="allow")

    number: str
    name: str
    end_x: float
    end_y: float
    hidden: bool = Field(default=False, json_schema_extra=_TS_OPTIONAL)
    electrical_type: str = Field(default="", json_schema_extra=_TS_OPTIONAL)
    shape: str = Field(default="line", json_schema_extra=_TS_OPTIONAL)
    rotation: float = Field(default=0, json_schema_extra=_TS_OPTIONAL)
    length: float = Field(default=0, ge=0, json_schema_extra=_TS_OPTIONAL)


class SchematicSymbol(CamelModel):
    model_config = ConfigDict(extra="allow")

    name: str
    primitives: list[SchematicPrimitive]
    pins: list[SchematicPin]
    bounds: SchematicBounds
    missing: bool
    lib_id: str = Field(default="", json_schema_extra=_TS_OPTIONAL)
    unit: int = Field(default=1, ge=1, json_schema_extra=_TS_OPTIONAL)
    available_units: list[int] = Field(
        default_factory=list, json_schema_extra=_TS_OPTIONAL
    )
    status: Literal["loaded", "partial", "missing"] = Field(
        default="loaded", json_schema_extra=_TS_OPTIONAL
    )
    warnings: list[str] = Field(default_factory=list, json_schema_extra=_TS_OPTIONAL)
    warning: str | None = Field(default=None, json_schema_extra=_TS_OPTIONAL)
    source_file: str | None = Field(default=None, json_schema_extra=_TS_OPTIONAL)


class SchematicSource(CamelModel):
    path: str
    line: int = Field(ge=1)


class SchematicTerminal(CamelModel):
    """A terminal whose net assignment comes from the existing PCB pad."""

    number: str
    name: str
    net: str | None


class SchematicComponent(CamelModel):
    id: str
    reference: str
    value: str
    ato_address: str
    source: SchematicSource | None
    symbol: SchematicSymbol
    pins: list[SchematicTerminal]


class SchematicNetMember(CamelModel):
    component_id: str
    reference: str
    pin: str


class SchematicNet(CamelModel):
    id: str
    name: str
    members: list[SchematicNetMember]


class SchematicData(CamelModel):
    version: Literal[1]
    project_root: str
    target: str
    layout_path: str
    revision: str
    connectivity_kind: Literal["logical_pad_net_assignments"]
    components: list[SchematicComponent]
    nets: list[SchematicNet]
    warnings: list[str]


class SchematicSelection(CamelModel):
    project_root: str
    target: str
    layout_path: str
    component_ids: list[str]
    pad_ids: list[str]
    net_name: str | None
    sequence: int = Field(default=0, ge=0, json_schema_extra=_TS_OPTIONAL)


class SchematicExportResult(CamelModel):
    """A saved native KiCad snapshot; reopening never overwrites user edits."""

    path: str
    relative_path: str
    project_root: str
    target: str
    revision: str
    layout_path: str
    component_count: int = Field(ge=0)
    net_count: int = Field(ge=0)
    warnings: list[str]
    reused: bool
    opened: bool = False
    open_error: str | None = None

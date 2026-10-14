// The wire contract is generated from the backend's Pydantic models.
export type {
  SchematicData, SchematicComponent, SchematicNet, SchematicSelection,
  SchematicPoint as Point, SchematicBounds as Bounds, SchematicPin as SymbolPin,
} from "../../protocol/generated-types";
import type { SchematicSymbol } from "../../protocol/generated-types";
export type SymbolPrimitive = SchematicSymbol["primitives"][number];

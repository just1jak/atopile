import type { SchematicSelection } from "../../panel-schematic/types";
import type { LayoutDecorations } from "./editor";

export function matchesSchematicSelection(selection: SchematicSelection | null, projectRoot: string | null | undefined,
  target: string | null | undefined, layoutPath: string | null | undefined): selection is SchematicSelection {
  return Boolean(selection && selection.projectRoot === projectRoot && selection.target === target && selection.layoutPath === layoutPath);
}

export function schematicSelectionDecorations(selection: SchematicSelection): LayoutDecorations {
  const color: [number, number, number, number] = [1, 0.42, 0.12, 1];
  return {
    // Footprint painter uses raw UUIDs; pad painter uses generated layout pad IDs.
    footprints: new Map(selection.componentIds.map((id) => [id, { color, highlightColor: color, highlighted: true }])),
    pads: new Map(selection.padIds.map((id) => [id, { color, highlightColor: color, outlined: true, highlighted: true }])),
  };
}

export function parseSchematicSelectionEvent(raw: string): SchematicSelection | null {
  try {
    const event: unknown = JSON.parse(raw);
    if (!event || typeof event !== "object") return null;
    const value = event as Record<string, unknown>;
    if (value.type !== "schematic_selection" || typeof value.projectRoot !== "string" || typeof value.target !== "string"
      || typeof value.layoutPath !== "string" || !Array.isArray(value.componentIds) || !Array.isArray(value.padIds)
      || !value.componentIds.every((id) => typeof id === "string") || !value.padIds.every((id) => typeof id === "string")
      || !(value.netName === null || typeof value.netName === "string")) return null;
    return value as unknown as SchematicSelection;
  } catch { return null; }
}

import { expect, test } from "bun:test";
import { matchesSchematicSelection, parseSchematicSelectionEvent, schematicSelectionDecorations } from "../../src/ui/webview/common/layout/schematicSelection";

const selection = { projectRoot: "/project", target: "default", layoutPath: "/project/main.kicad_pcb", componentIds: ["component-uuid"], padIds: ["fp:component-uuid:pad:1"], netName: "GND" };
test("schematic selection is scoped to the exact project, build, and board", () => {
  expect(matchesSchematicSelection(selection, "/project", "default", selection.layoutPath)).toBe(true);
  expect(matchesSchematicSelection(selection, "/other", "default", selection.layoutPath)).toBe(false);
  expect(matchesSchematicSelection(selection, "/project", "other", selection.layoutPath)).toBe(false);
  expect(matchesSchematicSelection(selection, "/project", "default", "/other/board.kicad_pcb")).toBe(false);
  expect(matchesSchematicSelection(null, "/project", "default", selection.layoutPath)).toBe(false);
});
test("PCB decoration keys match the actual footprint and pad painters", () => {
  const decorations = schematicSelectionDecorations(selection);
  expect(decorations.footprints?.get("component-uuid")?.highlighted).toBe(true);
  expect(decorations.pads?.get("fp:component-uuid:pad:1")?.highlighted).toBe(true);
  expect(decorations.footprints?.has("fp:component-uuid")).toBe(false);
});
test("accepts only well formed schematic selection messages", () => {
  expect(parseSchematicSelectionEvent(JSON.stringify({ type: "schematic_selection", ...selection }))).toEqual({ type: "schematic_selection", ...selection });
  expect(parseSchematicSelectionEvent("invalid")).toBeNull();
  expect(parseSchematicSelectionEvent(JSON.stringify({ type: "STATE", ...selection }))).toBeNull();
  expect(parseSchematicSelectionEvent(JSON.stringify({ type: "schematic_selection", ...selection, padIds: [42] }))).toBeNull();
});

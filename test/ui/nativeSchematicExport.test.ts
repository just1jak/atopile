import { describe, expect, test } from "bun:test";
import { initialNativeExportState, nativeExportReducer, requestNativeSchematic } from "../../src/ui/webview/panel-schematic/nativeExport";
import type { SchematicExportResult } from "../../src/ui/protocol/generated-types";

const result: SchematicExportResult = {
  path: "/circuit/schematics/default-001.kicad_sch", relativePath: "schematics/default-001.kicad_sch",
  projectRoot: "/circuit", target: "default", revision: "revision-1", layoutPath: "/circuit/default.kicad_pcb",
  componentCount: 3, netCount: 3, warnings: [], reused: false, opened: true, openError: null,
};

describe("native schematic export state", () => {
  test("starts only on explicit action and keeps pending/error/success distinct", () => {
    let state = initialNativeExportState("circuit-default");
    expect(state.status).toBe("idle"); expect(state.result).toBeNull();
    state = nativeExportReducer(state, { type: "start", contextKey: state.contextKey, requestId: 1 });
    expect(state.status).toBe("pending");
    state = nativeExportReducer(state, { type: "error", contextKey: state.contextKey, requestId: 1, error: "Build the selected target first" });
    expect(state.status).toBe("error"); expect(state.error).toBe("Build the selected target first");
    state = nativeExportReducer(state, { type: "start", contextKey: state.contextKey, requestId: 2 });
    expect(state.error).toBeNull();
    state = nativeExportReducer(state, { type: "success", contextKey: state.contextKey, requestId: 2, result });
    expect(state.status).toBe("success"); expect(state.result).toBe(result);
  });
  test("ignores a late response after the project or build changes", () => {
    let state = nativeExportReducer(initialNativeExportState("old"), { type: "start", contextKey: "old", requestId: 1 });
    state = nativeExportReducer(state, { type: "reset", contextKey: "new" });
    expect(nativeExportReducer(state, { type: "success", contextKey: "old", requestId: 1, result })).toBe(state);
    expect(nativeExportReducer(state, { type: "error", contextKey: "old", requestId: 1, error: "Old error" })).toBe(state);
  });
  test("newer attempts win and a saved file survives KiCad launch failure", () => {
    let state = nativeExportReducer(initialNativeExportState("board"), { type: "start", contextKey: "board", requestId: 2 });
    expect(nativeExportReducer(state, { type: "success", contextKey: "board", requestId: 1, result })).toBe(state);
    const saved = { ...result, opened: false, openError: "Install KiCad to open this file" };
    state = nativeExportReducer(state, { type: "success", contextKey: "board", requestId: 2, result: saved });
    expect(state.status).toBe("success"); expect(state.result?.path).toBe(result.path); expect(state.result?.openError).toBe(saved.openError);
  });
});

describe("native schematic request", () => {
  test("opens through the native action without forcing a replacement", async () => {
    const calls: { action: string; args: Record<string, unknown> }[] = [];
    const client = { async requestAction<T>(action: string, args: Record<string, unknown>) { calls.push({ action, args }); return result as T; } };
    expect(await requestNativeSchematic(client, "/circuit", "default")).toBe(result);
    expect(calls).toEqual([{ action: "exportSchematic", args: { projectRoot: "/circuit", target: "default", openInKicad: true } }]);
    await requestNativeSchematic(client, "/circuit", "default", true);
    expect(calls[1]?.args).toEqual({ projectRoot: "/circuit", target: "default", openInKicad: true, forceNew: true });
  });
  test("rejects results belonging to another project or target", async () => {
    const client = { async requestAction<T>() { return { ...result, target: "other" } as T; } };
    await expect(requestNativeSchematic(client, "/circuit", "default")).rejects.toThrow("different project or build target");
  });
  test("preserves backend errors for the visible stop state", async () => {
    const client = { async requestAction<T>(): Promise<T> { throw new Error("KiCad symbol is unavailable"); } };
    await expect(requestNativeSchematic(client, "/circuit", "default")).rejects.toThrow("KiCad symbol is unavailable");
  });
  test("a nonresponsive export has a bounded, actionable timeout", async () => {
    const client = { requestAction<T>(): Promise<T> { return new Promise(() => {}); } };
    await expect(requestNativeSchematic(client, "/circuit", "default", false, 1)).rejects.toThrow("timed out");
  });
});

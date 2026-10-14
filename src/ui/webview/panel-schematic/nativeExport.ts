import type { SchematicExportResult } from "../../protocol/generated-types";
import { samePath } from "../../protocol/paths";

export interface NativeExportState {
  contextKey: string;
  requestId: number;
  status: "idle" | "pending" | "success" | "error";
  result: SchematicExportResult | null;
  error: string | null;
}
export type NativeExportEvent =
  | { type: "reset"; contextKey: string }
  | { type: "start"; contextKey: string; requestId: number }
  | { type: "success"; contextKey: string; requestId: number; result: SchematicExportResult }
  | { type: "error"; contextKey: string; requestId: number; error: string };

export const initialNativeExportState = (contextKey: string): NativeExportState => ({
  contextKey, requestId: 0, status: "idle", result: null, error: null,
});

/** A response for a previous project, build, or attempt cannot replace the visible result. */
export function nativeExportReducer(state: NativeExportState, event: NativeExportEvent): NativeExportState {
  if (event.type === "reset") return initialNativeExportState(event.contextKey);
  if (event.type === "start") return {
    ...(state.contextKey === event.contextKey ? state : initialNativeExportState(event.contextKey)),
    requestId: event.requestId, status: "pending", error: null,
  };
  if (event.contextKey !== state.contextKey || event.requestId !== state.requestId) return state;
  if (event.type === "success") return { ...state, status: "success", result: event.result, error: null };
  return { ...state, status: "error", error: event.error };
}

export async function requestNativeSchematic(
  client: { requestAction<T>(action: string, args: Record<string, unknown>): Promise<T> },
  projectRoot: string, target: string, forceNew = false, timeoutMs = 75_000,
): Promise<SchematicExportResult> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const result = await Promise.race([
      client.requestAction<SchematicExportResult>("exportSchematic", {
        projectRoot, target, openInKicad: true, ...(forceNew ? { forceNew: true } : {}),
      }),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("Preparing the KiCad schematic timed out. Check KiCad, then try opening the saved snapshot again.")), timeoutMs);
      }),
    ]);
    if (!samePath(result.projectRoot, projectRoot) || result.target !== target) {
      throw new Error("The returned schematic belongs to a different project or build target.");
    }
    return result;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

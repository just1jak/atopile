import { createDiagram } from "./geometry";
import type { SchematicData } from "./types";

// Build as one standalone script: a VS Code webview loads workers through a Blob URL.
globalThis.onmessage = (event: MessageEvent<SchematicData>) => {
  try { globalThis.postMessage({ diagram: createDiagram(event.data) }); }
  catch (reason) { globalThis.postMessage({ error: reason instanceof Error ? reason.message : String(reason) }); }
};

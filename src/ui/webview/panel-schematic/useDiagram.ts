import { useEffect, useState } from "react";
import type { Diagram } from "./geometry";
import type { SchematicData } from "./types";

declare global { interface Window { __ATOPILE_SCHEMATIC_WORKER_URL__?: string } }

/** Cancel superseded routing work when a new build or target is selected. */
export function useDiagram(data: SchematicData, supplied?: Diagram, retryKey = 0): { diagram?: Diagram; error?: string } {
  const [state, setState] = useState<{ data: SchematicData; diagram?: Diagram; error?: string }>({ data });
  useEffect(() => {
    if (supplied) return;
    const controller = new AbortController();
    let worker: Worker | undefined, objectUrl: string | undefined, alive = true;
    setState({ data });
    void (async () => {
      try {
        const workerUrl = window.__ATOPILE_SCHEMATIC_WORKER_URL__;
        if (!workerUrl) throw new Error("Schematic worker asset is unavailable. Rebuild or reinstall the extension.");
        const response = await fetch(workerUrl, { signal: controller.signal });
        if (!response.ok) throw new Error(`Could not load schematic layout worker (${response.status}).`);
        const source = await response.blob();
        if (!alive) return;
        objectUrl = URL.createObjectURL(source); worker = new Worker(objectUrl);
        worker.onmessage = (event: MessageEvent<{ diagram?: Diagram; error?: string }>) => {
          if (!alive) return;
          setState({ data, ...event.data }); worker?.terminate();
          if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = undefined; }
        };
        worker.onerror = (event) => { if (alive) setState({ data, error: event.message || "Could not calculate schematic wiring." }); };
        worker.postMessage(data);
      } catch (reason) {
        if (alive) setState({ data, error: reason instanceof Error ? reason.message : String(reason) });
      }
    })();
    return () => {
      alive = false; controller.abort(); worker?.terminate();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [data, supplied, retryKey]);
  return supplied ? { diagram: supplied } : state.data === data ? state : {};
}

import { useCallback, useEffect, useRef, useState } from "react";
import { CircuitBoard, RefreshCw } from "lucide-react";
import { WebviewRpcClient, rpcClient } from "../common/webviewRpcClient";
import { SchematicView, type SchematicActions } from "./SchematicView";
import { Button } from "../common/components/Button";
import type { SchematicData } from "./types";

export function SchematicPreview() {
  const project = WebviewRpcClient.useSubscribe("projectState");
  const layout = WebviewRpcClient.useSubscribe("layoutData");
  const building = WebviewRpcClient.useSubscribe("selectedBuildInProgress");
  const connected = WebviewRpcClient.useSubscribe("connected");
  const [data, setData] = useState<SchematicData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const serial = useRef(0);
  const projectRoot = project.selectedProjectRoot;
  const target = project.selectedTarget?.name;
  const selectionKey = `${projectRoot ?? ""}\0${target ?? ""}`;
  const lastSelection = useRef(selectionKey);
  useEffect(() => {
    const request = ++serial.current;
    if (lastSelection.current !== selectionKey) { setData(null); setError(null); lastSelection.current = selectionKey; }
    if (!projectRoot || !target || !connected) { setLoading(false); return; }
    if (building) { setLoading(false); return; }
    setLoading(true);
    const timer = setTimeout(() => {
      void rpcClient!.requestAction<SchematicData>("getSchematicData", { projectRoot, target }).then((result) => {
        if (serial.current !== request) return;
        setData((current) => current?.revision === result.revision && current.projectRoot === result.projectRoot && current.target === result.target ? current : result); setError(null);
      }).catch((reason: unknown) => {
        if (serial.current === request) setError(reason instanceof Error ? reason.message : String(reason));
      }).finally(() => { if (serial.current === request) setLoading(false); });
    }, 150);
    return () => { clearTimeout(timer); serial.current++; };
  }, [selectionKey, layout.path, layout.revision, building, connected, refresh]);
  const action = useCallback(async (name: string, args: Record<string, unknown>, openPcb = false) => {
    if (!rpcClient || !projectRoot || !target) throw new Error("Select a project and build target first.");
    await rpcClient.requestAction(name, { projectRoot, target, ...args });
    if (openPcb) {
      await rpcClient.requestAction("syncSelectedLayout");
      await rpcClient.requestAction("vscode.openPanel", { panelId: "panel-layout" });
    }
  }, [projectRoot, target]);
  const actions: SchematicActions = {
    openSource: (componentId) => action("schematicOpenSource", { componentId }),
    showComponentOnPcb: (componentId) => action("schematicSelectComponent", { componentId }, true),
    showNetOnPcb: (netName) => action("schematicSelectNet", { netName }, true),
  };
  const toolbar = <Button variant="outline" size="sm" title="Refresh schematic from the current build" aria-label="Refresh schematic" disabled={loading} onClick={() => setRefresh((value) => value + 1)}><RefreshCw size={15} /></Button>;
  if (data && data.projectRoot === projectRoot && data.target === target && connected && data.components.length > 0 && !error) return <SchematicView key={selectionKey} data={data} actions={actions} refreshing={loading || building} toolbar={toolbar} retryKey={refresh} />;
  const message = !projectRoot || !target ? "Select a project and build target to view its schematic."
    : !connected ? "Connecting to Atopile Local…"
    : error ? error
    : loading || building ? "Reading compiled symbols and connections…"
    : "Build this target to see its electrical schematic. The current build has no components to display.";
  return <div className="schematic-empty"><CircuitBoard size={32} /><h2>Schematic</h2><p role={error ? "alert" : "status"}>{message}</p>
    {error && <p>Build the selected target, then refresh to load its symbols and nets.</p>}
    {projectRoot && target && connected && toolbar}
  </div>;
}

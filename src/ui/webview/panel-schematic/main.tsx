import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { render } from "../common/render";
import { WebviewRpcClient, rpcClient } from "../common/webviewRpcClient";
import { Button } from "../common/components/Button";
import { NativeSchematicPanel } from "./NativeSchematicPanel";
import { SchematicPreview } from "./SchematicPreview";
import { initialNativeExportState, nativeExportReducer, requestNativeSchematic } from "./nativeExport";

function App() {
  const project = WebviewRpcClient.useSubscribe("projectState");
  const layout = WebviewRpcClient.useSubscribe("layoutData");
  const building = WebviewRpcClient.useSubscribe("selectedBuildInProgress");
  const connected = WebviewRpcClient.useSubscribe("connected");
  const projectRoot = project.selectedProjectRoot;
  const target = project.selectedTarget?.name ?? null;
  const selectionKey = `${projectRoot ?? ""}\0${target ?? ""}`;
  const contextKey = `${selectionKey}\0${layout.path ?? ""}\0${layout.revision}`;
  const [state, dispatch] = useReducer(nativeExportReducer, contextKey, initialNativeExportState);
  const [preview, setPreview] = useState(false);
  const requestId = useRef(0);
  const activeContext = useRef(contextKey);
  activeContext.current = contextKey;

  useEffect(() => {
    requestId.current++;
    dispatch({ type: "reset", contextKey });
    return () => { requestId.current++; };
  }, [contextKey]);
  useEffect(() => { setPreview(false); }, [selectionKey]);

  const openSchematic = useCallback(async (forceNew = false) => {
    const client = rpcClient;
    if (!client || !projectRoot || !target || !connected || building || state.status === "pending") return;
    const id = ++requestId.current;
    dispatch({ type: "start", contextKey, requestId: id });
    try {
      const result = await requestNativeSchematic(client, projectRoot, target, forceNew);
      if (requestId.current !== id || activeContext.current !== contextKey) return;
      dispatch({ type: "success", contextKey, requestId: id, result });
    } catch (reason) {
      if (requestId.current !== id || activeContext.current !== contextKey) return;
      dispatch({ type: "error", contextKey, requestId: id, error: reason instanceof Error ? reason.message : String(reason) });
    }
  }, [projectRoot, target, connected, building, state.status, contextKey]);

  if (preview) return <div className="schematic-preview-page">
    <div className="schematic-preview-back"><Button variant="ghost" size="sm" onClick={() => setPreview(false)}><ArrowLeft size={14} />Back to KiCad schematic</Button></div>
    <div className="schematic-preview-host"><SchematicPreview /></div>
  </div>;
  return <NativeSchematicPanel projectRoot={projectRoot} target={target} connected={connected} building={building}
    state={state.contextKey === contextKey ? state : initialNativeExportState(contextKey)}
    onOpen={() => void openSchematic()} onNewSnapshot={() => void openSchematic(true)} onPreview={() => setPreview(true)} />;
}

render(App);

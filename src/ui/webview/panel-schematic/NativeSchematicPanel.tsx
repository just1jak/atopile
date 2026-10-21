import { CircuitBoard, ExternalLink, FilePlus2, Loader2, Eye } from "lucide-react";
import { Button } from "../common/components/Button";
import { Alert, AlertDescription, AlertTitle } from "../common/components/Alert";
import { basename } from "../../protocol/paths";
import type { NativeExportState } from "./nativeExport";
import "./native.css";

export function NativeSchematicPanel({ projectRoot, target, connected, building, state, onOpen, onNewSnapshot, onPreview }: {
  projectRoot: string | null; target: string | null; connected: boolean; building: boolean;
  state: NativeExportState; onOpen(): void; onNewSnapshot(): void; onPreview(): void;
}) {
  const selected = Boolean(projectRoot && target);
  const pending = state.status === "pending";
  const disabled = !selected || !connected || building || pending;
  const result = state.result;
  return <div className="native-schematic-page">
    <header className="native-schematic-header"><CircuitBoard size={18} /><strong>Schematic</strong><span>KiCad</span></header>
    <main className="native-schematic-content">
      <section className="native-schematic-card" aria-labelledby="native-schematic-title" aria-busy={pending}>
        <div className="native-schematic-icon"><CircuitBoard size={28} /></div>
        <h1 id="native-schematic-title">Edit your schematic in KiCad</h1>
        <p className="native-schematic-intro">Open this circuit’s saved native <code>.kicad_sch</code> schematic, or generate a snapshot from the selected build. Requires KiCad installed on this computer.</p>
        {selected && <dl className="native-schematic-context"><div><dt>Project</dt><dd title={projectRoot ?? undefined}>{basename(projectRoot!)}</dd></div><div><dt>Build target</dt><dd>{target}</dd></div></dl>}
        {!selected && <p className="native-schematic-notice" role="status">Select a project and build target to open its schematic.</p>}
        {selected && !connected && <p className="native-schematic-notice" role="status">Connecting to Atopile Local…</p>}
        {selected && connected && building && <p className="native-schematic-notice" role="status">A build is in progress. Open its schematic when the build finishes.</p>}
        {state.error && <Alert variant="destructive"><AlertTitle>Couldn’t open the schematic</AlertTitle><AlertDescription>{state.error}</AlertDescription></Alert>}
        {result && <div className="native-schematic-result" role="status">
          <strong>{result.opened ? "Schematic opened in KiCad" : "Schematic saved"}</strong>
          <code title={result.path}>{result.relativePath}</code>
          <span>{result.componentCount} components · {result.netCount} nets · {result.reused ? "Saved schematic preserved" : "New snapshot created"}</span>
        </div>}
        {result?.openError && <Alert variant="warning"><AlertTitle>The file is saved, but KiCad did not open</AlertTitle><AlertDescription>{result.openError}</AlertDescription></Alert>}
        <div className="native-schematic-actions">
          <Button onClick={onOpen} disabled={disabled} size="lg">
            {pending ? <Loader2 className="native-schematic-spinner" size={16} /> : <ExternalLink size={16} />}
            {pending ? "Preparing KiCad schematic…" : "Open in KiCad"}
          </Button>
          {result && <Button variant="outline" onClick={onNewSnapshot} disabled={disabled} size="sm"><FilePlus2 size={15} />Generate new from circuit</Button>}
        </div>
        <p className="native-schematic-preservation">Open in KiCad uses the configured native schematic. Projects without one use a generated snapshot. Generate new from circuit creates a separate snapshot. Existing files are never overwritten.</p>
        {result && result.warnings.length > 0 && <details className="native-schematic-warnings"><summary>{result.warnings.length} {result.warnings.length === 1 ? "note" : "notes"}</summary><ul>{result.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details>}
      </section>
      <section className="native-schematic-editing" aria-labelledby="native-schematic-editing-title">
        <h2 id="native-schematic-editing-title">Your KiCad file stays editable</h2>
        <p>Arrange symbols and edit the schematic in KiCad, then save that file. Those edits stay in the saved <code>.kicad_sch</code>; they do not update the circuit’s <code>.ato</code> source.</p>
        <p className="native-schematic-keep-copy">If the opened file is under <code>build/</code>, use KiCad’s Save As to keep a copy elsewhere before cleaning build artifacts.</p>
      </section>
      <div className="native-schematic-preview-link"><Button variant="ghost" size="sm" disabled={!selected || !connected || pending} onClick={onPreview}><Eye size={15} />Preview connections in this panel</Button><p>Optional, read-only view of the compiled symbols and nets.</p></div>
    </main>
  </div>;
}

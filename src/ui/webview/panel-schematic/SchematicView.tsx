import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { CircuitBoard, Code2, Crosshair, Search, X, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "../common/components/Button";
import { Input } from "../common/components/Input";
import { svgPath, type Diagram, type PlacedComponent } from "./geometry";
import { useDiagram } from "./useDiagram";
import type { Bounds, Point, SchematicData, SymbolPrimitive } from "./types";
import "./main.css";

export interface SchematicActions {
  openSource(componentId: string): Promise<void>;
  showComponentOnPcb(componentId: string): Promise<void>;
  showNetOnPcb(netName: string): Promise<void>;
}

function Graphic({ graphic }: { graphic: SymbolPrimitive }) {
  const style = { strokeWidth: graphic.strokeWidth || 0.2,
    fill: graphic.fill === "background" ? "var(--schematic-paper)" : graphic.fill === "outline" ? "currentColor" : "none" };
  switch (graphic.type) {
    case "line": return <line {...style} x1={graphic.x1} y1={graphic.y1} x2={graphic.x2} y2={graphic.y2} />;
    case "rect": return <rect {...style} x={graphic.x} y={graphic.y} width={graphic.width} height={graphic.height} />;
    case "circle": return <circle {...style} cx={graphic.cx} cy={graphic.cy} r={graphic.r} />;
    case "polyline": return graphic.closed
      ? <polygon {...style} points={graphic.points.map((p) => `${p.x},${p.y}`).join(" ")} />
      : <polyline {...style} points={graphic.points.map((p) => `${p.x},${p.y}`).join(" ")} />;
    case "text": return <text x={graphic.x} y={graphic.y} fill="currentColor" stroke="none"
      fontSize={graphic.size || 1.27} textAnchor={graphic.anchor || "middle"} dominantBaseline="middle"
      transform={graphic.angle ? `rotate(${graphic.angle} ${graphic.x} ${graphic.y})` : undefined}>{graphic.text}</text>;
  }
}

function Symbol({ placed, selected, connected, onSelect }: {
  placed: PlacedComponent; selected: boolean; connected: boolean; onSelect(): void;
}) {
  const { component, x, y, bounds, annotation } = placed;
  return <g className={`schematic-component${selected ? " selected" : ""}${connected ? " connected" : ""}`}
    role="button" tabIndex={0} aria-label={`${component.reference} ${component.value}`}
    onClick={(event) => { event.stopPropagation(); onSelect(); }}
    onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(); } }}>
    <title>{`${component.reference} — ${component.value}\n${component.symbol.name}${component.source ? `\n${component.source.path}:${component.source.line}` : ""}`}</title>
    <rect className="schematic-component-hit" x={bounds.x - 1.8} y={bounds.y - 1} width={bounds.width + 3.6} height={bounds.height + 2} rx={0.8} />
    <g className="schematic-symbol" transform={`translate(${x} ${y})`}>
      {component.symbol.primitives.map((graphic, i) => <Graphic key={i} graphic={graphic} />)}
      {component.symbol.missing && <g className="schematic-missing">
        <text x={component.symbol.bounds.x + component.symbol.bounds.width / 2} y={0} fontSize={2} textAnchor="middle">Symbol unavailable</text>
      </g>}
    </g>
    <text className="schematic-reference" x={annotation.x} y={annotation.y} textAnchor={annotation.anchor}>{component.reference}</text>
    <text className="schematic-value" x={annotation.x} y={annotation.y + 2.7} textAnchor={annotation.anchor}>{component.value}</text>
  </g>;
}

export function SchematicView({ data, actions, refreshing = false, toolbar, diagram: supplied, retryKey = 0 }: {
  data: SchematicData; actions: SchematicActions; refreshing?: boolean; toolbar?: ReactNode; diagram?: Diagram; retryKey?: number;
}) {
  const { diagram, error } = useDiagram(data, supplied, retryKey);
  if (!diagram) return <div className="schematic-empty"><CircuitBoard size={32} /><h2>Schematic</h2>
    <p role={error ? "alert" : "status"}>{error ?? "Arranging symbols and connections…"}</p>
    {error && <p>Refresh the schematic to try again.</p>}{toolbar}</div>;
  return <SchematicDrawing data={data} actions={actions} refreshing={refreshing} toolbar={toolbar} diagram={diagram} />;
}

function SchematicDrawing({ data, actions, refreshing, toolbar, diagram }: {
  data: SchematicData; actions: SchematicActions; refreshing: boolean; toolbar?: ReactNode; diagram: Diagram;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const [view, setView] = useState<Bounds>(diagram.bounds);
  const [selectedNet, setSelectedNet] = useState<string | null>(null);
  const [selectedComponent, setSelectedComponent] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const drag = useRef<{ id: number; x: number; y: number; view: Bounds; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const panFrame = useRef<number | null>(null);
  const nextPan = useRef<Bounds | null>(null);
  useEffect(() => () => { if (panFrame.current !== null) cancelAnimationFrame(panFrame.current); }, []);
  useEffect(() => {
    setView(diagram.bounds); setSelectedNet(null); setSelectedComponent(null); setActionError(null);
  }, [data.projectRoot, data.target]);
  // Drop selections that no longer exist in the refreshed compiled data.
  useEffect(() => {
    if (selectedComponent && !data.components.some((component) => component.id === selectedComponent)) setSelectedComponent(null);
    if (selectedNet && !data.nets.some((net) => net.name === selectedNet)) setSelectedNet(null);
  }, [data, selectedComponent, selectedNet]);
  const component = data.components.find((c) => c.id === selectedComponent);
  const net = data.nets.find((n) => n.name === selectedNet);
  const connectedComponents = useMemo(() => new Set(net?.members.map((member) => member.componentId) ?? []), [net]);
  const componentNets = useMemo(() => new Set(component?.pins.map((pin) => pin.net).filter(Boolean) ?? []), [component]);
  const filteredNets = data.nets.filter((n) => `${n.name} ${n.members.map((m) => `${m.reference}.${m.pin}`).join(" ")}`.toLowerCase().includes(search.toLowerCase()));
  const warnings = useMemo(() => [...data.warnings, ...diagram.warnings], [data.warnings, diagram.warnings]);
  const zoom = useCallback((factor: number, anchor?: Point) => {
    setView((current) => {
      const origin = anchor ?? { x: current.x + current.width / 2, y: current.y + current.height / 2 };
      const width = Math.max(diagram.bounds.width / 16, Math.min(diagram.bounds.width * 4, current.width * factor));
      const ratio = width / current.width;
      return { x: origin.x - (origin.x - current.x) * ratio, y: origin.y - (origin.y - current.y) * ratio, width, height: current.height * ratio };
    });
  }, [diagram.bounds.width]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setActionError(null);
    try { await action(); } catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };
  const selectNet = (name: string) => { setSelectedNet(name); setSelectedComponent(null); };
  const selectComponent = (id: string) => { setSelectedComponent(id); setSelectedNet(null); };
  const worldPoint = (clientX: number, clientY: number) => {
    const element = svg.current; const matrix = element?.getScreenCTM();
    if (!element || !matrix) return null;
    const point = element.createSVGPoint(); point.x = clientX; point.y = clientY;
    return point.matrixTransform(matrix.inverse());
  };
  useEffect(() => {
    const element = svg.current; if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      zoom(Math.exp(Math.max(-0.35, Math.min(0.35, event.deltaY * 0.0015))), worldPoint(event.clientX, event.clientY) ?? undefined);
    };
    // React's wheel listener is passive; use an explicit listener to prevent page scrolling.
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [zoom]);
  const pointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0 || (event.target as Element).closest("[role=button]")) return;
    const point = worldPoint(event.clientX, event.clientY); if (!point) return;
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, view, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const start = drag.current; if (!start || start.id !== event.pointerId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (Math.abs(event.clientX - start.x) + Math.abs(event.clientY - start.y) > 4) start.moved = true;
    // preserveAspectRatio=meet uses the smaller axis scale and can letterbox.
    const scale = Math.max(start.view.width / rect.width, start.view.height / rect.height);
    nextPan.current = { ...start.view, x: start.view.x - (event.clientX - start.x) * scale, y: start.view.y - (event.clientY - start.y) * scale };
    if (panFrame.current === null) panFrame.current = requestAnimationFrame(() => {
      if (nextPan.current) setView(nextPan.current);
      panFrame.current = null;
    });
  };
  return <div className="schematic-app">
    <header className="schematic-toolbar">
      <div className="schematic-title"><CircuitBoard size={18} /><strong>Schematic</strong><span>{data.target}</span></div>
      <div className="schematic-tools">
        {refreshing && <span className="schematic-updating">Updating…</span>}{toolbar}
        <Button variant="outline" size="sm" onClick={() => zoom(1.25)} title="Zoom out" aria-label="Zoom out"><ZoomOut size={16} /></Button>
        <Button variant="outline" size="sm" onClick={() => zoom(0.8)} title="Zoom in" aria-label="Zoom in"><ZoomIn size={16} /></Button>
        <Button variant="outline" size="sm" onClick={() => setView(diagram.bounds)} title="Fit schematic" aria-label="Fit schematic"><Crosshair size={16} /><span>Fit</span></Button>
      </div>
    </header>
    <div className="schematic-workspace">
      <section className="schematic-sheet" aria-label="Schematic canvas">
        <svg ref={svg} viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`} aria-label="Electrical schematic"
          onPointerDown={pointerDown} onPointerMove={pointerMove}
          onPointerUp={(event) => { suppressClick.current = drag.current?.moved ?? false; drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
          onPointerCancel={() => { drag.current = null; }}
          onClick={() => { if (!suppressClick.current) { setSelectedNet(null); setSelectedComponent(null); } suppressClick.current = false; }}>
          <g className={`schematic-wires${selectedNet || selectedComponent ? " has-selection" : ""}`}>
            {diagram.nets.map((drawing) => <g key={drawing.id} className={`schematic-net${drawing.name === selectedNet || componentNets.has(drawing.name) ? " active" : ""}`}
              role="button" tabIndex={0} aria-label={`Net ${drawing.name}`}
              onClick={(event) => { event.stopPropagation(); selectNet(drawing.name); }}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectNet(drawing.name); } }}>
              <title>{drawing.name}</title>
              {drawing.paths.map((path, i) => <g key={i}><path className="schematic-wire-hit" d={svgPath(path)} /><path className="schematic-wire" d={svgPath(path)} /></g>)}
              {drawing.junctions.map((p, i) => <circle className="schematic-junction" key={i} cx={p.x} cy={p.y} r={0.5} />)}
              {(drawing.incomplete ? diagram.pins.filter((p) => p.net === drawing.name).map((p) => p.escape) : [drawing.label]).map((p, i) =>
                <text className="schematic-net-label" key={i} x={p.x + 1} y={p.y - 0.9}>{drawing.name}</text>)}
            </g>)}
          </g>
          {diagram.components.map((placed) => <Symbol key={placed.component.id} placed={placed}
            selected={placed.component.id === selectedComponent} connected={connectedComponents.has(placed.component.id)} onSelect={() => selectComponent(placed.component.id)} />)}
          <g className="schematic-pins">{diagram.pins.map((pin, i) => <circle key={i} cx={pin.x} cy={pin.y}
            r={0.5} className={`${pin.net ? "connected" : "unconnected"}${pin.net === selectedNet ? " active" : ""}`}
            role="button" tabIndex={0} aria-label={`${data.components.find((c) => c.id === pin.componentId)?.reference}.${pin.number} ${pin.net ?? "unconnected"}`}
            onClick={(event) => { event.stopPropagation(); pin.net ? selectNet(pin.net) : selectComponent(pin.componentId); }}
            onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); pin.net ? selectNet(pin.net) : selectComponent(pin.componentId); } }}>
            <title>{`${pin.number} ${pin.name}: ${pin.net ?? "unconnected"}`}</title>
          </circle>)}</g>
        </svg>
        <div className="schematic-sheet-note">Compiled connections · drag to pan · scroll to zoom</div>
      </section>
      <aside className="schematic-sidebar" aria-label="Schematic inspector">
        {(component || net) && <section className="schematic-inspector">
          <div className="schematic-section-title"><strong>{component?.reference ?? "Selected net"}</strong><button aria-label="Clear selection" onClick={() => { setSelectedNet(null); setSelectedComponent(null); }}><X size={14} /></button></div>
          {component ? <>
            <p className="schematic-selected-value">{component.value}</p><p className="schematic-symbol-name">{component.symbol.name}</p>
            <div className="schematic-selection-actions">
              <Button variant="outline" size="sm" disabled={busy || !component.source} title={component.source ? `${component.source.path}:${component.source.line}` : "No circuit source location was found"} onClick={() => void run(() => actions.openSource(component.id))}><Code2 size={14} />Code</Button>
              <Button variant="outline" size="sm" disabled={busy} onClick={() => void run(() => actions.showComponentOnPcb(component.id))}><CircuitBoard size={14} />PCB</Button>
            </div>
            <dl className="schematic-pin-list">{component.pins.map((pin, i) => <div key={i}><dt>{pin.number} {pin.name}</dt><dd>{pin.net ? <button onClick={() => selectNet(pin.net!)}>{pin.net}</button> : <span>Unconnected</span>}</dd></div>)}</dl>
          </> : net && <>
            <p className="schematic-selected-value">{net.name}</p>
            <div className="schematic-selection-actions"><Button variant="outline" size="sm" disabled={busy} onClick={() => void run(() => actions.showNetOnPcb(net.name))}><CircuitBoard size={14} />Show net on PCB</Button></div>
            <div className="schematic-member-list">{net.members.map((member, i) => <button key={i} onClick={() => selectComponent(member.componentId)}><span>{member.reference}</span><span>pin {member.pin}</span></button>)}</div>
          </>}
        </section>}
        {actionError && <p role="alert" className="schematic-action-error">{actionError}</p>}
        <div className="schematic-net-heading"><strong>Nets</strong><span>{data.nets.length}</span></div>
        <label className="schematic-search"><Search size={14} /><Input aria-label="Search nets or pins" placeholder="Search nets or pins" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <div className="schematic-net-list">{filteredNets.length ? filteredNets.map((n) => <button key={n.id} className={n.name === selectedNet ? "selected" : ""} onClick={() => selectNet(n.name)}><span>{n.name}</span><small>{n.members.length} pins</small></button>) : <p>No matching nets.</p>}</div>
        <details className="schematic-components"><summary>Components · {data.components.length}</summary>{data.components.map((c) => <button key={c.id} onClick={() => selectComponent(c.id)}><span>{c.reference}</span><span>{c.value}</span></button>)}</details>
      </aside>
    </div>
    {warnings.length > 0 && <details className="schematic-warnings"><summary>{warnings.length} schematic {warnings.length === 1 ? "note" : "notes"}</summary><ul>{warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details>}
    <footer className="schematic-footer"><span>{data.components.length} components · {data.nets.length} nets</span><span>Read-only · automatic symbol placement</span></footer>
  </div>;
}

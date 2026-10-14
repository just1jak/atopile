import type { Bounds, Point, SchematicComponent, SchematicData, SymbolPin } from "./types";

export interface PlacedComponent { component: SchematicComponent; x: number; y: number; bounds: Bounds;
  annotation: { x: number; y: number; anchor: "start" | "middle" } }
export interface PlacedPin extends Point { componentId: string; number: string; name: string; net: string | null; escape: Point }
export interface NetDrawing { id: string; name: string; paths: Point[][]; junctions: Point[]; label: Point; incomplete: boolean }
export interface Diagram { components: PlacedComponent[]; pins: PlacedPin[]; nets: NetDrawing[]; bounds: Bounds; warnings: string[] }
const round = (n: number) => Math.round(n * 10000) / 10000;
const key = (p: Point) => `${round(p.x)},${round(p.y)}`;
const edgeKey = (a: Point, b: Point) => [key(a), key(b)].sort().join("|");
const distance = (a: Point, b: Point) => Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
export const WIRE_CLEARANCE = 1;
const inflate = (b: Bounds, by: number): Bounds => ({ x: b.x - by, y: b.y - by, width: b.width + by * 2, height: b.height + by * 2 });

/** Open rectangle interiors are obstacles; their exterior routing lanes stay usable. */
export function segmentHitsBounds(a: Point, b: Point, box: Bounds): boolean {
  const eps = 0.00001;
  if (a.x === b.x) return a.x > box.x + eps && a.x < box.x + box.width - eps
    && Math.max(a.y, b.y) > box.y + eps && Math.min(a.y, b.y) < box.y + box.height - eps;
  if (a.y === b.y) return a.y > box.y + eps && a.y < box.y + box.height - eps
    && Math.max(a.x, b.x) > box.x + eps && Math.min(a.x, b.x) < box.x + box.width - eps;
  return true;
}

/** Near-parallel wires merge visually even when their floating point coordinates differ. */
export function parallelWireConflict(a: Point, b: Point, c: Point, d: Point, clearance = WIRE_CLEARANCE): boolean {
  if (a.y === b.y && c.y === d.y) return Math.abs(a.y - c.y) < clearance - 0.00001
    && Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x)) - Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x)) > -clearance;
  if (a.x === b.x && c.x === d.x) return Math.abs(a.x - c.x) < clearance - 0.00001
    && Math.min(Math.max(a.y, b.y), Math.max(c.y, d.y)) - Math.max(Math.min(a.y, b.y), Math.min(c.y, d.y)) > -clearance;
  return false;
}

function pointSegmentDistance(p: Point, a: Point, b: Point): number {
  return Math.hypot(p.x - Math.max(Math.min(a.x, b.x), Math.min(Math.max(a.x, b.x), p.x)),
    p.y - Math.max(Math.min(a.y, b.y), Math.min(Math.max(a.y, b.y), p.y)));
}

function safeBounds(b: Bounds): Bounds {
  if (![b.x, b.y, b.width, b.height].every(Number.isFinite) || b.width < 0 || b.height < 0) {
    return { x: -5, y: -5, width: 10, height: 10 };
  }
  return { ...b, width: Math.max(b.width, 3), height: Math.max(b.height, 3) };
}

function escapePin(pin: SymbolPin, placed: PlacedComponent): Point {
  const x = round(pin.x + placed.x), y = round(pin.y + placed.y);
  const dx = pin.x - pin.endX, dy = pin.y - pin.endY;
  const b = inflate(placed.bounds, 2);
  if (Math.abs(dx) > Math.abs(dy)) return { x: round(dx < 0 ? b.x : b.x + b.width), y };
  if (Math.abs(dy) > 0) return { x, y: round(dy < 0 ? b.y : b.y + b.height) };
  const sides = [
    { point: { x: b.x, y }, d: Math.abs(x - b.x) },
    { point: { x: b.x + b.width, y }, d: Math.abs(x - b.x - b.width) },
    { point: { x, y: b.y }, d: Math.abs(y - b.y) },
    { point: { x, y: b.y + b.height }, d: Math.abs(y - b.y - b.height) },
  ];
  return sides.sort((a, c) => a.d - c.d)[0]!.point;
}

class Heap {
  private items: { id: number; score: number }[] = [];
  push(item: { id: number; score: number }) {
    const a = this.items; a.push(item); let i = a.length - 1;
    while (i > 0) { const p = (i - 1) >> 1; if (a[p]!.score <= item.score) break; a[i] = a[p]!; i = p; } a[i] = item;
  }
  pop() {
    const a = this.items, top = a[0], last = a.pop();
    if (a.length && last) {
      let i = 0;
      while (i * 2 + 1 < a.length) {
        let c = i * 2 + 1;
        if (c + 1 < a.length && a[c + 1]!.score < a[c]!.score) c++;
        if (a[c]!.score >= last.score) break;
        a[i] = a[c]!; i = c;
      }
      a[i] = last;
    }
    return top;
  }
}

/** Coordinate-compressed Manhattan routing. Different nets may cross, but never share a wire. */
class Router {
  private xs: number[]; private ys: number[];
  private occupied = new Map<string, string>();
  private nodes = new Map<string, Set<string>>();
  private blocked = new Map<string, boolean>();
  private segments: { a: Point; b: Point; net: string }[] = [];
  private clearanceCache = new Map<string, boolean>();
  private routingNet: string | null = null;
  constructor(private obstacles: Bounds[], pins: PlacedPin[], bounds: Bounds) {
    const xs = [bounds.x, bounds.x + bounds.width], ys = [bounds.y, bounds.y + bounds.height];
    for (const b of obstacles) {
      // Multiple lanes provide room for parallel nets around a symbol.
      for (const offset of [0.8, 2.4, 4, 5.6]) {
        xs.push(b.x - offset, b.x + b.width + offset);
        ys.push(b.y - offset, b.y + b.height + offset);
      }
    }
    for (const pin of pins) {
      xs.push(pin.escape.x); ys.push(pin.escape.y);
      // Reserve every electrical escape before routing any net, including later nets.
      if (pin.net) this.segments.push({ a: pin, b: pin.escape, net: pin.net });
    }
    this.xs = [...new Set(xs.map(round))].sort((a, b) => a - b);
    this.ys = [...new Set(ys.map(round))].sort((a, b) => a - b);
  }
  route(start: Point, end: Point, net: string): Point[] | null {
    if (net !== this.routingNet) { this.clearanceCache.clear(); this.routingNet = net; }
    const w = this.xs.length;
    const point = (node: number): Point => ({ x: this.xs[node % w]!, y: this.ys[Math.floor(node / w)]! });
    const locate = (p: Point) => this.ys.indexOf(round(p.y)) * w + this.xs.indexOf(round(p.x));
    const first = locate(start), goal = locate(end);
    const costs = new Map<number, number>([[first * 3, 0]]), previous = new Map<number, number>();
    const heap = new Heap(); heap.push({ id: first * 3, score: distance(start, end) });
    let iterations = 0;
    while (iterations++ < 30000) {
      const item = heap.pop(); if (!item) return null;
      const node = Math.floor(item.id / 3), direction = item.id % 3, a = point(node), cost = costs.get(item.id)!;
      if (item.score > cost + distance(a, end) + 0.0001) continue;
      if (node === goal) {
        const result: Point[] = []; let id: number | undefined = item.id;
        while (id !== undefined) { result.push(point(Math.floor(id / 3))); id = previous.get(id); }
        return result.reverse();
      }
      const x = node % w, y = Math.floor(node / w);
      const neighbors: [number, number][] = [];
      if (x > 0) neighbors.push([node - 1, 1]);
      if (x + 1 < w) neighbors.push([node + 1, 1]);
      if (y > 0) neighbors.push([node - w, 2]);
      if (y + 1 < this.ys.length) neighbors.push([node + w, 2]);
      for (const [next, nextDirection] of neighbors) {
        const b = point(next), edge = edgeKey(a, b), owner = this.occupied.get(edge);
        if (owner && owner !== net) continue;
        let conflicts = this.clearanceCache.get(edge);
        if (conflicts === undefined) {
          conflicts = this.segments.some((segment) => segment.net !== net && (
            parallelWireConflict(a, b, segment.a, segment.b)
            // Cross the middle of a wire freely; keep crossings away from its ends/corners.
            || pointSegmentDistance(segment.a, a, b) < WIRE_CLEARANCE - 0.00001
            || pointSegmentDistance(segment.b, a, b) < WIRE_CLEARANCE - 0.00001));
          this.clearanceCache.set(edge, conflicts);
        }
        if (conflicts) continue;
        const foreignNode = [...(this.nodes.get(key(a)) ?? [])].some((id) => id !== net);
        // A crossing has no junction; do not turn or terminate onto another net's wire.
        if (foreignNode && direction !== 0 && direction !== nextDirection) continue;
        if (next === goal && [...(this.nodes.get(key(b)) ?? [])].some((id) => id !== net)) continue;
        let blocked = this.blocked.get(edge);
        if (blocked === undefined) { blocked = this.obstacles.some((box) => segmentHitsBounds(a, b, box)); this.blocked.set(edge, blocked); }
        if (blocked) continue;
        const nextCost = cost + distance(a, b) + (direction !== 0 && direction !== nextDirection ? 1.5 : 0) + (foreignNode ? 2 : 0);
        const id = next * 3 + nextDirection;
        if (nextCost >= (costs.get(id) ?? Infinity)) continue;
        costs.set(id, nextCost); previous.set(id, item.id);
        heap.push({ id, score: nextCost + distance(b, end) });
      }
    }
    return null;
  }
  occupy(path: Point[], net: string) {
    for (let i = 1; i < path.length; i++) this.occupied.set(edgeKey(path[i - 1]!, path[i]!), net);
    for (const p of path) { const owners = this.nodes.get(key(p)) ?? new Set<string>(); owners.add(net); this.nodes.set(key(p), owners); }
    const simplified = simplifyPath(path);
    for (let i = 1; i < simplified.length; i++) this.segments.push({ a: simplified[i - 1]!, b: simplified[i]!, net });
  }
}

export function simplifyPath(path: Point[]): Point[] {
  return path.filter((p, i) => i === 0 || i === path.length - 1 || !(
    (path[i - 1]!.x === p.x && p.x === path[i + 1]!.x)
    || (path[i - 1]!.y === p.y && p.y === path[i + 1]!.y)
  ));
}

/** Layout is an inspection drawing, independent from the PCB's physical placement. */
export function createDiagram(data: SchematicData): Diagram {
  const sorted = [...data.components].sort((a, b) => a.reference.localeCompare(b.reference, undefined, { numeric: true }));
  const columns = Math.max(1, Math.ceil(Math.sqrt(sorted.length * 1.35)));
  const geometry = sorted.map((component) => {
    const b = safeBounds(component.symbol.bounds);
    const vertical = component.symbol.pins.some((p) => Math.abs(p.y - p.endY) > Math.abs(p.x - p.endX))
      && !component.symbol.pins.some((p) => Math.abs(p.x - p.endX) > Math.abs(p.y - p.endY));
    const textWidth = Math.max(component.reference.length * 1.3, component.value.length * 1.05);
    // Keep vertical pin extensions clear by placing their reference and value beside the body.
    return vertical ? { size: { ...b, width: b.width + textWidth + 3 },
      annotation: { x: b.x + b.width + 2, y: b.y + b.height / 2 - 1.2, anchor: "start" as const } }
      : { size: { x: b.x + b.width / 2 - Math.max(b.width, textWidth) / 2, y: b.y - 6.5, width: Math.max(b.width, textWidth), height: b.height + 6.5 },
        annotation: { x: b.x + b.width / 2, y: b.y - 4.5, anchor: "middle" as const } };
  });
  const sizes = geometry.map((g) => g.size);
  const cellWidth = Math.max(38, ...sizes.map((b) => b.width + 24));
  const cellHeight = Math.max(34, ...sizes.map((b) => b.height + 27));
  const components = sorted.map((component, i): PlacedComponent => {
    const local = sizes[i]!, x = (i % columns) * cellWidth + (cellWidth - local.width) / 2 - local.x;
    const y = Math.floor(i / columns) * cellHeight + (cellHeight - local.height) / 2 - local.y;
    const bounds = { ...local, x: local.x + x, y: local.y + y };
    const annotation = geometry[i]!.annotation;
    return { component, x, y, bounds, annotation: { ...annotation, x: annotation.x + x, y: annotation.y + y } };
  });
  const pins: PlacedPin[] = [];
  for (const placed of components) for (const pin of placed.component.symbol.pins) {
    // Hidden power pins still carry compiled connectivity and remain selectable.
    const compiled = placed.component.pins.find((p) => p.number === pin.number);
    pins.push({ x: round(pin.x + placed.x), y: round(pin.y + placed.y), componentId: placed.component.id,
      number: pin.number, name: pin.name, net: compiled?.net ?? null, escape: escapePin(pin, placed) });
  }
  const bounds: Bounds = { x: -8, y: -8, width: columns * cellWidth + 16, height: Math.max(1, Math.ceil(sorted.length / columns)) * cellHeight + 16 };
  const obstacles = components.map((p) => inflate(p.bounds, 0.8));
  const router = new Router(obstacles, pins, bounds), warnings: string[] = [];
  const nets: NetDrawing[] = [];
  for (const net of data.nets) {
    const members = pins.filter((p) => p.net === net.name);
    if (!members.length) continue;
    const paths: Point[][] = members.map((pin) => [pin, pin.escape]);
    const connected = [members[0]!]; let incomplete = false;
    for (const pin of members.slice(1)) {
      const nearest = [...connected].sort((a, b) => distance(a.escape, pin.escape) - distance(b.escape, pin.escape));
      let route: Point[] | null = null;
      for (const candidate of nearest.slice(0, 4)) { route = router.route(pin.escape, candidate.escape, net.id); if (route) break; }
      if (route) { router.occupy(route, net.id); paths.push(route); } else { incomplete = true; }
      connected.push(pin);
    }
    const adjacency = new Map<string, Set<string>>(), points = new Map<string, Point>();
    for (const path of paths) for (let i = 1; i < path.length; i++) {
      const a = path[i - 1]!, b = path[i]!; if (key(a) === key(b)) continue;
      for (const [from, to] of [[a, b], [b, a]]) {
        const neighbors = adjacency.get(key(from!)) ?? new Set<string>(); neighbors.add(key(to!)); adjacency.set(key(from!), neighbors); points.set(key(from!), from!);
      }
    }
    const junctions = [...adjacency].filter(([, links]) => links.size >= 3).map(([id]) => points.get(id)!);
    const label = members[0]!.escape;
    if (incomplete) warnings.push(`${net.name}: some connections use matching net labels because a clear wire route was unavailable.`);
    nets.push({ id: net.id, name: net.name, paths: paths.map(simplifyPath), junctions, label, incomplete });
  }
  // Fit the visible drawing rather than the larger internal placement/routing grid.
  const visible: Point[] = components.flatMap(({ bounds: box }) => [
    { x: box.x, y: box.y }, { x: box.x + box.width, y: box.y + box.height },
  ]);
  for (const net of nets) {
    for (const path of net.paths) visible.push(...path);
    const labels = net.incomplete ? pins.filter((pin) => pin.net === net.name).map((pin) => pin.escape) : [net.label];
    for (const label of labels) visible.push({ x: label.x, y: label.y - 2.5 }, { x: label.x + 1 + net.name.length * 1.1, y: label.y });
  }
  const left = Math.min(...visible.map((p) => p.x)), top = Math.min(...visible.map((p) => p.y));
  const right = Math.max(...visible.map((p) => p.x)), bottom = Math.max(...visible.map((p) => p.y));
  const displayBounds = visible.length ? { x: left - 4, y: top - 4, width: right - left + 8, height: bottom - top + 8 } : bounds;
  return { components, pins, nets, bounds: displayBounds, warnings };
}

export const svgPath = (points: Point[]) => points.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ");

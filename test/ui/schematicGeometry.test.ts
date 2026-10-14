import { describe, expect, test } from "bun:test";
import { createDiagram, parallelWireConflict, segmentHitsBounds, simplifyPath } from "../../src/ui/webview/panel-schematic/geometry";
import type { SchematicComponent, SchematicData } from "../../src/ui/webview/panel-schematic/types";

function component(id: string, nets: [string | null, string | null]): SchematicComponent {
  return { id, reference: id, value: "1k", atoAddress: `app.${id}`, source: null,
    symbol: { name: "Device:R", missing: false, bounds: { x: -5, y: -2, width: 10, height: 4 },
      primitives: [{ type: "rect", x: -2, y: -1, width: 4, height: 2 }],
      pins: [{ number: "1", name: "A", x: -5, y: 0, endX: -2, endY: 0 }, { number: "2", name: "B", x: 5, y: 0, endX: 2, endY: 0 }] },
    pins: nets.map((net, i) => ({ number: String(i + 1), name: String(i + 1), net })) };
}
function data(components: SchematicComponent[]): SchematicData {
  const nets = new Map<string, SchematicData["nets"][number]>();
  for (const c of components) for (const pin of c.pins) if (pin.net) {
    const net = nets.get(pin.net) ?? { id: pin.net, name: pin.net, members: [] };
    net.members.push({ componentId: c.id, reference: c.reference, pin: pin.number }); nets.set(pin.net, net);
  }
  return { version: 1, projectRoot: "/demo", target: "default", layoutPath: "/demo/main.kicad_pcb", revision: "1", connectivityKind: "logical_pad_net_assignments", components, nets: [...nets.values()], warnings: [] };
}
const pointKey = (p: { x: number; y: number }) => `${p.x},${p.y}`;

describe("compiled schematic geometry", () => {
  test("connects every pin of a branching net with orthogonal wires and a junction", () => {
    const result = createDiagram(data([component("R1", ["GND", null]), component("R2", ["GND", null]), component("R3", ["GND", null])]));
    const drawing = result.nets[0]!;
    expect(drawing.incomplete).toBe(false); expect(result.warnings).toEqual([]); expect(drawing.junctions.length).toBeGreaterThan(0);
    const vertices = drawing.paths.flat().map(pointKey);
    for (const pin of result.pins.filter((p) => p.net === "GND")) expect(vertices).toContain(pointKey(pin));
    for (const path of drawing.paths) for (let i = 1; i < path.length; i++) {
      expect(path[i]!.x === path[i - 1]!.x || path[i]!.y === path[i - 1]!.y).toBe(true);
    }
  });
  test("routes between components around symbol bodies", () => {
    const result = createDiagram(data([component("R1", ["A", "B"]), component("R2", ["B", "A"]), component("R3", ["A", "B"]), component("R4", ["B", "A"])]));
    expect(result.warnings).toEqual([]);
    for (const net of result.nets) for (const path of net.paths.filter((p) => p.length > 2)) {
      for (let i = 1; i < path.length; i++) for (const placed of result.components) {
        expect(segmentHitsBounds(path[i - 1]!, path[i]!, placed.bounds)).toBe(false);
      }
    }
    // Different electrical nets must never share a collinear wire segment.
    const [a, b] = result.nets;
    for (const ap of a!.paths) for (const bp of b!.paths) for (let i = 1; i < ap.length; i++) for (let j = 1; j < bp.length; j++) {
      const p = ap[i - 1]!, q = ap[i]!, r = bp[j - 1]!, s = bp[j]!;
      const overlap = p.x === q.x && r.x === s.x && p.x === r.x
        ? Math.min(Math.max(p.y, q.y), Math.max(r.y, s.y)) - Math.max(Math.min(p.y, q.y), Math.min(r.y, s.y))
        : p.y === q.y && r.y === s.y && p.y === r.y
          ? Math.min(Math.max(p.x, q.x), Math.max(r.x, s.x)) - Math.max(Math.min(p.x, q.x), Math.min(r.x, s.x)) : 0;
      expect(overlap).toBeLessThanOrEqual(0);
    }
  });
  test("uses actual compiled pin nets; leaves unconnected pins unwired", () => {
    const source = data([component("R1", ["A", null]), component("R2", ["A", null])]);
    const result = createDiagram(source);
    expect(result.pins.filter((p) => p.net === null)).toHaveLength(2);
    expect(result.nets.map((n) => n.name)).toEqual(["A"]);
    expect(source.components[0]!.symbol.pins[0]!.x).toBe(-5);
  });
  test("real LED demo keeps distinct wires visibly separated, including pin escape stubs", () => {
    const led = component("D1", ["lv", "2"]); led.value = "LED5mm";
    led.symbol.bounds = { x: -4.572, y: -1.27, width: 8.382, height: 3.556 };
    led.symbol.pins = [{ number: "1", name: "K", x: -3.81, y: 0, endX: -1.27, endY: 0 }, { number: "2", name: "A", x: 3.81, y: 0, endX: 1.27, endY: 0 }];
    const input = component("J1", ["hv", "lv"]); input.value = "Input2";
    input.symbol.bounds = { x: -5.08, y: -1.27, width: 8.9535, height: 5.08 };
    input.symbol.pins = [{ number: "1", name: "Pin_1", x: -5.08, y: 0, endX: -1.27, endY: 0 }, { number: "2", name: "Pin_2", x: -5.08, y: 2.54, endX: -1.27, endY: 2.54 }];
    const resistor = component("R1", ["hv", "2"]); resistor.value = "Resistor330R";
    resistor.symbol.bounds = { x: -1.016, y: -3.81, width: 2.032, height: 7.62 };
    resistor.symbol.pins = [{ number: "1", name: "", x: 0, y: -3.81, endX: 0, endY: -2.54 }, { number: "2", name: "", x: 0, y: 3.81, endX: 0, endY: 2.54 }];
    const source = data([led, input, resistor]); source.nets.sort((a, b) => a.name.localeCompare(b.name));
    const result = createDiagram(source); expect(result.warnings).toEqual([]);
    expect(result.bounds.x).toBeGreaterThan(0);
    expect(result.bounds.height).toBeLessThan(35);
    for (let a = 0; a < result.nets.length; a++) for (let b = a + 1; b < result.nets.length; b++) {
      for (const ap of result.nets[a]!.paths) for (const bp of result.nets[b]!.paths) for (let i = 1; i < ap.length; i++) for (let j = 1; j < bp.length; j++) {
        expect(parallelWireConflict(ap[i - 1]!, ap[i]!, bp[j - 1]!, bp[j]!)).toBe(false);
      }
    }
  });
  test("near-parallel lines conflict but a perpendicular crossing does not imply a junction", () => {
    expect(parallelWireConflict({ x: 1, y: 25.7 }, { x: 10, y: 25.7 }, { x: 3, y: 25.918 }, { x: 15, y: 25.918 })).toBe(true);
    expect(parallelWireConflict({ x: 1, y: 25.7 }, { x: 10, y: 25.7 }, { x: 3, y: 27 }, { x: 15, y: 27 })).toBe(false);
    expect(parallelWireConflict({ x: 1, y: 5 }, { x: 10, y: 5 }, { x: 4, y: 1 }, { x: 4, y: 9 })).toBe(false);
  });
  test("placement is stable and naturally orders reference numbers", () => {
    const source = data([component("R10", [null, null]), component("R2", [null, null]), component("R1", [null, null])]);
    expect(createDiagram(source).components.map((p) => p.component.reference)).toEqual(["R1", "R2", "R10"]);
    expect(createDiagram(source)).toEqual(createDiagram(source));
  });
  test("empty and malformed bounds still yield a finite usable drawing", () => {
    expect(Object.values(createDiagram(data([])).bounds).every(Number.isFinite)).toBe(true);
    const source = component("R1", [null, null]); source.symbol.bounds.width = NaN;
    expect(Object.values(createDiagram(data([source])).bounds).every(Number.isFinite)).toBe(true);
  });
  test("simplifies bends without adding diagonal shortcuts", () => {
    expect(simplifyPath([{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 2, y: 0 }, { x: 2, y: 1 }]))
      .toEqual([{ x: 0, y: 0 }, { x: 2, y: 0 }, { x: 2, y: 1 }]);
  });
});

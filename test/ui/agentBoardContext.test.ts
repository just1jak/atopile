import { describe, expect, test } from "bun:test";
import { boardContextStatus } from "../../src/ui/webview/agent/runtime/boardContext";
import type { UiAgentSessionData } from "../../src/ui/protocol/generated-types";

type BoardContext = NonNullable<UiAgentSessionData["boardContext"]>;
const ready: BoardContext = {
  status: "ready", projectRoot: "/projects/circuit", target: "default",
  layoutPath: "/projects/circuit/layouts/default/default.kicad_pcb",
  componentCount: 3, netCount: 3, error: null, checkedAt: 1_700_000_000,
};

describe("chat board context", () => {
  test("project selection alone never claims board access", () => {
    expect(boardContextStatus(null, "/projects/circuit", "default")).toEqual({
      state: "unchecked", label: "Board not checked", detail: null,
    });
    expect(boardContextStatus(ready, null, "default").state).toBe("unchecked");
  });

  test("a previous project or target check cannot label the current board ready", () => {
    expect(boardContextStatus(ready, "/projects/other", "default").state).toBe("unchecked");
    expect(boardContextStatus(ready, "/projects/circuit", "other").state).toBe("unchecked");
    expect(boardContextStatus({ ...ready, status: "unavailable", error: "Old board error" }, "/projects/other", "default").detail).toBeNull();
  });

  test("ready count labels come from the completed host check", () => {
    expect(boardContextStatus(ready, "/projects/circuit/", undefined)).toEqual({
      state: "ready", label: "Board last read · default · 3 parts · 3 nets",
      detail: `Read ${new Date("2023-11-14T22:13:20Z").toLocaleString()}`,
    });
    expect(boardContextStatus({ ...ready, componentCount: 1, netCount: 0 }, "/projects/circuit", "default").label).toBe("Board last read · default · 1 part · 0 nets");
  });

  test("an absent or invalid read timestamp never displays an invented check time", () => {
    for (const checkedAt of [null, 0, -1, Number.NaN, Number.POSITIVE_INFINITY, 1e20]) {
      const status = boardContextStatus({ ...ready, checkedAt }, "/projects/circuit", "default");
      expect(status.detail).toBeNull();
      expect(status.label).toContain("Board last read");
    }
  });

  test("checking and actual failures stay distinct from a successful board read", () => {
    expect(boardContextStatus({ ...ready, status: "checking" }, "/projects/circuit", "default")).toEqual({
      state: "checking", label: "Checking board · default", detail: null,
    });
    expect(boardContextStatus({ ...ready, status: "unavailable", error: "Build this target first" }, "/projects/circuit", "default")).toEqual({
      state: "unavailable", label: "Board unavailable · default", detail: "Build this target first",
    });
  });
});

import type { UiAgentSessionData } from "../../../protocol/generated-types";
import { samePath } from "../../../protocol/paths";

export interface BoardContextStatus {
  state: "unchecked" | "checking" | "ready" | "unavailable";
  label: string;
  detail: string | null;
}

/** Display only the host's actual check of the currently selected board. */
export function boardContextStatus(
  context: UiAgentSessionData["boardContext"] | undefined,
  projectRoot: string | null,
  selectedTarget: string | null | undefined,
): BoardContextStatus {
  const unchecked: BoardContextStatus = {
    state: "unchecked", label: "Board not checked", detail: null,
  };
  const target = selectedTarget || "default";
  if (!projectRoot || !context || !samePath(projectRoot, context.projectRoot) || context.target !== target) {
    return unchecked;
  }
  if (context.status === "checking") {
    return { state: "checking", label: `Checking board · ${target}`, detail: null };
  }
  if (context.status === "unavailable") {
    return { state: "unavailable", label: `Board unavailable · ${target}`, detail: context.error || null };
  }
  if (context.status !== "ready") return unchecked;
  const details = ["Board last read", target];
  if (context.componentCount != null) details.push(`${context.componentCount} ${context.componentCount === 1 ? "part" : "parts"}`);
  if (context.netCount != null) details.push(`${context.netCount} ${context.netCount === 1 ? "net" : "nets"}`);
  const checkedAt = context.checkedAt;
  const checkedDate = typeof checkedAt === "number" && Number.isFinite(checkedAt) && checkedAt > 0
    ? new Date(checkedAt * 1000) : null;
  const detail = checkedDate && Number.isFinite(checkedDate.getTime())
    ? `Read ${checkedDate.toLocaleString()}` : null;
  return { state: "ready", label: details.join(" · "), detail };
}

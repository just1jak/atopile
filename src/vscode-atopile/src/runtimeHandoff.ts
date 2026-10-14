import { readFileSync } from "node:fs";
import { isAbsolute, join } from "node:path";

/** Installer-owned handoff; invalid data never falls back to an upstream CLI. */
export function readRuntimeHandoff(storagePath: string | undefined): string | undefined {
  if (!storagePath) return undefined;
  try {
    const data: unknown = JSON.parse(readFileSync(join(storagePath, "runtime.json"), "utf8"));
    if (!data || typeof data !== "object" || Array.isArray(data)) return undefined;
    const candidate = (data as Record<string, unknown>).ato;
    if (typeof candidate !== "string") return undefined;
    const ato = candidate.trim();
    if (!isAbsolute(ato) || /[\r\n\0]/.test(ato)) return undefined;
    return ato;
  } catch {
    return undefined;
  }
}

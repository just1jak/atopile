import { afterEach, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { readRuntimeHandoff } from "../src/runtimeHandoff";

const dirs: string[] = [];
function handoff(content: string): string {
  const dir = mkdtempSync(join(tmpdir(), "atopile-local-handoff-"));
  dirs.push(dir);
  writeFileSync(join(dir, "runtime.json"), content);
  return dir;
}
afterEach(() => { for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true }); });

test("loads an absolute installer launcher path, including spaces", () => {
  const ato = join(tmpdir(), "Atopile Local", "bin", "ato-local");
  expect(readRuntimeHandoff(handoff(JSON.stringify({ ato })))).toBe(ato);
});

test("ignores malformed, missing, relative and non-path handoffs", () => {
  for (const value of ["broken JSON", "null", "[]", "{}", '{"ato": 42}', '{"ato":"bin/ato-local"}', '{"ato":"/tmp/ato\\n-local"}']) {
    expect(readRuntimeHandoff(handoff(value))).toBeUndefined();
  }
  expect(readRuntimeHandoff(undefined)).toBeUndefined();
  expect(readRuntimeHandoff(join(tmpdir(), "nonexistent-atopile-storage"))).toBeUndefined();
});

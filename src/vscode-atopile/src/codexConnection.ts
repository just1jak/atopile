/** Use the native Codex login flow. Never open or copy its credential store. */
import { execFile } from "child_process";
import { accessSync, constants } from "fs";
import { delimiter, join, resolve } from "path";

export type CodexLoginStatus = "chatgpt" | "api-key" | "signed-out";
export interface CodexResult { exitCode: number; stdout: string; stderr: string }
export type CodexRunner = (path: string, args: string[], signal?: AbortSignal) => Promise<CodexResult>;

export function codexLoginEnvironment(source: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const env = { ...source };
  // A ChatGPT connection must not silently select a separately billed API key.
  for (const key of ["OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "ATOPILE_AGENT_API_KEY", "ANTHROPIC_API_KEY"]) delete env[key];
  return env;
}

function isExecutable(path: string): boolean {
  try { accessSync(path, constants.X_OK); return true; } catch { return false; }
}

export function discoverCodexExecutable(
  configured: string = "", env: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform, exists = isExecutable,
): string | undefined {
  const value = configured.trim();
  if (value && /[\r\n\0]/.test(value)) throw new Error("Invalid Codex executable path.");
  const executable = platform === "win32" ? "codex.exe" : "codex";
  if (value && (value.includes("/") || value.includes("\\"))) {
    const path = resolve(value);
    return exists(path) ? path : undefined;
  }
  const candidates = (env.PATH || "").split(delimiter).filter(Boolean).map(dir => join(dir, value || executable));
  if (!value && platform === "darwin") candidates.push(
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
    "/Applications/Codex.app/Contents/Resources/codex",
  );
  return candidates.find(exists);
}

export const runCodex: CodexRunner = (path, args, signal) => new Promise(resolveResult => {
  execFile(path, args, {
    env: codexLoginEnvironment(), signal, windowsHide: true,
    timeout: args.includes("status") ? 15_000 : 300_000, maxBuffer: 64 * 1024,
  }, (error, stdout, stderr) => resolveResult({
    exitCode: error ? (typeof error.code === "number" ? error.code : 1) : 0,
    stdout: String(stdout), stderr: String(stderr),
  }));
});

export async function readCodexLoginStatus(path: string, run: CodexRunner = runCodex): Promise<CodexLoginStatus> {
  const result = await run(path, ["login", "status"]);
  if (result.exitCode !== 0) return "signed-out";
  const message = `${result.stdout}\n${result.stderr}`;
  if (/logged in using chatgpt/i.test(message)) return "chatgpt";
  if (/api\s*key/i.test(message)) return "api-key";
  // Unknown login modes must never be presented as ChatGPT plan access.
  return "signed-out";
}

export interface CodexConnection {
  discover: (configured?: string) => string | undefined;
  status: (path: string) => Promise<CodexLoginStatus>;
  login: (path: string, signal?: AbortSignal) => Promise<CodexResult>;
}

export const nativeCodexConnection: CodexConnection = {
  discover: discoverCodexExecutable,
  status: readCodexLoginStatus,
  login: (path, signal) => runCodex(path, ["login"], signal),
};

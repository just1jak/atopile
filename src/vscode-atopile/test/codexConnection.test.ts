import { expect, test } from "bun:test";
import { codexLoginEnvironment, discoverCodexExecutable, readCodexLoginStatus } from "../src/codexConnection";

test("native account detection accepts ChatGPT and rejects API-key or unknown modes", async () => {
  for (const [output, expected] of [
    ["Logged in using ChatGPT", "chatgpt"],
    ["Logged in using an API key", "api-key"],
    ["Logged in using unknown method", "signed-out"],
  ]) {
    expect(await readCodexLoginStatus("/native/codex", async (path, args) => {
      expect(path).toBe("/native/codex"); expect(args).toEqual(["login", "status"]);
      return { exitCode: 0, stdout: "", stderr: output };
    })).toBe(expected);
  }
});

test("login discovery uses PATH or the installed macOS app without reading auth files", () => {
  const bundle = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex";
  expect(discoverCodexExecutable("", { PATH: "/custom/bin" }, "darwin", path => path === "/custom/bin/codex")).toBe("/custom/bin/codex");
  expect(discoverCodexExecutable("", { PATH: "" }, "darwin", path => path === bundle)).toBe(bundle);
  expect(discoverCodexExecutable("/my tools/codex", {}, "darwin", path => path === "/my tools/codex")).toBe("/my tools/codex");
});

test("Codex login does not inherit separately billed API provider keys", () => {
  const original = { PATH: "/bin", OPENAI_API_KEY: "api-secret", CODEX_API_KEY: "other-secret", CODEX_ACCESS_TOKEN: "other-account", ATOPILE_AGENT_API_KEY: "agent-secret" };
  expect(codexLoginEnvironment(original)).toEqual({ PATH: "/bin" });
  expect(original.OPENAI_API_KEY).toBe("api-secret");
});

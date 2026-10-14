import { beforeEach, expect, test } from "bun:test";
import { vscodeState } from "./vscodeFixture";
import type { CodexConnection } from "../src/codexConnection";

const { registerLocalAgentCommands, loadAgentEnvironment, getPublicAgentConfig } = await import("../src/localAgent");
let secretReads = 0;
const context = { subscriptions: [], secrets: {
  get: async () => { secretReads++; return "previous-api-secret"; },
  store: async () => { throw new Error("ChatGPT credentials must remain in native Codex"); },
  delete: async () => {},
} };
const existingLogin: CodexConnection = {
  discover: () => "/native/codex", status: async () => "chatgpt",
  login: async () => { throw new Error("Existing ChatGPT login must not open a browser"); },
};

beforeEach(() => {
  secretReads = 0; vscodeState.registered.clear(); vscodeState.configUpdates.length = 0;
  vscodeState.executedCommands.length = 0; vscodeState.messages.length = 0;
  Object.assign(vscodeState.settings, { "agent.provider": "codex", "agent.model": "", "agent.baseUrl": "https://previous.invalid/v1", "agent.codexPath": "" });
});

test("existing native ChatGPT login configures a secret-free backend", async () => {
  const env = await loadAgentEnvironment(context as never, existingLogin);
  expect(secretReads).toBe(0); expect(env.ATOPILE_AGENT_PROVIDER).toBe("codex");
  expect(env.ATOPILE_AGENT_MODEL).toBe(""); expect(env.ATOPILE_AGENT_BASE_URL).toBe("");
  expect(env.ATOPILE_AGENT_API_KEY).toBe(""); expect(getPublicAgentConfig().chatgptConnected).toBe(true);
});

test("Connect ChatGPT reuses native login and changes only explicit global provider settings", async () => {
  vscodeState.settings["agent.provider"] = "openai"; vscodeState.settings["agent.model"] = "previous-api-model";
  registerLocalAgentCommands(context as never, existingLogin);
  await vscodeState.registered.get("atopileLocal.connectChatGPT")!();
  expect(vscodeState.configUpdates).toEqual([
    { key: "agent.model", value: "", target: 1 }, { key: "agent.provider", value: "codex", target: 1 },
  ]);
  expect(secretReads).toBe(0); expect(vscodeState.executedCommands).toContain("workbench.action.reloadWindow");
});

test("API-key login cannot be mistaken for a ChatGPT connection", async () => {
  registerLocalAgentCommands(context as never, {
    ...existingLogin, status: async () => "api-key", login: async () => ({ exitCode: 0, stdout: "", stderr: "" }),
  });
  await vscodeState.registered.get("atopileLocal.connectChatGPT")!();
  expect(vscodeState.configUpdates).toHaveLength(0);
  expect(vscodeState.messages.at(-1)).toContain("not signed in with ChatGPT");
});

test("signed-out startup never opens login or falls back to an API key", async () => {
  const env = await loadAgentEnvironment(context as never, { ...existingLogin, status: async () => "signed-out" });
  expect(secretReads).toBe(0); expect(env.ATOPILE_AGENT_API_KEY).toBe("");
  expect(env.ATOPILE_AGENT_PROVIDER).toBe("codex"); expect(getPublicAgentConfig().chatgptConnected).toBe(false);
});

test("Connect ChatGPT runs native login only when needed and verifies the resulting account", async () => {
  let signedIn = false, logins = 0;
  registerLocalAgentCommands(context as never, {
    ...existingLogin, status: async () => signedIn ? "chatgpt" : "signed-out",
    login: async () => { logins++; signedIn = true; return { exitCode: 0, stdout: "", stderr: "" }; },
  });
  await vscodeState.registered.get("atopileLocal.connectChatGPT")!();
  expect(logins).toBe(1); expect(vscodeState.configUpdates).toEqual([{ key: "agent.provider", value: "codex", target: 1 }]);
});

test("failed native login makes no settings or secret changes", async () => {
  registerLocalAgentCommands(context as never, {
    ...existingLogin, status: async () => "signed-out",
    login: async () => ({ exitCode: 1, stdout: "", stderr: "native sign-in failed" }),
  });
  await vscodeState.registered.get("atopileLocal.connectChatGPT")!();
  expect(vscodeState.configUpdates).toHaveLength(0); expect(secretReads).toBe(0);
  expect(vscodeState.executedCommands).not.toContain("workbench.action.reloadWindow");
});

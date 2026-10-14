import { beforeEach, expect, test } from "bun:test";

import { vscodeState } from "./vscodeFixture";
const { registered, settings } = vscodeState;
const stored = new Map<string, string>();
const { registerLocalAgentCommands, loadAgentEnvironment, getPublicAgentConfig } = await import("../src/localAgent");
const context = {
  subscriptions: [],
  secrets: { get: async (key: string) => stored.get(key), store: async (key: string, value: string) => { stored.set(key, value); }, delete: async (key: string) => { stored.delete(key); } },
};

beforeEach(() => { stored.clear(); registered.clear(); vscodeState.configWrites = 0; vscodeState.inputPassword = false; settings["agent.provider"] = "openai"; registerLocalAgentCommands(context as never); });

test("collects a hidden key in SecretStorage and sends no key in public metadata", async () => {
  await registered.get("atopileLocal.setApiKey")!();
  const env = await loadAgentEnvironment(context as never);
  expect(vscodeState.inputPassword).toBe(true);
  expect(stored.get("atopileLocal.agent.apiKey.openai")).toBe("secret-test-key");
  expect(vscodeState.configWrites).toBe(0);
  expect(env.ATOPILE_AGENT_API_KEY).toBe("secret-test-key");
  expect(JSON.stringify(getPublicAgentConfig())).not.toContain("secret-test-key");
  expect(getPublicAgentConfig().keyConfigured).toBe(true);
  await registered.get("atopileLocal.clearApiKey")!();
  expect(stored.size).toBe(0);
});

test("keeps provider keys separate when changing providers", async () => {
  stored.set("atopileLocal.agent.apiKey.openai", "openai-only");
  settings["agent.provider"] = "anthropic";
  stored.set("atopileLocal.agent.apiKey.anthropic", "anthropic-only");
  expect((await loadAgentEnvironment(context as never)).ATOPILE_AGENT_API_KEY).toBe("anthropic-only");
});

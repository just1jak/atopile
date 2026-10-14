import { expect, test } from "bun:test";
import { buildAgentEnvironment, redactSecrets, serializePublicAgentConfig, validateAgentSettings } from "../src/localAgentConfig";

test("forwards the configured provider and model without an Atopile gateway", () => {
  expect(buildAgentEnvironment({ provider: "openai", baseUrl: "http://127.0.0.1:11434/v1/", model: "my-local-model" }, "test-key")).toEqual({
    ATOPILE_LOCAL_MODE: "1", ATOPILE_AGENT_PROVIDER: "openai",
    ATOPILE_AGENT_BASE_URL: "http://127.0.0.1:11434/v1", ATOPILE_AGENT_MODEL: "my-local-model",
    ATOPILE_AGENT_API_KEY: "test-key",
  });
});

test("rejects credentials embedded in endpoints and invalid protocols", () => {
  for (const baseUrl of ["https://user:password@example.com/v1", "file:///tmp/agent", "https://example.com?api_key=key", "not a URL"]) {
    expect(() => validateAgentSettings({ provider: "openai", baseUrl, model: "test" })).toThrow();
  }
});

test("public metadata cannot break out of an inline script and has no secret field", () => {
  const serialized = serializePublicAgentConfig({ localMode: true, provider: "anthropic", baseUrl: "", model: "</script><script>bad()</script>", keyConfigured: true });
  expect(serialized).not.toContain("</script>");
  expect(JSON.parse(serialized)).toEqual({ localMode: true, provider: "anthropic", baseUrl: "", model: "</script><script>bad()</script>", keyConfigured: true });
  expect(serialized).not.toContain("apiKey");
});

test("redacts every occurrence of API keys from backend logs", () => {
  expect(redactSecrets("Bearer key-one and key-one / key-two", ["key-one", "", "key-two"])).toBe("Bearer [REDACTED] and [REDACTED] / [REDACTED]");
});

test("ChatGPT uses native Codex without forwarding API credentials or endpoints", () => {
  expect(buildAgentEnvironment({ provider: "codex", baseUrl: "https://old.invalid?key=old", model: "", codexPath: "/Applications/ChatGPT.app/codex" }, "must-not-forward")).toEqual({
    ATOPILE_LOCAL_MODE: "1", ATOPILE_AGENT_PROVIDER: "codex", ATOPILE_AGENT_CODEX_PATH: "/Applications/ChatGPT.app/codex",
    ATOPILE_AGENT_MODEL: "", ATOPILE_AGENT_BASE_URL: "", ATOPILE_AGENT_API_KEY: "",
  });
});

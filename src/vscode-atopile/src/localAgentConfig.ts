export type LocalAgentProvider = "codex" | "openai" | "anthropic";

export interface LocalAgentSettings {
  provider: LocalAgentProvider;
  baseUrl: string;
  model: string;
  codexPath?: string;
}

export interface LocalAgentPublicConfig extends LocalAgentSettings {
  localMode: true;
  keyConfigured: boolean;
  chatgptConnected?: boolean;
}

export function validateAgentSettings(settings: LocalAgentSettings): LocalAgentSettings {
  const model = settings.model.trim();
  if ((!model && settings.provider !== "codex") || /[\r\n\0]/.test(model)) {
    throw new Error("Set a valid model ID in Atopile Local AI settings.");
  }
  if (settings.provider === "codex") {
    const codexPath = settings.codexPath?.trim() || "";
    if (/[\r\n\0]/.test(codexPath)) throw new Error("Set a valid Codex executable path.");
    return { provider: "codex", baseUrl: "", model, codexPath };
  }
  const baseUrl = settings.baseUrl.trim().replace(/\/+$/, "");
  if (baseUrl) {
    let url: URL;
    try {
      url = new URL(baseUrl);
    } catch {
      throw new Error("The AI endpoint must be an http:// or https:// URL.");
    }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error("Use an HTTP(S) AI endpoint without embedded credentials, query parameters, or fragments.");
    }
  }
  return { provider: settings.provider, baseUrl, model };
}

export function buildAgentEnvironment(settings: LocalAgentSettings, apiKey: string): Record<string, string> {
  const validated = validateAgentSettings(settings);
  if (validated.provider === "codex") {
    return {
      ATOPILE_LOCAL_MODE: "1",
      ATOPILE_AGENT_PROVIDER: "codex",
      ATOPILE_AGENT_CODEX_PATH: validated.codexPath || "",
      ATOPILE_AGENT_MODEL: validated.model,
      ATOPILE_AGENT_BASE_URL: "",
      ATOPILE_AGENT_API_KEY: "",
    };
  }
  return {
    ATOPILE_LOCAL_MODE: "1",
    ATOPILE_AGENT_PROVIDER: validated.provider,
    ATOPILE_AGENT_BASE_URL: validated.baseUrl,
    ATOPILE_AGENT_MODEL: validated.model,
    ATOPILE_AGENT_API_KEY: apiKey,
  };
}

/** Safe even when embedded in an inline HTML script. Never accepts an API key. */
export function serializePublicAgentConfig(config: LocalAgentPublicConfig): string {
  return JSON.stringify(config).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
}

export function redactSecrets(text: string, secrets: string[]): string {
  for (const secret of secrets) {
    if (secret) text = text.split(secret).join("[REDACTED]");
  }
  return text;
}

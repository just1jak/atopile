import { getVscodeApi } from "./vscodeApi";

export interface LocalAgentConfig {
  localMode: true;
  provider: "codex" | "openai" | "anthropic";
  baseUrl: string;
  model: string;
  keyConfigured: boolean;
  chatgptConnected?: boolean;
}

declare global {
  interface Window {
    __ATOPILE_LOCAL_AGENT__?: LocalAgentConfig;
  }
}

export const localAgent = window.__ATOPILE_LOCAL_AGENT__;
export const isLocalMode = localAgent?.localMode === true;

export function localAgentCommand(command: "setApiKey" | "clearApiKey" | "openAgentSettings" | "connectChatGPT"): void {
  getVscodeApi()?.postMessage({ type: "extension:localAgentCommand", command });
}

export function localProviderLabel(): string {
  return localAgent?.provider === "codex" ? "ChatGPT (Codex)"
    : localAgent?.provider === "anthropic" ? "Anthropic" : "OpenAI-compatible";
}

export function localModelLabel(): string {
  return localAgent?.model || (localAgent?.provider === "codex" ? "Codex default" : "Configure a model");
}

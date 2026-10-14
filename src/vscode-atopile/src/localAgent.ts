import * as vscode from "vscode";
import { nativeCodexConnection, type CodexConnection } from "./codexConnection";
import {
  buildAgentEnvironment,
  validateAgentSettings,
  type LocalAgentPublicConfig,
  type LocalAgentSettings,
} from "./localAgentConfig";

let publicConfig: LocalAgentPublicConfig = {
  localMode: true, provider: "codex", baseUrl: "", model: "", keyConfigured: false, chatgptConnected: false,
};

export function getPublicAgentConfig(): LocalAgentPublicConfig {
  return { ...publicConfig };
}

function getSettings(): LocalAgentSettings {
  const config = vscode.workspace.getConfiguration("atopileLocal");
  const provider = config.get<string>("agent.provider", "codex");
  if (provider !== "codex" && provider !== "openai" && provider !== "anthropic") {
    throw new Error("Select ChatGPT (Codex), OpenAI, or Anthropic in Atopile Local AI settings.");
  }
  return validateAgentSettings({
    provider,
    baseUrl: config.get<string>("agent.baseUrl", ""),
    model: config.get<string>("agent.model", "").trim() || (provider === "codex" ? "" : provider === "anthropic" ? "claude-sonnet-4-6" : "gpt-5.4"),
    codexPath: config.get<string>("agent.codexPath", ""),
  });
}

function secretKey(provider: LocalAgentSettings["provider"]): string {
  return `atopileLocal.agent.apiKey.${provider}`;
}

/** API keys stay in VS Code SecretStorage and the spawned backend environment. */
export async function loadAgentEnvironment(context: vscode.ExtensionContext, connection: CodexConnection = nativeCodexConnection): Promise<Record<string, string>> {
  const settings = getSettings();
  if (settings.provider === "codex") {
    const path = connection.discover(settings.codexPath);
    const status = path ? await connection.status(path) : "signed-out";
    publicConfig = { ...settings, localMode: true, keyConfigured: false, chatgptConnected: status === "chatgpt" };
    return buildAgentEnvironment({ ...settings, codexPath: path || settings.codexPath }, "");
  }
  const apiKey = await context.secrets.get(secretKey(settings.provider))
    ?? process.env.ATOPILE_AGENT_API_KEY
    ?? process.env[settings.provider === "anthropic" ? "ANTHROPIC_API_KEY" : "OPENAI_API_KEY"]
    ?? "";
  publicConfig = { ...settings, localMode: true, keyConfigured: Boolean(apiKey) };
  return buildAgentEnvironment(settings, apiKey);
}

export function registerLocalAgentCommands(context: vscode.ExtensionContext, connection: CodexConnection = nativeCodexConnection): void {
  const restart = () => vscode.commands.executeCommand("workbench.action.reloadWindow");
  context.subscriptions.push(
    vscode.commands.registerCommand("atopileLocal.openAgentSettings", () =>
      vscode.commands.executeCommand("workbench.action.openSettings", "atopileLocal.agent")),
    vscode.commands.registerCommand("atopileLocal.connectChatGPT", async () => {
      const config = vscode.workspace.getConfiguration("atopileLocal");
      const path = connection.discover(config.get<string>("agent.codexPath", ""));
      if (!path) {
        await vscode.window.showErrorMessage("Codex was not found. Install Codex or set Atopile Local › Agent: Codex Path.");
        return;
      }
      let status = await connection.status(path);
      if (status !== "chatgpt") {
        const result = await vscode.window.withProgress({
          location: vscode.ProgressLocation.Notification, title: "Connect ChatGPT: complete the Codex sign-in in your browser", cancellable: true,
        }, async (_progress, token) => {
          const controller = new AbortController();
          const cancellation = token.onCancellationRequested(() => controller.abort());
          try { return await connection.login(path, controller.signal); }
          finally { cancellation.dispose(); }
        });
        if (result.exitCode !== 0) {
          await vscode.window.showErrorMessage("ChatGPT sign-in did not complete. Use Connect ChatGPT to try again.");
          return;
        }
        status = await connection.status(path);
      }
      if (status !== "chatgpt") {
        await vscode.window.showErrorMessage("Codex is not signed in with ChatGPT. Sign in with your ChatGPT account to use its Codex allowance.");
        return;
      }
      if (config.get<string>("agent.provider", "codex") !== "codex") {
        await config.update("agent.model", "", vscode.ConfigurationTarget.Global);
      }
      await config.update("agent.provider", "codex", vscode.ConfigurationTarget.Global);
      await vscode.window.showInformationMessage("Atopile Local is connected to your ChatGPT account through Codex.");
      await restart();
    }),
    vscode.commands.registerCommand("atopileLocal.setApiKey", async () => {
      const provider = getSettings().provider;
      if (provider === "codex") { await vscode.commands.executeCommand("atopileLocal.connectChatGPT"); return; }
      const apiKey = await vscode.window.showInputBox({
        title: `Atopile Local: ${provider === "anthropic" ? "Anthropic" : "OpenAI-compatible"} API key`,
        prompt: "Stored securely in VS Code. Sent only to your configured AI endpoint.",
        password: true,
        ignoreFocusOut: true,
        validateInput: (value) => value.trim() && !/[\r\n\0]/.test(value) ? null : "Enter a valid API key.",
      });
      if (apiKey === undefined) return;
      await context.secrets.store(secretKey(provider), apiKey.trim());
      await restart();
    }),
    vscode.commands.registerCommand("atopileLocal.clearApiKey", async () => {
      const provider = getSettings().provider;
      if (provider === "codex") { await vscode.window.showInformationMessage("ChatGPT sign-in is managed by Codex. No API key is stored by Atopile Local."); return; }
      await context.secrets.delete(secretKey(provider));
      await restart();
    }),
  );
}

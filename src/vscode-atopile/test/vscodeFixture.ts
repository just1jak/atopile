import { mock } from "bun:test";

export const file = (fsPath: string) => ({ fsPath, toString: () => `file://${fsPath}` });
export const stat = mock(async () => ({}));
export const vscodeState = {
  registered: new Map<string, () => Promise<unknown>>(),
  settings: {
    "agent.provider": "openai", "agent.baseUrl": "http://127.0.0.1:11434/v1", "agent.model": "local-model",
  } as Record<string, unknown>,
  inputPassword: false,
  configWrites: 0,
  configUpdates: [] as { key: string; value: unknown; target: unknown }[],
  messages: [] as string[],
  executedCommands: [] as string[],
};

// Bun's module mocks are shared by files in one test process. Register a single
// superset fixture so independently loaded test suites never remove an export.
mock.module("vscode", () => ({
  Uri: { file },
  ConfigurationTarget: { Global: 1, Workspace: 2 },
  ProgressLocation: { Notification: 15 },
  workspace: {
    fs: { stat },
    getConfiguration: () => ({
      get: (key: string, fallback: unknown) => vscodeState.settings[key] ?? fallback,
      update: async (key: string, value: unknown, target: unknown) => {
        vscodeState.configWrites++;
        vscodeState.configUpdates.push({ key, value, target });
        vscodeState.settings[key] = value;
      },
    }),
  },
  commands: {
    registerCommand: (id: string, callback: () => Promise<unknown>) => {
      vscodeState.registered.set(id, callback);
      return { dispose() {} };
    },
    executeCommand: async (id: string) => { vscodeState.executedCommands.push(id); },
  },
  window: {
    showErrorMessage: async (message: string) => { vscodeState.messages.push(message); },
    showInformationMessage: async (message: string) => { vscodeState.messages.push(message); },
    withProgress: async (_options: unknown, task: Function) => task({}, {
      onCancellationRequested: () => ({ dispose() {} }),
    }),
    showInputBox: async (options: { password: boolean }) => {
      vscodeState.inputPassword = options.password;
      return "secret-test-key";
    },
  },
}));

import { beforeEach, expect, mock, test } from "bun:test";

import { file, stat } from "./vscodeFixture";
mock.module("../src/webviewHost", () => ({ AGENT_VIEW_ID: "atopileLocal.agentView" }));
const { ExtensionRpcHandler, AtoDiffContentProvider } = await import("../src/extensionRpcHandler");

beforeEach(() => {
  stat.mockReset();
  stat.mockImplementation(async () => ({}));
});

function setup() {
  const logger = { scope() { return this; } };
  const handler = new ExtensionRpcHandler(
    () => {}, () => {}, () => {}, () => {}, () => {},
    logger as never, new AtoDiffContentProvider(),
  );
  const webview = {
    options: { enableScripts: true, localResourceRoots: [file("/extensions/atopile"), file("/workspace")] },
    asWebviewUri: (uri: ReturnType<typeof file>) => {
      // Model the webview's resource-root restriction, independently of the
      // extension's decision about which directory to allow.
      expect(webview.options.localResourceRoots.some(root =>
        uri.fsPath.startsWith(`${root.fsPath}/`),
      )).toBe(true);
      return { toString: () => `https://webview.example${uri.fsPath}` };
    },
  };
  const request = {
    type: "extension_request" as const,
    requestId: "model-request",
    action: "vscode.resolveThreeDModel",
    target: { modelPath: "/outside/project/build/builds/default/default.pcba.glb" },
  };
  return { handler, webview, request };
}

test("authorizes the selected model outside workspace folders without exposing the project", async () => {
  const { handler, webview, request } = setup();
  const result = await handler.handle(webview as never, request);
  expect(result.ok && result.result).toMatchObject({ exists: true });
  expect(webview.options.enableScripts).toBe(true);
  expect(webview.options.localResourceRoots.map(root => root.fsPath)).toEqual([
    "/extensions/atopile", "/workspace", "/outside/project/build/builds/default",
  ]);
  await handler.handle(webview as never, request);
  expect(webview.options.localResourceRoots).toHaveLength(3);
});

test("does not broaden resource access for a nonexistent model", async () => {
  const { handler, webview, request } = setup();
  stat.mockRejectedValue(new Error("not found"));
  webview.asWebviewUri = uri => ({ toString: () => `https://webview.example${uri.fsPath}` });
  const result = await handler.handle(webview as never, request);
  expect(result.ok && result.result).toMatchObject({ exists: false });
  expect(webview.options.localResourceRoots).toHaveLength(2);
});

import { expect, test } from "bun:test";
import { buildContentSecurityPolicy } from "../src/contentSecurityPolicy";
import { buildHtml } from "../src/htmlBuilder";

test("allows local scripts, nonce bootstrap and WASM without arbitrary remote scripts", () => {
  const policy = buildContentSecurityPolicy("https://local.vscode-cdn.net", "test-nonce");
  const scripts = policy.split(";").map((directive) => directive.trim()).find((directive) => directive.startsWith("script-src"))!;
  expect(scripts).toContain("https://local.vscode-cdn.net");
  expect(scripts).toContain("'nonce-test-nonce'");
  expect(scripts).toContain("'wasm-unsafe-eval'");
  expect(scripts).not.toContain("'unsafe-inline'");
  expect(scripts).not.toContain("'unsafe-eval'");
  expect(scripts).not.toMatch(/\shttps:(?:\s|$)/);
  expect(policy).toContain("worker-src https://local.vscode-cdn.net blob:");
});

test("every helper HTML page has a CSP and matching style/script nonces", () => {
  const html = buildHtml({ title: "Local preview", cspSource: "https://local.vscode-cdn.net", body: "<div>Ready</div>", scripts: [{ src: "https://local.vscode-cdn.net/viewer.js" }] });
  expect(html).toContain('http-equiv="Content-Security-Policy"');
  const nonce = html.match(/'nonce-([^']+)'/)![1];
  expect(html).toContain(`<style nonce="${nonce}">`);
  expect(html).toContain(`<script nonce="${nonce}"`);
});

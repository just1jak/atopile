export function buildContentSecurityPolicy(localSource: string, nonce: string): string {
  return [
    "default-src 'none'",
    `script-src ${localSource} 'nonce-${nonce}' 'wasm-unsafe-eval'`,
    `style-src ${localSource} 'nonce-${nonce}'`,
    // React and canvas overlays set geometry through element style attributes.
    "style-src-attr 'unsafe-inline'",
    `img-src ${localSource} https: data: blob:`,
    `font-src ${localSource} data:`,
    `connect-src ${localSource} http://127.0.0.1:* http://localhost:* ws://127.0.0.1:* ws://localhost:* blob:`,
    `worker-src ${localSource} blob:`,
    `media-src ${localSource} blob:`,
    "base-uri 'none'",
    "form-action 'none'",
    "object-src 'none'",
  ].join("; ");
}

import { defineConfig } from 'vitest/config';
export default defineConfig({ test: { include:['packages/**/*.test.ts','desktop/**/*.test.ts','mobile/**/*.test.ts'], environment:'node' } });

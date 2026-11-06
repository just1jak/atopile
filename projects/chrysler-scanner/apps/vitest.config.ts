import { defineConfig } from 'vitest/config';
export default defineConfig({ test: { include:['packages/**/*.test.ts','desktop/**/*.test.ts'], environment:'node' } });

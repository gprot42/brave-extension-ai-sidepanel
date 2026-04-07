import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';

const host = process.env.TAURI_DEV_HOST;
const version = readFileSync('version.md', 'utf-8').trim();

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: host || false,
    hmr: host
      ? { protocol: 'ws', host, port: 5174 }
      : undefined,
    watch: {
      ignored: ['**/src-tauri/**'],
    },
  },
});

import { defineConfig, mergeConfig } from 'vite'
import offlineConfig from './vite.config.offline.mjs'

function workerNodeStubs() {
  const stubs = {
    stream: 'export class Stream {}\nexport default { Stream }',
    timers: 'export const setImmediate = (fn, ...a) => setTimeout(fn, 0, ...a)\nexport const clearImmediate = (id) => clearTimeout(id)\nexport default { setImmediate, clearImmediate }',
  }
  return {
    name: 'codex-worker-node-stubs',
    enforce: 'pre',
    resolveId: (id) => stubs[id] ? '\0codex-worker-stub:' + id : null,
    load: (id) => id.startsWith('\0codex-worker-stub:') ? stubs[id.slice(19)] : null,
  }
}

// codex 版使用独立入口和目录，不覆盖已交付的正式离线版。
export default defineConfig(mergeConfig(offlineConfig, {
  build: {
    outDir: 'dist-codex',
    rollupOptions: { input: 'codex.html' },
  },
  worker: {
    plugins: () => [workerNodeStubs()],
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
}))

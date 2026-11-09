import path from "path"
import { fileURLToPath } from "node:url"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { inspectAttr } from 'kimi-plugin-inspect-react'
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// officecrypto-tool（投喂文件解密）的依赖链会 require 这两个 node 内置模块
// （sax 里有 try/catch 兜底、xml2js 只用 setImmediate），浏览器里垫成最小实现，
// 避免 build 报 "Module ... has been externalized" 警告
function nodeBuiltinStubs() {
  const stubs: Record<string, string> = {
    stream: 'export class Stream {}\nexport default { Stream }',
    timers: 'export const setImmediate = (fn, ...a) => setTimeout(fn, 0, ...a)\nexport const clearImmediate = (id) => clearTimeout(id)\nexport default { setImmediate, clearImmediate }',
  }
  return {
    name: 'node-builtin-stubs',
    enforce: 'pre' as const, // 必须抢在 vite:resolve 的 node 内置模块 externalize 之前
    resolveId: (id: string) => (stubs[id] ? '\0stub:' + id : null),
    load: (id: string) => (id.startsWith('\0stub:') ? stubs[id.slice(6)] : null),
  }
}

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [inspectAttr(), react(), nodeBuiltinStubs()],
  server: {
    port: 3000,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // officecrypto-tool 用的 node:crypto 子集 → crypto-js 纯 JS 垫片（浏览器可跑）
      "crypto": path.resolve(__dirname, "./src/lib/node-crypto-shim.js"),
      // xml2js 的 EventEmitter / 全局 Buffer → 对应 npm polyfill 包
      "events": path.resolve(__dirname, "./node_modules/events/events.js"),
      "buffer": path.resolve(__dirname, "./node_modules/buffer/index.js"),
    },
  },
});

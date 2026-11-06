import path from "path"
import { fileURLToPath } from "node:url"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// officecrypto-tool（投喂文件解密）的依赖链会 require 这两个 node 内置模块
// （sax 里有 try/catch 兜底、xml2js 只用 setImmediate），浏览器里垫成最小实现，
// 避免 build 报 "Module ... has been externalized" 警告
function nodeBuiltinStubs() {
  const stubs = {
    stream: 'export class Stream {}\nexport default { Stream }',
    timers: 'export const setImmediate = (fn, ...a) => setTimeout(fn, 0, ...a)\nexport const clearImmediate = (id) => clearTimeout(id)\nexport default { setImmediate, clearImmediate }',
  }
  return {
    name: 'node-builtin-stubs',
    enforce: 'pre', // 必须抢在 vite:resolve 的 node 内置模块 externalize 之前
    resolveId: (id) => (stubs[id] ? '\0stub:' + id : null),
    load: (id) => (id.startsWith('\0stub:') ? stubs[id.slice(6)] : null),
  }
}

// 离线打包专用：不挂 inspect 插件，目标降到 chrome63（兼容 Win7 上的 360/搜狗/老 Chrome 双核浏览器；
// ?? 与 ?. 是 chrome80 原生语法，target 只到 80 的话 esbuild 会原样保留，更老内核直接整包 SyntaxError 白屏），
// 关 modulePreload、全量内联小资产，产出给 build-offline.mjs 合成单文件 HTML
export default defineConfig({
  base: './',
  plugins: [react(), nodeBuiltinStubs()],
  build: {
    outDir: 'dist-offline',
    target: 'chrome63',
    cssTarget: 'chrome63',
    modulePreload: false,
    assetsInlineLimit: 100 * 1024 * 1024,
    chunkSizeWarningLimit: 1024 * 1024,
    // 投喂解密（officecrypto-tool）在页面里是 dynamic import；离线版是单文件 html，
    // file:// 下按相对路径再加载分包必失败，必须全部内联回主包
    rollupOptions: { output: { inlineDynamicImports: true } },
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

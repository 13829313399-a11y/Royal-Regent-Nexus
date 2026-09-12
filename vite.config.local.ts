import { fileURLToPath, URL } from 'node:url'
import { defineConfig, mergeConfig } from 'vite'
import base from './vite.config'

/*
  dsh-worktree 专用的本地开发配置：只覆盖依赖预构建缓存目录，其余全部继承 vite.config.ts。

  原因：本 worktree 的 node_modules 是指向主检出的目录联接，Vite 默认把预构建缓存写在
  <root>/node_modules/.vite/deps。两个 checkout 共用同一物理目录，而缓存指纹包含解析后的
  root/cacheDir 绝对路径，因此两边会互相判定缓存失效并反复重新预构建。

  这里把缓存改到 node_modules/.vite-worktree/（node_modules 已在 .gitignore 第 10 行），
  既隔离缓存、又不影响主检出正在运行的 5173 服务。启动方式：
    node node_modules/vite/bin/vite.js --config vite.config.local.ts --port 5174
*/
export default defineConfig(configEnv =>
  mergeConfig(base(configEnv), {
    cacheDir: fileURLToPath(new URL('./node_modules/.vite-worktree', import.meta.url)),
  }),
)

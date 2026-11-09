import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'
import { aliases } from './vite.config'
export default defineConfig({
  root: fileURLToPath(new URL('../../../', import.meta.url)),
  cacheDir: fileURLToPath(new URL('../build/vitest-cache', import.meta.url)),
  plugins: [vue()], resolve: { alias: aliases },
  test: { environment: 'jsdom', include: ['tools/customer-order-trial/web/src/**/*.spec.ts'] },
})

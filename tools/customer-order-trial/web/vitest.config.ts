import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'
import { aliases } from './vite.config'
export default defineConfig({
  root: fileURLToPath(new URL('../../../', import.meta.url)),
  cacheDir: fileURLToPath(new URL('../build/vitest-cache', import.meta.url)),
  plugins: [vue()], resolve: { alias: [{ find: /^@\/api\/customerOrder$/, replacement: fileURLToPath(new URL('./src/greenToysOrderApi.ts', import.meta.url)) }, ...aliases] },
  test: { environment: 'jsdom', exclude: ['tools/customer-order-trial/web/src/HuadengApp.spec.ts', 'tools/customer-order-trial/web/src/HuaxingTrialApp.spec.ts'], include: ['tools/customer-order-trial/web/src/**/*.spec.ts'] },
})

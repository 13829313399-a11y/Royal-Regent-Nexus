import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import { imageTranslationPlugin } from './scripts/vite-image-translation'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue(), tailwindcss(), imageTranslationPlugin()],
    server: {
      // Worker artifacts are data, not frontend sources. HTML previews must
      // never trigger a full-page reload that discards the current selection.
      watch: {
        ignored: ['**/backend/data/**', '**/outputs/**', '**/backend/.pytest-tmp*/**', '**/dist/**'],
      },
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
  }
})

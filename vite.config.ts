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
      // Runtime and test artifacts are not frontend sources. Ignore locked
      // temporary files and previews that could crash or reload the dev server.
      watch: {
        ignored: [
          '**/backend/data/**',
          '**/outputs/**',
          '**/.tmp/**',
          '**/.tmp-tests/**',
          '**/.local-dev/**',
          '**/backend/.pytest-tmp*/**',
          '**/dist/**',
          '**/*.tmpdir/**',
          '**/.*.tmpdir/**',
        ],
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

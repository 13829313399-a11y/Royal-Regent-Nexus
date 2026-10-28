import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import { imageTranslationPlugin } from './scripts/vite-image-translation'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    // Isolated QA apps may share node_modules, but must not replace this
    // server's optimized dependency files while it is running.
    cacheDir: fileURLToPath(new URL('./.local-dev/vite-cache', import.meta.url)),
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
        ...(env.ONLYOFFICE_DEV_PROXY_TARGET ? {
          '/office': {
            target: env.ONLYOFFICE_DEV_PROXY_TARGET,
            changeOrigin: true,
            ws: true,
            rewrite: (path: string) => path.replace(/^\/office/, ''),
            headers: {
              'X-Forwarded-Host': env.ONLYOFFICE_DEV_PUBLIC_HOST || '127.0.0.1:5173/office',
              'X-Forwarded-Proto': 'http',
            },
          },
        } : {}),
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

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv, type ViteDevServer } from 'vite'
import { imageTranslationPlugin } from './scripts/vite-image-translation'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    // Isolated QA apps may share node_modules, but must not replace this
    // server's optimized dependency files while it is running.
    cacheDir: fileURLToPath(new URL('./.local-dev/vite-cache', import.meta.url)),
    plugins: [vue(), tailwindcss(), imageTranslationPlugin(), {
      name: 'office-connection-boundary',
      configureServer(server: ViteDevServer) {
        server.middlewares.use((req, res, next) => {
          const url = req.url ?? ''
          if (url.startsWith('/office')) {
            try {
              const path = url.split('?')[0] ?? ''
              const decoded = decodeURIComponent(path)
              const staticAsset = /^\/office\/(?:[^/?]+\/)?(?:web-apps|sdkjs|fonts|core-fonts|dictionaries|healthcheck)(?:\/|$)/.test(path)
              const dynamic = /^\/office\/(?:[^/?]+\/)?(?:doc|cache|downloadas|savefile|printfile|downloadfile|upload)\//.test(path)
              if ((!staticAsset && decoded !== path) || decoded.includes('%') || decoded.includes('\\') || decoded.includes('//') || decoded.split('/').some(p => p === '.' || p === '..') || (!staticAsset && !dynamic) ||
                  (/[?&](?:EIO|transport)=/i.test(url) && !/^\/office\/(?:[^/?]+\/)?doc\/[^/?]+\/c\/?$/.test(path))) {
                res.statusCode = 403; res.end('Invalid document connection path'); return
              }
            } catch { res.statusCode = 403; res.end(); return }
          }
          next()
        })
      },
    }],
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
          '^/office/(?:[^/?]+/)?(?:doc|cache|downloadas|savefile|printfile|downloadfile|upload)/': {
            target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
            changeOrigin: false,
            ws: true,
          },
          '/office': {
            target: env.ONLYOFFICE_DEV_PROXY_TARGET,
            changeOrigin: true,
            ws: false,
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

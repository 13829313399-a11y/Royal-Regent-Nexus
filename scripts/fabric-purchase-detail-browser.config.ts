import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import base from '../vite.config'

// Browser acceptance only. Delay the original read without changing the client timeout.
export default defineConfig(context => {
  const config = base(context)
  const target = process.env.VITE_API_PROXY_TARGET ?? ''
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(target)) {
    throw new Error('Use a loopback API connected to an independent acceptance database copy.')
  }
  const directory = resolve('.tmp/fabric-purchase-detail-browser')
  const flag = resolve(directory, 'delay-detail.flag')
  return {
    ...config,
    cacheDir: resolve(directory, 'vite-cache'),
    optimizeDeps: { ...config.optimizeDeps, entries: ['index.html'] },
    plugins: [...(config.plugins ?? []), {
      name: 'acceptance-purchase-detail-delay',
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          const url = new URL(request.url ?? '/', 'http://127.0.0.1')
          if (request.method !== 'GET' ||
              !/^\/api\/fabric-warehouse\/procurement\/lines\/[\w-]{1,64}$/.test(url.pathname) ||
              url.searchParams.get('factory_id') !== 'huakang-c') return next()
          let delay: number
          try { delay = Number(readFileSync(flag, 'utf8').trim()) }
          catch (error) {
            if ((error as NodeJS.ErrnoException).code !== 'ENOENT') return next(error)
            return next()
          }
          if (!Number.isInteger(delay) || delay <= 0 || delay > 20_000) return next()
          const timer = setTimeout(() => {
            response.off('close', cancel)
            if (!response.destroyed) next()
          }, delay)
          const cancel = () => clearTimeout(timer)
          response.once('close', cancel)
        })
      },
    }],
  }
})

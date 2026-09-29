import { createReadStream, existsSync, statSync } from 'node:fs'
import { extname, resolve, sep } from 'node:path'
import type { Plugin } from 'vite'

const mimeTypes: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.wasm': 'application/wasm',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.md': 'text/plain; charset=utf-8',
}

/** Serve the separately built server-backed translation UI during development. */
export function imageTranslationPlugin(): Plugin {
  return {
    name: 'rr-image-translation',
    configureServer(server) {
      const root = resolve(server.config.root, 'shinobu-web/apps/web/dist')
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url ?? '/', 'http://localhost').pathname
        if (pathname !== '/image-translation' && !pathname.startsWith('/image-translation/')) return next()
        if (pathname === '/image-translation') {
          response.writeHead(302, { Location: `/image-translation/${new URL(request.url!, 'http://localhost').search}` })
          response.end()
          return
        }
        let relativePath: string
        try { relativePath = decodeURIComponent(pathname.slice('/image-translation/'.length)) || 'index.html' }
        catch { response.writeHead(400); response.end(); return }
        const path = resolve(root, relativePath)
        if (!path.startsWith(`${root}${sep}`) || !existsSync(path) || !statSync(path).isFile()) {
          response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
          response.end('图片翻译资源尚未构建。请执行 npm run build:image-translation。')
          return
        }
        response.writeHead(200, {
          'Content-Type': mimeTypes[extname(path)] ?? 'application/octet-stream',
          'Content-Length': statSync(path).size,
          'Cache-Control': 'no-store',
          'X-Content-Type-Options': 'nosniff',
        })
        if (request.method === 'HEAD') response.end()
        else createReadStream(path).pipe(response)
      })
    },
  }
}

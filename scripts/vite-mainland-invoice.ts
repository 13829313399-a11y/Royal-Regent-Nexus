import { createReadStream, existsSync, statSync } from 'node:fs'
import { extname, resolve, sep } from 'node:path'
import type { Plugin } from 'vite'

/** Preview code only; never serve templates or records. */
export function mainlandInvoicePlugin(): Plugin {
  return {
    name: 'rr-mainland-invoice',
    configureServer(server) {
      const root = resolve(server.config.root, 'services/mainland-invoice/dist')
      server.middlewares.use((request, response, next) => {
        const url = new URL(request.url ?? '/', 'http://localhost')
        const pathname = (request.url ?? '/').split('?')[0]!
        if (pathname === '/mainland-invoice') {
          response.writeHead(302, { Location: '/mainland-invoice/' + url.search })
          response.end()
          return
        }
        if (!pathname.startsWith('/mainland-invoice/')) return next()
        let relative: string
        try { relative = decodeURIComponent(pathname.slice('/mainland-invoice/'.length)) || 'index.html' }
        catch { response.writeHead(400); response.end(); return }
        const file = resolve(root, relative)
        if (!file.startsWith(root + sep) || !existsSync(file) || !statSync(file).isFile()) {
          response.writeHead(404)
          response.end('请先执行 npm run build:mainland-invoice')
          return
        }
        const mime: Record<string, string> = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }
        if (!mime[extname(file)]) { response.writeHead(404); response.end(); return }
        response.writeHead(200, { 'Content-Type': mime[extname(file)]!, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' })
        if (request.method === 'HEAD') response.end()
        else createReadStream(file).pipe(response)
      })
    },
  }
}

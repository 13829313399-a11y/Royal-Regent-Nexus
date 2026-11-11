import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, extname } from 'node:path'

const root = resolve('dist')
const allowed = new Set(['.html', '.js', '.css', '.svg'])
function inspect(dir) {
  for (const entry of readdirSync(dir)) {
    const path = resolve(dir, entry)
    if (statSync(path).isDirectory()) { inspect(path); continue }
    if (!allowed.has(extname(path))) throw new Error('Unexpected invoice static asset: ' + entry)
    const text = readFileSync(path, 'utf8')
    if (text.includes('__OFFLINE_ASSETS__') || text.includes('data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        || text.includes('发票系统离线版_') || text.includes('invoice-gen-history')) {
      throw new Error('Offline data or history leaked to the public bundle')
    }
  }
}
inspect(root)
console.log('Invoice release boundaries verified: code only, no embedded templates or records.')

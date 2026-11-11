/**
 * 构建独立 codex 版单文件 HTML，所有发票模板内置，可在 file:// 离线使用。
 * 运行：node scripts/build-codex.mjs
 * 正式版 dist / dist-offline 不受影响。
 */
import { requirePrivateAssets } from './check-private-assets.mjs';
import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const out = join(root, 'dist-codex')
const publicDir = join(root, 'public')

requirePrivateAssets();

console.log('1/3 构建 codex 版独立入口…')
execFileSync(process.execPath, [join(root, 'node_modules/vite/bin/vite.js'), 'build', '--config', 'vite.config.codex.mjs'], { cwd: root, stdio: 'inherit' })

console.log('2/3 内联程序、样式及全部内置工作簿模板…')
let html = readFileSync(join(out, 'codex.html'), 'utf8')
html = html.replace(/<script([^>]*?)\ssrc="\.\/assets\/([^"]+)"([^>]*)><\/script>/g, (_m, pre, file, post) => {
  const js = readFileSync(join(out, 'assets', file), 'utf8').replace(/<\/script/gi, '<\\/script')
  return `<script${pre}${post}>\n${js}\n</script>`
})
html = html.replace(/<link([^>]*?)rel="stylesheet"([^>]*?)href="\.\/assets\/([^"]+)"([^>]*?)\/?>/g, (_m, _a, _b, file) => {
  const css = readFileSync(join(out, 'assets', file), 'utf8').replace(/<\/style/gi, '<\\/style')
  return `<style>\n${css}\n</style>`
})
html = html.replace(/<link[^>]*rel="modulepreload"[^>]*>/g, '')

function workbookFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    return entry.isDirectory() ? workbookFiles(path) : /\.xlsx$/i.test(entry.name) ? [path] : []
  })
}
const templates = workbookFiles(publicDir).sort()
if (!templates.length) throw new Error('没有找到内置工作簿模板')
const assets = Object.fromEntries(templates.map((path) => [
  '/' + relative(publicDir, path).split('\\').join('/'),
  readFileSync(path).toString('base64'),
]))
const inject = `<script>window.__OFFLINE_ASSETS__=${JSON.stringify(assets)};</script>`
const scriptIdx = html.search(/<script/)
if (scriptIdx < 0) throw new Error('codex.html 缺少程序入口')
html = html.slice(0, scriptIdx) + inject + html.slice(scriptIdx)

const leftovers = html.match(/(?:src|href)="\.\/assets\/[^"]+"/g)
if (leftovers) throw new Error(`还有未内联的本地资源: ${leftovers.join(', ')}`)
const outFile = join(out, '大陆发票系统_codex版_20261028.html')
writeFileSync(outFile, html)
console.log(`3/3 完成: ${outFile}（${(statSync(outFile).size / 1024 / 1024).toFixed(1)} MB，${templates.length} 个内置工作簿）`)

import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const project = resolve(root, 'services/mainland-invoice')
if (!existsSync(resolve(project, 'node_modules/vite/package.json'))) {
  throw new Error('请先在 services/mainland-invoice 执行 npm ci。')
}
const npmCli = process.env.npm_execpath
if (!npmCli) throw new Error('请通过 npm run build:mainland-invoice 运行。')
const result = spawnSync(process.execPath, [npmCli, 'run', 'build'], { cwd: project, stdio: 'inherit' })
if (result.error) throw result.error
if (result.status !== 0) process.exit(result.status ?? 1)
const destination = resolve(root, 'dist/mainland-invoice')
// Only the generated invoice bundle: do not retain obsolete assets on rebuild.
rmSync(destination, { recursive: true, force: true })
mkdirSync(destination, { recursive: true })
cpSync(resolve(project, 'dist'), destination, { recursive: true })

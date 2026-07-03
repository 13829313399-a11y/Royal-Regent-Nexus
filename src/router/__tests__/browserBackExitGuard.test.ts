import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
const guardSource = readFileSync(join(process.cwd(), 'src/lib/browserBackExitGuard.ts'), 'utf8')

assert.match(routerSource, /installBrowserBackExitGuard/)
assert.match(routerSource, /browserBackExitGuard\.lock\(to\.fullPath\)/)
assert.match(routerSource, /browserBackExitGuard\.unlock\(\)/)

for (const requiredImplementation of [
  'popstate',
  'history.pushState',
  'history.replaceState',
  'currentLockedFullPath',
  'router\\.replace\\(currentLockedFullPath\\)',
  '__rr_browser_back_exit_guard__',
]) {
  assert.match(guardSource, new RegExp(requiredImplementation))
}

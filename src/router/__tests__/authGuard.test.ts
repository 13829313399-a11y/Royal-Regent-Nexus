import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

for (const requiredImplementation of [
  '/login',
  'useAuthStore',
  'ensureSession',
  'requiresAuth',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

assert.match(source, /path:\s*'\/login'[\s\S]{0,220}fullPage:\s*true/)
assert.doesNotMatch(source, /meta:\s*\{[\s\S]{0,220}permission:/)
assert.doesNotMatch(source, /authStore\.hasPermission/)
assert.doesNotMatch(source, /name:\s*'forbidden'/)

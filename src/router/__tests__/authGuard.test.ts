import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

for (const requiredImplementation of [
  '/login',
  'useAuthStore',
  'ensureSession',
  'requiresAuth',
  'authStore.hasPermission',
  'forbidden',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

assert.match(source, /path:\s*'\/login'[\s\S]{0,220}fullPage:\s*true/)

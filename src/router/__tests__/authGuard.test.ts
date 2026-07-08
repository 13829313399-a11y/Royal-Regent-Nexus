import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

for (const requiredImplementation of [
  '/login',
  '/register',
  '/system/users',
  'useAuthStore',
  'ensureSession',
  'requiresAuth',
  'permissions',
  'hasAnyPermission',
  'forbidden',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

assert.match(source, /path:\s*'\/login'[\s\S]{0,220}fullPage:\s*true/)
assert.match(source, /path:\s*'\/register'[\s\S]{0,260}fullPage:\s*true/)
assert.match(source, /path:\s*'\/system\/users'[\s\S]{0,360}permissions:\s*\[['"]system:user_manage['"]\]/)

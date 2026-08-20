import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

for (const requiredImplementation of [
  '/login',
  '/register',
  '/reset-password',
  '/change-password',
  '/system/users',
  'useAuthStore',
  'ensureSession',
  'requiresAuth',
  'permissions',
  'authStore.can',
  'forbidden',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

assert.match(source, /path:\s*'\/login'[\s\S]{0,220}fullPage:\s*true/)
assert.match(source, /path:\s*'\/register'[\s\S]{0,260}fullPage:\s*true/)
assert.match(source, /path:\s*'\/reset-password'[\s\S]{0,260}requiresAuth:\s*false/)
assert.match(source, /path:\s*'\/change-password'[\s\S]{0,260}requiresAuth:\s*true/)
assert.match(source, /currentUser\?\.force_password_change/)
assert.match(source, /path:\s*'\/system\/users'[\s\S]{0,360}permissions:\s*\[['"]system:user_manage['"]\]/)
assert.match(source, /path:\s*'\/system\/users\/:userId\/access'[\s\S]{0,360}permissions:\s*\[['"]system:access_manage['"]\]/)
assert.match(source, /path:\s*'\/modules\/molding-sample'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:read['"],\s*['"]molding_sample:cross_factory_read['"]\]/)
assert.match(source, /path:\s*'\/modules\/production\/molding-sample-tasks'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:production_read['"]\]/)
assert.match(source, /path:\s*'\/modules\/pmc-warehouse\/raw-material-management'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:raw_material_write['"]\]/)
assert.match(source, /path:\s*'\/modules\/sales-business\/customer-price-conversion'[\s\S]{0,360}permissions:\s*\[['"]customer_price:read['"]\]/)
assert.match(source, /path:\s*'\/modules\/sales-business\/po-schedule-intake'[\s\S]{0,360}permissions:\s*\[['"]customer_order:read['"]\]/)

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/stores/auth.ts'), 'utf8')

for (const requiredImplementation of [
  'defineStore',
  'useAuthStore',
  'currentUser',
  'roles',
  'permissions',
  'grants',
  'factoryScopes',
  'isAuthenticated',
  'authApi.login',
  'authApi.getMe',
  'authApi.changePassword',
  'authApi.logout',
  'hasPermission',
  'hasAnyPermission',
  'hasFactoryScope',
  'matchingGrants',
  'matchingEffectiveAccess',
  'can',
  'authorizationVersion',
  'effectiveAccess',
  'refreshSession',
  'authzMode',
  'canAny',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

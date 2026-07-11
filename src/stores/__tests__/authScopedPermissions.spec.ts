import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AuthMeResponse } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

function session(overrides: Partial<AuthMeResponse> = {}): AuthMeResponse {
  return {
    id: 'user-1',
    username: 'engineer',
    display_name: '工程师',
    roles: ['工程师'],
    permissions: ['maintenance:update', 'system:user_manage'],
    factory_scopes: ['huaxing'],
    department_scopes: ['engineering'],
    grants: [{
      role_id: 'engineer',
      role_code: 'engineer',
      role_name: '工程师',
      factory_id: 'huaxing',
      department: 'engineering',
      permissions: ['maintenance:update'],
      data_scope: 'department',
    }],
    authz_mode: 'legacy',
    force_password_change: false,
    ...overrides,
  }
}

describe('authStore scoped permission decisions', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('keeps the legacy flat permission plus factory-scope behavior', () => {
    const store = useAuthStore()
    store.applySession(session())

    expect(store.can('maintenance:update', 'huaxing', 'engineering')).toBe(true)
    expect(store.can('maintenance:update', 'huaxing', 'qa')).toBe(true)
    expect(store.can('maintenance:update', 'huadeng', 'engineering')).toBe(false)
    expect(store.matchingGrants('maintenance:update', 'huaxing', 'engineering')).toHaveLength(1)
  })

  it('uses the effective access snapshot and gives a scoped deny priority', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'enforce',
      effective_access: [
        {
          permission_code: 'maintenance:update',
          factory_id: 'huaxing',
          department: 'engineering',
          effect: 'allow',
          allowed: true,
          source_type: 'role',
          source_ids: ['engineer'],
        },
        {
          permission_code: 'maintenance:update',
          factory_id: 'huaxing',
          department: 'engineering',
          effect: 'deny',
          allowed: false,
          source_type: 'override',
          source_ids: ['override-1'],
        },
        {
          permission_code: 'system:user_manage',
          factory_id: 'huadeng',
          department: 'engineering',
          effect: 'allow',
          allowed: true,
          source_type: 'role',
          source_ids: ['factory-manager'],
        },
      ],
    }))

    expect(store.can('maintenance:update', 'huaxing', 'engineering')).toBe(false)
    expect(store.can('maintenance:update', 'huaxing')).toBe(false)
    expect(store.can('system:user_manage')).toBe(true)
    expect(store.can('maintenance:update', 'huaxing', 'qa')).toBe(false)
  })

  it('treats an explicitly empty effective snapshot as default deny', () => {
    const store = useAuthStore()
    store.applySession(session({ authz_mode: 'enforce', effective_access: [] }))

    expect(store.hasPermission('maintenance:update')).toBe(true)
    expect(store.can('maintenance:update', 'huaxing', 'engineering')).toBe(false)
  })

  it('lets the protected wildcard administrator access newly registered permissions', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'enforce',
      permissions: [],
      effective_access: [],
      grants: [{
        role_id: 'admin',
        role_code: 'admin',
        role_name: '集团超级管理员',
        factory_id: '*',
        department: '*',
        permissions: [],
        data_scope: 'global',
      }],
    }))

    expect(store.can('new_module:manage', 'huaxing', 'engineering')).toBe(true)
  })

  it('recognizes the legacy protected administrator system department binding', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'enforce',
      permissions: [],
      effective_access: [],
      grants: [{
        role_id: 'admin',
        role_code: 'admin',
        role_name: '集团超级管理员',
        factory_id: '*',
        department: 'system',
        permissions: [],
        data_scope: 'global',
      }],
    }))

    expect(store.can('new_module:manage', 'huaxing', 'engineering')).toBe(true)
  })

  it.each(['legacy', 'shadow'] as const)('keeps old flat permission and scope checks in %s mode', (authzMode) => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: authzMode,
      effective_access: [{
        permission_code: 'maintenance:update',
        factory_id: 'huaxing',
        department: 'engineering',
        effect: 'deny',
        allowed: false,
        source_type: 'override',
        source_ids: ['deny-1'],
      }],
    }))

    expect(store.can('maintenance:update', 'huaxing', 'engineering')).toBe(true)
    expect(store.can('maintenance:update', 'huaxing', 'qa')).toBe(true)
    expect(store.can('maintenance:update', 'huadeng', 'engineering')).toBe(false)
    expect(store.can('unknown:read', 'huaxing', 'engineering')).toBe(false)
  })

  it('uses canonical effective access instead of flat unions in enforce mode', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'enforce',
      permissions: ['maintenance:update'],
      factory_scopes: ['huaxing'],
      department_scopes: ['engineering'],
      effective_access: [],
    }))

    expect(store.can('maintenance:update', 'huaxing', 'engineering')).toBe(false)
  })

  it('fails closed when enforce mode omits the canonical snapshot', () => {
    const store = useAuthStore()
    store.applySession(session({ authz_mode: 'enforce', effective_access: undefined }))

    expect(store.can('maintenance:update', 'huaxing', 'engineering')).toBe(false)
  })
})

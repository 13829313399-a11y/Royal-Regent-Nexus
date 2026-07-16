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

  it.each(['legacy', 'shadow'] as const)(
    'does not mistake an ordinary role with default scope metadata for a system position in %s mode',
    (authzMode) => {
      const store = useAuthStore()
      store.applySession(session({
        authz_mode: authzMode,
        grants: [{
          role_id: 'engineer',
          role_code: 'engineer',
          role_name: '工程师',
          factory_id: 'huaxing',
          department: 'engineering',
          permissions: ['maintenance:update'],
          scope_mode: 'own_factory',
          read_permission_codes: [],
          unrestricted_department: false,
          data_scope: 'department',
        }],
      }))

      expect(store.can('maintenance:update', 'huaxing', 'qa')).toBe(true)
      expect(store.can('maintenance:update', 'huadeng', 'engineering')).toBe(false)
    },
  )

  it.each(['legacy', 'shadow', 'enforce'] as const)(
    'lets a system position use its permissions across departments in its own factory in %s mode',
    (authzMode) => {
      const store = useAuthStore()
      store.applySession(session({
        authz_mode: authzMode,
        permissions: ['maintenance:update'],
        grants: [{
          role_id: 'position-engineering-engineer',
          role_code: 'position_engineering_engineer',
          role_name: '工程师',
          factory_id: 'huaxing',
          department: 'engineering',
          permissions: ['maintenance:update'],
          scope_mode: 'own_factory',
          read_permission_codes: [],
          unrestricted_department: true,
          data_scope: 'department',
        }],
        effective_access: authzMode === 'enforce'
          ? [{
              permission_code: 'maintenance:update',
              factory_id: 'huaxing',
              department: 'engineering',
              effect: 'allow',
              allowed: true,
              source_type: 'role_binding',
              source_ids: ['position-binding'],
            }]
          : undefined,
      }))

      expect(store.can('maintenance:update', 'huaxing', 'engineering')).toBe(true)
      expect(store.can('maintenance:update', 'huaxing', 'qa')).toBe(true)
      expect(store.can('maintenance:update', 'huadeng', 'engineering')).toBe(false)
    },
  )

  it.each(['legacy', 'shadow', 'enforce'] as const)(
    'limits cross-factory-read positions to their declared read permissions in %s mode',
    (authzMode) => {
      const store = useAuthStore()
      store.applySession(session({
        authz_mode: authzMode,
        permissions: ['maintenance:read', 'maintenance:update'],
        factory_scopes: ['*'],
        grants: [{
          role_id: 'position-engineering-engineer',
          role_code: 'position_engineering_engineer',
          role_name: '工程师',
          factory_id: 'huaxing',
          department: 'engineering',
          permissions: ['maintenance:read', 'maintenance:update'],
          scope_mode: 'cross_factory_read',
          read_permission_codes: ['maintenance:read'],
          unrestricted_department: true,
          data_scope: 'all',
        }],
        effective_access: authzMode === 'enforce'
          ? [
              {
                permission_code: 'maintenance:read',
                factory_id: 'huaxing',
                department: 'engineering',
                effect: 'allow',
                allowed: true,
                source_type: 'role_binding',
                source_ids: ['position-binding'],
              },
              {
                permission_code: 'maintenance:update',
                factory_id: 'huaxing',
                department: 'engineering',
                effect: 'allow',
                allowed: true,
                source_type: 'role_binding',
                source_ids: ['position-binding'],
              },
            ]
          : undefined,
      }))

      expect(store.can('maintenance:read', 'huadeng', 'qa')).toBe(true)
      expect(store.can('maintenance:update', 'huaxing', 'qa')).toBe(true)
      expect(store.can('maintenance:update', 'huadeng', 'engineering')).toBe(false)
      expect(store.matchingGrants('maintenance:read', 'huadeng', 'qa')).toHaveLength(1)
      expect(store.matchingGrants('maintenance:update', 'huadeng', 'qa')).toHaveLength(0)
    },
  )

  it.each(['legacy', 'shadow', 'enforce'] as const)(
    'lets cross-factory-operate positions use every selected permission across factories in %s mode',
    (authzMode) => {
      const store = useAuthStore()
      store.applySession(session({
        authz_mode: authzMode,
        permissions: ['maintenance:read', 'maintenance:update'],
        factory_scopes: ['*'],
        grants: [{
          role_id: 'position-engineering-manager',
          role_code: 'position_engineering_manager',
          role_name: '经理',
          factory_id: 'huaxing',
          department: 'engineering',
          permissions: ['maintenance:read', 'maintenance:update'],
          scope_mode: 'cross_factory_operate',
          read_permission_codes: ['maintenance:read'],
          unrestricted_department: true,
          data_scope: 'all',
        }],
        effective_access: authzMode === 'enforce'
          ? [
              {
                permission_code: 'maintenance:read',
                factory_id: 'huaxing',
                department: 'engineering',
                effect: 'allow',
                allowed: true,
                source_type: 'role_binding',
                source_ids: ['position-binding'],
              },
              {
                permission_code: 'maintenance:update',
                factory_id: 'huaxing',
                department: 'engineering',
                effect: 'allow',
                allowed: true,
                source_type: 'role_binding',
                source_ids: ['position-binding'],
              },
            ]
          : undefined,
      }))

      expect(store.can('maintenance:read', 'huadeng', 'qa')).toBe(true)
      expect(store.can('maintenance:update', 'huadeng', 'qa')).toBe(true)
    },
  )

  it('does not let a wildcard system-position binding bypass its configured scope mode', () => {
    const store = useAuthStore()
    const applyPosition = (scopeMode: 'own_factory' | 'cross_factory_read' | 'cross_factory_operate') => {
      store.applySession(session({
        authz_mode: 'legacy',
        permissions: ['maintenance:read', 'maintenance:update'],
        grants: [{
          role_id: 'position_engineering_engineer',
          role_code: 'position_engineering_engineer',
          role_name: '工程师',
          factory_id: '*',
          department: '*',
          permissions: ['maintenance:read', 'maintenance:update'],
          scope_mode: scopeMode,
          read_permission_codes: ['maintenance:read'],
          unrestricted_department: true,
          data_scope: 'all',
        }],
      }))
    }

    applyPosition('own_factory')
    expect(store.can('maintenance:read', 'huadeng', 'qa')).toBe(false)
    expect(store.can('maintenance:update', 'huadeng', 'qa')).toBe(false)

    applyPosition('cross_factory_read')
    expect(store.can('maintenance:read', 'huadeng', 'qa')).toBe(true)
    expect(store.can('maintenance:update', 'huadeng', 'qa')).toBe(false)

    applyPosition('cross_factory_operate')
    expect(store.can('maintenance:read', 'huadeng', 'qa')).toBe(true)
    expect(store.can('maintenance:update', 'huadeng', 'qa')).toBe(true)
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

  it('passes factory and department scope through canAny decisions', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'enforce',
      effective_access: [{
        permission_code: 'molding_sample:cross_factory_read',
        factory_id: '*',
        department: 'engineering',
        effect: 'allow',
        allowed: true,
        source_type: 'role',
        source_ids: ['group-molding-sample-viewer'],
      }],
    }))

    expect(store.canAny(
      ['molding_sample:read', 'molding_sample:cross_factory_read'],
      'huadeng',
      'engineering',
    )).toBe(true)
    expect(store.canAny(
      ['molding_sample:read', 'molding_sample:cross_factory_read'],
      'huadeng',
      'production',
    )).toBe(false)
  })

  it('does not let a wildcard default deny hide an exact scoped role allow', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'enforce',
      grants: [
        {
          role_id: 'group-molding-readonly',
          role_code: 'group-molding-readonly',
          role_name: '集团啤办只读',
          factory_id: '*',
          department: '*',
          permissions: ['molding_sample:cross_factory_read'],
          data_scope: 'all',
        },
        {
          role_id: 'engineer',
          role_code: 'engineer',
          role_name: '工程师',
          factory_id: 'huaxing',
          department: 'engineering',
          permissions: ['molding_sample:create'],
          data_scope: 'department',
        },
      ],
      effective_access: [
        {
          permission_code: 'molding_sample:create',
          factory_id: '*',
          department: '*',
          effect: 'deny',
          allowed: false,
          source_type: 'default',
          source_ids: [],
        },
        {
          permission_code: 'molding_sample:create',
          factory_id: 'huaxing',
          department: 'engineering',
          effect: 'allow',
          allowed: true,
          source_type: 'role_binding',
          source_ids: ['engineer-binding'],
        },
      ],
    }))

    expect(store.can('molding_sample:create', 'huaxing', 'engineering')).toBe(true)
    expect(store.can('molding_sample:create', 'huadeng', 'engineering')).toBe(false)
  })

  it('keeps an explicit wildcard user deny above an exact scoped role allow', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'enforce',
      effective_access: [
        {
          permission_code: 'molding_sample:create',
          factory_id: '*',
          department: '*',
          effect: 'deny',
          allowed: false,
          source_type: 'user_override',
          source_ids: ['deny-create'],
        },
        {
          permission_code: 'molding_sample:create',
          factory_id: 'huaxing',
          department: 'engineering',
          effect: 'allow',
          allowed: true,
          source_type: 'role_binding',
          source_ids: ['engineer-binding'],
        },
      ],
    }))

    expect(store.can('molding_sample:create', 'huaxing', 'engineering')).toBe(false)
  })

  it('keeps a home-factory deny local while a scoped position still allows another factory', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'enforce',
      permissions: ['maintenance:read'],
      grants: [{
        role_id: 'position_engineering_engineer',
        role_code: 'position_engineering_engineer',
        role_name: '工程师',
        factory_id: 'huaxing',
        department: 'engineering',
        permissions: ['maintenance:read'],
        scope_mode: 'cross_factory_read',
        read_permission_codes: ['maintenance:read'],
        unrestricted_department: true,
        data_scope: 'all',
      }],
      effective_access: [{
        permission_code: 'maintenance:read',
        factory_id: 'huaxing',
        department: 'engineering',
        effect: 'deny',
        allowed: false,
        source_type: 'user_override',
        source_ids: ['deny-home-read'],
      }],
    }))

    expect(store.can('maintenance:read', 'huaxing', 'engineering')).toBe(false)
    expect(store.can('maintenance:read', 'huadeng', 'qa')).toBe(true)
    expect(store.can('maintenance:read')).toBe(true)
  })

  it('keeps a wildcard explicit deny above an anywhere permission summary', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'enforce',
      permissions: ['maintenance:read'],
      effective_access: [{
        permission_code: 'maintenance:read',
        factory_id: '*',
        department: '*',
        effect: 'deny',
        allowed: false,
        source_type: 'user_override',
        source_ids: ['deny-all-read'],
      }],
    }))

    expect(store.can('maintenance:read')).toBe(false)
  })
})

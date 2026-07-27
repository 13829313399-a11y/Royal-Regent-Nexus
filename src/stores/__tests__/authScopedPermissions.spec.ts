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
    'expands only production-task read for an own-factory system position in %s mode',
    (authzMode) => {
      const store = useAuthStore()
      store.applySession(session({
        authz_mode: authzMode,
        permissions: ['molding_sample:production_read', 'carton_mark:read'],
        factory_scopes: ['huaxing', '*'],
        grants: [{
          role_id: 'position_qa_clerk',
          role_code: 'position_qa_clerk',
          role_name: 'QA文员',
          factory_id: 'huaxing',
          department: 'qa',
          permissions: ['molding_sample:production_read', 'carton_mark:read'],
          scope_mode: 'own_factory',
          read_permission_codes: ['molding_sample:production_read', 'carton_mark:read'],
          unrestricted_department: true,
          data_scope: 'department',
        }],
        effective_access: authzMode === 'enforce'
          ? [
              {
                permission_code: 'molding_sample:production_read',
                factory_id: 'huaxing',
                department: 'qa',
                effect: 'allow',
                allowed: true,
                source_type: 'role_binding',
                source_ids: ['position-qa-clerk'],
              },
              {
                permission_code: 'carton_mark:read',
                factory_id: 'huaxing',
                department: 'qa',
                effect: 'allow',
                allowed: true,
                source_type: 'role_binding',
                source_ids: ['position-qa-clerk'],
              },
            ]
          : undefined,
      }))

      expect(store.can('molding_sample:production_read', 'huaxing', 'production')).toBe(true)
      expect(store.can('molding_sample:production_read', 'huadeng', 'production')).toBe(true)
      expect(store.can('carton_mark:read', 'huaxing', 'qa')).toBe(true)
      expect(store.can('carton_mark:read', 'huadeng', 'qa')).toBe(false)
      expect(store.can('molding_sample:production_fillback', 'huaxing', 'production')).toBe(false)
      expect(store.can('molding_sample:production_fillback', 'huadeng', 'production')).toBe(false)
    },
  )

  it.each(['legacy', 'shadow', 'enforce'] as const)(
    'lets fixed sales positions read other factories but initiate quotes only for their home factory and department in %s mode',
    (authzMode) => {
      const store = useAuthStore()
      const permissions = [
        'internal_quote:read',
        'internal_quote:create',
        'internal_quote:clone',
      ]
      store.applySession(session({
        authz_mode: authzMode,
        permissions,
        factory_scopes: ['*'],
        department_scopes: ['sales-business'],
        grants: [{
          role_id: 'position_sales_business',
          role_code: 'position_sales_business',
          role_name: '业务',
          factory_id: 'huaxing',
          department: 'sales-business',
          permissions,
          scope_mode: 'cross_factory_read',
          read_permission_codes: ['internal_quote:read'],
          unrestricted_department: true,
          data_scope: 'all',
        }],
        effective_access: authzMode === 'enforce'
          ? permissions.map((permission) => ({
              permission_code: permission,
              factory_id: 'huaxing',
              department: 'sales-business',
              effect: 'allow' as const,
              allowed: true,
              source_type: 'role_binding',
              source_ids: ['sales-position-binding'],
            }))
          : undefined,
      }))

      expect(store.can('internal_quote:read', 'huadeng', 'sales-business')).toBe(true)
      expect(store.can('internal_quote:create', 'huaxing', 'sales-business')).toBe(true)
      expect(store.can('internal_quote:clone', 'huaxing', 'sales-business')).toBe(true)
      expect(store.can('internal_quote:create', 'huaxing', 'engineering')).toBe(false)
      expect(store.can('internal_quote:clone', 'huaxing', 'engineering')).toBe(false)
      expect(store.can('internal_quote:create', 'huadeng', 'sales-business')).toBe(false)
      expect(store.can('internal_quote:clone', 'huadeng', 'sales-business')).toBe(false)
    },
  )

  it.each(['legacy', 'shadow'] as const)(
    'keeps valid custom quote grants additive beside a fixed sales position in %s mode',
    (authzMode) => {
      const store = useAuthStore()
      const permissions = ['internal_quote:read', 'internal_quote:create']
      store.applySession(session({
        authz_mode: authzMode,
        permissions,
        factory_scopes: ['*'],
        grants: [
          {
            role_id: 'position_sales_business',
            role_code: 'position_sales_business',
            role_name: '业务',
            factory_id: 'huaxing',
            department: 'sales-business',
            permissions,
            scope_mode: 'cross_factory_read',
            read_permission_codes: ['internal_quote:read'],
            unrestricted_department: true,
            data_scope: 'all',
          },
          {
            role_id: 'custom-engineering-creator',
            role_code: 'custom-engineering-creator',
            role_name: '工程建单补充授权',
            factory_id: 'huaxing',
            department: 'engineering',
            permissions: ['internal_quote:create'],
            unrestricted_department: false,
            data_scope: 'department',
          },
          {
            role_id: 'custom-huadeng-sales-creator',
            role_code: 'custom-huadeng-sales-creator',
            role_name: '华登业务建单补充授权',
            factory_id: 'huadeng',
            department: 'sales-business',
            permissions: ['internal_quote:create'],
            unrestricted_department: false,
            data_scope: 'department',
          },
        ],
      }))

      expect(store.can('internal_quote:create', 'huaxing', 'sales-business')).toBe(true)
      expect(store.can('internal_quote:create', 'huaxing', 'engineering')).toBe(true)
      expect(store.can('internal_quote:create', 'huadeng', 'sales-business')).toBe(true)
      expect(store.can('internal_quote:create', 'huadeng', 'engineering')).toBe(false)
      expect(store.can('internal_quote:create', 'huakang-c', 'sales-business')).toBe(false)
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

  it('keeps cross-factory-read position notifications inside the home factory and department', () => {
    const store = useAuthStore()
    store.applySession(session({
      permissions: ['molding_sample:read', 'molding_sample:notification_read'],
      factory_scopes: ['*'],
      grants: [{
        role_id: 'position_engineering_engineer',
        role_code: 'position_engineering_engineer',
        role_name: '工程师',
        factory_id: 'huaxing',
        department: 'engineering',
        permissions: ['molding_sample:read', 'molding_sample:notification_read'],
        scope_mode: 'cross_factory_read',
        read_permission_codes: ['molding_sample:read', 'molding_sample:notification_read'],
        unrestricted_department: true,
        data_scope: 'all',
      }],
    }))

    expect(store.can('molding_sample:read', 'huadeng', 'engineering')).toBe(true)
    expect(store.can('molding_sample:notification_read', 'huaxing', 'engineering')).toBe(true)
    expect(store.can('molding_sample:notification_read', 'huaxing', 'production')).toBe(false)
    expect(store.can('molding_sample:notification_read', 'huadeng', 'engineering')).toBe(false)
  })

  it('lets a molding supervisor receive cross-factory production notifications only', () => {
    const store = useAuthStore()
    store.applySession(session({
      permissions: ['molding_sample:production_read', 'molding_sample:notification_read'],
      factory_scopes: ['*'],
      grants: [{
        role_id: 'position_molding_supervisor',
        role_code: 'position_molding_supervisor',
        role_name: '啤机主管',
        factory_id: 'huaxing',
        department: 'production',
        permissions: ['molding_sample:production_read', 'molding_sample:notification_read'],
        scope_mode: 'cross_factory_operate',
        read_permission_codes: ['molding_sample:production_read', 'molding_sample:notification_read'],
        unrestricted_department: true,
        data_scope: 'all',
      }],
    }))

    expect(store.can('molding_sample:notification_read', 'huaxing', 'molding')).toBe(true)
    expect(store.can('molding_sample:notification_read', 'huadeng', 'production')).toBe(true)
    expect(store.can('molding_sample:notification_read', 'huadeng', 'engineering')).toBe(false)
  })

  it('keeps the general manager notification scope unrestricted', () => {
    const store = useAuthStore()
    store.applySession(session({
      permissions: ['molding_sample:notification_read'],
      factory_scopes: ['*'],
      grants: [{
        role_id: 'position_general_manager',
        role_code: 'position_general_manager',
        role_name: '总经理',
        factory_id: 'huaxing',
        department: 'management',
        permissions: ['molding_sample:notification_read'],
        scope_mode: 'cross_factory_operate',
        read_permission_codes: ['molding_sample:notification_read'],
        unrestricted_department: true,
        data_scope: 'all',
      }],
    }))

    expect(store.can('molding_sample:notification_read', 'huadeng', 'engineering')).toBe(true)
    expect(store.can('molding_sample:notification_read', 'huadeng', 'production')).toBe(true)
  })

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

  it('requires the explicit injection cross-factory permission and never broadens edit access', () => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: 'legacy',
      permissions: [
        'injection_schedule:read',
        'injection_schedule:edit',
        'injection_schedule:cross_factory_read',
      ],
      grants: [{
        role_id: 'position_molding_planner',
        role_code: 'position_molding_planner',
        role_name: '啤机排产员',
        factory_id: 'huaxing',
        department: 'molding',
        permissions: [
          'injection_schedule:read',
          'injection_schedule:edit',
          'injection_schedule:cross_factory_read',
        ],
        scope_mode: 'cross_factory_read',
        read_permission_codes: [
          'injection_schedule:read',
          'injection_schedule:cross_factory_read',
        ],
        unrestricted_department: true,
        data_scope: 'all',
      }],
      effective_access: [],
    }))

    expect(store.can('injection_schedule:read', 'huaxing', 'molding')).toBe(true)
    expect(store.can('injection_schedule:read', 'huadeng', 'molding')).toBe(false)
    expect(store.can('injection_schedule:cross_factory_read', 'huadeng', 'molding')).toBe(true)
    expect(store.can('injection_schedule:edit', 'huaxing', 'molding')).toBe(true)
    expect(store.can('injection_schedule:edit', 'huadeng', 'molding')).toBe(false)
  })

  it.each(['legacy', 'enforce'] as const)(
    'does not let a cross-factory-operate position broaden injection writes in %s mode',
    (authzMode) => {
    const store = useAuthStore()
    store.applySession(session({
      authz_mode: authzMode,
      permissions: [
        'injection_schedule:read',
        'injection_schedule:edit',
        'injection_schedule:publish',
        'injection_schedule:config',
        'injection_schedule:cross_factory_read',
      ],
      grants: [{
        role_id: 'position_general_manager',
        role_code: 'position_general_manager',
        role_name: '集团总经理',
        factory_id: 'huaxing',
        department: '*',
        permissions: [
          'injection_schedule:read',
          'injection_schedule:edit',
          'injection_schedule:publish',
          'injection_schedule:config',
          'injection_schedule:cross_factory_read',
        ],
        scope_mode: 'cross_factory_operate',
        read_permission_codes: [
          'injection_schedule:read',
          'injection_schedule:cross_factory_read',
        ],
        unrestricted_department: true,
        data_scope: 'all',
      }],
      effective_access: authzMode === 'enforce'
        ? [
            {
              permission_code: 'injection_schedule:read',
              factory_id: '*',
              department: '*',
              effect: 'allow',
              allowed: true,
              source_type: 'role',
              source_ids: ['position_general_manager'],
            },
            {
              permission_code: 'injection_schedule:edit',
              factory_id: '*',
              department: '*',
              effect: 'allow',
              allowed: true,
              source_type: 'role',
              source_ids: ['position_general_manager'],
            },
            {
              permission_code: 'injection_schedule:publish',
              factory_id: '*',
              department: '*',
              effect: 'allow',
              allowed: true,
              source_type: 'role',
              source_ids: ['position_general_manager'],
            },
            {
              permission_code: 'injection_schedule:config',
              factory_id: '*',
              department: '*',
              effect: 'allow',
              allowed: true,
              source_type: 'role',
              source_ids: ['position_general_manager'],
            },
            {
              permission_code: 'injection_schedule:cross_factory_read',
              factory_id: '*',
              department: '*',
              effect: 'allow',
              allowed: true,
              source_type: 'role',
              source_ids: ['position_general_manager'],
            },
          ]
        : [],
    }))

    expect(store.can('injection_schedule:cross_factory_read', 'huadeng', 'molding')).toBe(true)
    expect(store.can('injection_schedule:read', 'huadeng', 'molding')).toBe(false)
    expect(store.can('injection_schedule:edit', 'huadeng', 'molding')).toBe(false)
    expect(store.can('injection_schedule:publish', 'huadeng', 'molding')).toBe(false)
    expect(store.can('injection_schedule:config', 'huadeng', 'molding')).toBe(false)
  })
})

import { defineStore } from 'pinia'
import {
  authApi,
  type AuthEffectiveAccess,
  type AuthGrant,
  type AuthMeResponse,
  type AuthzMode,
  type LoginRequest,
} from '@/api/auth'

function scopeValueMatches(granted: string, requested?: string) {
  return !requested || granted === '*' || granted === requested
}

function grantUsesScopedPositionContract(grant: AuthGrant) {
  return grant.unrestricted_department === true
}

const crossFactoryReadLocalOnlyPermissions = new Set([
  'molding_sample:notification_read',
])

const positionDepartmentAliasGroups = [
  new Set(['production', 'molding']),
  new Set(['pmc-warehouse', 'warehouse']),
]

const positionDepartmentSensitivePermissions = new Set([
  'molding_sample:notification_read',
  'internal_quote:create',
  'internal_quote:clone',
])

function grantDepartmentMatches(grant: AuthGrant, permission: string, department?: string) {
  if (!grant.unrestricted_department) {
    return scopeValueMatches(grant.department, department)
  }
  if (!positionDepartmentSensitivePermissions.has(permission) || !department || department === '*') {
    return true
  }
  if (grant.role_id === 'position_general_manager' || grant.department === '*') {
    return true
  }
  if (grant.department === department) {
    return true
  }
  return positionDepartmentAliasGroups.some((aliases) =>
    aliases.has(grant.department) && aliases.has(department),
  )
}

function grantFactoryMatches(grant: AuthGrant, permission: string, factoryId?: string) {
  if (!factoryId) return true

  if (grant.scope_mode === 'cross_factory_operate') return true
  if (
    grant.scope_mode === 'cross_factory_read'
    && (grant.read_permission_codes ?? []).includes(permission)
    && !crossFactoryReadLocalOnlyPermissions.has(permission)
  ) {
    return true
  }

  return grant.factory_id === factoryId
}

function responseStatus(error: unknown) {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined
  const response = (error as { response?: { status?: unknown } }).response
  return typeof response?.status === 'number' ? response.status : undefined
}

export function grantMatchesScope(
  grant: Pick<AuthGrant, 'factory_id' | 'department'>,
  factoryId?: string,
  department?: string,
) {
  return scopeValueMatches(grant.factory_id, factoryId)
    && scopeValueMatches(grant.department, department)
}

export function grantAllowsPermission(
  grant: AuthGrant,
  permission: string,
  factoryId?: string,
  department?: string,
) {
  if (!grant.permissions.includes(permission)) return false
  if (!grantUsesScopedPositionContract(grant)) {
    return grantMatchesScope(grant, factoryId, department)
  }
  return grantFactoryMatches(grant, permission, factoryId)
    && grantDepartmentMatches(grant, permission, department)
}

export function effectiveAccessMatchesScope(
  access: Pick<AuthEffectiveAccess, 'factory_id' | 'department'>,
  factoryId?: string,
  department?: string,
) {
  return scopeValueMatches(access.factory_id, factoryId)
    && scopeValueMatches(access.department, department)
}

interface AuthState {
  currentUser: AuthMeResponse | null
  roles: string[]
  permissions: string[]
  grants: AuthGrant[]
  effectiveAccess: AuthEffectiveAccess[]
  hasEffectiveAccessSnapshot: boolean
  authorizationVersion: number
  authzMode: AuthzMode
  factoryScopes: string[]
  departmentScopes: string[]
  isAuthenticated: boolean
  hasLoadedSession: boolean
  sessionVersion: number
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    currentUser: null,
    roles: [],
    permissions: [],
    grants: [],
    effectiveAccess: [],
    hasEffectiveAccessSnapshot: false,
    authorizationVersion: 0,
    authzMode: 'legacy',
    factoryScopes: [],
    departmentScopes: [],
    isAuthenticated: false,
    hasLoadedSession: false,
    sessionVersion: 0,
  }),
  actions: {
    applySession(user: AuthMeResponse) {
      this.currentUser = user
      this.roles = user.roles ?? []
      this.permissions = user.permissions ?? []
      this.grants = user.grants ?? []
      this.effectiveAccess = user.effective_access ?? []
      this.hasEffectiveAccessSnapshot = Array.isArray(user.effective_access)
      this.authorizationVersion = user.authorization_version ?? 0
      this.authzMode = user.authz_mode ?? 'legacy'
      this.factoryScopes = user.factory_scopes ?? []
      this.departmentScopes = user.department_scopes ?? []
      this.isAuthenticated = true
      this.hasLoadedSession = true
      this.sessionVersion += 1
    },
    clearSession() {
      this.currentUser = null
      this.roles = []
      this.permissions = []
      this.grants = []
      this.effectiveAccess = []
      this.hasEffectiveAccessSnapshot = false
      this.authorizationVersion = 0
      this.authzMode = 'legacy'
      this.factoryScopes = []
      this.departmentScopes = []
      this.isAuthenticated = false
      this.hasLoadedSession = true
      this.sessionVersion += 1
    },
    async login(payload: LoginRequest) {
      const user = await authApi.login(payload)
      this.applySession(user)
      return user
    },
    async ensureSession() {
      if (this.currentUser) {
        return true
      }

      const sessionVersionAtRequestStart = this.sessionVersion

      try {
        const user = await authApi.getMe()
        if (this.sessionVersion !== sessionVersionAtRequestStart) {
          return this.isAuthenticated
        }

        this.applySession(user)
        return true
      } catch {
        if (this.sessionVersion !== sessionVersionAtRequestStart) {
          return this.isAuthenticated
        }

        this.clearSession()
        return false
      }
    },
    async refreshSession() {
      if (!this.isAuthenticated && !this.currentUser) {
        return false
      }

      const sessionVersionAtRequestStart = this.sessionVersion
      try {
        const user = await authApi.getMe()
        if (this.sessionVersion !== sessionVersionAtRequestStart) {
          return this.isAuthenticated
        }

        this.applySession(user)
        return true
      } catch (error) {
        if (this.sessionVersion !== sessionVersionAtRequestStart) {
          return this.isAuthenticated
        }
        if (responseStatus(error) === 401) {
          this.clearSession()
        }
        return false
      }
    },
    async logout() {
      try {
        await authApi.logout()
      } finally {
        this.clearSession()
      }
    },
    hasPermission(permission: string) {
      return this.permissions.includes(permission)
    },
    hasAnyPermission(permissions: string[]) {
      return permissions.some((permission) => this.hasPermission(permission))
    },
    hasFactoryScope(factoryId: string) {
      return this.factoryScopes.includes('*') || this.factoryScopes.includes(factoryId)
    },
    matchingGrants(permission: string, factoryId?: string, department?: string) {
      return this.grants.filter((grant) =>
        grantAllowsPermission(grant, permission, factoryId, department),
      )
    },
    matchingEffectiveAccess(permission: string, factoryId?: string, department?: string) {
      return this.effectiveAccess.filter((access) =>
        access.permission_code === permission
        && effectiveAccessMatchesScope(access, factoryId, department),
      )
    },
    can(permission: string, factoryId?: string, department?: string) {
      const hasWildcardAdmin = this.grants.some((grant) =>
        (grant.role_code === 'admin' || grant.role_id === 'admin')
        && grant.factory_id === '*'
        && ['*', 'system'].includes(grant.department),
      )
      if (hasWildcardAdmin) {
        return true
      }

      if (this.authzMode !== 'enforce') {
        const scopedPositionGrants = this.grants.filter((grant) =>
          grantUsesScopedPositionContract(grant)
          && grant.permissions.includes(permission),
        )
        if (scopedPositionGrants.length) {
          const regularScopedGrants = this.grants.filter((grant) =>
            !grantUsesScopedPositionContract(grant)
            && grant.permissions.includes(permission),
          )
          return scopedPositionGrants.some((grant) =>
            grantAllowsPermission(grant, permission, factoryId, department),
          ) || regularScopedGrants.some((grant) =>
            grantAllowsPermission(grant, permission, factoryId, department),
          )
        }

        const hasLegacyFactoryScope = !factoryId
          || this.factoryScopes.includes('*')
          || this.factoryScopes.includes(factoryId)
        return this.hasPermission(permission) && hasLegacyFactoryScope
      }

      if (!this.hasEffectiveAccessSnapshot) return false

      const matchingAccess = this.matchingEffectiveAccess(permission, factoryId, department)
      if (!factoryId && !department) {
        const permissionWasEvaluated = this.effectiveAccess.some((access) =>
          access.permission_code === permission,
        )
        if (!permissionWasEvaluated) return false

        const hasWildcardExplicitDeny = this.effectiveAccess.some((access) =>
          access.permission_code === permission
          && access.factory_id === '*'
          && access.department === '*'
          && (access.effect === 'deny' || access.allowed === false)
          && ['override', 'user_override', 'inactive_permission', 'inactive_account'].includes(access.source_type),
        )
        return !hasWildcardExplicitDeny && this.hasPermission(permission)
      }

      if (matchingAccess.some((access) =>
        (access.effect === 'deny' || access.allowed === false)
        && ['override', 'user_override', 'inactive_permission', 'inactive_account'].includes(access.source_type),
      )) {
        return false
      }
      if (matchingAccess.some((access) => access.effect === 'allow' && access.allowed !== false)) {
        return true
      }

      const hasCanonicalAnchor = this.effectiveAccess.some((access) =>
        access.permission_code === permission
        && access.effect === 'allow'
        && access.allowed !== false,
      )
      const hasEvaluatedScopedGrantAnchor = this.effectiveAccess.some((access) =>
        access.permission_code === permission,
      ) && this.grants.some((grant) =>
        grantUsesScopedPositionContract(grant)
        && grant.permissions.includes(permission),
      )
      if (!hasCanonicalAnchor && !hasEvaluatedScopedGrantAnchor) return false

      return this.grants.some((grant) =>
        grantUsesScopedPositionContract(grant)
        && grantAllowsPermission(grant, permission, factoryId, department),
      )
    },
    canAny(permissions: string[], factoryId?: string, department?: string) {
      return permissions.some((permission) => this.can(permission, factoryId, department))
    },
  },
})

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
        grant.permissions.includes(permission)
        && grantMatchesScope(grant, factoryId, department),
      )
    },
    matchingEffectiveAccess(permission: string, factoryId?: string, department?: string) {
      return this.effectiveAccess.filter((access) =>
        access.permission_code === permission
        && effectiveAccessMatchesScope(access, factoryId, department),
      )
    },
    can(permission: string, factoryId?: string, department?: string) {
      if (this.authzMode !== 'enforce') {
        const hasLegacyFactoryScope = !factoryId
          || this.factoryScopes.includes('*')
          || this.factoryScopes.includes(factoryId)
        return this.hasPermission(permission) && hasLegacyFactoryScope
      }

      const hasWildcardAdmin = this.grants.some((grant) =>
        (grant.role_code === 'admin' || grant.role_id === 'admin')
        && grant.factory_id === '*'
        && ['*', 'system'].includes(grant.department),
      )
      if (hasWildcardAdmin) {
        return true
      }

      const matchingAccess = this.matchingEffectiveAccess(permission, factoryId, department)
      if (!factoryId && !department) {
        return matchingAccess.some((access) => access.effect === 'allow' && access.allowed !== false)
      }
      if (matchingAccess.some((access) =>
        (access.effect === 'deny' || access.allowed === false)
        && ['override', 'user_override', 'inactive_permission', 'inactive_account'].includes(access.source_type),
      )) {
        return false
      }
      return matchingAccess.some((access) => access.effect === 'allow' && access.allowed !== false)
    },
    canAny(permissions: string[], factoryId?: string, department?: string) {
      return permissions.some((permission) => this.can(permission, factoryId, department))
    },
  },
})

import { defineStore } from 'pinia'
import { authApi, type AuthGrant, type AuthMeResponse, type LoginRequest } from '@/api/auth'

interface AuthState {
  currentUser: AuthMeResponse | null
  roles: string[]
  permissions: string[]
  grants: AuthGrant[]
  factoryScopes: string[]
  departmentScopes: string[]
  isAuthenticated: boolean
  hasLoadedSession: boolean
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    currentUser: null,
    roles: [],
    permissions: [],
    grants: [],
    factoryScopes: [],
    departmentScopes: [],
    isAuthenticated: false,
    hasLoadedSession: false,
  }),
  actions: {
    applySession(user: AuthMeResponse) {
      this.currentUser = user
      this.roles = user.roles
      this.permissions = user.permissions
      this.grants = user.grants
      this.factoryScopes = user.factory_scopes
      this.departmentScopes = user.department_scopes
      this.isAuthenticated = true
      this.hasLoadedSession = true
    },
    clearSession() {
      this.currentUser = null
      this.roles = []
      this.permissions = []
      this.grants = []
      this.factoryScopes = []
      this.departmentScopes = []
      this.isAuthenticated = false
      this.hasLoadedSession = true
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

      try {
        const user = await authApi.getMe()
        this.applySession(user)
        return true
      } catch {
        this.clearSession()
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
  },
})

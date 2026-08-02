import { http } from '../lib/http.js'

export interface AuthHttpClient {
  get<T = unknown>(url: string): Promise<{ data: T }>
  post<T = unknown>(
    url: string,
    data?: unknown,
    config?: { headers?: Record<string, string> },
  ): Promise<{ data: T }>
  delete?<T = unknown>(url: string): Promise<{ data: T }>
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  display_name: string
  password: string
  confirm_password: string
  phone: string
  email: string
  factory_id: string
  department: string
  position: string
}

export interface RegisterResponse {
  status: string
  message: string
}

export interface PasswordResetRequest {
  username: string
  display_name: string
  contact: string
  note: string
}

export interface PasswordResetResponse {
  status: string
  message: string
  request_id?: string | null
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
  confirm_password: string
}

export type AuthGrantScopeMode = 'own_factory' | 'cross_factory_read' | 'cross_factory_operate'

export interface AuthGrant {
  role_id: string
  role_code?: string
  role_name: string
  factory_id: string
  department: string
  permissions: string[]
  scope_mode?: AuthGrantScopeMode
  read_permission_codes?: string[]
  unrestricted_department?: boolean
  data_scope: string
}

export interface AuthEmployeeProfile {
  primary_factory_id: string
  primary_department: string
  position: string
  confirmation_status: string
}

export interface AuthEffectiveAccess {
  permission_code: string
  factory_id: string
  department: string
  effect: 'allow' | 'deny'
  allowed: boolean
  source_type: string
  source_ids: string[]
  source_name?: string
}

export type AuthzMode = 'legacy' | 'shadow' | 'enforce'

export interface AuthMeResponse {
  id: string
  username: string
  display_name: string
  roles: string[]
  permissions: string[]
  factory_scopes: string[]
  department_scopes: string[]
  grants: AuthGrant[]
  authz_mode?: AuthzMode
  profile?: AuthEmployeeProfile | null
  authorization_version?: number
  effective_access?: AuthEffectiveAccess[]
  force_password_change: boolean
  avatar_url?: string
}

export function createAuthApi(client: AuthHttpClient = http) {
  return {
    async login(payload: LoginRequest) {
      const response = await client.post<AuthMeResponse>('/auth/login', payload)
      return response.data
    },
    async register(payload: RegisterRequest) {
      const response = await client.post<RegisterResponse>('/auth/register', payload)
      return response.data
    },
    async requestPasswordReset(payload: PasswordResetRequest) {
      const response = await client.post<PasswordResetResponse>('/auth/password-reset-requests', payload)
      return response.data
    },
    async getMe() {
      const response = await client.get<AuthMeResponse>('/auth/me')
      return response.data
    },
    async changePassword(payload: ChangePasswordRequest) {
      const response = await client.post<AuthMeResponse>('/auth/change-password', payload)
      return response.data
    },
    async uploadAvatar(file: File) {
      const formData = new FormData()
      formData.append('file', file)
      const response = await client.post<AuthMeResponse>('/auth/me/avatar', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return response.data
    },
    async deleteAvatar() {
      if (!client.delete) {
        throw new Error('当前认证客户端不支持删除头像')
      }

      const response = await client.delete<AuthMeResponse>('/auth/me/avatar')
      return response.data
    },
    async logout() {
      const response = await client.post<void>('/auth/logout')
      return response.data
    },
  }
}

export const authApi = createAuthApi()

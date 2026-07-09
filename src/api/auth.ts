import { http } from '../lib/http.js'

export interface AuthHttpClient {
  get<T = unknown>(url: string): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
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
}

export interface AuthGrant {
  role_id: string
  role_name: string
  factory_id: string
  department: string
  permissions: string[]
  data_scope: string
}

export interface AuthMeResponse {
  id: string
  username: string
  display_name: string
  roles: string[]
  permissions: string[]
  factory_scopes: string[]
  department_scopes: string[]
  grants: AuthGrant[]
  force_password_change: boolean
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
    async logout() {
      const response = await client.post<void>('/auth/logout')
      return response.data
    },
  }
}

export const authApi = createAuthApi()

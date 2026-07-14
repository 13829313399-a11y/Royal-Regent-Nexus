import { http } from '../lib/http.js'

export interface SystemHttpClient {
  get<T = unknown>(url: string): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
  patch<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
}

export interface RoleAssignmentRequest {
  role_id: string
  factory_id: string
  department: string
}

export interface RegistrationApproveRequest {
  role_assignments: RoleAssignmentRequest[]
  review_comment?: string
  position?: string
}

export interface RegistrationRejectRequest {
  review_comment: string
}

export interface UserStatusUpdateRequest {
  status: 'active' | 'suspended'
}

export interface UserPasswordResetRequest {
  temporary_password: string
  notification_id?: string
}

export interface SystemNotificationUpdateRequest {
  status: 'read' | 'handled'
}

export interface RoleResponse {
  id: string
  code: string
  name: string
  description: string
  applicable_departments: string[]
  requires_global_factory: boolean
  scope_guidance: string
}

export interface UserRoleAssignmentResponse {
  id: string
  role_id: string
  role_name: string
  role_code: string
  factory_id: string
  department: string
}

export interface RegistrationRequestResponse {
  id: string
  user_id: string
  username: string
  display_name: string
  phone: string
  email: string
  factory_id: string
  department: string
  position: string
  status: string
  reviewer_user_id: string
  review_comment: string
  submitted_at: string
  reviewed_at: string
  created_at: string
  updated_at: string
  recommended_role_ids: string[]
}

export interface UserResponse {
  id: string
  username: string
  display_name: string
  phone: string
  email: string
  status: string
  force_password_change: boolean
  last_login_at: string
  created_at: string
  updated_at: string
  roles: UserRoleAssignmentResponse[]
  avatar_url?: string
}

export interface SystemNotificationResponse {
  id: string
  target_user_id: string
  target_permission: string
  target_factory_id: string
  type: string
  title: string
  message: string
  payload: Record<string, unknown>
  status: string
  created_at: string
  read_at: string
  handled_at: string
}

export function createSystemApi(client: SystemHttpClient = http) {
  return {
    async listNotifications() {
      const response = await client.get<SystemNotificationResponse[]>('/system/notifications')
      return response.data
    },
    async updateNotification(notificationId: string, payload: SystemNotificationUpdateRequest) {
      const response = await client.patch<SystemNotificationResponse>(`/system/notifications/${notificationId}`, payload)
      return response.data
    },
    async listRegistrationRequests(status = 'pending') {
      const response = await client.get<RegistrationRequestResponse[]>(`/system/registration-requests?status=${encodeURIComponent(status)}`)
      return response.data
    },
    async approveRegistrationRequest(requestId: string, payload: RegistrationApproveRequest) {
      const response = await client.post<RegistrationRequestResponse>(`/system/registration-requests/${requestId}/approve`, payload)
      return response.data
    },
    async rejectRegistrationRequest(requestId: string, payload: RegistrationRejectRequest) {
      const response = await client.post<RegistrationRequestResponse>(`/system/registration-requests/${requestId}/reject`, payload)
      return response.data
    },
    async listUsers(status = '') {
      const suffix = status ? `?status=${encodeURIComponent(status)}` : ''
      const response = await client.get<UserResponse[]>(`/system/users${suffix}`)
      return response.data
    },
    async updateUserStatus(userId: string, payload: UserStatusUpdateRequest) {
      const response = await client.patch<UserResponse>(`/system/users/${userId}/status`, payload)
      return response.data
    },
    async resetUserPassword(userId: string, payload: UserPasswordResetRequest) {
      const response = await client.post<UserResponse>(`/system/users/${userId}/reset-password`, payload)
      return response.data
    },
    async listRoles() {
      const response = await client.get<RoleResponse[]>('/system/roles')
      return response.data
    },
  }
}

export const systemApi = createSystemApi()

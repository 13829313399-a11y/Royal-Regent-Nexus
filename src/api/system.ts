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

export interface RegistrationProfileRequest {
  display_name: string
  phone: string
  email: string
  factory_id: string
  department: string
  position: string
}

export interface RegistrationApproveRequest {
  system_position_role_id: string
  profile: RegistrationProfileRequest
  review_comment?: string
  /** @deprecated Compatibility only. New approval screens must not send this field. */
  role_assignments?: RoleAssignmentRequest[]
  /** @deprecated Compatibility only. Use profile.position. */
  position?: string
}

export interface RegistrationRejectRequest {
  review_comment: string
}

export interface UserStatusUpdateRequest {
  status: 'active' | 'suspended'
}

export type PasswordResetStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'completed'
  | 'expired'
  | 'legacy_invalid'

export interface PasswordResetReviewRequest {
  review_comment: string
  identity_verified?: boolean
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
  is_system_position: boolean
  position_department: string
  position_department_name: string
  position_sort_order: number
  permission_count: number
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
  primary_factory_id?: string
  primary_department?: string
  position?: string
  system_position_role_id?: string
  system_position_role_name?: string
}

export interface SystemNotificationResponse {
  id: string
  target_user_id: string
  target_permission: string
  target_factory_id: string
  target_department?: string
  type: string
  title: string
  message: string
  payload: Record<string, unknown>
  status: string
  created_at: string
  read_at: string
  handled_at: string
}

export interface PasswordResetMatchedUser {
  id: string
  username: string
  display_name: string
  status: string
  factory_id: string
  department: string
  position: string
  phone: string
  email: string
}

export interface PasswordResetRequestDetail {
  id: string
  user_id?: string | null
  username: string
  display_name: string
  contact: string
  note: string
  factory_id: string
  department: string
  status: PasswordResetStatus
  reviewer_user_id?: string | null
  review_comment: string
  notification_id?: string | null
  submitted_at: string
  approved_at: string
  expires_at: string
  completed_at: string
  rejected_at: string
  created_at: string
  updated_at: string
  issue_count: number
  matched_user?: PasswordResetMatchedUser | null
  match_checks: Record<string, boolean>
}

export interface PasswordResetApproveResponse {
  request: PasswordResetRequestDetail
  expires_at: string
  message: string
}

export interface SystemNotificationFilters {
  changed_after?: string
}

export function createSystemApi(client: SystemHttpClient = http) {
  return {
    async listNotifications(filters: SystemNotificationFilters = {}) {
      const params = new URLSearchParams()
      if (filters.changed_after) {
        params.set('changed_after', filters.changed_after)
      }
      const query = params.toString()
      const response = await client.get<SystemNotificationResponse[]>(
        query ? `/system/notifications?${query}` : '/system/notifications',
      )
      return response.data
    },
    async updateNotification(notificationId: string, payload: SystemNotificationUpdateRequest) {
      const response = await client.patch<SystemNotificationResponse>(`/system/notifications/${notificationId}`, payload)
      return response.data
    },
    async listPasswordResetRequests(status: PasswordResetStatus = 'pending') {
      const response = await client.get<PasswordResetRequestDetail[]>(
        `/system/password-reset-requests?status=${encodeURIComponent(status)}`,
      )
      return response.data
    },
    async getPasswordResetRequest(requestId: string) {
      const response = await client.get<PasswordResetRequestDetail>(
        `/system/password-reset-requests/${encodeURIComponent(requestId)}`,
      )
      return response.data
    },
    async approvePasswordResetRequest(requestId: string, payload: PasswordResetReviewRequest) {
      const response = await client.post<PasswordResetApproveResponse>(
        `/system/password-reset-requests/${encodeURIComponent(requestId)}/approve`,
        payload,
      )
      return response.data
    },
    async rejectPasswordResetRequest(requestId: string, payload: PasswordResetReviewRequest) {
      const response = await client.post<PasswordResetRequestDetail>(
        `/system/password-reset-requests/${encodeURIComponent(requestId)}/reject`,
        payload,
      )
      return response.data
    },
    async reissuePasswordResetRequest(requestId: string, payload: PasswordResetReviewRequest) {
      const response = await client.post<PasswordResetApproveResponse>(
        `/system/password-reset-requests/${encodeURIComponent(requestId)}/reissue`,
        payload,
      )
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
    async listRoles() {
      const response = await client.get<RoleResponse[]>('/system/roles')
      return response.data
    },
    async listSystemPositions() {
      const response = await client.get<RoleResponse[]>('/system/positions')
      return response.data
    },
  }
}

export const systemApi = createSystemApi()

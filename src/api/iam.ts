import { http } from '../lib/http.js'

export interface IamHttpClient {
  get<T = unknown>(url: string): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }>
}

export type PermissionRiskLevel = 'normal' | 'high'
export type PermissionScopeType = 'global' | 'factory' | 'department' | 'factory_department'
export type PermissionEffect = 'allow' | 'deny'
export type PermissionDraftEffect = PermissionEffect | 'inherit'

export interface PermissionCatalogItem {
  code: string
  name: string
  description?: string
  module_code: string
  module_name: string
  action: string
  risk_level: PermissionRiskLevel
  scope_type: PermissionScopeType
  status: 'active' | 'inactive'
  sort_order: number
  applicable_departments: string[]
  requires_global_factory: boolean
  scope_guidance: string
}

export interface ManageableScope {
  factory_id: string
  factory_name: string
  department: string
  department_name: string
}

export interface ManageableScopesResponse {
  is_super_admin: boolean
  can_manage_role_templates: boolean
  can_review_access_requests: boolean
  scopes: ManageableScope[]
}

export interface IamUserSummary {
  id: string
  username: string
  display_name: string
  status: string
  phone?: string
  email?: string
  primary_factory_id?: string
  primary_department?: string
  position?: string
  manageable?: boolean
}

export interface EmployeeProfile {
  primary_factory_id: string
  primary_department: string
  position: string
  confirmation_status: string
}

export interface RoleBinding {
  id: string
  role_id: string
  role_code: string
  role_name: string
  factory_id: string
  department: string
  state: 'active' | 'suspended' | 'revoked'
  source_type: string
  valid_from?: string | null
  valid_until?: string | null
}

export interface UserPermissionOverride {
  id: string
  permission_code: string
  effect: PermissionEffect
  factory_id: string
  department: string
  state: 'active' | 'suspended' | 'revoked'
  valid_from?: string | null
  valid_until?: string | null
  reason?: string
}

export interface EffectiveAccessEntry {
  permission_code: string
  factory_id: string
  department: string
  effect: PermissionEffect
  allowed: boolean
  source_type: string
  source_ids: string[]
  source_name?: string
}

export interface UserAccessResponse {
  user: IamUserSummary
  profile: EmployeeProfile | null
  authorization_version: number
  role_bindings: RoleBinding[]
  overrides: UserPermissionOverride[]
  effective_access: EffectiveAccessEntry[]
  system_position_role_id: string
  system_position_role_name: string
  recommended_system_position_role_id: string
  legacy_role_count: number
  active_override_count: number
  cleanup_role_count: number
  cleanup_override_count: number
}

export interface RoleBindingDraft {
  operation: 'add' | 'update' | 'revoke'
  binding_id?: string
  role_id?: string
  factory_id: string
  department: string
  valid_until?: string | null
}

export interface PermissionOverrideDraft {
  permission_code: string
  effect: PermissionDraftEffect
  factory_id: string
  department: string
  valid_until?: string | null
}

export interface UserAccessPreviewRequest {
  base_revision: number
  reason: string
  role_bindings?: RoleBindingDraft[]
  overrides: PermissionOverrideDraft[]
}

export interface PermissionAccessDiff {
  permission_code: string
  factory_id: string
  department: string
  before: PermissionEffect | 'none'
  after: PermissionEffect | 'none'
  before_source?: string
  after_source?: string
  risk_level: PermissionRiskLevel
}

export interface UserAccessPreviewResponse {
  preview_token: string
  base_revision: number
  diffs: PermissionAccessDiff[]
  requires_approval: boolean
  high_risk: boolean
  expires_at?: string
}

export interface AccessCommitResponse {
  status: 'committed' | 'pending_approval'
  authorization_version: number
  request_id?: string
  message?: string
}

export interface RoleSummary {
  id: string
  code: string
  name: string
  description: string
  version: number
  is_protected: boolean
  binding_count: number
  permission_count: number
  applicable_departments: string[]
  requires_global_factory: boolean
  scope_guidance: string
  is_system_position: boolean
  position_department: string
  position_department_name: string
  position_sort_order: number
}

export interface RoleAccessResponse extends RoleSummary {
  permission_codes: string[]
}

export interface RoleAccessPreviewRequest {
  base_version: number
  reason: string
  permission_codes: string[]
}

export interface RolePermissionDiff {
  permission_code: string
  before: boolean
  after: boolean
  risk_level: PermissionRiskLevel
}

export interface RoleAccessPreviewResponse {
  preview_token: string
  base_version: number
  diffs: RolePermissionDiff[]
  affected_user_count: number
  high_risk: boolean
}

export interface UserSystemPositionPreviewRequest {
  base_revision: number
  system_position_role_id: string
  reason?: string
}

export interface UserSystemPositionPreviewResponse {
  preview_token: string
  base_revision: number
  before_role_ids: string[]
  before_role_names: string[]
  after_role_id: string
  after_role_name: string
  removed_role_count: number
  removed_override_count: number
  requires_approval: boolean
  high_risk: boolean
  diffs: PermissionAccessDiff[]
  expires_at?: string
}

function buildQuery(params: Record<string, string | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value) query.set(key, value)
  })
  const value = query.toString()
  return value ? `?${value}` : ''
}

export function createIamApi(client: IamHttpClient = http) {
  return {
    async listPermissions(status = 'active') {
      const response = await client.get<PermissionCatalogItem[]>(`/iam/permissions${buildQuery({ status })}`)
      return response.data
    },
    async getManageableScopes() {
      const response = await client.get<ManageableScopesResponse>('/iam/manageable-scopes')
      return response.data
    },
    async searchUsers(query = '', status = '') {
      const response = await client.get<IamUserSummary[]>(`/iam/users/search${buildQuery({ query, status })}`)
      return response.data
    },
    async getUserAccess(userId: string) {
      const response = await client.get<UserAccessResponse>(`/iam/users/${encodeURIComponent(userId)}/access`)
      return response.data
    },
    async previewUserAccess(userId: string, payload: UserAccessPreviewRequest) {
      const response = await client.post<UserAccessPreviewResponse>(
        `/iam/users/${encodeURIComponent(userId)}/access/preview`,
        payload,
      )
      return response.data
    },
    async commitUserAccess(userId: string, previewToken: string, confirmHighRisk = false) {
      const response = await client.post<AccessCommitResponse>(
        `/iam/users/${encodeURIComponent(userId)}/access/commit`,
        { preview_token: previewToken, confirm_high_risk: confirmHighRisk },
      )
      return response.data
    },
    async previewUserSystemPosition(userId: string, payload: UserSystemPositionPreviewRequest) {
      const response = await client.post<UserSystemPositionPreviewResponse>(
        `/iam/users/${encodeURIComponent(userId)}/system-position/preview`,
        payload,
      )
      return response.data
    },
    async commitUserSystemPosition(userId: string, previewToken: string, confirmHighRisk = false) {
      const response = await client.post<AccessCommitResponse>(
        `/iam/users/${encodeURIComponent(userId)}/system-position/commit`,
        { preview_token: previewToken, confirm_high_risk: confirmHighRisk },
      )
      return response.data
    },
    async listRoles() {
      const response = await client.get<RoleSummary[]>('/iam/roles')
      return response.data
    },
    async listSystemPositions() {
      const response = await client.get<RoleSummary[]>('/iam/system-positions')
      return response.data
    },
    async getRoleAccess(roleId: string) {
      const response = await client.get<RoleAccessResponse>(`/iam/roles/${encodeURIComponent(roleId)}/access`)
      return response.data
    },
    async previewRoleAccess(roleId: string, payload: RoleAccessPreviewRequest) {
      const response = await client.post<RoleAccessPreviewResponse>(
        `/iam/roles/${encodeURIComponent(roleId)}/access/preview`,
        payload,
      )
      return response.data
    },
    async commitRoleAccess(roleId: string, previewToken: string, confirmHighRisk = false) {
      const response = await client.post<AccessCommitResponse>(
        `/iam/roles/${encodeURIComponent(roleId)}/access/commit`,
        { preview_token: previewToken, confirm_high_risk: confirmHighRisk },
      )
      return response.data
    },
  }
}

export const iamApi = createIamApi()

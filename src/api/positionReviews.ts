import { http } from '@/lib/http'
import type { AccessTuple, OrganizationCatalog } from './identity'

export interface Position { org_unit_id: string; department_code: string; position: string }
export interface Declaration extends Position { note: string }
export type ReviewStatus = 'pending' | 'returned' | 'applied' | 'withdrawn' | 'invalidated'
export interface PositionReview {
  id: string; user_id: string; employment_epoch: number; origin: 'employee' | 'admin'; status: ReviewStatus
  revision: number; declaration: Declaration; base_official: Position | null; confirmed_profile: Position | null
  decision: 'apply_package' | 'keep_permissions' | null; review_comment: string; created_at: string; updated_at: string
}
export interface SelfPositionProfile {
  official_position: Position | null; open_review: PositionReview | null; effective_permission_summary: string[]
  can_submit: boolean; blocked_reason: string | null
}
export interface WorkItem {
  item_key: string; kind: 'registration' | 'position'; origin: 'employee' | 'admin'
  user: { id: string; display_name: string; username: string }; source_revision: string; status: string
  before: Position | null; declaration: Declaration; created_at: string; updated_at: string; available_actions: string[]
}
export interface WorkItemDetail extends WorkItem {
  review_comment?: string; confirmed_profile?: Position | null; decision?: string; decision_at?: string
  current_official: Position | null; identity_mode: 'legacy' | 'v2' | 'registration_pending'
  identity_version: number; authorization_version: number; primary_assignment_id: string | null
  current_bindings: { binding_id: string; role_id: string; role_name: string; role_version_id: string | null
    source_type: string; assignment_id: string | null; factory_ids: string[]; department: string; source_review_required: boolean }[]
  independent_allows: { override_id: string; permission_code: string; permission_name: string; factory_id: string; department: string; decision_required: boolean }[]
  explicit_denials: AccessTuple[]; registration_details: RegistrationDetails | null; can_keep_permissions: boolean; blocked_reasons: string[]
}
export interface RegistrationDetails { display_name: string; phone: string; email: string }
export interface BuiltinPackage {
  role_id: string; name: string; department: string; description: string; definition_hash: string
  role_version_id: string | null; assignable: boolean; blocked_reason: string | null; scope_mode: string; capability_summary: string[]
}
export interface FactoryScope { kind: 'home' | 'selected' | 'all_current'; factory_ids: string[] }
export interface PackageSelection {
  role_id: string; definition_hash: string; role_version_id?: string | null; factory_scope: FactoryScope; permission_department: string
}
export interface ReviewDraft {
  expected_source_revision: string; decision: 'apply_package' | 'keep_permissions'; confirmed_profile: Position
  package_selection?: PackageSelection | null
  independent_allow_decisions: { override_id: string; decision: 'keep_original_scope' | 'end' }[]
  registration_details_correction?: RegistrationDetails | null
}
export interface ReviewPreview {
  preview_token: string; expires_at: string; server_now: string; source_revision: string; preview_fingerprint: string
  decision: ReviewDraft['decision']; permission_diffs: { added: AccessTuple[]; removed: AccessTuple[]; retained: AccessTuple[]; source_changed: AccessTuple[] }
  retained_sources: string[]; explicit_denials: AccessTuple[]; high_risk: boolean; requires_independent_approval: boolean
  allowed_to_commit: boolean; blocked_reasons: string[]; handover_summary: string
}
export interface CommitCommand { expected_source_revision: string; preview_token: string; command_id: string; risk_acknowledged: boolean }
export interface DecisionCommand { expected_source_revision: string; command_id: string; action: 'return_position' | 'reject_registration'; reason: string }
export interface ReviewResult {
  command_id: string; status: 'committed'; item_key: string; decision: string; source_status: string; source_revision: string
  target_identity_version: number; target_authorization_version: number; notification_state: 'queued' | 'delivered' | 'retrying'; committed_at: string; message: string
}
const root = '/iam/position-workbench'
const item = (key: string) => `${root}/items/${encodeURIComponent(key)}`
export const positionReviewsApi = {
  profile: async () => (await http.get<SelfPositionProfile>('/auth/me/position-profile')).data,
  catalog: async () => (await http.get<OrganizationCatalog>('/auth/organization-catalog')).data,
  history: async (page = 1) => (await http.get<{ items: PositionReview[]; total: number }>('/auth/me/position-reviews', { params: { page } })).data,
  submit: async (declaration: Declaration) => (await http.post<{ changed: boolean; review: PositionReview | null; message: string }>('/auth/me/position-reviews', { declaration })).data,
  edit: async (review: PositionReview, declaration: Declaration) => (await http.patch<{ changed: boolean; review: PositionReview; message: string }>(`/auth/me/position-reviews/${review.id}`, { expected_revision: review.revision, declaration })).data,
  withdraw: async (review: PositionReview) => (await http.post<{ review: PositionReview; message: string }>(`/auth/me/position-reviews/${review.id}/withdraw`, { expected_revision: review.revision })).data,
  queue: async (params: Record<string, string | number>) => (await http.get<{ items: WorkItem[]; total: number; actionable_total: number; routing_attention: boolean }>(`${root}/queue`, { params })).data,
  detail: async (key: string) => (await http.get<WorkItemDetail>(item(key))).data,
  packages: async (params: { item_key?: string; org_unit_id?: string; department_code?: string; scope_kind?: string; factory_ids?: string[] } = {}) =>
    (await http.get<{ items: BuiltinPackage[]; catalog_revision: string }>(`${root}/packages`, { params, paramsSerializer: { indexes: null } })).data,
  preview: async (key: string, draft: ReviewDraft) => (await http.post<ReviewPreview>(`${item(key)}/preview`, draft)).data,
  commit: async (key: string, command: CommitCommand) => (await http.post<ReviewResult>(`${item(key)}/commit`, command)).data,
  decide: async (key: string, command: DecisionCommand) => (await http.post<ReviewResult>(`${item(key)}/decision`, command)).data,
  receipt: async (id: string) => (await http.get<{ command_id: string; status: 'committed' | 'not_observed'; result: ReviewResult | null }>(`${root}/receipts/${id}`)).data,
  adjust: async (target_user_id: string, proposed_profile: Position) => (await http.post<{ item_key: string; review: PositionReview; reused: boolean }>(`${root}/admin-adjustments`, { target_user_id, proposed_profile, reason: '管理员核对岗位与权限' })).data,
}
export const positionStatus: Record<string, string> = { pending: '待分配', returned: '待补充', applied: '已完成', approved: '已通过', rejected: '已拒绝', withdrawn: '已撤回', invalidated: '已失效' }

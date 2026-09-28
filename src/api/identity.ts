import { http } from '@/lib/http'
import type { RoleBinding, UserPermissionOverride } from '@/api/iam'

export interface Assignment {
  id: string; org_unit_id: string; org_name: string; factory_id: string; department_code: string
  official_position_title: string; assignment_type: string; is_primary: boolean
  valid_from: string; valid_until: string | null; state: string; revision: number; source_request_id: string | null
}
export interface IdentityContext {
  confirmation_status?: string
  identity_mode: 'legacy' | 'v2'; identity_version: number; employment_epoch: number; employment_status: string
  primary_assignment: Assignment | null; active_assignments_summary: Assignment[]; assignments: Assignment[]
  primary_factory_id: string; primary_department: string; position: string
  server_now: string; next_transition_at: string | null; effective_context_key: string
}
export interface PersonIdentity extends IdentityContext {
  id: string; display_name: string; status: string; authorization_version: number
  role_bindings: RoleBinding[]; overrides: UserPermissionOverride[]; handover: HandoverSummary
}
export interface Person {
  id: string; display_name: string; username: string; status: string; primary_factory_id: string
  primary_org_unit_id?: string; primary_department: string; position: string; identity_mode: string; employment_status: string; identity_version: number
}
export interface Organization { id: string; name: string; kind: string; factory_id: string; status: string; departments: { code: string; name: string }[] }
export interface OrganizationCatalog { can_manage_delegations?: boolean; organizations: Organization[]; writes_enabled: boolean; scheduling_enabled: boolean; authz_mode: string }
export interface HandoverItem { id: string; resource_id: string; factory_id: string; adapter_key: string; status: string; expected_resource_revision: number; successor_user_id: string | null }
export interface HandoverSummary { count: number; status: string; coverage: { module: string; status: string; basis: string }[] }
export type ChangeKind = 'confirm_identity' | 'primary_assignment_transfer' | 'add_assignment' | 'end_assignment' | 'profile_correction' | 'freeze' | 'unfreeze' | 'leave' | 'rehire' | 'upgrade_packages'
export interface ChangePayload {
  request_type: ChangeKind; target_user_id: string; reason: string; base_identity_version: number; base_authorization_version: number
  source_assignment_id?: string; effective_at?: string; display_name?: string; official_position_title?: string
  new_assignment?: { org_unit_id: string; department_code: string; official_position_title: string; assignment_type: string; is_primary: boolean; valid_until?: string
    role_bindings: { role_id: string; department: string; factory_scope: { kind: string; factory_ids: string[] } }[] }
  binding_dispositions: { binding_id: string; source: string }[]
  exception_decisions: { override_id: string; decision: string }[]
}
export interface ChangeRecord { handover_refresh_pending?: boolean; id: string; target_user_id: string; requester_user_id: string; request_type: ChangeKind; state: string; revision: number; reason: string; effective_at: string; created_at: string; payload: ChangePayload }
export interface AccessTuple { permission_code: string; permission_name?: string; factory_id: string; factory_name?: string; department: string; department_name?: string }
export interface ChangePreview {
  preview_token: string; expires_at: string; request_revision: number; requires_approval: boolean; high_risk: boolean
  before_identity: IdentityContext; after_identity: IdentityContext; effective_at: string
  permission_diffs: { added: AccessTuple[]; removed: AccessTuple[]; retained: AccessTuple[]; source_changed: AccessTuple[] }
  handover_summary: HandoverSummary
}
export const changeLabels: Record<ChangeKind, string> = {
  confirm_identity: '确认正式任职', primary_assignment_transfer: '调厂调岗', add_assignment: '增加兼任 / 支援',
  end_assignment: '结束任职', profile_correction: '更正正式资料', freeze: '冻结账号', unfreeze: '恢复冻结账号',
  leave: '办理离职', rehire: '重新确认复职', upgrade_packages: '升级权限包',
}
export const stateLabels: Record<string, string> = { draft: '草稿', pending_approval: '待有权管理员审核', scheduled: '已预约', applied: '已生效', rejected: '已驳回', cancelled: '已撤回', current: '当前任职', ended: '已结束', revoked: '已撤销', active: '在用', suspended: '已冻结', left: '已离职', pending: '待接管', completed: '已接管', manual_review_required: '需人工核实', no_longer_required: '业务已结束', changed_externally: '责任已由业务流程调整' }
export const identityApi = {
  catalog: async () => (await http.get<OrganizationCatalog>('/system/organization-catalog')).data,
  people: async (params: Record<string, string | number>) => (await http.get<{ total: number; items: Person[] }>('/system/people', { params })).data,
  person: async (id: string) => (await http.get<PersonIdentity>(`/system/users/${id}/identity`)).data,
  draft: async (payload: ChangePayload, existing?: ChangeRecord) => existing
    ? (await http.patch<ChangeRecord>(`/iam/identity-changes/${existing.id}`, { expected_request_revision: existing.revision, change: payload })).data
    : (await http.post<ChangeRecord>('/iam/identity-changes', payload)).data,
  preview: async (id: string) => (await http.post<ChangePreview>(`/iam/identity-changes/${id}/preview`)).data,
  commit: async (row: ChangeRecord, preview: ChangePreview, key: string, approve = false) => (await http.post<ChangeRecord>(`/iam/identity-changes/${row.id}/${approve ? 'approve' : 'commit'}`,
    { expected_request_revision: row.revision, preview_token: preview.preview_token, confirm_high_risk: true }, { headers: { 'Idempotency-Key': key } })).data,
  changes: async (params: Record<string, string | number>) => (await http.get<{ total: number; items: ChangeRecord[] }>('/iam/identity-changes', { params })).data,
  decide: async (row: ChangeRecord, action: 'cancel' | 'reject', reason: string) => (await http.post<ChangeRecord>(`/iam/identity-changes/${row.id}/${action}`, { expected_request_revision: row.revision, reason })).data,
  handovers: async (id: string) => (await http.get<{ items: HandoverItem[]; coverage: HandoverSummary['coverage'] }>(`/iam/identity-changes/${id}/handover-items`)).data,
  handoverCandidates: async (id: string) => (await http.get<{ items: { id: string; display_name: string }[] }>(`/iam/handover-items/${id}/candidates`)).data,
  refreshHandover: async (id: string) => (await http.post(`/iam/identity-changes/${id}/handover-refresh`)).data,
  reassign: async (item: HandoverItem, successor_user_id: string) => (await http.post(`/iam/handover-items/${item.id}/reassign`, { successor_user_id, expected_resource_revision: item.expected_resource_revision })).data,
}

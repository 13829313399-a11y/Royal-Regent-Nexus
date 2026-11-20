import { http } from '@/lib/http'
import type { AccessTuple, ChangePayload, ChangePreview } from './identity'
import type { FactoryScope } from './positionReviews'
import type { TaskKind, TaskState } from '@/features/identity-management/workspace/contracts'

export interface StudioPackage {
  binding_id: string
  role_id: string
  role_name: string
  is_system_position: boolean
  factory_id: string
  factory_ceiling: string[] | null
  department: string
  role_version_id: string | null
  source_type: string
  assignment_id: string | null
  is_primary_assignment: boolean
  version_outdated: boolean
  valid_until: string | null
}
export interface PersonAccessSummary {
  active_packages: StudioPackage[]
  effective_factories: string[]
  override_counts: { allow: number; deny: number }
  open_task: {
    key: string
    kind: TaskKind
    state: TaskState
    summary: string
  } | null
  task_coverage_complete: boolean
}
export interface EffectiveGroup {
  module_code: string
  module_name: string
  items: {
    code: string
    name: string
    access_kind: string
    factory_ids: string[]
    factory_names: string[]
    scopes?: { factory_id: string; department_codes: string[] }[]
    source_ids: string[]
  }[]
}
export interface PackageAddition {
  role_id: string
  department: string
  factory_scope: FactoryScope
  role_version_id?: string
}
export interface StudioDraft {
  official_posting?: import('./positionReviews').Position
  scope_updates?: { binding_id: string; factory_ids: string[] }[]
  add_overrides?: {
    permission_code: string
    effect: 'allow' | 'deny'
    factory_id: string
    department: string
    valid_until?: string
  }[]
  end_override_ids?: string[]
  position_review?: {
    item_key: string
    expected_source_revision: string
    confirmed_profile: import('./positionReviews').Position
  }
  base_identity_version: number
  base_authorization_version: number
  source_assignment_id: string
  official_position_title?: string
  add_packages: PackageAddition[]
  remove_binding_ids: string[]
  upgrade_binding_ids: string[]
  reason: string
}
export interface StudioPreview {
  preview_token: string
  expires_at: string
  server_now: string
  permission_diffs: ChangePreview['permission_diffs']
  high_risk: boolean
  requires_approval: boolean
  requires_empty_confirmation: boolean
  explicit_denials: AccessTuple[]
  allowed_to_commit: boolean
  blocked_reasons?: string[]
  handover_summary?: string
  will_confirm_legacy?: boolean
}
export interface StudioCommand {
  preview_token: string
  risk_acknowledged: boolean
  confirm_empty_packages: boolean
}
export interface StudioResult {
  command_id: string
  status: 'committed'
  decision: 'applied' | 'pending_approval'
  change_id: string
  message: string
}
const studio = (id: string) => `/iam/users/${encodeURIComponent(id)}/access-studio`
export const accessStudioApi = {
  async packageAbilities() {
    return (
      await http.get<Record<string, { code: string; name: string }[]>>('/iam/access-studio/package-abilities')
    ).data
  },
  async effective(id: string) {
    const { data } = await http.get<{
      current_packages: StudioPackage[]
      effective_permissions_grouped: EffectiveGroup[]
    }>(`/system/users/${encodeURIComponent(id)}/effective-access`)
    if (!Array.isArray(data.current_packages) || !Array.isArray(data.effective_permissions_grouped)) {
      throw new Error('当前服务尚未提供新版有效权限明细。')
    }
    return data
  },
  async legacyPreview(id: string, draft: ChangePayload) {
    return (await http.post<StudioPreview>(`${studio(id)}/legacy-preview`, draft)).data
  },
  async preview(id: string, draft: StudioDraft | ChangePayload) {
    return (await http.post<StudioPreview>(`${studio(id)}/preview`, draft)).data
  },
  async commit(id: string, command: StudioCommand, key: string) {
    return (
      await http.post<StudioResult>(`${studio(id)}/commit`, command, {
        headers: { 'Idempotency-Key': key },
      })
    ).data
  },
  async receipt(id: string) {
    return (
      await http.get<{
        status: 'not_observed' | 'committed'
        result: StudioResult | null
      }>(`/iam/access-studio/receipts/${encodeURIComponent(id)}`)
    ).data
  },
}

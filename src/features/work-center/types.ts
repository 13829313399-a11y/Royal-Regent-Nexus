export type WorkView = 'todo' | 'assigned' | 'team' | 'waiting' | 'info' | 'history'
export interface WorkEntry {
  id: string; kind: 'task' | 'info'; module: string; title: string; summary: string
  reference_label: string; lifecycle: 'open' | 'in_progress' | 'resolved' | 'cancelled' | 'superseded' | null
  details?: { label: string; value: string; format?: 'text' | 'datetime' }[]
  viewer_relation: 'assignee' | 'candidate' | 'watcher' | 'recipient'
  source_factory: { id: string; label: string } | null
  execution_factory: { id: string; label: string } | null
  department_label: string; stage_label: string; responsible_label: string; why_me: string
  priority: 'urgent' | 'high' | 'normal'; priority_reasons: string[]; due_at: string | null
  due_source: string | null; opened_at: string | null; can_act_now: boolean; unavailable_reason: string | null
  verification_state: 'verified' | 'unverified'; resolution_reason: string | null
  content_version: number; attention_version: number
  personal: { read_state: 'unread' | 'read' | 'legacy_unknown'; snoozed_until: string | null; archived_at: string | null; pinned: boolean; state_version: number; following?: boolean }
  actions: { key: string; label: string; mode: 'navigate' | 'refresh_identity'; enabled: boolean; disabled_reason: string | null
    target: { route_key: string; params: Record<string, string>; query: Record<string, string> } | null }[]
}
export interface WorkSnapshot {
  context: { viewer_key: string; scope_key: string; server_time: string; business_timezone: string; authz_recheck_at: string | null }
  summary: { actionable_total: number; assigned_total: number; team_queue_total: number; focus_total: number; snoozed_total: number; overdue_total: number; info_unread_total: number; waiting_total: number; verification_required_total: number }
  query: { filtered_total: number | null; cursor: string | null }; items: WorkEntry[]; next_cursor: string | null
  selected_entry_state: WorkEntry | { id: string; state: 'unavailable' } | null
  health: { status: 'fresh' | 'partial' | 'stale'; as_of: string; unavailable_sources: string[]; issues?: { module: string; reason: 'source_missing' | 'source_inconsistent'; count: number }[]; coverage: { module: string; state: string }[] }
}
export interface WorkQuery { view: WorkView; factory_scope: string; module: string; q: string; due: string; unread_only: boolean; cursor?: string; limit: number; selected_id?: string }
export interface WorkPreferences { sound_enabled: boolean; toast_level: 'assigned' | 'all_tasks' | 'none'; version: number; business_timezone: string }
export interface PersonalPatch { observed_content_version?: number; state_version?: number; snoozed_until?: string | null; archived?: boolean; pinned?: boolean; following?: boolean }

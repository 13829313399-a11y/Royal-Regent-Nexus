import type { WorkEntry, WorkSnapshot } from '../types'

export const entry = (id = 'first'): WorkEntry => ({ id, kind: 'task', module: 'molding', title: '审核啤办单', summary: '测试', reference_label: id,
  lifecycle: 'open', viewer_relation: 'assignee', source_factory: { id: 'huakang-c', label: '华康C' }, execution_factory: { id: 'huakang-a', label: '华康A' },
  department_label: '工程', stage_label: '审核', responsible_label: '本人', why_me: '当前责任人', priority: 'normal', priority_reasons: [], due_at: null,
  due_source: null, opened_at: '2026-09-28T02:00:00Z', can_act_now: true, unavailable_reason: null, verification_state: 'verified', resolution_reason: null,
  content_version: 1, attention_version: 1, personal: { read_state: 'unread', snoozed_until: null, archived_at: null, pinned: false, state_version: 0 },
  actions: [{ key: 'open', label: '审核', mode: 'navigate', enabled: true, disabled_reason: null, target: { route_key: 'molding_production', params: { id }, query: { factory: 'huakang-a' } } }] })
export const snap = (items: WorkEntry[] = [entry()]): WorkSnapshot => ({
  context: { viewer_key: 'A', scope_key: 'authorized', server_time: '2026-09-28T02:00:00Z', business_timezone: 'Asia/Shanghai', authz_recheck_at: null },
  summary: { actionable_total: items.length, assigned_total: items.length, team_queue_total: 0, focus_total: items.length, snoozed_total: 0, overdue_total: 0, info_unread_total: 0, waiting_total: 0, verification_required_total: 0 },
  query: { filtered_total: items.length, cursor: null }, items, next_cursor: null, selected_entry_state: null,
  health: { status: 'fresh', as_of: '2026-09-28T02:00:00Z', unavailable_sources: [], coverage: [] },
})

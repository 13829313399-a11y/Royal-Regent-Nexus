import type { Person } from '@/api/identity'
export type TaskKind = 'position' | 'registration' | 'password-reset' | 'identity-change'
export type TaskState = 'actionable' | 'blocked' | 'waiting_employee' | 'scheduled' | 'closed'
export type TaskKey = `${TaskKind}:${string}`
export type PersonPanel = 'profile' | 'exceptions' | 'account' | 'advanced'
export interface WorkspaceTask {
  key: TaskKey; kind: TaskKind; source_id: string; source_revision: string
  subject: { user_id: string; display_name: string; username: string }
  org_unit_id: string; department: string; current_position: string; proposed_position: string
  raw_status: string; state: TaskState; created_at: string
  available_actions: string[]; blocked_reasons: string[]
}
export interface SourceCoverage {
  kind: TaskKind; readable: boolean; state: 'ready' | 'not_authorized' | 'unavailable' | 'disabled'; message?: string
}
export interface WorkspaceTaskPage {
  items: WorkspaceTask[]; page: number; page_size: number; visible_total: number | null
  actionable_total: number | null; count_scope: 'current_normalized_filter'
  coverage: SourceCoverage[]; partial: boolean; server_now: string
}
export const taskLabels: Record<TaskKind, string> = {
  position: '岗位更新', registration: '注册开通', 'password-reset': '密码找回', 'identity-change': '高级任职',
}
export const taskStateLabels: Record<TaskState, string> = {
  actionable: '待处理', blocked: '需核对', waiting_employee: '待本人处理', scheduled: '已预约', closed: '已结束',
}
export function workspaceCapabilities(can: (permission: string) => boolean) {
  return { people: can('system:user_manage'), exceptions: can('system:access_manage'),
    catalog: can('system:permission_catalog_read'), audit: can('system:audit_read') }
}
export const personOrg = (person: Person) => person.primary_org_unit_id || person.primary_factory_id
export function taskStatusText(task: WorkspaceTask) {
  if (task.state === 'blocked') return '需核对'
  if (task.kind === 'password-reset' && task.state === 'waiting_employee') return '已核验，待本人改密'
  if (task.kind === 'password-reset' && task.available_actions.includes('reissue')) return '已过期，可重新开放'
  if (task.kind === 'password-reset' && task.state === 'closed' && ['pending', 'approved'].includes(task.raw_status)) return task.blocked_reasons[0] || '找回窗口已失效'
  return ({ pending: '待办理', returned: '已退回，待本人补充', applied: '已生效', approved: task.kind === 'registration' ? '注册已通过' : '已核验',
    rejected: '已拒绝', cancelled: '已撤回', withdrawn: '已撤回', completed: '本人已完成', expired: '已过期', legacy_invalid: '旧申请已失效',
    draft: '草稿', pending_approval: '待有权管理员审核', scheduled: task.state === 'closed' ? '预约已到期生效' : '已预约，尚未生效', invalidated: '已失效',
  } as Record<string,string>)[task.raw_status] || taskStateLabels[task.state]
}

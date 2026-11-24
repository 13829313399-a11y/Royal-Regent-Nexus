import { Bell, Factory, FileSpreadsheet, Info, PackageCheck, ShieldCheck, UserCheck } from '@lucide/vue'
import { factoryContexts } from '@/data/enterpriseMock'
import type { WorkEntry } from './types'

export function normalizeFactory(scope: unknown) {
  return typeof scope === 'string' && factoryContexts.some((f) => f.id !== 'group' && f.id === scope)
    ? scope
    : 'authorized'
}

const modules = {
  molding: { label: '啤办', icon: Factory, color: 'bg-teal-50 text-teal-800' },
  internal_quote: { label: '内部报价', icon: FileSpreadsheet, color: 'bg-blue-50 text-blue-800' },
  carton_supplier: { label: '供应商送货', icon: PackageCheck, color: 'bg-amber-50 text-amber-800' },
  position_reviews: { label: '岗位核对', icon: UserCheck, color: 'bg-slate-100 text-teal-800' },
  account_requests: { label: '账户申请', icon: ShieldCheck, color: 'bg-slate-100 text-slate-700' },
  identity: { label: '任职知会', icon: Bell, color: 'bg-sky-50 text-sky-800' },
}
export const moduleMeta = (key: string) =>
  modules[key as keyof typeof modules] ?? {
    label: '其他事项',
    icon: Info,
    color: 'bg-muted text-muted-foreground',
  }
export const canArchive = (entry: WorkEntry) =>
  entry.kind === 'info' || ['resolved', 'cancelled', 'superseded'].includes(entry.lifecycle ?? '')
export const attentionGroup = (entry: WorkEntry) =>
  entry.priority === 'urgent' ? '逾期 / 紧急' : entry.viewer_relation === 'assignee' ? '指派给我' : '团队队列'

const boilerplate = new Set([
  '员工岗位资料已更新；确认前原权限保持不变。',
  '核对实到、破损与拒收数量后，使用原收料流程确认。',
  '报价流程或成果已更新，请在原单据查看授权范围内的资料。',
  '源业务阶段已变化，请查看原单据的当前进展。',
  '生产问题仍开放，请在原单据核实处理。',
  '请核对目标职位、权限包和生效范围后办理。',
  '任职信息发生变化，请刷新账户上下文，提交业务前重新核对当前权限和厂区。',
])
export function entrySummary(entry: WorkEntry) {
  if (
    boilerplate.has(entry.summary) ||
    entry.summary === entry.reference_label ||
    entry.summary === entry.title
  )
    return ''
  return (entry.summary || '').replace(/；请核对申请组织与任职资料。$/, '')
}

const tracks: Record<string, { labels: string[]; stages: Record<string, number> }> = {
  molding: {
    labels: ['工程提交', '主管审核', '经理终审', '生产执行', '完成'],
    stages: {
      rework: 0,
      supervisor_review: 1,
      manager_review: 2,
      production_start: 3,
      production_fill: 3,
      problem: 3,
    },
  },
  internal_quote: {
    labels: ['部门填写', '汇总提交', '审核把关', '发布生效'],
    stages: { fill: 0, review: 0, final_submit: 1, whole_review: 2, final_review: 2 },
  },
  carton_supplier: {
    labels: ['供应商发货', '仓库验收收料', '入账完成'],
    stages: { receipt: 1, receipt_correction: 1 },
  },
  position_reviews: { labels: ['资料申报', '管理核对', '权限生效'], stages: { position_review: 1 } },
  identity: { labels: ['提交调整', '审批核对', '生效'], stages: { identity_approval: 1 } },
  registration: { labels: ['提交注册', '审核批准', '账号激活'], stages: { registration: 1 } },
  password: {
    labels: ['发起申请', '核验批准', '原浏览器重设'],
    stages: { password_reset: 1, password_reset_claim: 2 },
  },
}
export function workflow(entry: WorkEntry) {
  if (
    entry.kind !== 'task' ||
    !['open', 'in_progress'].includes(entry.lifecycle ?? '') ||
    entry.verification_state !== 'verified'
  )
    return null
  const stage = (entry.stage_code ?? entry.actions[0]?.target?.query.stage ?? '').split(':')[0]!
  const key =
    entry.module === 'account_requests'
      ? stage === 'registration'
        ? 'registration'
        : 'password'
      : entry.module
  const track = tracks[key],
    current = track?.stages[stage]
  if (!track || current === undefined) return null
  const warning = (
    { rework: '驳回或撤回重填', problem: '待处理问题', receipt_correction: '冲销更正' } as Record<
      string,
      string
    >
  )[stage]
  return { labels: track.labels, current, warning }
}

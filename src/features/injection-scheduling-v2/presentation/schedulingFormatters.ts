import { fitDecisionMeta, taskStatusMeta } from './schedulingLabels'

export function formatPlanRevision(value: unknown) {
  const revision = Number(value)
  return Number.isInteger(revision) && revision >= 0 ? `版本 ${revision}` : '版本待确认'
}

export function formatElapsedMilliseconds(value: unknown) {
  const milliseconds = Number(value)
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return '耗时待确认'
  if (milliseconds < 1_000) return '耗时不到 1 秒'
  return `耗时 ${(milliseconds / 1_000).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 秒`
}

export function formatConflictTitle(value: unknown) {
  const title = String(value ?? '').trim()
  if (!title) return '检测到版本冲突'
  if (/\brevision\b|\bconflict\b/i.test(title)) return '检测到版本冲突'
  return title.replace(/\brevision\b/gi, '版本')
}

export function formatConflictMessage(value: unknown) {
  const message = String(value ?? '').trim()
  if (!message) return '服务器数据已更新，请比较差异后选择处理方式。'
  if (/\brevision\b|\bconflict\b/i.test(message)) return '服务器数据已更新，请比较差异后采用服务器值，或基于最新版本重新应用。'
  return message
}

const conflictFieldLabels: Record<string, string> = {
  status: '任务状态',
  machineId: '安排机台',
  moldId: '使用模具',
  orderId: '生产订单',
  sequence: '机台内顺序',
  targetQuantity: '计划目标数',
  reportedQuantity: '已回报数量',
  shiftCompleted: '本班已啤',
  completedQuantity: '累计已啤',
  downtime: '停机时间',
  plannedDowntimeMinutes: '计划停机分钟数',
  exception: '异常类型',
  plannedStart: '计划开始',
  plannedFinish: '计划完成',
  estimatedStart: '预计开始',
  estimatedFinish: '预计完成',
  warehouse: '仓库',
  locked: '是否锁定',
  manualOverrideReason: '人工调整原因',
  fit: '机台适配结论',
  fitDecision: '机台适配结论',
  remark: '备注',
  revision: '数据版本',
  taskRevision: '任务版本',
  orderRevision: '订单版本',
  planRevision: '计划版本',
  ruleRevision: '规则版本',
}

export function conflictFieldLabel(value: unknown) {
  return conflictFieldLabels[String(value ?? '')] ?? '其他变更字段'
}

export function conflictFieldValue(key: unknown, value: unknown) {
  const field = String(key ?? '')
  if (field === 'status') return taskStatusMeta(value).label
  if (field === 'fit' || field === 'fitDecision') return fitDecisionMeta(value).label
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

const auditEventLabels: Record<string, string> = {
  order_created: '订单已创建',
  order_updated: '订单资料已更新',
  manual_demand_updated: '手工需求已更新',
  manual_demand_cancelled: '手工需求已取消',
  backlog_order_cancelled: '待排订单已取消',
  plan_draft_created: '排产草案已创建',
  plan_task_created: '任务已排入计划',
  plan_task_updated: '任务安排已更新',
  plan_tasks_bulk_moved: '任务已批量移动',
  plan_task_withdrawn_to_backlog: '任务已撤回待排',
  plan_published: '排产计划已发布',
  plan_rolled_back: '排产计划已回退',
  shift_report_recorded: '生产回报已记录',
  progress_adjusted: '生产进度已调整',
  auto_schedule_preview_created: '自动排期方案已生成',
  auto_schedule_run_applied: '自动排期方案已应用',
  import_confirmed: '导入结果已确认',
}

export function formatAuditEventLabel(value: unknown) {
  return auditEventLabels[String(value ?? '').trim()] ?? '业务记录已更新'
}

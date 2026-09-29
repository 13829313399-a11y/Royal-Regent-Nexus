import type { CartonImportPreviewRow } from '@/api/cartonProcurement'
import type { CartonTone } from '@/features/carton-procurement/demoData'

export interface ScheduleOrderReminder {
  state: 'WAIT' | 'DUE_SOON' | 'DUE_TODAY' | 'OVERDUE' | 'ORDERED' | 'REVIEW' | 'DATE_REVIEW' | 'RULE_REVIEW'
  label: string
  tone: CartonTone
  attention: boolean
  deadline: string
  arrivalDate: string
  days: number | null
  detail: string
}

export function completeScheduleDate(value?: string) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return ''
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : ''
}

function offsetDate(value: string, days: number) {
  return new Date(Date.parse(`${value}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10)
}

/** Current procurement timing, kept separate from immutable import matching evidence. */
export function scheduleOrderReminder(source: CartonImportPreviewRow, options: {
  today: string
  leadDays: number
  productionDays: number | null
  marked: boolean
  orderStatus?: string
  orderCount: number
  identityReview?: boolean
}): ScheduleOrderReminder | null {
  if (source.schedule_section && source.schedule_section !== 'PENDING') return null
  if (source.template === 'unified-item' && !['正单', '加单', '正式PO'].includes(source.order_type?.trim() ?? '')) return null
  const result = (state: ScheduleOrderReminder['state'], label: string, tone: CartonTone, detail: string): ScheduleOrderReminder =>
    ({ state, label, tone, detail, attention: state !== 'WAIT' && state !== 'ORDERED', deadline: '', arrivalDate: '', days: null })
  if (options.orderCount > 1 || options.identityReview || source.schedule_change === 'REVIEW_REQUIRED'
    || source.match_status === 'AMBIGUOUS') return result('REVIEW', '待人工确认', 'amber', '订单身份或关联不唯一，请核实后判断是否已下单。')
  if (options.marked || ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED'].includes(options.orderStatus ?? '')) {
    return result('ORDERED', options.marked ? '人工已下单' : options.orderStatus === 'COMPLETED' ? '已完单' : '已下单', 'green', '已下单，停止下单时限提醒；排期退单和数量变化继续核对。')
  }
  if (!source.item_no?.trim() || !(source.contract_no || source.reference)?.trim() || Number(source.quantity ?? 0) <= 0) {
    return result('REVIEW', '待人工确认', 'amber', '合同、货号或数量不完整，请核实后计算下单时限。')
  }
  const dateValues = [source.inspection_window, source.customer_due_date].filter(Boolean)
  const dates = dateValues.map(completeScheduleDate).filter(Boolean).sort()
  if (source.date_review_required || dateValues.some(value => !completeScheduleDate(value)) || !dates.length || !completeScheduleDate(options.today)) {
    return result('DATE_REVIEW', '交期待确认', 'amber', '缺少完整交期或日期原文需要确认，暂不判定漏单。')
  }
  if (options.productionDays === null || !Number.isInteger(options.productionDays) || options.productionDays < 0
    || !Number.isInteger(options.leadDays) || options.leadDays < 0) {
    return result('RULE_REVIEW', '交期规则待确认', 'amber', '请先加载或设置供应商生产送货周期和安全提前量。')
  }
  // Do not clamp to today: a missed order deadline must remain overdue.
  const arrivalDate = offsetDate(dates[0]!, -options.leadDays)
  const deadline = offsetDate(arrivalDate, -options.productionDays)
  const days = Math.round((Date.parse(`${deadline}T00:00:00Z`) - Date.parse(`${options.today}T00:00:00Z`)) / 86_400_000)
  const state = days < 0 ? 'OVERDUE' : days === 0 ? 'DUE_TODAY' : days <= 3 ? 'DUE_SOON' : 'WAIT'
  const created = ['DRAFT', 'CONFIRMED'].includes(options.orderStatus ?? '')
  const label = state === 'OVERDUE' ? `疑似漏单 · 超时 ${-days} 天`
    : state === 'DUE_TODAY' ? '今天必须下单' : state === 'DUE_SOON' ? `即将到期 · 剩 ${days} 天` : '待下单'
  return { state, label: created ? `${label} · 待确认下单` : label,
    tone: state === 'OVERDUE' || state === 'DUE_TODAY' ? 'red' : state === 'DUE_SOON' ? 'amber' : 'blue',
    attention: state !== 'WAIT', deadline, arrivalDate, days,
    detail: `最迟下单 ${deadline}；纸箱需到仓 ${arrivalDate}（验货/走货较早日期 ${dates[0]}－安全提前 ${options.leadDays} 天）；生产送货 ${options.productionDays} 天。${created ? '已建单但未确认锁定，仍需完成下单。' : ''}` }
}

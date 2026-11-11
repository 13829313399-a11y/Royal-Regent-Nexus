import type { CartonImportPreviewRow, CartonScheduleOrder } from '@/api/cartonProcurement'
import type { WeeklyCheckRow } from './demoData'
import type { ScheduleOrderReminder } from '@/lib/cartonScheduleDeadline'

export type ScheduleWorkView = 'ATTENTION' | 'FUTURE' | 'ORDERED' | 'ALL'
export type ScheduleOrderCategory = 'UNPLACED' | 'CREATED' | 'ORDERED' | 'COMPLETED' | 'REVIEW'
export type ScheduleWorkReviews = Partial<Record<'cancellation' | 'quantity' | 'date', boolean>>

export interface ScheduleWorkItem {
  attention: boolean
  future: boolean
  ordered: boolean
  historical: boolean
  priority: number
  deadline: string
  reason: string
}

export interface ScheduleWorkProjection {
  category: ScheduleOrderCategory
  reminder: ScheduleOrderReminder | null
  result: string
  source?: CartonImportPreviewRow
  order?: Pick<CartonScheduleOrder, 'status' | 'customer_due_date' | 'product_order_quantity' | 'split_records'>
  pendingSplit?: boolean
  reviews?: ScheduleWorkReviews
}

const purchaseTypes = new Set(['正单', '正式PO', '加单', '改单'])
const deadlines = {
  OVERDUE: { priority: 1, reason: '逾期未下单' },
  DUE_TODAY: { priority: 2, reason: '今天必须下单' },
  DUE_SOON: { priority: 3, reason: '三天内需下单' },
}

function scheduleDifference(row: WeeklyCheckRow, { source, order, reviews, result }: ScheduleWorkProjection) {
  const quantity = order?.product_order_quantity
  // Only a comparable whole-order quantity can clear a saved quantity difference.
  const quantitiesAgree = quantity != null && quantity !== '' && !row.quantityMissing
    && !order?.split_records?.some(plan => plan.status !== 'CANCELLED')
    && Number(quantity) === row.quantity
  if ((source?.match_status === 'QUANTITY_MISMATCH' || result === '数量差异')
    && reviews?.quantity !== false && !quantitiesAgree) return '核对数量差异'
  const datesAgree = source?.customer_due_date && source.customer_due_date === order?.customer_due_date
  if ((source?.match_status === 'DATE_MISMATCH' || result === '交期差异')
    && reviews?.date !== false && !datesAgree) return '核对交期差异'
  return ''
}

/** Read-only queue membership; it never changes source evidence or action eligibility. */
export function scheduleWorkItem(row: WeeklyCheckRow, projection: ScheduleWorkProjection): ScheduleWorkItem {
  const { category, reminder, result, source, order, reviews } = projection
  const ordered = category === 'ORDERED' || category === 'COMPLETED'
  const section = row.scheduleSection
  const change = row.scheduleChange
  const deadline = reminder?.deadline || ''
  const item = (priority: number, reason: string, attention = true, historical = false): ScheduleWorkItem =>
    ({ attention, future: !attention && !historical && category === 'UNPLACED' && reminder?.state === 'WAIT', ordered, historical, priority, deadline, reason })

  const cancellation = change === 'CANCELLED' || change === 'CANCELLED_AFTER_ORDER'
  const openPurchase = category === 'CREATED' || (category === 'ORDERED' && Boolean(order))
  if (reviews?.cancellation !== false
    && (cancellation || reviews?.cancellation || (section === 'CANCELLED' && openPurchase))) return item(0, '核实退单')
  if (projection.pendingSplit) return item(4, '拆单待仓库确认')
  if (change === 'REOPENED') return item(4, '核实恢复下单')
  if (source?.missing_review?.status === 'PENDING') return item(4, '核实排期缺行')
  if (section === 'CANCELLED') return item(6, '退单排期留存', false, true)
  if (section === 'SHIPPED' && category !== 'CREATED') return item(6, '已送货排期留存', false, true)

  const difference = scheduleDifference(row, projection)
  const markedChange = reminder?.state === 'CHANGE_REVIEW'
  if (category === 'COMPLETED') {
    if (change === 'MODIFIED' && (difference || markedChange)) return item(4, difference || '复核已下单需求变化')
    return item(6, '已完单', false, true)
  }

  const state = reminder?.state
  const timing = state === 'OVERDUE' || state === 'DUE_TODAY' || state === 'DUE_SOON' ? deadlines[state] : undefined
  if (category === 'CREATED') return item(timing?.priority ?? 4,
    order?.status === 'CONFIRMED' ? '待发供应商' : '待核对并确认锁定')
  if (!ordered && source?.template === 'unified-item' && !purchaseTypes.has((source.order_type || row.orderType || '').trim()))
    return item(7, '其他排期记录', false)
  if (!ordered && timing) return item(timing.priority, timing.reason)
  if (markedChange) return item(4, '复核已下单依据')
  if (difference) return item(4, difference)
  if (!ordered && (row.dateReviewRequired || source?.date_review_required || state === 'DATE_REVIEW'))
    return item(4, '核实日期原文')
  if (state === 'RULE_REVIEW') return item(4, '核实下单周期')
  if (row.identityDuplicate || source?.schedule_identity_duplicate || source?.legacy_match_stale
    || change === 'REVIEW_REQUIRED' || source?.match_status === 'AMBIGUOUS' || state === 'REVIEW'
    || result === '待人工选择' || result === '匹配不唯一') return item(4, '核对订单身份或资料')
  if (!ordered && (category === 'REVIEW' || result === '待人工确认')) return item(4, '核对排期资料')

  // Legacy evidence without a timing projection remains visible for review rather than guessed as far future.
  if (!reminder && !ordered && result !== '已匹配')
    return item(4, '核实下单与交期')
  if (ordered) return item(6, '已下单', false)
  if (category === 'UNPLACED' && state === 'WAIT') return item(5, '后续未下单', false)
  return item(7, '其他排期记录', false)
}

export function scheduleWorkViewMatches(item: ScheduleWorkItem, view: ScheduleWorkView): boolean {
  if (view === 'ATTENTION') return item.attention
  if (view === 'FUTURE') return item.future
  if (view === 'ORDERED') return item.ordered || item.historical
  return true
}

/** Stable tie-breaks are supplied by Array.sort, retaining source order for equal/unknown dates. */
export function compareScheduleWorkPriority(left: ScheduleWorkItem, right: ScheduleWorkItem): number {
  if (left.priority !== right.priority) return left.priority - right.priority
  if (left.deadline && right.deadline) return left.deadline.localeCompare(right.deadline)
  return left.deadline ? -1 : right.deadline ? 1 : 0
}

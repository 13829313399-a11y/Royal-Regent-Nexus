import type { CartonImportPreviewRow } from '@/api/cartonProcurement'
import type { WeeklyCheckRow } from './demoData'
import type { ScheduleOrderReminder } from '@/lib/cartonScheduleDeadline'

export type ScheduleWorkView = 'ATTENTION' | 'FUTURE' | 'ORDERED' | 'ALL'
export type ScheduleOrderCategory = 'UNPLACED' | 'CREATED' | 'ORDERED' | 'COMPLETED' | 'REVIEW'

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
  pendingSplit?: boolean
}

const reviewResults = new Set(['数量差异', '交期差异', '待人工选择', '待人工确认', '匹配不唯一'])
const substantiveReviewResults = new Set(['数量差异', '交期差异', '待人工选择', '匹配不唯一'])
const reviewReminderStates = new Set<ScheduleOrderReminder['state']>(['REVIEW', 'DATE_REVIEW', 'RULE_REVIEW', 'CHANGE_REVIEW'])

/** Read-only queue membership; it never changes source evidence or action eligibility. */
export function scheduleWorkItem(row: WeeklyCheckRow, projection: ScheduleWorkProjection): ScheduleWorkItem {
  const { category, reminder, result, source } = projection
  const ordered = category === 'ORDERED' || category === 'COMPLETED'
  const deadline = reminder?.deadline || ''
  const item = (priority: number, reason: string, attention = true, historical = false): ScheduleWorkItem =>
    ({ attention, future: !attention && !historical && category === 'UNPLACED' && reminder?.state === 'WAIT', ordered, historical, priority, deadline, reason })

  // Placed records still need cancellation/change hand-off; they cannot vanish into the history view.
  if (['CANCELLED', 'CANCELLED_AFTER_ORDER'].includes(row.scheduleChange || '')) return item(0, '核实退单')
  if (row.scheduleSection === 'CANCELLED' && (ordered || category === 'CREATED')) return item(0, '核实退单')

  const substantiveReview = substantiveReviewResults.has(result)
    || ['QUANTITY_MISMATCH', 'DATE_MISMATCH', 'AMBIGUOUS'].includes(source?.match_status || '')
    || row.identityDuplicate || source?.schedule_identity_duplicate || source?.legacy_match_stale
    || row.scheduleChange === 'REVIEW_REQUIRED'
  const historicalSource = row.scheduleSection === 'SHIPPED'
    || (row.scheduleSection === 'CANCELLED' && !ordered && category !== 'CREATED')
  // The parser labels archived source sections REVIEW_REQUIRED merely to retain them.
  // Neither that label nor an incomplete historical date creates a current procurement task.
  if (historicalSource && category !== 'CREATED' && !projection.pendingSplit
    && row.scheduleChange !== 'REOPENED' && !substantiveReview)
    return item(6, row.scheduleSection === 'SHIPPED' ? '已送货排期留存' : '旧退单排期留存', false, true)
  if (reminder?.state === 'OVERDUE') return item(1, '逾期未下单')
  if (reminder?.state === 'DUE_TODAY') return item(2, '今天必须下单')
  if (reminder?.state === 'DUE_SOON') return item(3, '三天内需下单')
  if (category === 'CREATED') return item(4, '待核对并确认锁定')
  if (projection.pendingSplit) return item(4, '拆单待仓库确认')
  if (row.scheduleChange === 'REOPENED') return item(4, '核实恢复下单')
  if (row.dateReviewRequired || source?.date_review_required) return item(4, '核实日期原文')
  if (row.identityDuplicate || source?.schedule_identity_duplicate || source?.legacy_match_stale
    || row.scheduleChange === 'REVIEW_REQUIRED' || category === 'REVIEW'
    || reviewResults.has(result) || ['QUANTITY_MISMATCH', 'DATE_MISMATCH', 'AMBIGUOUS'].includes(source?.match_status || '')
    || (reminder && reviewReminderStates.has(reminder.state))) return item(4, '核实排期差异或资料')

  // Legacy evidence without a timing projection remains visible for review rather than guessed as far future.
  if (!reminder && !ordered && result !== '已匹配' && (!row.scheduleSection || row.scheduleSection === 'PENDING'))
    return item(4, '核实下单与交期')
  return item(ordered ? 6 : category === 'UNPLACED' && reminder?.state === 'WAIT' ? 5 : 7,
    ordered ? '已下单 / 已完单' : category === 'UNPLACED' && reminder?.state === 'WAIT' ? '后续未下单' : '其他排期记录', false)
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

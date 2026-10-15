import { describe, expect, it } from 'vitest'
import type { CartonImportPreviewRow } from '@/api/cartonProcurement'
import type { WeeklyCheckRow } from '../demoData'
import { scheduleOrderReminder } from '@/lib/cartonScheduleDeadline'
import { compareScheduleWorkPriority, scheduleWorkItem, scheduleWorkViewMatches, type ScheduleOrderCategory } from '../scheduleWorkViews'

const source: CartonImportPreviewRow = {
  template: 'unified-item', order_type: '正单', contract_no: 'C-001', item_no: 'I-001', quantity: 100,
  schedule_section: 'PENDING', schedule_change: 'BASELINE', customer_due_date: '2026-10-20',
  inspection_window: '2026-10-18', match_status: 'MISSING_ORDER',
}
const row: WeeklyCheckRow = {
  id: 'WK-ITEM-1', reference: 'C-001', poNumbers: '', customer: '客户', itemNo: 'I-001', productName: '玩具',
  quantity: 100, cartonRule: '外箱', inspectionWindow: '2026-10-18', result: '未匹配订单', tone: 'amber',
  linkedOrder: '', suggestion: '', scheduleSection: 'PENDING', scheduleChange: 'BASELINE', orderType: '正单',
}
const options = { today: '2026-10-08', leadDays: 3, productionDays: 7, marked: false, orderCount: 0 }
const work = (changes: Partial<CartonImportPreviewRow> = {}, today = options.today,
  category: ScheduleOrderCategory = 'UNPLACED', orderStatus?: string, marked = false) => {
  const currentSource = { ...source, ...changes }
  const reminder = scheduleOrderReminder(currentSource, { ...options, today, orderStatus, marked,
    orderCount: orderStatus ? 1 : 0 })
  const currentRow = { ...row, scheduleSection: currentSource.schedule_section,
    scheduleChange: currentSource.schedule_change, identityDuplicate: currentSource.schedule_identity_duplicate,
    dateReviewRequired: currentSource.date_review_required }
  return scheduleWorkItem(currentRow, { category, reminder, result: reminder?.label || row.result, source: currentSource })
}

describe('carton schedule staff work views', () => {
  it.each([
    ['2026-10-04', false, true],
    ['2026-10-05', true, false],
    ['2026-10-07', true, false],
    ['2026-10-08', true, false],
    ['2026-10-09', true, false],
  ])('focuses only existing deadline urgency at %s, keeping later work visible', (today, attention, future) => {
    expect(work({}, today)).toMatchObject({ attention, future, ordered: false, deadline: '2026-10-08' })
  })

  it('removes manually or formally placed normal rows from the default queue', () => {
    expect(work({}, '2026-12-01', 'ORDERED', undefined, true)).toMatchObject({ attention: false, future: false, ordered: true })
    expect(work({}, '2026-12-01', 'ORDERED', 'PENDING_SUPPLIER')).toMatchObject({ attention: false, future: false, ordered: true })
    expect(work({}, '2026-12-01', 'COMPLETED', 'COMPLETED')).toMatchObject({ attention: false, future: false, ordered: true })
  })

  it.each(['DRAFT', 'CONFIRMED'])('keeps %s drafts in the confirmation queue without claiming they are placed or overdue', status => {
    expect(work({}, '2026-10-09', 'CREATED', status)).toMatchObject({ attention: true, future: false, ordered: false })
    expect(work({}, '2026-10-04', 'CREATED', status)).toMatchObject({
      attention: true, future: false, ordered: false, priority: 4, deadline: '2026-10-08', reason: '待核对并确认锁定',
    })
  })

  it.each(['CANCELLED', 'CANCELLED_AFTER_ORDER', 'REOPENED'])('retains an ordered %s hand-off in both attention and placed views', schedule_change => {
    const item = work({ schedule_change, schedule_section: schedule_change === 'REOPENED' ? 'PENDING' : 'CANCELLED' },
      '2026-10-04', 'ORDERED', 'PENDING_SUPPLIER')
    expect(item).toMatchObject({ attention: true, future: false, ordered: true })
    expect(scheduleWorkViewMatches(item, 'ATTENTION')).toBe(true)
    expect(scheduleWorkViewMatches(item, 'ORDERED')).toBe(true)
  })

  it.each(['QUANTITY_MISMATCH', 'DATE_MISMATCH', 'AMBIGUOUS'] as const)('keeps ordered %s evidence in the queue', match_status => {
    expect(work({ match_status }, '2026-10-04', 'ORDERED', 'PENDING_SUPPLIER'))
      .toMatchObject({ attention: true, future: false, ordered: true })
  })

  it('keeps placed split targets awaiting warehouse confirmation in both attention and placed views', () => {
    const reminder = scheduleOrderReminder(source, { ...options, orderStatus: 'PENDING_SUPPLIER', orderCount: 1 })
    const item = scheduleWorkItem(row, { category: 'ORDERED', reminder, result: reminder!.label, source, pendingSplit: true })
    expect(item).toMatchObject({ attention: true, ordered: true, future: false, priority: 4, reason: '拆单待仓库确认' })
    expect(scheduleWorkViewMatches(item, 'ATTENTION')).toBe(true)
    expect(scheduleWorkViewMatches(item, 'ORDERED')).toBe(true)
    expect(scheduleWorkItem(row, { category: 'ORDERED', reminder, result: reminder!.label, source, pendingSplit: false }))
      .toMatchObject({ attention: false, ordered: true, future: false })
  })

  it.each([
    { customer_due_date: '', inspection_window: '' },
    { customer_due_date: '10/20' },
    { inspection_window: '2026-02-30' },
    { inspection_window: '9/1-10% 9/14-100%' },
    { date_review_required: true },
    { schedule_identity_duplicate: true },
  ])('shows incomplete/ambiguous evidence for review without inventing a date', changes => {
    expect(work(changes, '2026-10-04')).toMatchObject({ attention: true, future: false, deadline: '' })
  })

  it('does not elevate a far-future normal PO just because its imported matching snapshot requires manual procurement', () => {
    expect(work({ order_type: '正式PO', match_status: 'REVIEW_REQUIRED' }, '2026-10-04'))
      .toMatchObject({ attention: false, future: true, ordered: false })
  })

  it('retains an explicitly stale legacy identity for review even when the date is far away', () => {
    expect(work({ legacy_match_stale: true }, '2026-10-04'))
      .toMatchObject({ attention: true, future: false, ordered: false, priority: 4 })
  })

  it('keeps shipped/other evidence available in all and legacy undated pending rows in attention', () => {
    const shipped = scheduleWorkItem({ ...row, scheduleSection: 'SHIPPED' }, { category: 'UNPLACED', reminder: null, result: '未匹配订单' })
    expect(shipped).toMatchObject({ attention: false, future: false, ordered: false, historical: true })
    expect(scheduleWorkViewMatches(shipped, 'ALL')).toBe(true)
    expect(scheduleWorkViewMatches(shipped, 'ORDERED')).toBe(true)
    expect(scheduleWorkItem(row, { category: 'UNPLACED', reminder: null, result: '未匹配订单' }))
      .toMatchObject({ attention: true, future: false })
  })

  it.each(['SHIPPED', 'CANCELLED'] as const)('archives ordinary %s parser review evidence without assigning a business completion state', scheduleSection => {
    const historicalRow = { ...row, scheduleSection, scheduleChange: scheduleSection === 'SHIPPED' ? 'BASELINE' : 'NOT_TRACKED',
      dateReviewRequired: true, procurementState: '待确认', result: '待人工确认' }
    const item = scheduleWorkItem(historicalRow, { category: 'REVIEW', reminder: null, result: '待人工确认',
      source: { ...source, schedule_section: scheduleSection, match_status: 'REVIEW_REQUIRED', date_review_required: true } })
    expect(item).toMatchObject({ attention: false, future: false, ordered: false, historical: true })
    expect(scheduleWorkViewMatches(item, 'ORDERED')).toBe(true)
    expect(historicalRow.procurementState).toBe('待确认')
  })

  it.each(['QUANTITY_MISMATCH', 'DATE_MISMATCH', 'AMBIGUOUS'] as const)('keeps substantive archived %s evidence as a current review', match_status => {
    expect(scheduleWorkItem({ ...row, scheduleSection: 'SHIPPED', result: '待人工确认' },
      { category: 'REVIEW', reminder: null, result: '待人工确认', source: { ...source, schedule_section: 'SHIPPED', match_status } }))
      .toMatchObject({ attention: true, historical: false, priority: 4 })
  })

  it.each(['ORDERED', 'COMPLETED', 'CREATED'] as const)('keeps an existing %s order in an unchanged cancellation source for explicit hand-off', category => {
    expect(scheduleWorkItem({ ...row, scheduleSection: 'CANCELLED', scheduleChange: 'NOT_TRACKED' },
      { category, reminder: null, result: '待人工确认', source: { ...source, schedule_section: 'CANCELLED', match_status: 'REVIEW_REQUIRED' } }))
      .toMatchObject({ attention: true, historical: false, priority: 0, reason: '核实退单' })
  })

  it.each(['CANCELLED', 'CANCELLED_AFTER_ORDER'] as const)('keeps a genuine new %s change even without a current purchase', scheduleChange => {
    expect(scheduleWorkItem({ ...row, scheduleSection: 'CANCELLED', scheduleChange },
      { category: 'REVIEW', reminder: null, result: '待人工确认' })).toMatchObject({ attention: true, historical: false, priority: 0 })
  })

  it('keeps pending split confirmation and created orders ahead of historical archive hints', () => {
    const shipped = { ...row, scheduleSection: 'SHIPPED' as const, scheduleChange: 'BASELINE', dateReviewRequired: true }
    expect(scheduleWorkItem(shipped, { category: 'ORDERED', reminder: null, result: '待人工确认', pendingSplit: true }))
      .toMatchObject({ attention: true, ordered: true, historical: false, reason: '拆单待仓库确认' })
    expect(scheduleWorkItem(shipped, { category: 'CREATED', reminder: null, result: '待人工确认' }))
      .toMatchObject({ attention: true, ordered: false, historical: false, reason: '待核对并确认锁定' })
  })

  it('prioritizes cancellation, overdue, today, soon and review, then nearest deadline without mutating evidence', () => {
    const entries = [
      work({ inspection_window: '', customer_due_date: '2026-10-20' }), // soon: deadline 10/10
      work({ inspection_window: '', customer_due_date: '2026-10-19' }), // soon: deadline 10/09
      work({ customer_due_date: '', inspection_window: '' }),
      work({}, '2026-10-09'),
      work(),
      work({ schedule_section: 'CANCELLED', schedule_change: 'CANCELLED_AFTER_ORDER' }, undefined, 'ORDERED'),
    ]
    expect([...entries].sort(compareScheduleWorkPriority).map(item => [item.priority, item.deadline]))
      .toEqual([[0, ''], [1, '2026-10-08'], [2, '2026-10-08'], [3, '2026-10-09'], [3, '2026-10-10'], [4, '']])
    expect(source).toMatchObject({ match_status: 'MISSING_ORDER', customer_due_date: '2026-10-20' })
    expect(compareScheduleWorkPriority(entries[2]!, entries[2]!)).toBe(0)
  })
})

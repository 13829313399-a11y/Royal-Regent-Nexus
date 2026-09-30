import { describe, expect, it } from 'vitest'
import { completeScheduleDate, scheduleOrderReminder } from '../cartonScheduleDeadline'
import type { CartonImportPreviewRow } from '@/api/cartonProcurement'

const source: CartonImportPreviewRow = {
  template: 'unified-item', order_type: '正单', contract_no: 'C-001', item_no: 'I-001', quantity: 100,
  schedule_section: 'PENDING', schedule_change: 'BASELINE', customer_due_date: '2026-10-20',
  inspection_window: '2026-10-18', match_status: 'MISSING_ORDER',
}
const options = { today: '2026-10-08', leadDays: 3, productionDays: 7, marked: false, orderCount: 0 }

describe('current schedule order deadline', () => {
  it.each([
    ['2026-10-04', 'WAIT', false, 4],
    ['2026-10-05', 'DUE_SOON', true, 3],
    ['2026-10-07', 'DUE_SOON', true, 1],
    ['2026-10-08', 'DUE_TODAY', true, 0],
    ['2026-10-09', 'OVERDUE', true, -1],
  ])('classifies %s using the earlier inspection/shipping date and both intervals', (today, state, attention, days) => {
    expect(scheduleOrderReminder(source, { ...options, today })).toMatchObject({
      state, attention, days, arrivalDate: '2026-10-15', deadline: '2026-10-08',
    })
  })

  it.each(['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED'])('stops timing reminders for a live %s order despite a missing import snapshot', orderStatus => {
    expect(scheduleOrderReminder(source, { ...options, orderStatus, orderCount: 1, today: '2026-12-01' })).toMatchObject({ state: 'ORDERED', attention: false })
  })

  it('stops only after a manual mark or formal confirmation, keeping unconfirmed drafts overdue', () => {
    expect(scheduleOrderReminder(source, { ...options, marked: true })).toMatchObject({ state: 'ORDERED', attention: false })
    for (const orderStatus of ['DRAFT', 'CONFIRMED']) {
      expect(scheduleOrderReminder(source, { ...options, orderStatus, orderCount: 1, today: '2026-10-09' })).toMatchObject({ state: 'OVERDUE', label: '疑似漏单 · 超时 1 天 · 待确认下单' })
    }
    // A cancelled linked order is no longer evidence of placing a live order.
    expect(scheduleOrderReminder(source, { ...options, orderStatus: 'CANCELLED', today: '2026-10-09' })).toMatchObject({ state: 'OVERDUE' })
  })

  it.each(['正单', '加单', '正式PO'])('uses the same deadline for %s while preserving the imported type', order_type => {
    const row = { ...source, order_type, match_status: 'REVIEW_REQUIRED' as const }
    expect(scheduleOrderReminder(row, options)).toMatchObject({ state: 'DUE_TODAY' })
    expect(row.order_type).toBe(order_type)
  })

  it.each(['备料单', '样板单', ''])('does not classify nonformal %s records as missing orders', order_type => {
    expect(scheduleOrderReminder({ ...source, order_type }, options)).toBeNull()
  })

  it.each(['CANCELLED', 'SHIPPED'] as const)('stops pending-order deadlines for the %s source section', schedule_section => {
    expect(scheduleOrderReminder({ ...source, schedule_section }, options)).toBeNull()
  })

  it.each([
    { customer_due_date: '', inspection_window: '' },
    { customer_due_date: '10/20' },
    { inspection_window: '2026-02-30' },
    { inspection_window: '9/1-10% 9/14-100%' },
    { date_review_required: true },
  ])('keeps incomplete or staged dates for review without guessing', changes => {
    expect(scheduleOrderReminder({ ...source, ...changes }, options)).toMatchObject({ state: 'DATE_REVIEW', deadline: '' })
  })

  it('blocks ambiguous identities and nonpositive quantities before reporting a missing order', () => {
    expect(scheduleOrderReminder(source, { ...options, orderCount: 2 })).toMatchObject({ state: 'REVIEW' })
    expect(scheduleOrderReminder({ ...source, schedule_change: 'REVIEW_REQUIRED' }, options)).toMatchObject({ state: 'REVIEW' })
    expect(scheduleOrderReminder({ ...source, quantity: 0 }, options)).toMatchObject({ state: 'REVIEW' })
  })

  it('shows a soft SO collision warning without hiding invalid quantities', () => {
    expect(scheduleOrderReminder({ ...source, schedule_identity_duplicate: true, schedule_change: 'REVIEW_REQUIRED' }, options))
      .toMatchObject({ state: 'REVIEW', label: '待人工确认', detail: expect.stringContaining('仍可标记已下单或按此下单') })
    expect(scheduleOrderReminder({ ...source, schedule_identity_duplicate: true, quantity: 0 }, options))
      .toMatchObject({ state: 'REVIEW', detail: expect.stringContaining('数量不完整') })
  })

  it('supports changed or zero-day cycles and retains calendar dates across month boundaries', () => {
    const row = { ...source, inspection_window: '', customer_due_date: '2026-03-03' }
    expect(scheduleOrderReminder(row, { ...options, today: '2026-02-28', productionDays: 0 })).toMatchObject({ deadline: '2026-02-28', state: 'DUE_TODAY' })
    expect(scheduleOrderReminder(row, { ...options, productionDays: 10 })).toMatchObject({ deadline: '2026-02-18' })
    expect(scheduleOrderReminder(row, { ...options, productionDays: null })).toMatchObject({ state: 'RULE_REVIEW', deadline: '' })
    expect(completeScheduleDate('2026-02-30')).toBe('')
  })
})

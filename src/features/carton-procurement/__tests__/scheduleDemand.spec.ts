import { describe, expect, it } from 'vitest'
import { effectiveSchedulePo, scheduleDemandSnapshot, scheduleMarkChanges, scheduleMarkState } from '../scheduleDemand'
import { scheduleOrderReminder } from '@/lib/cartonScheduleDeadline'
import { scheduleWorkItem } from '../scheduleWorkViews'
import { buildBusinessOrderAlerts } from '../businessAlerts'
import type { CartonImportPreviewRow } from '@/api/cartonProcurement'

const row: CartonImportPreviewRow = { template: 'unified-item', order_type: '正单', contract_no: 'SC', item_no: 'ITEM',
  schedule_section: 'PENDING', quantity: 360, carton_rule: '6', customer_due_date: '2026-10-20', manual_ordered: true }

describe('weekly demand acknowledgements', () => {
  it('uses SO first and preserves leading zeroes in fallback PO', () => {
    expect(effectiveSchedulePo({ customer_po: ' 00123 ' })).toBe('00123')
    expect(effectiveSchedulePo({ source_reference: ' SO-1 ', customer_po: '00123' })).toBe('so-1')
  })
  it('preserves the acknowledged demand until a person reviews changes', () => {
    const frozen = { marked: true, demand_snapshot: scheduleDemandSnapshot(row) }
    expect(scheduleMarkChanges({ ...row, carton_rule: ' 6.0 ' }, frozen)).toEqual([])
    const changed = { ...row, quantity: 720, carton_rule: '12', customer_due_date: '2026-10-01' }
    expect(scheduleMarkChanges(changed, frozen)).toEqual(['数量', '装箱', '客户交期'])
    const reminder = scheduleOrderReminder(changed, { today: '2026-10-10', leadDays: 3, productionDays: 7,
      marked: true, orderCount: 0, markChanges: scheduleMarkChanges(changed, frozen) })!
    expect(reminder).toMatchObject({ state: 'CHANGE_REVIEW', attention: true })
    const work = scheduleWorkItem({ scheduleSection: 'PENDING' } as never, { category: 'ORDERED', result: reminder.label, reminder, source: changed })
    expect(work.attention).toBe(true)
    expect(scheduleMarkChanges(changed, { ...frozen, demand_snapshot: scheduleDemandSnapshot(changed) })).toEqual([])
  })
  it('shows unverifiable historical acknowledgement as review, and creates an actionable alert', () => {
    expect(scheduleMarkChanges(row, { marked: true })).toEqual(['原下单依据待核实'])
    expect(scheduleMarkState({ ...row, schedule_identity: 'PO-A', schedule_identity_aliases: ['OLD'] }, { OLD: { marked: true } }))
      .toMatchObject({ marked: false, review_required: true, demand_snapshot: null })
    const reminder = scheduleOrderReminder(row, { today: '2026-10-10', leadDays: 3, productionDays: 7,
      marked: true, orderCount: 0, markChanges: scheduleMarkChanges(row, { marked: true }) })!
    const alerts = buildBusinessOrderAlerts({ factoryId: 'huaxing', exceptions: [], ordersForSource: () => [], reminder: () => reminder,
      batches: [{ id: 'B', factory_id: 'huaxing', status: 'REQUIRES_REVIEW', parse_summary: { rows: [row] } } as never] })
    expect(alerts).toHaveLength(1)
    expect(alerts[0]).toMatchObject({ kind: 'QUANTITY_REVIEW', status: 'OPEN', reminder: { attention: true } })
  })
})

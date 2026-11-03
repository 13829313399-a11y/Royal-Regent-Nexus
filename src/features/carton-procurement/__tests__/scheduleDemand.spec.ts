import { describe, expect, it } from 'vitest'
import { effectiveSchedulePo, scheduleDemandSnapshot, scheduleMarkChanges, scheduleMarkState, scheduleQuantityCandidates } from '../scheduleDemand'
import { scheduleOrderReminder } from '@/lib/cartonScheduleDeadline'
import { scheduleWorkItem } from '../scheduleWorkViews'
import { buildBusinessOrderAlerts } from '../businessAlerts'
import type { CartonImportPreviewRow, CartonScheduleOrder } from '@/api/cartonProcurement'

const row: CartonImportPreviewRow = { template: 'unified-item', order_type: '正单', contract_no: 'SC', item_no: 'ITEM',
  schedule_section: 'PENDING', quantity: 360, carton_rule: '6', customer_due_date: '2026-10-20', manual_ordered: true }

describe('weekly demand acknowledgements', () => {
  it('uses SO first and preserves leading zeroes in fallback PO', () => {
    expect(effectiveSchedulePo({ customer_po: ' 00123 ' })).toBe('00123')
    expect(effectiveSchedulePo({ source_reference: ' SO-1 ', customer_po: '00123' })).toBe('so-1')
  })
  it.each(['正单', '改单'])('preserves acknowledged %s demand until a person reviews changes', order_type => {
    const frozen = { marked: true, demand_snapshot: scheduleDemandSnapshot(row) }
    expect(scheduleMarkChanges({ ...row, carton_rule: ' 6.0 ' }, frozen)).toEqual([])
    const changed = { ...row, order_type, quantity: 720, carton_rule: '12', customer_due_date: '2026-10-01' }
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

describe('current server quantity and packing evidence', () => {
  const source: CartonImportPreviewRow = { ...row, schedule_customer_code: 'TEST', contract_no: '00123', item_no: '0004',
    schedule_identity: 'SOURCE', source_reference: 'SO1', carton_rule: '12' }
  const purchase: CartonScheduleOrder = { id: 'O', factory_id: 'huakang-b', order_no: 'CT1', customer_code: 'TEST', customer_name: 'Test',
    contract_no: '00123', item_no: '0004', customer_po: '', status: 'CONFIRMED', product_order_quantity: '360', product_name: 'Test',
    customer_due_date: '2026-10-20', schedule_quantity_matches: [{ version: 1, basis: 'CONTRACT_ITEM_QUANTITY_PACKING',
      factory_id: 'huakang-b', customer_code: 'test', contract_no: '00123', item_no: '0004', source_identity: 'BUSINESS',
      schedule_identity: 'SOURCE', source_batch_id: 'B', source_sheet: 'ITEM', source_row: 4,
      quantity: '360', carton_rule: '0/12', ambiguous: false, reason: 'Unique current evidence' }] }

  it('uses proof for an empty-PO order and refuses incomplete or changed evidence', () => {
    const match = (changes: Partial<CartonImportPreviewRow> = {}, orders = [purchase], factory = 'huakang-b') =>
      scheduleQuantityCandidates({ ...source, ...changes }, orders, factory)
    expect(match()).toEqual([purchase])
    expect(match({ carton_rule: ' 0/12.0 ' })).toEqual([purchase])
    expect(match({ quantity: 720 })).toEqual([])
    expect(match({ carton_rule: undefined })).toEqual([])
    expect(match({ contract_no: '123' })).toEqual([])
    expect(match({ schedule_customer_code: 'OTHER' })).toEqual([])
    expect(match({}, [purchase], 'huaxing')).toEqual([])
    expect(match({}, [{ ...purchase, customer_po: 'OTHER-PO' }])).toEqual([])
    expect(match({}, [{ ...purchase, schedule_quantity_matches: [] }])).toEqual([])
    expect(match({}, [{ ...purchase, status: 'CANCELLED' }])).toEqual([])
  })

  it('keeps ambiguity as review and consumes a later unique proof despite an old import snapshot', () => {
    const ambiguous = { ...purchase, schedule_quantity_matches: purchase.schedule_quantity_matches!.map(proof => ({ ...proof, ambiguous: true })) }
    expect(scheduleQuantityCandidates(source, [ambiguous], 'huakang-b')).toEqual([])
    expect(scheduleQuantityCandidates(source, [ambiguous], 'huakang-b', true)).toEqual([ambiguous])
    expect(scheduleQuantityCandidates({ ...source, match_status: 'AMBIGUOUS' }, [purchase], 'huakang-b')).toEqual([purchase])
    const reminder = { state: 'REVIEW', quantityMatchReview: true, label: '数量及装箱匹配待核对', detail: '核对候选',
      attention: true, tone: 'amber', deadline: '', arrivalDate: '', days: null } as const
    const alerts = buildBusinessOrderAlerts({ factoryId: 'huakang-b', exceptions: [], ordersForSource: () => [], reminder: () => reminder,
      batches: [{ id: 'B', factory_id: 'huakang-b', status: 'REQUIRES_REVIEW', parse_summary: { rows: [source] } } as never] })
    expect(alerts).toHaveLength(1)
    expect(alerts[0]).toMatchObject({ kind: 'QUANTITY_REVIEW', reminder: { state: 'REVIEW' } })
  })
})

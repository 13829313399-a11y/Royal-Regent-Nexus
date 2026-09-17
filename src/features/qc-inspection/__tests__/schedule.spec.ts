import { describe, expect, it } from 'vitest'
import type { QcInspectionOrder, QcScheduleChange } from '@/api/qcInspection'
import { effectiveInspectionDate, sortInspectionSchedule, scheduleStatus, filterSchedule, isImportedPendingInspection, selectedImportDecisions, type ScheduleFilters } from '../schedule'

const defaults: ScheduleFilters = { customer: '', search: '', status: '', dateField: 'planned_inspection_date', from: '', to: '', agency: '' }
const orders = [
  { id: 'a', customer_name: 'WMC', customer_po_no: '0012', week_key: '2026-W38', planned_inspection_date: '', inspection_result: 'PENDING' },
  { id: 'b', customer_name: 'WMU', customer_po_no: '0013', week_key: '2026-W42', planned_inspection_date: '2026-10-15', actual_inspection_date: '2026-10-16', inspection_result: 'PASS' },
  { id: 'c', customer_name: 'WMC', customer_po_no: '0014', planned_inspection_date: '2026-09-16', inspection_result: 'CANCELLED' },
] as QcInspectionOrder[]
describe('QC total schedule', () => {
  it('uses shipment date only when customer inspection date is absent, for filtering, status and ordering', () => {
    const fallback = { ...orders[0]!, shipment_date: '2026-12-28' }
    const explicit = { ...orders[0]!, id: 'explicit', planned_inspection_date: '2026-12-20', shipment_date: '2026-12-30' }
    expect(effectiveInspectionDate(fallback)).toBe('2026-12-28')
    expect(effectiveInspectionDate(explicit)).toBe('2026-12-20')
    expect(scheduleStatus(fallback)).toBe('pending')
    expect(filterSchedule([fallback, explicit, orders[0]!], { ...defaults, from: '2026-12-28', to: '2026-12-28' })).toEqual([fallback])
    expect(sortInspectionSchedule([orders[0]!, fallback, explicit])).toEqual([explicit, fallback, orders[0]!])
    expect(effectiveInspectionDate({ ...fallback, shipment_date: '2027-01-02' })).toBe('2027-01-02')
    expect(effectiveInspectionDate({ planned_inspection_date: '9/21-10% 10/23-80%', shipment_date: '2026-12-28' })).toBe('9/21-10% 10/23-80%')
  })
  it('includes only imported unfinished orders in schedule details', () => {
    const imported = { ...orders[0]!, source_type: 'SCHEDULE_IMPORT', status: 'SCHEDULED' }
    expect(isImportedPendingInspection(imported)).toBe(true)
    expect(isImportedPendingInspection({ ...imported, status: 'IN_PROGRESS', actual_inspection_date: '2026-09-16' })).toBe(true)
    expect(isImportedPendingInspection({ ...imported, source_type: 'MANUAL' })).toBe(false)
    expect(isImportedPendingInspection({ ...imported, status: 'COMPLETED' })).toBe(false)
    expect(isImportedPendingInspection({ ...imported, status: 'CANCELLED' })).toBe(false)
    for (const inspection_result of ['PASS', 'FAIL', 'REJECTED', 'CONDITIONAL_PASS', 'CANCELLED']) {
      expect(isImportedPendingInspection({ ...imported, inspection_result })).toBe(false)
    }
  })
  it('keeps all weeks and unscheduled orders by default', () => {
    expect(filterSchedule(orders, defaults).map(order => order.id)).toEqual(['a', 'b', 'c'])
    expect(filterSchedule(orders, { ...defaults, customer: 'WMC', status: 'unplanned' }).map(order => order.id)).toEqual(['a'])
  })
  it('filters the selected date field without treating cancelled orders as completed', () => {
    expect(filterSchedule(orders, { ...defaults, dateField: 'actual_inspection_date', from: '2026-10-16', to: '2026-10-16' }).map(order => order.id)).toEqual(['b'])
    expect(filterSchedule(orders, { ...defaults, status: 'completed' }).map(order => order.id)).toEqual(['b'])
    expect(filterSchedule(orders, { ...defaults, search: '0012' }).map(order => order.id)).toEqual(['a'])
  })
  it('submits only selected valid pending rows and requires an explicit multiple-match target', () => {
    const row = (id: string, overrides: Partial<QcScheduleChange> = {}) => ({ id, match_status: 'NEW', decision_status: 'PENDING', validation_errors: [], candidate_order_ids: [], ...overrides }) as QcScheduleChange
    const rows = [row('a'), row('unselected'), row('invalid', { validation_errors: ['PO不能为空'] }), row('done', { decision_status: 'CREATE' }), row('multi', { match_status: 'MULTIPLE_MATCHES', candidate_order_ids: ['order-a', 'order-b'] })]
    expect(selectedImportDecisions(rows, ['a', 'invalid', 'done', 'multi'], {})).toEqual([{ row_id: 'a', action: 'CREATE', target_order_id: undefined }])
    expect(selectedImportDecisions(rows, ['multi'], { multi: 'outside-factory' })).toEqual([])
    expect(selectedImportDecisions(rows, ['multi'], { multi: 'order-b' })).toEqual([{ row_id: 'multi', action: 'UPDATE', target_order_id: 'order-b' }])
    expect(selectedImportDecisions(rows, ['invalid', 'multi'], {}, { invalid: 'SKIP', multi: 'SKIP' }).map(item => item.action)).toEqual(['SKIP', 'SKIP'])
    expect(selectedImportDecisions([row('exact', { match_status: 'EXACT' })], ['exact'], {}, { exact: 'KEEP' })).toEqual([{ row_id: 'exact', action: 'KEEP', target_order_id: undefined }])
  })
})

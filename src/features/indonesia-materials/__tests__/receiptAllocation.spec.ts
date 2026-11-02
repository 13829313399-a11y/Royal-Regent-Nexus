import { describe, expect, it } from 'vitest'
import type { BoardOrder, Data, MaterialRecord } from '@/api/indonesiaMaterials'
import { additionalReservations, allocationIssue, sortedTargets, suggestAllocations } from '../receiptAllocation'
import { receiptSummary } from '../receiptSummary'

const source = (normal = '150', spare = '10') => ({ normal_quantity: normal, spare_quantity: spare })
const target = (id: string, date: string | null, remaining = '100', fallback = '2026-12-01'): Data => ({ order_id: id, demand_id: `d-${id}`, order_version: 2, required_date: date, delivery_date: fallback, remaining })
describe('received material allocation proposals', () => {
  it('uses required date then missing-date fallback, with deterministic ties and undated orders last', () => {
    expect(sortedTargets([target('z', null, '100', ''), target('b', '2026-11-03'), target('a', null, '100', '2026-11-02'), target('c', '2026-11-01', '100', '2027-01-01'), target('a2', '2026-11-02')]).map(t => t.order_id)).toEqual(['c', 'a', 'a2', 'b', 'z'])
  })
  it('splits normal and spare quantities across earliest contracts without exceeding either total', () => {
    const plans = suggestAllocations(source(), [target('late', '2026-11-02'), target('early', '2026-11-01')], [])
    expect(plans.map(p => [p.order_id, p.normal_quantity, p.spare_quantity])).toEqual([['early', '100', '0'], ['late', '50', '10']])
    expect(allocationIssue(source(), plans)).toBe('')
  })
  it('reserves the first receipt row before proposing the second, while keeping manual choices', () => {
    const targets = [target('a', '2026-11-01'), target('b', '2026-11-02')]
    const first = suggestAllocations(source('70', '0'), targets, [])
    const second = suggestAllocations(source('80', '10'), targets, first)
    expect(second.map(p => [p.order_id, p.normal_quantity, p.spare_quantity])).toEqual([['a', '30', '0'], ['b', '50', '10']])
    expect(first[0]!.normal_quantity).toBe('70')
    const released = suggestAllocations(source('80', '10'), targets, [])
    expect(released.map(p => p.order_id)).toEqual(['a'])
  })
  it('preserves exact eight-place values and floors sixteen-place capacity rather than rounding up', () => {
    const plans = suggestAllocations(source('0.00000002', '0'), [target('a', null, '0.0000000199999999'), target('b', null, '0.00000001')], [])
    expect(plans.map(p => p.normal_quantity)).toEqual(['0.00000001', '0.00000001'])
    expect(allocationIssue(source('0.00000002', '0'), plans)).toBe('')
  })
  it('leaves excess, incomplete manual values and unavailable quantities visible instead of forcing allocation', () => {
    const targets = [target('a', null, '5')]
    expect(allocationIssue(source('10', '1'), suggestAllocations(source('10', '1'), targets, []))).toContain('正常 5／备品 1')
    expect(suggestAllocations(source('1', '0'), targets, [{ order_id: 'a', demand_id: 'd-a', normal_quantity: '', spare_quantity: '0' }])).toEqual([])
    expect(allocationIssue(source('1', '0'), [{ order_id: 'a', demand_id: 'd-a', normal_quantity: '2', spare_quantity: '0' }])).toContain('超过')
  })
  it('caps source allocations at 100 and honors the remaining 200-line shipment budget', () => {
    const targets = Array.from({ length: 201 }, (_, i) => target(String(i).padStart(3, '0'), null, '1'))
    const plans = suggestAllocations(source('150', '0'), targets, [], 200)
    expect(plans).toHaveLength(100)
    expect(allocationIssue(source('150', '0'), plans)).toContain('正常 50')
    expect(suggestAllocations(source('20', '0'), targets, [], 3)).toHaveLength(3)
    expect(suggestAllocations(source('20', '0'), targets, [], 0)).toEqual([])
  })
  it('does not double reserve historical allocations, but reserves an explicitly changed PO or increase', () => {
    const old = [{ order_id: 'a', demand_id: 'd-a', normal_quantity: '20', spare_quantity: '5' }]
    expect(additionalReservations(old, old)[0]!.normal_quantity).toBe('0')
    expect(additionalReservations([{ ...old[0], normal_quantity: '30' }], old)[0]!.normal_quantity).toBe('10')
    expect(additionalReservations([{ ...old[0], order_id: 'b', demand_id: 'd-b' }], old)[0]!.normal_quantity).toBe('25')
  })
})
describe('outstanding material summaries', () => {
  const material = (id: string, name: string): MaterialRecord => ({ id, kind: 'material', version: 1, data: { code: 'SAME', name, unit: 'pcs' } } as MaterialRecord)
  const order = (id: string, material_id: string, quantity: string, coverage: string): BoardOrder => ({ id, item_no: '40149', demands: [{ id: `d-${id}`, material_id, quantity, coverage, unit: 'PCS' }] } as BoardOrder)
  it('groups by material identity, not shared code, and never subtracts overcoverage on a different contract', () => {
    const rows = receiptSummary([order('a', 'm', '100', '20'), order('b', 'm', '50', '70'), order('c', 'm', '20', '0'), order('d', 'm2', '10', '0')], [material('m', '绿色拉杆'), material('m2', '蓝色拉杆')])
    expect(rows.map(r => [r.key, r.quantity, r.coverage, r.remaining, r.orders.size])).toEqual([['m', '120', '20', '100', 2], ['m2', '10', '0', '10', 1]])
  })
  it('keeps fractional recipe quantities precise and exposes missing or mismatched materials', () => {
    const rows = receiptSummary([order('a', 'm', '123456789012.1234567890123456', '0.00000001'), order('b', 'missing', '10', '0')], [material('m', '物料')])
    expect(rows[0]!.remaining).toBe('123456789012.1234567790123456')
    expect(rows[0]!.valid).toBe(true); expect(rows[1]!.valid).toBe(false)
    const mismatch = material('m', '物料'); mismatch.data.unit = 'KGM'
    expect(receiptSummary([order('a', 'm', '10', '0')], [mismatch])[0]!.valid).toBe(false)
  })
})

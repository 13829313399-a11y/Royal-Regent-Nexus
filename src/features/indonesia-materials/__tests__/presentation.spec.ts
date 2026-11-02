import { describe, expect, it } from 'vitest'
import { confirmedShipmentSummary, fixedText, hasReceiptRisk, needsPlanningData, readyMaterials, sumText } from '../presentation'
import type { BoardOrder, Data } from '@/api/indonesiaMaterials'

function line(id: string, code: string, amount = '0.005', currency = 'CNY') {
  return { allocation_id: id, material: { code, name: code, unit: 'PCS' }, normal_quantity: '1', spare_quantity: '0.1', item_no: 'ITEM', contract_no: 'CONTRACT', supply: { supplier: 'Supplier', currency }, amount }
}
function shipment(): Data {
  return { status: 'confirmed', supplier_summary: [{ name: 'Supplier', currency: 'CNY', materials: 3, amount: '0.03' }], snapshot_lines: [line('a', 'A'), line('b', 'B'), line('c', 'C'), line('b2', 'B')], packing_totals: {
    cartons: 7, cbm: '0.70',
    groups: [
      { label: 'A+B', cartons: 2, total_cbm: '0.2', items: [{ allocation_id: 'a' }, { allocation_id: 'b' }] },
      { label: 'B+C', cartons: 3, total_cbm: '0.3', items: [{ allocation_id: 'b2' }, { allocation_id: 'c' }] },
      { label: 'A整箱', cartons: 2, total_cbm: '0.2', items: [{ allocation_id: 'a' }] },
    ],
    lines: Object.fromEntries(['a', 'b', 'c', 'b2'].map(id => [id, { net_weight_kg: '0.10', carton_weight_kg: '0.02', gross_weight_kg: '0.12' }])),
  } }
}
describe('confirmed shipment presentation', () => {
  it('keeps shared codes on distinct material IDs and names in separate export rows', () => {
    const data = shipment()
    data.snapshot_lines.forEach((row: Data, index: number) => {
      row.material.code = '53003116'; row.material.name = ['子弹筒', '绿拉杆', '蓝拉杆', '推杆'][index]
      row.supply.material_id = `material-${index}`
    })
    const result = confirmedShipmentSummary(data)!
    expect(result.rows).toHaveLength(4)
    expect(new Set(result.rows.map(row => row.id)).size).toBe(4)
    expect(result.rows.every(row => row.code === '53003116' && row.normal === '1')).toBe(true)
    data.snapshot_lines.forEach((row: Data) => { delete row.supply.material_id })
    expect(confirmedShipmentSummary(data)!.rows).toHaveLength(4)
  })
  it('adds decimal strings exactly and uses half-up display rounding', () => {
    expect(sumText(['999999999999999999.99999999', '0.1'])).toBe('1000000000000000000.09999999')
    expect(fixedText('12.345')).toBe('12.35')
    expect(fixedText('-0.005')).toBe('-0.01')
    expect(fixedText('0.0001', 3)).toBe('0.000')
  })
  it('groups overlapping mixed boxes and dedicated boxes exactly once', () => {
    const result = confirmedShipmentSummary(shipment())!
    expect(result.rows.map(row => row.code)).toEqual(['A', 'B', 'C'])
    expect(result.rows.map(row => row.span)).toEqual([3, 0, 0])
    expect(result.rows.filter(row => row.span).reduce((total, row) => total + row.cartons, 0)).toBe(7)
    expect(result.rows[1]).toMatchObject({ normal: '2', spare: '0.2', net: '0.20', carton: '0.04', gross: '0.24' })
    expect(result.cartons).toBe(7)
    expect(fixedText(result.gross)).toBe('0.48')
    expect(result.suppliers![0]).toMatchObject({ amount: '0.03', materials: 3, currency: 'CNY' })
  })
  it('keeps independent carton components and currencies separate', () => {
    const data = shipment()
    data.snapshot_lines.push(line('d', 'D', '1.234', 'USD'))
    data.packing_totals.groups.push({ label: 'D整箱', cartons: 1, total_cbm: '0.1', items: [{ allocation_id: 'd' }] })
    data.packing_totals.lines.d = { net_weight_kg: '1', carton_weight_kg: '0.1', gross_weight_kg: '1.1' }
    data.packing_totals.cartons = 8
    data.supplier_summary.push({ name: 'Another supplier', currency: 'USD', materials: 1, amount: '1.23' })
    const result = confirmedShipmentSummary(data)!
    expect(result.rows.map(row => row.span)).toEqual([3, 0, 0, 1])
    expect(result.suppliers!.map(row => [row.currency, row.amount])).toEqual([['CNY', '0.03'], ['USD', '1.23']])
  })
  it('does not invent final weights or amounts for drafts and old incomplete snapshots', () => {
    expect(confirmedShipmentSummary({ ...shipment(), status: 'draft' })).toBeNull()
    expect(confirmedShipmentSummary({ status: 'confirmed', packing_totals: {} })).toBeNull()
    const legacy = shipment()
    delete legacy.supplier_summary
    expect(confirmedShipmentSummary(legacy)?.suppliers).toBeNull()
    delete legacy.packing_totals.lines.a.gross_weight_kg
    expect(() => confirmedShipmentSummary(legacy)).toThrow('无效数值')
  })
  it('uses the frozen export subtotal instead of rounding source amounts differently', () => {
    const data = shipment()
    data.snapshot_lines.forEach((row: Data) => { row.amount = '0.0049999999999999999999' })
    data.supplier_summary = [{ name: 'Supplier', currency: 'CNY', materials: 3, amount: '0.04' }]
    expect(confirmedShipmentSummary(data)!.suppliers![0]!.amount).toBe('0.04')
  })
})
describe('board presentation uses backend statuses', () => {
  const row = { status: 'shortage', planning_status: 'ready', demands: [{ shortage: '0.00000000', risk: 'late_received' }, { shortage: '0.00000001', risk: 'late' }] } as BoardOrder
  it('does not label a completed contract with an old late receipt as an active risk', () => {
    expect(hasReceiptRisk(row)).toBe(true)
    expect(hasReceiptRisk({ ...row, status: 'complete' })).toBe(false)
    expect(readyMaterials(row)).toBe(1)
  })
  it('detects incomplete planning independently of physical completion', () => {
    expect(needsPlanningData(row)).toBe(false)
    expect(needsPlanningData({ ...row, status: 'complete', planning_status: 'missing_parameters' })).toBe(true)
  })
})

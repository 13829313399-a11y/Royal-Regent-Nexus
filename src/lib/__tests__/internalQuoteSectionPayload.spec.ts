import { describe, expect, it } from 'vitest'
import { normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'

describe('internal quote section payload normalization', () => {
  it('normalizes every authoritative section contract without generic cost rows', () => {
    expect(normalizeInternalQuotePayload('engineering', { materials: [{ item: '螺丝', category: 'hardware', quantity: '2', unit_price_rmb: '3' }], molds: [], cartons: [] })).toMatchObject({ materials: [{ item: '螺丝', category: 'hardware', quantity: 2, unit_price_rmb: 3 }] })
    expect(normalizeInternalQuotePayload('electronic', { components: [{ item: 'IC', quantity: 2, unit_price_hkd: 1.5, children: [{ item: '脚位', quantity: 1, unit_price_hkd: .2 }] }] })).toMatchObject({ components: [{ item: 'IC', children: [{ item: '脚位' }] }], profit_rate_percent: 10 })
    expect(normalizeInternalQuotePayload('molding', { injection_lines: [{ material: 'ABS', grade: '750SW', machine_code: '20A' }] })).toMatchObject({ injection_lines: [{ material: 'ABS', grade: '750SW', loss_rate_percent: 3, machine_code: '20A' }] })
    expect(normalizeInternalQuotePayload('painting', { rows: [{ item: '头部', operations: { clamp: { quantity: 2, unit_price_hkd: 3 } } }] })).toMatchObject({ rows: [{ operations: { clamp: { quantity: 2, unit_price_hkd: 3 }, wipe: { quantity: 0, unit_price_hkd: 0 } } }] })
    expect(normalizeInternalQuotePayload('slush', { lines: [{ item: '手臂', quantity: '2', unit_price_hkd: '4.5' }] })).toEqual({ lines: [{ item: '手臂', quantity: 2, unit_price_hkd: 4.5 }] })
    expect(normalizeInternalQuotePayload('sewing', { groups: [{ name: '衣服', category: 'clothes', materials: [{ item: '布', usage: 2, unit_price_rmb: 3 }] }] })).toMatchObject({ groups: [{ category: 'clothes', materials: [{ markup: 1 }] }] })
    expect(normalizeInternalQuotePayload('assembly', { groups: [{ name: '包装', category: 'packaging', processes: [{ name: '入袋', persons: 2, teams: 1, production_qty: 100 }] }] })).toMatchObject({ labor_base_hkd: 310, groups: [{ category: 'packaging', processes: [{ production_qty: 100 }] }] })
    expect(normalizeInternalQuotePayload('sales', { scenarios: [{ name: '盐田', capacity_cuft: 1980, carton_cuft: 2, qty_per_carton: 6 }] })).toMatchObject({ scenarios: [{ name: '盐田', freight_share: .48, lift_share: .52, markup: 1.2, settlement: .98 }] })
  })
})

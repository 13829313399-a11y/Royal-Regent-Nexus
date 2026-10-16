import { describe, it, expect } from 'vitest'
import { paperDemands, referencesAfterRemoval, reusableQuantityRule, type QuantityPaper } from '../paperQuantity'

const papers = (): QuantityPaper[] => [
  { packaging_type: '普通箱', usage_quantity: 12 },
  { packaging_type: '刀卡', usage_quantity: null, quantity_rule: { mode: 'PER_CARTON', carton_line_no: 1, per_carton_quantity: 3 } },
]
describe('paper demand', () => {
  it('rounds the parent carton first, then multiplies each carton kit', () => {
    expect(paperDemands(1001, papers()).map(line => line.actual)).toEqual([84, 252])
    expect(paperDemands('1.000001', [{ usage_quantity: '1' }])[0]!.actual).toBe(2)
    expect(paperDemands('0.3', [{ usage_quantity: '0.1' }])[0]!.actual).toBe(3)
  })
  it('keeps manual values until restored, including a manually adjusted parent', () => {
    const lines = papers()
    lines[0]!.quantity_rule = { mode: 'PACKING', manual_quantity: 85 }
    expect(paperDemands(1001, lines).map(line => line.actual)).toEqual([85, 255])
    lines[1]!.quantity_rule!.manual_quantity = 260
    expect(paperDemands(2000, lines).map(line => line.actual)).toEqual([85, 260])
    lines[0]!.quantity_rule!.manual_quantity = null
    expect(paperDemands(2000, lines).map(line => line.actual)).toEqual([167, 260])
    lines[1]!.quantity_rule!.manual_quantity = null
    expect(paperDemands(2000, lines).map(line => line.actual)).toEqual([167, 501])
  })
  it('does not silently turn a removed reference into a different carton', () => {
    const line = papers()[1]!
    expect(referencesAfterRemoval(line.quantity_rule, 0)?.carton_line_no).toBeNull()
    expect(referencesAfterRemoval({ mode: 'PER_CARTON', carton_line_no: 3 }, 0)?.carton_line_no).toBe(2)
    line.quantity_rule!.carton_line_no = 2
    expect(paperDemands(1001, papers().slice(1))[0]!.error).toBeTruthy()
    expect(paperDemands(1001, [papers()[0]!, line])[1]!.error).toBeTruthy()
  })
  it('rejects cleared manual quantities and strips overrides from reusable packaging', () => {
    const lines = papers()
    lines[1]!.quantity_rule!.manual_quantity = ''
    expect(paperDemands(1001, lines)[1]!.error).toBeTruthy()
    expect(reusableQuantityRule({ mode: 'PACKING', manual_quantity: 310 })?.manual_quantity).toBeNull()
  })
})

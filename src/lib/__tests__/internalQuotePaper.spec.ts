import { describe, it, expect } from 'vitest'
import { selectedPaperFactor, paperRowsError } from '../internalQuotePaper'
import { normalizeInternalQuotePayload, calculateCartonUnitCostHkd, type SalesPayload } from '../internalQuoteSectionPayload'
const snapshot = { paper_prices: [{ key: 'ab', name: 'A=B', price_factor_hkd: '2.60', remark: '测试' }, { key: 'flat', name: '平卡纸', price_factor_hkd: '3.20', remark: '测试' }] }
describe('frozen paper selections', () => {
  it('retains carton and flat-card keys through save normalization and computes each factor', () => {
    const payload = normalizeInternalQuotePayload('sales', { paper_price_factor: 2.75, cartons: [{ item:'主箱', length_in:9, width_in:4.75, height_in:15.75, qty_per_carton:6, paper_material_key:'ab', flat_cards:[{ name:'平卡', length_in:8, width_in:4, quantity:2, paper_material_key:'flat' }] }] }) as unknown as SalesPayload
    const carton = payload.cartons[0]!
    expect(carton.paper_material_key).toBe('ab'); expect(carton.flat_cards[0]!.paper_material_key).toBe('flat')
    expect(calculateCartonUnitCostHkd(carton, selectedPaperFactor(carton,2.75,snapshot),1.5,snapshot)).toBeCloseTo(((9+4.75+2)*(4.75+15.75+1)*2*2.6/1000+8*4*2*3.2/1000)/6)
    expect(carton.qty_per_carton).toBe(6)
  })
  it('uses legacy factors only when no material is selected', () => {
    expect(selectedPaperFactor({}, 2.75, snapshot)).toBe(2.75)
    expect(selectedPaperFactor({ paper_material_key:'missing' },2.75,snapshot)).toBe(0)
    expect(paperRowsError([{ key:'x', name:'A=B', price_factor_hkd:'', remark:'' }])).toContain('大于 0')
  })
})

import { describe, expect, it } from 'vitest'
import { calculateInternalQuoteSection } from '@/lib/internalQuoteCalculator'
import type { InternalQuoteSectionPayload } from '@/types/internalQuote'

const snapshot = {
  version: 'rr2-2026-v1',
  fx: { rmb_hkd: 0.85, hkd_usd: 7.8 },
  material_prices: [{ name: 'ABS', model: '抽粒料', price_hkd_lb: 4.6 }],
  machine_prices: [{ model: '4A-6A', price_hkd_shift: 940 }],
}

function payload(overrides: Partial<InternalQuoteSectionPayload>): InternalQuoteSectionPayload {
  return {
    currency: 'HKD',
    lossPct: 0,
    parameters: {},
    referenceSnapshot: snapshot,
    rows: [],
    ...overrides,
  }
}

describe('calculateInternalQuoteSection', () => {
  it('matches the server injection formula and frozen references', () => {
    const result = calculateInternalQuoteSection('molding', payload({ rows: [{
      id: 'inj', category: '注塑', itemName: 'ABS外壳', specification: '', quantity: 0,
      unitPriceHkd: 0, amountHkd: 0, note: '',
      fields: {
        mode: 'injection', material: 'ABS', material_grade: '抽粒料', weight_g: 100,
        loss_pct: 3, machine_model: '4A', sets: 2, target: 1000,
      },
    }] }))

    expect(result.totalHkd).toBe(1.51)
    expect(result.totalRmb).toBe(1.28)
    expect(result.lineBreakdown[0].formula).toContain('克重')
  })

  it('does not apply the generic loss field to P2 painting operations', () => {
    const result = calculateInternalQuoteSection('painting', payload({
      lossPct: 10,
      rows: [{
        id: 'paint', category: '二次加工', itemName: '喷油', specification: '', quantity: 2,
        unitPriceHkd: 3, amountHkd: 0, note: '', fields: { mode: 'operation' },
      }],
    }))

    expect(result.totalHkd).toBe(6)
    expect(result.lossAmountHkd).toBe(0)
  })
})

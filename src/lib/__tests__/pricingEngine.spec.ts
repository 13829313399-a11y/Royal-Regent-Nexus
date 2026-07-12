import { describe, expect, it } from 'vitest'
import { runPricing } from '@/lib/pricing'
import type { PricingContext } from '@/types/pricing'

const context: PricingContext = {
  customerId: 'buzzbee',
  customerName: 'BuzzBee',
  currency: 'HKD',
  taxRate: 13,
  rules: [
    { id: 'fixed-40', kind: 'fixed', value: 40 },
    { id: 'percent-10', productLine: '玩具', kind: 'percent', value: 10, minQty: 10 },
    { id: 'markup-100', productLine: '玩具', kind: 'markup', value: 100 },
  ],
  rebateTiers: [
    { threshold: 500, rate: 5 },
    { threshold: 900, rate: 10 },
  ],
}

describe('pricing engine', () => {
  it('applies markup, percent and fixed rules in the required order before rebate and tax', () => {
    const result = runPricing({
      customerId: 'buzzbee',
      lines: [
        { sku: 'A-001', description: '玩具主体', qty: 10, unitPrice: 100, productLine: '玩具' },
        { sku: 'B-001', description: '说明书', qty: 1, unitPrice: 50, productLine: '包装' },
      ],
    }, context)

    expect(result.lines[0]).toMatchObject({
      gross: 1000,
      afterDiscount: 950,
      appliedRules: ['markup-100', 'percent-10', 'fixed-40'],
    })
    expect(result.lines[1]).toMatchObject({ gross: 50, afterDiscount: 10, appliedRules: ['fixed-40'] })
    expect(result.subtotal).toBe(960)
    expect(result.rebate).toMatchObject({ amount: 96, tier: { threshold: 900, rate: 10 } })
    expect(result.tax).toEqual({ amount: 112.32, rate: 13 })
    expect(result.total).toBe(976.32)
  })

  it('never returns a negative line amount and does not mutate the pricing context', () => {
    const before = JSON.stringify(context)
    const result = runPricing({
      customerId: 'buzzbee',
      lines: [{ sku: 'FREE', description: '样品', qty: 1, unitPrice: 1 }],
    }, context)

    expect(result.lines[0].afterDiscount).toBe(0)
    expect(result.total).toBe(0)
    expect(JSON.stringify(context)).toBe(before)
  })
})

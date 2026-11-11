import { describe, expect, it } from 'vitest'
import { cloneInternalQuotePayload, normalizeInternalQuotePayload, resolveSalesMiscPricing } from '@/lib/internalQuoteSectionPayload'
import { normalizeInternalQuoteDraft } from '@/lib/internalQuoteMoldingReferences'

const currentReference = { misc_ratio: '0.03', settlement: '0.97' }

describe('quote-specific commercial defaults', () => {
  it('uses frozen new, historical or custom terms before the historical missing-reference fallback', () => {
    expect(resolveSalesMiscPricing({}, undefined, currentReference)).toEqual({ misc_ratio: .03, divisor: .97 })
    expect(resolveSalesMiscPricing({}, undefined, { misc_ratio: '0.02', settlement: '0.98' })).toEqual({ misc_ratio: .02, divisor: .98 })
    expect(resolveSalesMiscPricing({}, undefined, { misc_ratio: '.035' })).toEqual({ misc_ratio: .035, divisor: .965 })
    expect(resolveSalesMiscPricing({}, undefined)).toEqual({ misc_ratio: .02, divisor: .98 })
  })

  it('preserves explicit pricing, including zero, and derives its divisor', () => {
    expect(resolveSalesMiscPricing({ misc_ratio: 0, divisor: .98 }, undefined, currentReference)).toEqual({ misc_ratio: 0, divisor: 1 })
    expect(resolveSalesMiscPricing({ misc_ratio: .035, divisor: .97 }, undefined, currentReference)).toEqual({ misc_ratio: .035, divisor: .965 })
    expect(resolveSalesMiscPricing({ divisor: .98 }, undefined, currentReference)).toEqual({ misc_ratio: .02, divisor: .98 })
    expect(resolveSalesMiscPricing({}, .96, currentReference)).toEqual({ misc_ratio: .04, divisor: .96 })
  })

  it('normalizes editable and saved baselines with the same frozen defaults without mutating input', () => {
    const source = { shipping: { markup_x: 1.2 } }
    const saved = normalizeInternalQuoteDraft('sales', source, currentReference)
    expect(saved.shipping).toMatchObject({ misc_ratio: .03, divisor: .97 })
    expect(cloneInternalQuotePayload('sales', source, currentReference)).toEqual(saved)
    expect(normalizeInternalQuoteDraft('sales', saved, currentReference)).toEqual(saved)
    expect(source).toEqual({ shipping: { markup_x: 1.2 } })
    expect(normalizeInternalQuotePayload('sales', saved, { misc_ratio: '.02' }).shipping).toMatchObject({ misc_ratio: .03, divisor: .97 })
  })

  it('does not fabricate shipping inputs for an untouched department', () => {
    expect(normalizeInternalQuoteDraft('sales', {}, currentReference)).not.toHaveProperty('shipping')
  })
})

import { describe, expect, it } from 'vitest'
import { canCover, sameQuantity, purchaseFactsAgree } from '../warehouseMatching'
describe('exact warehouse matching quantities', () => {
  it('distinguishes quantities above floating-point precision and keeps all eight fractional places', () => {
    expect(sameQuantity('123456789012.12345678', '123456789012.12345679')).toBe(false)
    expect(canCover('123456789012.12345678', '123456789012.12345677', '0.00000001')).toBe(true)
    expect(canCover('123456789012.12345678', '123456789012.12345678', '0.00000001')).toBe(false)
    expect(sameQuantity('90.00', '90')).toBe(true)
    expect(sameQuantity('', '0')).toBe(false)
  })
  it('requires source purchase facts to agree before suggesting an existing batch', () => {
    expect(purchaseFactsAgree({ price: '.1', purchase_quantity: '100' }, { price: '0.10', purchase_quantity: '100.000' })).toBe(true)
    expect(purchaseFactsAgree({ price: '2' }, { price: '1' })).toBe(false)
    expect(purchaseFactsAgree({ purchase_date: '2026-10-22' }, { purchase_date: '2026-10-21' })).toBe(false)
  })
})

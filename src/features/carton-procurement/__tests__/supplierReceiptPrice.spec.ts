import { describe, expect, it } from 'vitest'
import { originalSupplierReceiptPrice, supplierReceiptPrice } from '../supplierReceiptPrice'

describe('supplier original receipt price', () => {
  it('reads the original price from a legacy unmatched supplier line', () => {
    const source = { source_type: 'AD_HOC_REVIEW', unit_price: '1.690000' }
    expect(originalSupplierReceiptPrice(source)).toBe('1.690000')
    expect(supplierReceiptPrice(source)).toMatchObject({ unit_price: 1.69, price_action: 'MATCH' })
  })

  it.each(['FORMAL_ORDER', 'SPECIAL_REQUEST', undefined])('never treats %s internal cost as supplier original', source_type => {
    expect(supplierReceiptPrice({ source_type, unit_price: '9.99' })).toMatchObject({ price_action: 'PENDING', unit_price: 0 })
  })

  it('preserves explicit missing original price and prefers an explicit supplier price', () => {
    expect(supplierReceiptPrice({ source_type: 'AD_HOC_REVIEW', unit_price: '1.69', delivery_unit_price: null }).price_action).toBe('PENDING')
    expect(supplierReceiptPrice({ source_type: 'AD_HOC_REVIEW', unit_price: '1.69', delivery_unit_price: '2.03' }).unit_price).toBe(2.03)
  })

  it('keeps legacy zero price pending unless the supplier explicitly confirms free', () => {
    expect(supplierReceiptPrice({ source_type: 'AD_HOC_REVIEW', unit_price: '0' }).price_action).toBe('PENDING')
    expect(supplierReceiptPrice({ source_type: 'AD_HOC_REVIEW', unit_price: '0', free_confirmed: true }).price_action).toBe('FREE')
  })
})

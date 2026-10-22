type SupplierReceiptPriceSource = {
  source_type?: string
  unit_price?: string | number | null
  delivery_unit_price?: string | number | null
  free_confirmed?: boolean
}

export function originalSupplierReceiptPrice(source: SupplierReceiptPriceSource) {
  // Legacy unmatched imports expose the vendor original as unit_price.
  // Formal rows use unit_price for internal cost, so they must never fall back.
  const raw = source.delivery_unit_price === undefined && source.source_type === 'AD_HOC_REVIEW'
    ? source.unit_price : source.delivery_unit_price
  return raw == null || raw === '' ? null : String(raw)
}

/** Physical acceptance follows the supplier note; a missing price is never free. */
export function supplierReceiptPrice(source: SupplierReceiptPriceSource, gift = false) {
  const raw = originalSupplierReceiptPrice(source)
  const price = raw == null || raw === '' ? null : Number(raw)
  const valid = price != null && Number.isFinite(price) && price >= 0
  if (gift) return { unit_price: 0, price_action: 'FREE' as const, zero_price_kind: 'FREE' as const,
    price_reason: valid && price === 0 && source.free_confirmed ? '' : '仓库核实为免费赠送，待供应商确认' }
  if (valid && price > 0) return { unit_price: price, price_action: 'MATCH' as const, zero_price_kind: undefined, price_reason: '' }
  if (valid && price === 0 && source.free_confirmed) return { unit_price: 0, price_action: 'FREE' as const, zero_price_kind: 'FREE' as const, price_reason: '' }
  return { unit_price: 0, price_action: 'PENDING' as const, zero_price_kind: 'PENDING' as const,
    price_reason: '供应商原单缺价或零价未注明免费，待供应商补价' }
}

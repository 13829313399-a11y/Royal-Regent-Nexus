/** Only advisory matching uses these checks; the server revalidates all facts with Decimal. */
export function quantity(value: unknown): bigint | null {
  const text = String(value ?? '').trim(), match = /^(\d*)(?:\.(\d{0,8}))?$/.exec(text)
  if (!match || !/\d/.test(text)) return null
  return BigInt((match[1] || '0') + (match[2] || '').padEnd(8, '0'))
}
export function sameQuantity(left: unknown, right: unknown) {
  const a = quantity(left), b = quantity(right)
  return a !== null && b !== null && a === b
}
export function canCover(remaining: unknown, normal: unknown, spare: unknown) {
  const limit = quantity(remaining), a = quantity(normal), b = quantity(spare)
  return limit !== null && a !== null && b !== null && limit >= a + b
}
export function purchaseFactsAgree(source: Record<string, any>, purchase: Record<string, any>) {
  return ['price', 'purchase_quantity'].every(key => !source[key] || sameQuantity(source[key], purchase[key]))
    && ['purchase_no', 'purchase_line', 'purchase_date', 'supplier', 'currency'].every(key => !source[key] || String(source[key]).normalize('NFKC').trim().toLowerCase() === String(purchase[key]).normalize('NFKC').trim().toLowerCase())
}

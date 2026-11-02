// Six decimal places in the backend contract; avoid floating point in receipt previews.
const scale = 1_000_000n
export function receiptQuantity(value: string): bigint | undefined {
  if (!/^\d{1,12}(\.\d{1,6})?$/.test(value.trim())) return undefined
  const [whole, fraction = ''] = value.trim().split('.')
  const result = BigInt(whole!) * scale + BigInt(fraction.padEnd(6, '0'))
  return result < 1_000_000_000_000n * scale ? result : undefined
}
export function quantityText(value: bigint): string {
  const whole = value / scale, fraction = String(value % scale).padStart(6, '0').replace(/0+$/, '')
  return fraction ? `${whole}.${fraction}` : String(whole)
}
export function receiptTotal(values: string[]): string | undefined {
  const amounts = values.map(receiptQuantity)
  if (!amounts.length || !amounts.every(value => value !== undefined && value > 0n)) return undefined
  const total = amounts.reduce<bigint>((sum, value) => sum + value!, 0n)
  return total < 1_000_000_000_000n * scale ? quantityText(total) : undefined
}
// Round the complete receipt once to cents, matching Decimal HALF_UP.
export function receiptAmount(quantity: string, price: string): string | undefined {
  const count = receiptQuantity(quantity), rate = receiptQuantity(price)
  if (count === undefined || rate === undefined) return undefined
  const cents = (count * rate + 5_000_000_000n) / 10_000_000_000n
  return `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`
}
export function receiptAmountTotals(rows: { amount?: string; currency: string }[]): { currency: string; amount: string }[] {
  const groups = new Map<string, bigint>()
  for (const row of rows) {
    if (!row.currency || row.amount === undefined) continue
    const [whole, cents] = row.amount.split('.')
    groups.set(row.currency, (groups.get(row.currency) ?? 0n) + BigInt(whole! + cents!))
  }
  return [...groups].map(([currency, cents]) => ({ currency, amount: `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}` }))
}

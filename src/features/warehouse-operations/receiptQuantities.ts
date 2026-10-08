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

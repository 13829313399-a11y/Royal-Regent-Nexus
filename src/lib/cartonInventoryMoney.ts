export interface InventoryMoney {
  cost_status?: string
  cost_currency?: string
  cost_amount?: string | null
  cost_unit_price?: string | null
}

// Keep server Decimal values as decimal strings, including scientific notation.
function decimal(value: string): [bigint, bigint] | null {
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(value.trim())
  if (!match) return null
  const exponent = Number(match[4] || 0) - (match[3]?.length || 0)
  if (Math.abs(exponent) > 100) return null
  const integer = BigInt(`${match[1] === '-' ? '-' : ''}${match[2]}${match[3] || ''}`)
  return exponent >= 0 ? [integer * 10n ** BigInt(exponent), 1n] : [integer, 10n ** BigInt(-exponent)]
}

function rounded(numerator: bigint, denominator: bigint): bigint {
  const sign = numerator < 0n ? -1n : 1n
  const absolute = numerator * sign
  return sign * ((absolute * 2n + denominator) / (denominator * 2n))
}

function fixed(cents: bigint): string {
  const absolute = cents < 0n ? -cents : cents
  return `${cents < 0n ? '-' : ''}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`
}

export function estimateMoney(source: InventoryMoney | undefined, quantity: string | number): InventoryMoney {
  if (source?.cost_status !== '已计价' || source.cost_unit_price == null) return { cost_status: source?.cost_status || '待核算' }
  const price = decimal(source.cost_unit_price)
  const qty = decimal(String(quantity))
  if (!price || !qty || qty[0] <= 0n) return { cost_status: '请填写数量' }
  return { ...source, cost_amount: fixed(rounded(price[0] * qty[0] * 100n, price[1] * qty[1])) }
}

export function moneyLabel(source?: InventoryMoney): string {
  if (source?.cost_status !== '已计价' || source.cost_amount == null || !source.cost_currency) return source?.cost_status || '待核算'
  const amount = decimal(source.cost_amount)
  return amount ? `${source.cost_currency} ${fixed(rounded(amount[0] * 100n, amount[1]))}` : '待核算'
}

export function unitCostLabel(source?: InventoryMoney): string {
  if (source?.cost_status !== '已计价' || source.cost_unit_price == null) return ''
  const price = decimal(source.cost_unit_price)
  if (!price) return ''
  // Six places for reference only; calculations always use the full precision.
  const value = rounded(price[0] * 1000000n, price[1])
  const fraction = String(value % 1000000n).padStart(6, '0').replace(/0+$/, '')
  return `${source.cost_currency} ${value / 1000000n}${fraction ? `.${fraction}` : ''}`
}

export function moneyTotals(items: (InventoryMoney | undefined)[]) {
  const totals = new Map<string, bigint>()
  let pending = 0
  for (const source of items) {
    const amount = source?.cost_amount == null ? null : decimal(source.cost_amount)
    if (source?.cost_status !== '已计价' || !source.cost_currency || !amount) { pending++; continue }
    totals.set(source.cost_currency, (totals.get(source.cost_currency) || 0n) + rounded(amount[0] * 100n, amount[1]))
  }
  return { amounts: [...totals].sort(([a], [b]) => a.localeCompare(b)).map(([currency, cents]) => `${currency} ${fixed(cents)}`), pending }
}

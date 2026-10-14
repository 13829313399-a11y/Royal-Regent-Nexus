/** Exact positive Decimal text, including historical Python scientific notation. */
export function multiplyQuantity(value: string, sets: number): string | undefined {
  const match = /^(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(value)
  if (!match || !Number.isSafeInteger(sets) || sets < 0) return undefined
  const fraction = match[2] ?? '', exponent = Number(match[3] ?? 0)
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 40) return undefined
  const scale = fraction.length - exponent
  const digits = (BigInt(match[1]! + fraction) * BigInt(sets)).toString()
  if (scale <= 0) return digits + '0'.repeat(-scale)
  const padded = digits.padStart(scale + 1, '0')
  return `${padded.slice(0, -scale)}.${padded.slice(-scale)}`
}

/** Exact six-place quantities; never round a clerk's count through Number. */
export function subtractQuantities(base: string, ...values: string[]): string | undefined {
  const parse = (text: string) => {
    const match = /^(-?)(\d+)(?:\.(\d{1,6}))?$/.exec(text)
    if (!match) return undefined
    return BigInt(match[2]! + (match[3] ?? '').padEnd(6, '0')) * (match[1] ? -1n : 1n)
  }
  let total = parse(base)
  if (total === undefined) return undefined
  for (const value of values) { const parsed = parse(value); if (parsed === undefined) return undefined; total -= parsed }
  const digits = (total < 0n ? -total : total).toString().padStart(7, '0')
  const fraction = digits.slice(-6).replace(/0+$/, '')
  return `${total < 0n ? '-' : ''}${digits.slice(0, -6)}${fraction ? '.' + fraction : ''}`
}

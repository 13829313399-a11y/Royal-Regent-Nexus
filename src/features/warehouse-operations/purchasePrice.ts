export function purchasePriceText(price: string | null | undefined, unit: string) {
  return price ? `${price} 元／${unit}` : '待补价'
}

export function canonicalPurchasePrice(price: string | null | undefined) {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(price?.trim() ?? '')
  if (!match) return undefined
  const whole = match[2]!.replace(/^0+(?=\d)/, '')
  const fraction = match[3]?.replace(/0+$/, '')
  if (match[1] === '-' && (whole !== '0' || fraction)) return undefined
  return fraction ? `${whole}.${fraction}` : whole
}

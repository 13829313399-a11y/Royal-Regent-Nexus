import type { DecimalString, Money } from '../contracts'

/**
 * 前端金额与数量的展示层十进制工具。
 *
 * 契约要求：金额是「币种 + Decimal 字符串」，正式入账由后端 Decimal/Numeric 计算。
 * 这里的运算只用于样例联动、即时预览与舍入展示，不使用二进制浮点做正式计算。
 * 所有内部计算走 BigInt 定点数，避免 0.1 + 0.2 类误差。
 */

const DEFAULT_SCALE = 6

export function toDecimalString(value: DecimalString | number | null | undefined): DecimalString {
  if (value === null || value === undefined) return '0'
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '0'
    return trimTrailingZeros(value.toFixed(DEFAULT_SCALE))
  }
  return value.trim() === '' ? '0' : value.trim()
}

export function trimTrailingZeros(value: string): string {
  if (!value.includes('.')) return value
  return value.replace(/0+$/, '').replace(/\.$/, '')
}

function scaleOf(value: string): number {
  const dot = value.indexOf('.')
  return dot === -1 ? 0 : value.length - dot - 1
}

/** 把十进制字符串解析为 (整数, 小数位) 形式，允许前导正负号。 */
function parse(value: string): { digits: bigint; scale: number } {
  const raw = value.trim()
  const negative = raw.startsWith('-')
  const body = negative || raw.startsWith('+') ? raw.slice(1) : raw
  const [intPart = '0', fracPart = ''] = body.split('.')
  const digits = BigInt(`${intPart || '0'}${fracPart}` || '0')
  return { digits: negative ? -digits : digits, scale: fracPart.length }
}

function align(a: { digits: bigint; scale: number }, b: { digits: bigint; scale: number }) {
  const scale = Math.max(a.scale, b.scale)
  return {
    scale,
    left: a.digits * 10n ** BigInt(scale - a.scale),
    right: b.digits * 10n ** BigInt(scale - b.scale),
  }
}

export function decimalAdd(a: DecimalString, b: DecimalString): DecimalString {
  const aligned = align(parse(toDecimalString(a)), parse(toDecimalString(b)))
  return trimTrailingZeros(formatScaled(aligned.left + aligned.right, aligned.scale))
}

export function decimalSubtract(a: DecimalString, b: DecimalString): DecimalString {
  const aligned = align(parse(toDecimalString(a)), parse(toDecimalString(b)))
  return trimTrailingZeros(formatScaled(aligned.left - aligned.right, aligned.scale))
}

export function decimalMultiply(a: DecimalString, b: DecimalString): DecimalString {
  const left = parse(toDecimalString(a))
  const right = parse(toDecimalString(b))
  return formatScaled(left.digits * right.digits, left.scale + right.scale)
}

export function decimalDivide(a: DecimalString, b: DecimalString, scale = DEFAULT_SCALE): DecimalString {
  const left = parse(toDecimalString(a))
  const right = parse(toDecimalString(b))
  if (right.digits === 0n) return '0'
  // 多算 4 位再按 half-away-from-zero 舍入到目标位数，避免截断
  // （例如 0.7 ÷ 0.6 应得 1.166667，而不是截断的 1.166666）。
  const guard = 4
  const targetScale = right.scale + scale + guard
  const numerator = left.digits * 10n ** BigInt(targetScale)
  const denominator = right.digits * 10n ** BigInt(left.scale)
  const negative = (numerator < 0n) !== (denominator < 0n)
  const absNumerator = numerator < 0n ? -numerator : numerator
  const absDenominator = denominator < 0n ? -denominator : denominator
  const divisor = 10n ** BigInt(guard)
  const unscaled = absNumerator / absDenominator
  const quotient = unscaled / divisor
  const remainder = unscaled % divisor
  const rounded = remainder * 2n >= divisor ? quotient + 1n : quotient
  return formatScaled(negative ? -rounded : rounded, scale)
}

export function decimalCompare(a: DecimalString, b: DecimalString): number {
  const aligned = align(parse(toDecimalString(a)), parse(toDecimalString(b)))
  if (aligned.left === aligned.right) return 0
  return aligned.left > aligned.right ? 1 : -1
}

export function decimalIsZero(a: DecimalString): boolean {
  return parse(toDecimalString(a)).digits === 0n
}

export function decimalMin(a: DecimalString, b: DecimalString): DecimalString {
  return decimalCompare(a, b) <= 0 ? toDecimalString(a) : toDecimalString(b)
}

export function decimalMax(a: DecimalString, b: DecimalString): DecimalString {
  return decimalCompare(a, b) >= 0 ? toDecimalString(a) : toDecimalString(b)
}

export function decimalSum(values: Array<DecimalString | null | undefined>): DecimalString {
  return values.reduce<DecimalString>((total, value) => decimalAdd(total, toDecimalString(value)), '0')
}

/** 四舍五入到指定小数位（half-away-from-zero，与 Python Decimal 默认 ROUND_HALF_UP 一致）。 */
export function decimalRound(value: DecimalString, scale: number): DecimalString {
  const parsed = parse(toDecimalString(value))
  if (parsed.scale <= scale) return formatScaled(parsed.digits, parsed.scale)
  const divisor = 10n ** BigInt(parsed.scale - scale)
  const negative = parsed.digits < 0n
  const abs = negative ? -parsed.digits : parsed.digits
  const quotient = abs / divisor
  const remainder = abs % divisor
  const rounded = remainder * 2n >= divisor ? quotient + 1n : quotient
  return formatScaled(negative ? -rounded : rounded, scale)
}

export function decimalToNumber(value: DecimalString | null | undefined): number {
  if (value === null || value === undefined) return 0
  const parsed = parse(toDecimalString(value))
  return Number(parsed.digits) / 10 ** parsed.scale
}

export function formatScaled(digits: bigint, scale: number): string {
  if (scale === 0) return digits.toString()
  const negative = digits < 0n
  const abs = negative ? -digits : digits
  const text = abs.toString().padStart(scale + 1, '0')
  const intPart = text.slice(0, text.length - scale)
  const fracPart = text.slice(text.length - scale)
  return `${negative ? '-' : ''}${intPart}.${fracPart}`
}

/** 各币种小数位。未知币种按 2 位处理，并在调用处标注待确认。 */
export const CURRENCY_MINOR_UNITS: Record<string, number> = {
  HKD: 2,
  CNY: 2,
  RMB: 2,
  USD: 2,
}

export function currencyMinorUnits(currency: string): number {
  return CURRENCY_MINOR_UNITS[currency.toUpperCase()] ?? 2
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  HKD: 'HK$',
  CNY: '¥',
  RMB: '¥',
  USD: 'US$',
}

export function currencySymbol(currency: string): string {
  return CURRENCY_SYMBOLS[currency.toUpperCase()] ?? `${currency.toUpperCase()} `
}

export function formatMoney(
  money: Money | null | undefined,
  options: { symbol?: boolean; blank?: string; signed?: boolean } = {},
): string {
  const { symbol = true, blank = '—', signed = false } = options
  if (!money) return blank
  const minor = currencyMinorUnits(money.currency)
  const rounded = decimalRound(money.amount, minor)
  const negative = rounded.startsWith('-')
  const abs = negative ? rounded.slice(1) : rounded
  const [intPart, fracPart = ''] = abs.split('.')
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const decimals = fracPart.padEnd(minor, '0')
  const body = minor > 0 ? `${grouped}.${decimals}` : grouped
  const sign = negative ? '-' : signed ? '+' : ''
  return symbol ? `${sign}${currencySymbol(money.currency)}${body}` : `${sign}${body}`
}

export function formatDecimal(
  value: DecimalString | null | undefined,
  maxScale = 2,
  blank = '—',
): string {
  if (value === null || value === undefined || value === '') return blank
  const rounded = trimTrailingZeros(decimalRound(value, maxScale))
  return rounded
}

export function formatQty(value: number | null | undefined, blank = '0'): string {
  if (value === null || value === undefined) return blank
  return value.toLocaleString('en-US')
}

export function formatPercent(
  value: DecimalString | null | undefined,
  maxScale = 1,
  blank = '—',
): string {
  if (value === null || value === undefined) return blank
  return `${formatDecimal(decimalMultiply(value, '100'), maxScale)}%`
}

export function money(currency: string, amount: DecimalString): Money {
  return { currency, amount: decimalRound(amount, currencyMinorUnits(currency)) }
}

/**
 * 把总额按等分规则分配给 N 个人，余数按稳定顺序补到最小币种单位。
 * 例：1.00 给三人 = 0.34 + 0.33 + 0.33，合计完全一致，不会变成 0.99。
 */
export function splitRemainder(
  total: DecimalString,
  count: number,
  currency: string,
  order: number[] = [],
): DecimalString[] {
  if (count <= 0) return []
  const minor = currencyMinorUnits(currency)
  const roundedTotal = decimalRound(total, minor)
  const totalMinor = parse(roundedTotal).digits
  const base = totalMinor / BigInt(count)
  let remainder = totalMinor - base * BigInt(count)
  const step = remainder < 0n ? -1n : 1n
  const remainderCount = Number(remainder < 0n ? -remainder : remainder)
  const bump = new Set<number>()
  for (let index = 0; index < remainderCount; index += 1) {
    bump.add(order[index] ?? index)
  }
  return Array.from({ length: count }, (_, index) => {
    const value = bump.has(index) ? base + step : base
    return formatScaled(value, minor)
  })
}

/** 折合瓶数 = 可用 ml / 包装容量 ml。包装容量缺失时返回 null，不假设 1000。 */
export function bottlesFromMl(availableMl: DecimalString, packageMl: DecimalString): DecimalString | null {
  if (decimalIsZero(packageMl)) return null
  return decimalDivide(availableMl, packageMl, 3)
}

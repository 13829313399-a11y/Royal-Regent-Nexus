import { computed, onBeforeUnmount, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import type { DimensionPreferenceScope } from './dimensionPreference'

export type DisplayCurrency = 'CNY' | 'HKD'
export interface MoneyPreference { currency: DisplayCurrency; cnyToHkd: string }
export const moneyPreferenceKey = (scope: DimensionPreferenceScope) =>
  `carton-money-display:v1:${encodeURIComponent(scope.userId)}:${scope.employmentEpoch}`
const eventName = 'carton-money-display-changed'
const defaults = (): MoneyPreference => ({ currency: 'CNY', cnyToHkd: '' })
export const validHkdRate = (value: string) => /^\d{1,6}(?:\.\d{1,8})?$/.test(value.trim()) && /[1-9]/.test(value)

/** Exact decimal multiplication, rounded half up. Display only; never used in ledger writes. */
export function convertCnyToHkd(value: string | number | null | undefined, rate: string, places: 2 | 6 = 2): string | null {
  if (value == null || !validHkdRate(rate)) return null
  const source = String(value).trim()
  if (!/^-?\d{1,24}(?:\.\d{1,12})?$/.test(source)) return null
  const decimal = (text: string) => {
    const [whole = '', fraction = ''] = text.split('.')
    return { integer: BigInt(whole + fraction), scale: fraction.length }
  }
  const negative = source.startsWith('-')
  const a = decimal(source.replace(/^-/, '')), b = decimal(rate.trim())
  const product = a.integer * b.integer * 10n ** BigInt(places)
  const denominator = 10n ** BigInt(a.scale + b.scale)
  const rounded = (product + denominator / 2n) / denominator
  const digits = rounded.toString().padStart(places + 1, '0')
  return `${negative && rounded !== 0n ? '-' : ''}${digits.slice(0, -places)}.${digits.slice(-places)}`
}

/** Per-account browser display preference, independent of invoice currency and settlement state. */
export function useMoneyPreference(scope: MaybeRefOrGetter<DimensionPreferenceScope | null>) {
  const preference = ref<MoneyPreference>(defaults()), error = ref('')
  const key = computed(() => { const current = toValue(scope); return current ? moneyPreferenceKey(current) : '' })
  function read() {
    preference.value = defaults(); error.value = ''
    if (!key.value) return
    try {
      const saved = JSON.parse(window.localStorage.getItem(key.value) || 'null')
      if (saved && (saved.currency === 'CNY' || saved.currency === 'HKD')) {
        const rate = typeof saved.cnyToHkd === 'string' && validHkdRate(saved.cnyToHkd) ? saved.cnyToHkd.trim() : ''
        preference.value = { currency: saved.currency === 'HKD' && rate ? 'HKD' : 'CNY', cnyToHkd: rate }
      }
    } catch { /* Invalid or unavailable storage retains the RMB default. */ }
  }
  watch(key, read, { immediate: true, flush: 'sync' })
  function setPreference(currency: DisplayCurrency, rate: string): boolean {
    error.value = ''
    if (!key.value) { error.value = '请登录后设置金额显示。'; return false }
    if (!['CNY', 'HKD'].includes(currency) || ((currency === 'HKD' || rate.trim()) && !validHkdRate(rate))) {
      error.value = '请输入有效汇率：1 人民币等于多少港币，大于 0，最多 8 位小数。'; return false
    }
    const next = { currency, cnyToHkd: rate.trim() }
    preference.value = next
    try { window.localStorage.setItem(key.value, JSON.stringify(next)) }
    catch { error.value = '当前浏览器无法保存金额习惯，本次可用，重新打开后需再次设置。' }
    window.dispatchEvent(new CustomEvent(eventName, { detail: { key: key.value, preference: next } }))
    return true
  }
  const changed = (event: Event) => {
    const detail = (event as CustomEvent<{ key: string; preference: MoneyPreference }>).detail
    if (detail?.key === key.value) preference.value = { ...detail.preference }
  }
  const storageChanged = (event: StorageEvent) => { if (event.key === key.value || event.key === null) read() }
  window.addEventListener(eventName, changed)
  window.addEventListener('storage', storageChanged)
  onBeforeUnmount(() => { window.removeEventListener(eventName, changed); window.removeEventListener('storage', storageChanged) })
  function reference(value: string | number | null | undefined, sourceCurrency: string, places: 2 | 6 = 2): string {
    if (preference.value.currency !== 'HKD' || sourceCurrency.trim().toUpperCase() !== 'CNY') return ''
    const converted = convertCnyToHkd(value, preference.value.cnyToHkd, places)
    return converted == null ? '' : `港币参考 HK$${converted}`
  }
  return { preference, error, setPreference, reference }
}

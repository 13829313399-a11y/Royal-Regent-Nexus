import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { convertCnyToHkd, moneyPreferenceKey, useMoneyPreference, validHkdRate } from '../moneyPreference'
import type { DimensionPreferenceScope } from '../dimensionPreference'

afterEach(() => { window.localStorage.clear(); vi.restoreAllMocks() })

function harness() {
  const scope = ref<DimensionPreferenceScope | null>({ userId: 'alice', employmentEpoch: 1 })
  let money!: ReturnType<typeof useMoneyPreference>
  const wrapper = mount(defineComponent({ setup() { money = useMoneyPreference(scope); return () => null } }))
  return { wrapper, scope, money }
}

describe('CNY to HKD reference arithmetic', () => {
  it.each([
    ['10.23', '1.1', 2, '11.25'], ['0.005', '1', 2, '0.01'], ['-0.005', '1', 2, '-0.01'],
    ['-0.0049', '1', 2, '0.00'], ['0', '1.1', 2, '0.00'], ['1.005', '1', 2, '1.01'],
    ['0.123456', '1.12345678', 6, '0.138697'], ['0.000001', '0.5', 6, '0.000001'],
    ['999999999999999999.99', '1.25', 2, '1249999999999999999.99'],
  ] as const)('converts %s at %s with %s decimals without floating point loss', (value, rate, places, expected) => {
    expect(convertCnyToHkd(value, rate, places)).toBe(expected)
  })
  it.each(['', '0', '-1', 'NaN', 'Infinity', '1e3', '1.123456789', '1000000', '1,1'])('rejects invalid rates %s', rate => {
    expect(validHkdRate(rate)).toBe(false)
    expect(convertCnyToHkd('100', rate)).toBeNull()
  })
  it.each([undefined, null, '', '待核实', NaN, Infinity, '1,000', '1e24'])('never converts an unknown amount to zero: %s', value => {
    expect(convertCnyToHkd(value, '1.1')).toBeNull()
  })
})

describe('personal money display preference', () => {
  it('defaults to RMB and synchronizes display across mounted views, without treating other currencies as RMB', () => {
    const first = harness(), second = harness()
    try {
      expect(first.money.preference.value).toEqual({ currency: 'CNY', cnyToHkd: '' })
      expect(first.money.setPreference('HKD', '')).toBe(false)
      expect(first.money.error.value).toContain('有效汇率')
      expect(second.money.reference('20', 'CNY')).toBe('')
      expect(first.money.setPreference('HKD', '1.1')).toBe(true)
      expect(second.money.reference('20', 'CNY')).toBe('港币参考 HK$22.00')
      expect(second.money.reference('2', 'CNY', 6)).toBe('港币参考 HK$2.200000')
      expect(second.money.reference('20', 'HKD')).toBe('')
      expect(second.money.reference('20', 'USD')).toBe('')
      expect(second.money.reference(null, 'CNY')).toBe('')
      first.money.setPreference('CNY', '1.1')
      expect(second.money.reference('20', 'CNY')).toBe('')
    } finally { first.wrapper.unmount(); second.wrapper.unmount() }
  })
  it('isolates accounts and employment identities, restores saved settings and rejects anonymous writes', () => {
    const { wrapper, scope, money } = harness()
    try {
      money.setPreference('HKD', '1.1')
      scope.value = { userId: 'bob', employmentEpoch: 1 }
      expect(money.preference.value.currency).toBe('CNY')
      scope.value = { userId: 'alice', employmentEpoch: 2 }
      expect(money.reference('20', 'CNY')).toBe('')
      scope.value = { userId: 'alice', employmentEpoch: 1 }
      expect(money.reference('20', 'CNY')).toBe('港币参考 HK$22.00')
      scope.value = null
      expect(money.setPreference('HKD', '1.2')).toBe(false)
      expect(money.reference('20', 'CNY')).toBe('')
    } finally { wrapper.unmount() }
  })
  it('validates storage updates and resets when cleared in another tab', () => {
    const { wrapper, money } = harness(), key = moneyPreferenceKey({ userId: 'alice', employmentEpoch: 1 })
    try {
      for (const saved of ['broken', '{"currency":"HKD","cnyToHkd":"0"}', '{"currency":"USD","cnyToHkd":"1"}']) {
        window.localStorage.setItem(key, saved)
        window.dispatchEvent(new StorageEvent('storage', { key }))
        expect(money.reference('20', 'CNY')).toBe('')
      }
      window.localStorage.setItem(key, JSON.stringify({ currency: 'HKD', cnyToHkd: '1.2' }))
      window.dispatchEvent(new StorageEvent('storage', { key }))
      expect(money.reference('20', 'CNY')).toBe('港币参考 HK$24.00')
      window.localStorage.clear(); window.dispatchEvent(new StorageEvent('storage', { key: null }))
      expect(money.reference('20', 'CNY')).toBe('')
    } finally { wrapper.unmount() }
  })
  it('continues to synchronize this session if browser storage is unavailable', () => {
    const first = harness(), second = harness()
    try {
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
      first.money.setPreference('HKD', '1.1')
      expect(first.money.error.value).toContain('无法保存')
      expect(second.money.reference('20', 'CNY')).toBe('港币参考 HK$22.00')
    } finally { first.wrapper.unmount(); second.wrapper.unmount() }
  })
})

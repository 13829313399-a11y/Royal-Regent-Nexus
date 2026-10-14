import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { describe, expect, it } from 'vitest'
import { calculateSewingGroupTotalHkd, normalizeInternalQuotePayload, type SewingPayload } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

describe('sewing pending prices and per-row multipliers', () => {
  it('retains blank inputs and source amount through normalization and edits', async () => {
    const modelValue = reactive(normalizeInternalQuotePayload('sewing', { groups: [{ name: '衣服', materials: [
      { item: 'IC灯', usage: null, unit_price_rmb: null, unit_price_source_currency: 'RMB', quoted_price_hkd: '17.55', markup: '1.1' },
      { item: '手工', usage: 1, unit_price_rmb: '1.7', markup: '1.1', extra_multiplier: '1.5' },
    ] }] }) as SewingPayload)
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'sewing', modelValue, rmbHkdRate: .85 } })
    expect(wrapper.text()).toContain('待补用量、单价；已按原价计入')
    expect(calculateSewingGroupTotalHkd(modelValue.groups[0], .85)).toBeCloseTo(20.85)
    const multipliers = wrapper.findAll('input[aria-label="车缝额外倍率"]')
    await multipliers[1].setValue('1.8')
    expect(calculateSewingGroupTotalHkd(modelValue.groups[0], .85)).toBeCloseTo(21.51)
    await wrapper.findAll('input[aria-label="车缝单价 RMB"]')[0].setValue('8.5')
    expect(wrapper.text()).toContain('待补用量、单价；已按原价计入')
    await wrapper.findAll('input[aria-label="车缝用量每码"]')[0].setValue('1')
    expect(wrapper.text()).not.toContain('待补用量、单价；已按原价计入')
    expect(calculateSewingGroupTotalHkd(modelValue.groups[0], .85)).toBeCloseTo(14.96)
    await wrapper.findAll('input[aria-label="车缝单价 RMB"]')[0].setValue('')
    const reloaded = normalizeInternalQuotePayload('sewing', JSON.parse(JSON.stringify(modelValue))) as SewingPayload
    expect(reloaded.groups[0].materials[0].unit_price_rmb).toBeNull()
    expect(reloaded.groups[0].materials[1].extra_multiplier).toBe(1.8)
    expect(calculateSewingGroupTotalHkd(reloaded.groups[0], .85)).toBeCloseTo(21.51)
    wrapper.unmount()
  })

  it('preserves HKD pending prices and locks multiplier controls on a frozen section', () => {
    const modelValue = normalizeInternalQuotePayload('sewing', { groups: [{ materials: [
      { item: 'IC灯', usage: null, unit_price_hkd: null, unit_price_source_currency: 'HKD', quoted_price_hkd: 17.55 },
    ] }] }) as SewingPayload
    expect(modelValue.groups[0].materials[0].unit_price_hkd).toBeNull()
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'sewing', modelValue, disabled: true, rmbHkdRate: .85 } })
    expect(wrapper.get('input[aria-label="车缝额外倍率"]').attributes('disabled')).toBeDefined()
    expect(calculateSewingGroupTotalHkd(modelValue.groups[0], .85)).toBe(17.55)
    wrapper.unmount()
  })
})

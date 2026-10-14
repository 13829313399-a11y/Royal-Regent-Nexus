import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { describe, expect, it } from 'vitest'
import { cloneInternalQuotePayload, normalizeInternalQuotePayload, type EngineeringPayload, type SalesPayload } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

describe('optional quote cost defaults', () => {
  it('starts fresh engineering with allocation off and preserves inputs when toggled', async () => {
    const modelValue = reactive(normalizeInternalQuotePayload('engineering', {}) as EngineeringPayload)
    expect(modelValue.mold_allocation_enabled).toBe(false)
    modelValue.production_mold_costs[0].cost_rmb = 7750
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'engineering', modelValue } })
    const toggle = wrapper.get('input[aria-label="启用生产模具费用分摊"]')
    expect((toggle.element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.text()).toContain('暂不分摊')
    await toggle.setValue(true)
    expect(modelValue.mold_allocation_enabled).toBe(true)
    await toggle.setValue(false)
    const reloaded = cloneInternalQuotePayload('engineering', modelValue) as EngineeringPayload
    expect(reloaded.mold_allocation_enabled).toBe(false)
    expect(reloaded.production_mold_costs[0].cost_rmb).toBe(7750)
    wrapper.unmount()
  })

  it('starts testing, freight and lifting off and enables them independently', async () => {
    const modelValue = reactive(normalizeInternalQuotePayload('sales', {}) as SalesPayload)
    modelValue.testing_fee_total_usd = 100
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'sales', modelValue } })
    for (const label of ['启用测试费计算', '启用运费计算', '启用吊柜费计算']) {
      expect((wrapper.get(`input[aria-label="${label}"]`).element as HTMLInputElement).checked).toBe(false)
    }
    await wrapper.get('input[aria-label="启用运费计算"]').setValue(true)
    expect(modelValue.freight_calc).toMatchObject({ enabled: true, freight_enabled: true, lifting_enabled: false })
    await wrapper.get('input[aria-label="启用吊柜费计算"]').setValue(true)
    await wrapper.get('input[aria-label="启用运费计算"]').setValue(false)
    expect(modelValue.freight_calc).toMatchObject({ enabled: true, freight_enabled: false, lifting_enabled: true })
    await wrapper.get('input[aria-label="启用吊柜费计算"]').setValue(false)
    const reloaded = cloneInternalQuotePayload('sales', modelValue) as SalesPayload
    expect(reloaded.testing_fee_enabled).toBe(false)
    expect(reloaded.testing_fee_total_usd).toBe(100)
    expect(reloaded.freight_calc).toMatchObject({ enabled: false, freight_enabled: false, lifting_enabled: false })
    wrapper.unmount()
  })

  it('retains explicit saved choices and the interpretation of historical payloads', () => {
    expect(normalizeInternalQuotePayload('engineering', { mold_allocation_enabled: true })).toMatchObject({ mold_allocation_enabled: true })
    expect(normalizeInternalQuotePayload('engineering', { molds: [{ cost_rmb: 100 }] })).toMatchObject({ mold_allocation_enabled: true })
    expect(normalizeInternalQuotePayload('sales', { testing_fee_total_usd: 100, freight_calc: { cap_40: 1980 } })).toMatchObject({
      testing_fee_enabled: true, freight_calc: { enabled: true, freight_enabled: true, lifting_enabled: true },
    })
  })
})

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { reactive } from 'vue'

import { normalizeInternalQuotePayload, type PaintingPayload } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

describe('painting UV entry', () => {
  it('shows the final paint price once and updates the quick total without an extra tax field', async () => {
    const modelValue = reactive(normalizeInternalQuotePayload('painting', { quote_mode: 'quick',
      quick_quote: { spray_labor_hkd: .48, paint_hkd: .2, paint_tax_rate_percent: 13 } }))
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'painting', modelValue } })
    expect(wrapper.text()).not.toContain('油漆税金')
    expect(wrapper.get('.quick-readonly.total output').text()).toBe('HKD 0.680')
    await wrapper.get('[aria-label="喷油快捷报价油漆 HKD"]').setValue('.3')
    expect(wrapper.get('.quick-readonly.total output').text()).toBe('HKD 0.780')
    wrapper.unmount()
  })

  it.each(['ordinary', 'component'] as const)('edits UV and keeps other operation prices in %s mode', async mode => {
    const modelValue = reactive(normalizeInternalQuotePayload('painting', { rows: [
      { name: '外壳', position: '正面', pricing_component_id: 'shell', operations: { spray: { quantity: 3, unit_price_hkd: .08 } } },
    ] }))
    const wrapper = mount(InternalQuoteSectionForm, { props: {
      code: 'painting', modelValue, ...(mode === 'component' ? {
        pricingMode: 'component' as const, pricingComponents: [{ id: 'shell', name: '外壳', markup_x: 1.2 }], activePricingComponentId: 'shell',
      } : {}),
    } })
    const headings = wrapper.findAll('table.painting thead tr:first-child th').map(th => th.text())
    expect(headings.slice(4, 8)).toEqual(['夹模', '移印', 'UV', '散枪'])
    await wrapper.get('[aria-label="UV数量"]').setValue('2')
    await wrapper.get('[aria-label="UV单价 HKD"]').setValue('0.52')
    const row = (modelValue as unknown as PaintingPayload).rows[0]
    expect(row.operations.uv).toEqual({ quantity: 2, unit_price_hkd: .52 })
    expect(row.operations.spray).toEqual({ quantity: 3, unit_price_hkd: .08 })
    expect(wrapper.get('table.painting tbody .amount').text()).toBe('1.280')
    expect(wrapper.get('table.painting tfoot').text()).toContain('1.040')
    await wrapper.setProps({ disabled: true })
    expect(wrapper.get('[aria-label="UV单价 HKD"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})

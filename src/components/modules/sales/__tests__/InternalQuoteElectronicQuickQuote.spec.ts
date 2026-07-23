import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteSectionForm from '@/components/modules/sales/internal-quote/InternalQuoteSectionForm.vue'
import { normalizeInternalQuotePayload, type ElectronicPayload } from '@/lib/internalQuoteSectionPayload'

describe('InternalQuoteSectionForm electronic quick quote', () => {
  it('shows the requested fields, calculates HKD and supports adding and deleting rows', async () => {
    const payload = normalizeInternalQuotePayload('electronic', {
      quote_mode: 'quick',
      quick_quotes: [{ item: '主控板', unit_price_rmb: 10, tax_rate_percent: 13, remark: '含税' }],
    }) as unknown as ElectronicPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'electronic',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
        rmbHkdRate: .85,
      },
    })

    expect(wrapper.get('input[aria-label="电子快捷报价零件名称"]').element).toHaveProperty('value', '主控板')
    expect(wrapper.get('input[aria-label="电子快捷报价单价 RMB"]').element).toHaveProperty('value', '10')
    expect(wrapper.get('input[aria-label="电子快捷报价税点"]').element).toHaveProperty('value', '13')
    expect(wrapper.get('input[aria-label="电子快捷报价备注"]').element).toHaveProperty('value', '含税')
    expect(wrapper.get('.electronicQuickTable .calculated-cell').text()).toBe('11.765')

    const addButton = wrapper.findAll('button').find((button) => button.text().includes('新增电子件'))
    expect(addButton).toBeDefined()
    await addButton!.trigger('click')
    expect(payload.quick_quotes).toHaveLength(2)
    expect(payload.quick_quotes[1]).toEqual({ item: '', unit_price_rmb: 0, tax_rate_percent: 13, remark: '' })

    const deleteButtons = wrapper.findAll('button[aria-label="删除电子快捷报价行"]')
    await deleteButtons[1].trigger('click')
    expect(payload.quick_quotes).toHaveLength(1)
  })
})

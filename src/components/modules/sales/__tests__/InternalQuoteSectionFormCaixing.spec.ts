import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteSectionForm from '@/components/modules/sales/internal-quote/InternalQuoteSectionForm.vue'
import { normalizeInternalQuotePayload, type SalesPayload } from '@/lib/internalQuoteSectionPayload'

describe('InternalQuoteSectionForm Caixing fields', () => {
  it('keeps only customer-specific metadata and reuses the shared carton and cost sections', () => {
    const payload = normalizeInternalQuotePayload('sales', {
      customer_quote_fields: {
        caixing: {
          product_type: 'plastic',
          item_number: '68963',
          item_name: 'Transforming Power Sword',
          quote_date: '2026-06-27',
          carton_length_in: 13,
          cost_rows: [{ group: 'purchase', description: '旧重复行' }],
        },
      },
    }) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        customer: '彩星',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
      },
    })

    expect(wrapper.text()).toContain('彩星客户报价专属资料')
    expect(wrapper.text()).toContain('外箱资料自动读取上方“基础纸箱”')
    expect(wrapper.find('input[aria-label="彩星 Item Number"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="彩星 Item Description"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="彩星 Quote Date"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="彩星 Carton Length"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="彩星 Carton CUFT"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="彩星 Pcs Per Shipper"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="彩星 Carton Price"]').exists()).toBe(false)
    expect(wrapper.find('select[aria-label="彩星 Cost Group"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('彩星塑胶/毛绒模板分组部分')
    expect(payload.customer_quote_fields.caixing).toEqual({
      product_type: 'plastic',
      item_number: '68963',
      item_name: 'Transforming Power Sword',
      quote_date: '2026-06-27',
    })
  })
})

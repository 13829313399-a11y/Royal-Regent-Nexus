import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteSectionForm from '../internal-quote/InternalQuoteSectionForm.vue'
import { normalizeInternalQuotePayload, cloneInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'

describe('Silverlit internal domestic quote handoff', () => {
  it('preserves an explicit RMB price and a deliberate zero through normalize/save', () => {
    for (const price of [55.615, 0, null]) {
      const payload = normalizeInternalQuotePayload('sales', {customer_quote_fields:{yinhui:{domestic_price_rmb:price}}})
      expect(cloneInternalQuotePayload('sales', payload).customer_quote_fields.yinhui.domestic_price_rmb).toBe(price)
    }
    expect(normalizeInternalQuotePayload('sales', {}).customer_quote_fields.yinhui.domestic_price_rmb).toBeNull()
  })
  it('shows the independent field for Huaxing Silverlit and updates the saved payload', async () => {
    const payload = normalizeInternalQuotePayload('sales', {})
    const wrapper = mount(InternalQuoteSectionForm, {props:{code:'sales',customer:'银辉',factoryId:'huaxing',modelValue:payload as unknown as Record<string,unknown>}})
    await wrapper.get('input[aria-label="银辉内销最终单价 RMB"]').setValue('55.615')
    expect(cloneInternalQuotePayload('sales', payload).customer_quote_fields.yinhui.domestic_price_rmb).toBe(55.615)
    await wrapper.setProps({factoryId:'huakang-a'})
    expect(wrapper.find('[data-testid="yinhui-domestic-price"]').exists()).toBe(false)
  })
})

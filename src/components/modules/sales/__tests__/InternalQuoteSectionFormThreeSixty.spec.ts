import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteSectionForm from '@/components/modules/sales/internal-quote/InternalQuoteSectionForm.vue'
import { normalizeInternalQuotePayload, type SalesPayload } from '@/lib/internalQuoteSectionPayload'

describe('InternalQuoteSectionForm 360 fields', () => {
  it('collects only customer header data and a server freight route', () => {
    const payload = normalizeInternalQuotePayload('sales', {
      customer_quote_fields: {
        three_sixty: {
          ms_brand: 'Cuddle Baby',
          prepared_by: '郑大能',
          quote_date: '2026-06-26',
          revision: '0',
          first_etd: '2026-08-01',
          freight_route_key: 'yt40',
          carton_length_in: 24.75,
          carton_price_hkd: 10.4,
          cost_rows: [{ group: 'purchase', description: '旧重复行' }],
        },
      },
    }) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        customer: '360',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
        referenceSnapshot: {
          freight: {
            routes: [{
              route_key: 'yt40',
              route_name: '40尺盐田柜',
              capacity_key: 'cap_40',
              freight_hkd: 7775,
              lifting_hkd: 0,
            }],
          },
        },
      },
    })

    expect(wrapper.text()).toContain('360 客户报价专属资料')
    expect(wrapper.text()).toContain('纸箱、CU.FT、装箱数、测试费及各分段成本均自动读取')
    for (const label of ['360 MS Brand', '360 製表人', '360 发行日期', '360 Version', '360 首次货柜出货日期']) {
      expect(wrapper.find(`input[aria-label="${label}"]`).exists()).toBe(true)
    }
    expect(wrapper.find('select[aria-label="360 运费路线"]').exists()).toBe(true)
    expect(wrapper.find('input[aria-label="360 Carton Length"]').exists()).toBe(false)
    expect(payload.customer_quote_fields.three_sixty).toEqual({
      ms_brand: 'Cuddle Baby',
      prepared_by: '郑大能',
      quote_date: '2026-06-26',
      revision: '0',
      first_etd: '2026-08-01',
      freight_route_key: 'yt40',
    })
  })
})

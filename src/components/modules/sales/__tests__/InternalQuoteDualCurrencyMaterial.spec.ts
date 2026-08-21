import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteSectionForm from '@/components/modules/sales/internal-quote/InternalQuoteSectionForm.vue'
import { normalizeInternalQuotePayload, type EngineeringPayload, type SalesPayload } from '@/lib/internalQuoteSectionPayload'

describe('InternalQuoteSectionForm dual-currency material prices', () => {
  it('lets sales enter packaging material HKD and derives RMB and amount', async () => {
    const payload = normalizeInternalQuotePayload('sales', {
      packaging_materials: [{
        item: '彩盒',
        specification: '四彩',
        category: 'color_box_inner_card',
        quantity: 2,
        unit_price_rmb: 3.4,
        tax_rate_percent: 10,
      }],
    }) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
        rmbHkdRate: .85,
      },
    })

    expect(wrapper.get('input[aria-label="包装材料原单价 RMB"]').attributes('step')).toBe('0.001')
    expect(wrapper.get('input[aria-label="包装材料原单价 HKD"]').attributes('step')).toBe('0.001')
    expect(wrapper.get('input[aria-label="包装材料用量"]').attributes('step')).toBe('1')
    expect(wrapper.get('input[aria-label="包装材料损耗率"]').attributes('step')).toBe('0.1')
    expect(wrapper.get('input[aria-label="包装材料原单价 HKD"]').element).toHaveProperty('value', '4')
    await wrapper.get('input[aria-label="包装材料原单价 HKD"]').setValue('5.2')

    expect(payload.packaging_materials[0]).toMatchObject({
      unit_price_source_currency: 'HKD',
      unit_price_hkd: 5.2,
      unit_price_rmb: 4.42,
    })
    expect(wrapper.findAll('.packagingMaterials tbody .calculated-cell')[1]?.text()).toBe('10.400')

    await wrapper.get('input[aria-label="包装材料原单价 RMB"]').setValue('3.4')
    expect(payload.packaging_materials[0]).toMatchObject({
      unit_price_source_currency: 'RMB',
      unit_price_rmb: 3.4,
      unit_price_hkd: 4,
    })
    expect(wrapper.findAll('.packagingMaterials tbody .calculated-cell')[1]?.text()).toBe('8.000')
  })

  it('lets engineering enter auxiliary material HKD and derives RMB and total', async () => {
    const payload = normalizeInternalQuotePayload('engineering', {
      materials: [{
        item: '胶袋',
        category: 'auxiliary',
        auxiliary_category: '胶袋',
        quantity: 3,
        unit_price_hkd: 1.5,
        tax_rate_percent: 13,
      }],
    }) as unknown as EngineeringPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'engineering',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
        rmbHkdRate: .85,
      },
    })

    expect(wrapper.get('input[aria-label="辅助材料/外购件原单价 RMB"]').attributes('step')).toBe('0.001')
    expect(wrapper.get('input[aria-label="辅助材料/外购件原单价 HKD"]').attributes('step')).toBe('0.001')
    expect(wrapper.get('input[aria-label="辅助材料/外购件用量"]').attributes('step')).toBe('1')
    expect(wrapper.get('input[aria-label="辅助材料/外购件损耗率"]').attributes('step')).toBe('0.1')
    expect(wrapper.get('input[aria-label="辅助材料/外购件原单价 RMB"]').element).toHaveProperty('value', '1.275')
    expect(wrapper.get('input[aria-label="辅助材料/外购件原单价 HKD"]').element).toHaveProperty('value', '1.5')
    await wrapper.get('input[aria-label="辅助材料/外购件原单价 HKD"]').setValue('2')

    expect(payload.materials[0]).toMatchObject({
      unit_price_source_currency: 'HKD',
      unit_price_hkd: 2,
      unit_price_rmb: 1.7,
    })
    expect(wrapper.findAll('.engineeringAuxiliary tbody .calculated-cell')[1]?.text()).toBe('6.000')
  })
})

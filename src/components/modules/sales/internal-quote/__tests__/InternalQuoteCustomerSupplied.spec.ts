import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { reactive } from 'vue'
import { getInternalQuoteFormBlocks } from '@/lib/internalQuoteBlockProgress'
import { calculateCustomerSuppliedFeeHkd, normalizeInternalQuotePayload, type SalesPayload } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

const components = [{ id: 'a', name: '主体', markup_x: 1.2 }, { id: 'b', name: '电话', markup_x: 1.5 }]
const material = { item: '眼睛饰品', unit_price_hkd: .8, fee_rate_percent: 3, pricing_component_id: 'a' }
const normalized = (rows: unknown[]) => normalizeInternalQuotePayload('sales', {
  pricing_mode: 'component', pricing_components: components, customer_supplied_materials: rows,
})

describe('JustPlay customer-supplied custody fees', () => {
  it('keeps fees scoped to their component while editing, adding and deleting', async () => {
    const payload = reactive(normalized([material, { ...material, item: '电话饰片', unit_price_hkd: 2, fee_rate_percent: 5, pricing_component_id: 'b' }]))
    const sales = payload as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'sales', modelValue: payload,
      pricingMode: 'component', pricingComponents: components, activePricingComponentId: 'a' } })
    expect(wrapper.get('[aria-label="客供物料保管费 HKD"]').text()).toBe('0.0240')
    expect(wrapper.findAll('[aria-label="客供物料名称"]')).toHaveLength(1)
    await wrapper.get('[aria-label="客供物料费率 %"]').setValue('4')
    expect(wrapper.get('[aria-label="客供物料保管费 HKD"]').text()).toBe('0.0320')
    await wrapper.setProps({ activePricingComponentId: 'b' })
    expect(wrapper.get<HTMLInputElement>('[aria-label="客供物料名称"]').element.value).toBe('电话饰片')
    expect(wrapper.get('[aria-label="客供物料保管费 HKD"]').text()).toBe('0.1000')
    await wrapper.get('[aria-label="新增客供物料"]').trigger('click')
    expect(sales.customer_supplied_materials?.at(-1)?.pricing_component_id).toBe('b')
    await wrapper.findAll('[aria-label="删除客供物料"]')[0]!.trigger('click')
    expect(sales.customer_supplied_materials?.map(row => row.item)).toEqual(['眼睛饰品', ''])
    expect(sales.customer_supplied_materials?.[0]?.fee_rate_percent).toBe(4)
    await wrapper.setProps({ disabled: true })
    expect(wrapper.get('[aria-label="新增客供物料"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[aria-label="客供物料费率 %"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('validates started rows, accepts zero fees, and discards markup overrides', () => {
    const status = (rows: unknown[]) => getInternalQuoteFormBlocks('sales', normalized(rows)).find(block => block.id === 'customer-supplied-materials')?.status
    expect(status([])).toBe('optional')
    expect(status([material])).toBe('complete')
    expect(status([{ ...material, fee_rate_percent: 0 }])).toBe('complete')
    for (const change of [{ item: '' }, { unit_price_hkd: '' }, { unit_price_hkd: -1 }, { fee_rate_percent: 101 }, { fee_rate_percent: '' }]) {
      expect(status([{ ...material, ...change }])).toBe('partial')
    }
    const row = (normalized([{ ...material, markup_override: 2 }]) as unknown as SalesPayload).customer_supplied_materials![0]!
    expect(row).not.toHaveProperty('markup_override')
    expect(calculateCustomerSuppliedFeeHkd(row)).toBe(.024)
    expect(calculateCustomerSuppliedFeeHkd({ ...row, unit_price_hkd: .35, fee_rate_percent: .1 })).toBe(.0004)
    expect(calculateCustomerSuppliedFeeHkd({ ...row, unit_price_hkd: .15, fee_rate_percent: .1 })).toBe(.0002)
    expect(row.pricing_component_id).toBe('a')
  })

  it('does not show this section for ordinary customers', () => {
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'sales', modelValue: normalizeInternalQuotePayload('sales', {}), pricingMode: 'standard' } })
    expect(wrapper.find('.sales-customer-supplied').exists()).toBe(false)
    wrapper.unmount()
  })
})

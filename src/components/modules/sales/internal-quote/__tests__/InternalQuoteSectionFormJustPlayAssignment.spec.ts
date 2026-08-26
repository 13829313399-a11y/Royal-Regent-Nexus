import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { normalizeInternalQuotePayload, type EngineeringPayload, type SalesPricingComponent } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteComponentScopePicker from '../InternalQuoteComponentScopePicker.vue'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

const pricingComponents: SalesPricingComponent[] = [
  { id: 'component-01', name: '配件一', markup_x: 1.2 },
  { id: 'component-02', name: '配件二', markup_x: 1.25 },
]

function engineeringModel() {
  return normalizeInternalQuotePayload('engineering', {
    materials: [
      { item: '五金件 A', category: 'hardware', quantity: 1, unit_price_rmb: 2, pricing_component_id: 'component-01' },
      { item: '五金件 B', category: 'hardware', quantity: 1, unit_price_rmb: 3, pricing_component_id: 'component-02' },
      { item: '胶袋', category: 'auxiliary', auxiliary_category: '胶袋', quantity: 1, unit_price_rmb: 1 },
    ],
  }) as unknown as EngineeringPayload
}

describe('InternalQuoteSectionForm JustPlay component scope', () => {
  it('filters rows by the shared active component and gives new rows that component automatically', async () => {
    const modelValue = engineeringModel()
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'engineering',
        modelValue: modelValue as unknown as Record<string, unknown>,
        pricingMode: 'component',
        pricingComponents,
        activePricingComponentId: 'component-01',
        disabled: false,
      },
    })

    expect(wrapper.find('.quote-pricing-assignment').exists()).toBe(false)
    expect((wrapper.get('[aria-label="五金零件名称"]').element as HTMLInputElement).value).toBe('五金件 A')
    expect(wrapper.find('[aria-label="报价分项归属"]').exists()).toBe(false)
    expect(wrapper.get('.engineeringHardware thead').text()).not.toContain('分项归属')

    await wrapper.setProps({ activePricingComponentId: 'component-02' })
    expect((wrapper.get('[aria-label="五金零件名称"]').element as HTMLInputElement).value).toBe('五金件 B')

    const addButton = wrapper.findAll('button').find((button) => button.text().includes('新增五金'))
    expect(addButton).toBeDefined()
    await addButton!.trigger('click')
    expect(modelValue.materials.at(-1)?.pricing_component_id).toBe('component-02')
  })

  it('keeps the existing detached multiplier panel and all rows for ordinary quotes', () => {
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'engineering',
        modelValue: engineeringModel() as unknown as Record<string, unknown>,
        pricingMode: 'standard',
        pricingComponents,
        activePricingComponentId: 'component-02',
        disabled: false,
      },
    })

    expect(wrapper.get('.quote-pricing-assignment').text()).toContain('明细倍率')
    expect(wrapper.findAll('[aria-label="五金零件名称"]').map((input) => (input.element as HTMLInputElement).value)).toEqual(['五金件 A', '五金件 B'])
  })

  it('offers one shared product-level picker instead of row-level assignment controls', async () => {
    const wrapper = mount(InternalQuoteComponentScopePicker, {
      props: { productName: 'JP 系列 / 单款 A', components: pricingComponents, modelValue: 'component-01' },
    })

    expect(wrapper.text()).toContain('JustPlay 当前配件')
    expect(wrapper.text()).toContain('当前款：JP 系列 / 单款 A')
    expect(wrapper.findAll('[role="radio"]')).toHaveLength(2)

    await wrapper.get('[aria-label="选择配件 配件二"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['component-02']])
  })
})

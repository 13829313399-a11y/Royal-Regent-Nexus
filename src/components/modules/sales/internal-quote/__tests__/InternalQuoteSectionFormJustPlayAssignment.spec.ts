import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { nextTick, reactive } from 'vue'

import { normalizeInternalQuotePayload, type EngineeringPayload, type SalesPayload, type SalesPricingComponent } from '@/lib/internalQuoteSectionPayload'
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
  it.each(['inch', 'cm'])('derives read-only main-carton dimensions from the color box in %s and keeps inner cartons editable', async (unit) => {
    const modelValue = reactive(normalizeInternalQuotePayload('sales', {
      pricing_mode: 'component', color_box_size_unit: unit,
      color_box_size_in: { length: 10, width: 5, height: 4 },
      cartons: [
        { item: '主纸箱', size_unit: unit, length_in: 99, width_in: 99, height_in: 99, qty_per_carton: 6 },
        { item: '内箱', length_in: 4, width_in: 3, height_in: 2, qty_per_carton: 2 },
      ],
    })) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, { props: {
      code: 'sales', modelValue: modelValue as unknown as Record<string, unknown>, pricingMode: 'component',
    } })
    const cards = wrapper.findAll('.carton-card')
    expect(modelValue.cartons[0]).toMatchObject({ length_in: 10.75, width_in: 5.75, height_in: 5, qty_per_carton: 6 })
    expect((cards[0]!.get(`[aria-label="纸箱长度 ${unit}"]`).element as HTMLInputElement).readOnly).toBe(true)
    expect((cards[1]!.get('[aria-label="纸箱长度 inch"]').element as HTMLInputElement).readOnly).toBe(false)
    const factor = unit === 'cm' ? 2.54 : 1
    await wrapper.get(`[aria-label="彩盒长度 ${unit}"]`).setValue(String(17.25 * factor))
    await wrapper.get(`[aria-label="彩盒宽度 ${unit}"]`).setValue(String(11.25 * factor))
    await wrapper.get(`[aria-label="彩盒高度 ${unit}"]`).setValue(String(9 * factor))
    expect(modelValue.cartons[0]).toMatchObject({ length_in: 18, width_in: 12, height_in: 10, qty_per_carton: 6 })
    expect(wrapper.get('[aria-label="每托板装箱数"]').text()).toBe('30')
    expect(wrapper.get('[aria-label="纸托板单件成本 HKD"]').text()).toBe('0.106')
    expect(modelValue.cartons[1]).toMatchObject({ length_in: 4, width_in: 3, height_in: 2 })
    await wrapper.get(`[aria-label="彩盒宽度 ${unit}"]`).setValue('')
    expect(modelValue.cartons[0]!.width_in).toBe(0)
    expect(wrapper.get('[aria-label="每托板装箱数"]').text()).toBe('0')
  })

  it('keeps ordinary-customer carton dimensions manually editable', async () => {
    const modelValue = reactive(normalizeInternalQuotePayload('sales', {
      color_box_size_in: { length: 10, width: 5, height: 4 },
      cartons: [{ length_in: 18, width_in: 12, height_in: 10, qty_per_carton: 24 }],
    })) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, { props: {
      code: 'sales', modelValue: modelValue as unknown as Record<string, unknown>, pricingMode: 'standard',
    } })
    const lengthInput = wrapper.get('[aria-label="纸箱长度 inch"]')
    expect((lengthInput.element as HTMLInputElement).readOnly).toBe(false)
    await wrapper.get('[aria-label="彩盒长度 inch"]').setValue('20')
    expect(modelValue.cartons[0]!.length_in).toBe(18)
    await lengthInput.setValue('22')
    expect(modelValue.cartons[0]!.length_in).toBe(22)
  })

  it('edits special packaging independently, hides formulas, and respects zero and disabled inputs', async () => {
    const modelValue = reactive(normalizeInternalQuotePayload('sales', {
      pricing_mode: 'component',
      pricing_components: pricingComponents,
      packaging_materials: [],
      color_box_size_in: { length: 23, width: 10, height: 14.5 },
      cartons: [{
        item: '主纸箱',
        length_in: 23.75,
        width_in: 10.75,
        height_in: 15.5,
        qty_per_carton: 2,
        flat_cards: [],
      }],
    }))
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: modelValue as unknown as Record<string, unknown>,
        pricingMode: 'component',
        pricingComponents,
        disabled: false,
      },
    })

    const special = wrapper.get('.justplay-packaging')
    expect(wrapper.get('.packagingMaterials').text()).not.toContain('胶纸/胶水/胶针')
    expect(wrapper.get('.packagingMaterials').text()).not.toContain('纸托板成本')
    expect(special.text()).not.toContain('3.9')
    expect(special.text()).not.toContain('19÷')
    expect((special.get('[aria-label="胶纸附加金额 HKD/件"]').element as HTMLInputElement).value).toBe('0.00')
    expect((special.get('[aria-label="纸托板附加金额 HKD/件"]').element as HTMLInputElement).value).toBe('0.00')
    expect(special.get('output[aria-label="每托板装箱数"]').text()).toBe('12')
    expect(special.get('[aria-label="胶纸单件成本 HKD"]').text()).toBe('0.088')
    expect(special.get('[aria-label="纸托板单件成本 HKD"]').text()).toBe('0.792')
    await special.get('[aria-label="胶纸附加金额 HKD/件"]').setValue('0.12')
    await special.get('[aria-label="纸托板附加金额 HKD/件"]').setValue('0.07')
    expect(modelValue.justplay_packaging).toEqual({ adhesive_extra_hkd: .12, paper_pallet_extra_hkd: .07 })
    expect(special.get('[aria-label="胶纸单件成本 HKD"]').text()).toBe('0.208')
    expect(special.get('[aria-label="纸托板单件成本 HKD"]').text()).toBe('0.862')
    for (const label of ['胶纸附加金额 HKD/件', '纸托板附加金额 HKD/件']) {
      const input = special.get(`[aria-label="${label}"]`)
      expect(input.attributes('step')).toBe('0.01')
      await input.trigger('focus')
      await input.setValue('0.049')
      await input.trigger('blur')
      expect((input.element as HTMLInputElement).value).toBe('0.05')
    }
    expect(modelValue.justplay_packaging).toEqual({ adhesive_extra_hkd: .05, paper_pallet_extra_hkd: .05 })
    await special.get('[aria-label="胶纸附加金额 HKD/件"]').setValue('0')
    await special.get('[aria-label="纸托板附加金额 HKD/件"]').setValue('0')
    expect(special.get('[aria-label="胶纸单件成本 HKD"]').text()).toBe('0.088')
    expect(special.get('[aria-label="纸托板单件成本 HKD"]').text()).toBe('0.792')
    expect(special.find('[role="alert"]').exists()).toBe(false)
    const mainCarton = (modelValue as unknown as SalesPayload).cartons[0]!
    const colorBox = (modelValue as unknown as SalesPayload).color_box_size_in
    colorBox.height = 0
    await nextTick()
    expect(special.get('[aria-label="每托板装箱数"]').text()).toBe('0')
    expect(special.get('[role="alert"]').text()).toContain('彩盒长、宽、高')
    Object.assign(colorBox, { length: 17.25, width: 11.25, height: 9 })
    mainCarton.qty_per_carton = 24
    await nextTick()
    expect(special.get('[aria-label="每托板装箱数"]').text()).toBe('30')
    expect(special.get('[aria-label="纸托板单件成本 HKD"]').text()).toBe('0.026')
    expect(special.find('[role="alert"]').exists()).toBe(false)
    await wrapper.setProps({ disabled: true })
    expect(special.findAll('input').every((input) => (input.element as HTMLInputElement).disabled)).toBe(true)
    await wrapper.setProps({ pricingMode: 'standard' })
    expect(wrapper.find('.justplay-packaging').exists()).toBe(false)
  })

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

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
  it('edits the pallet space in mm and recomputes capacity and cost without changing carton units', async () => {
    const payload = reactive(normalizeInternalQuotePayload('sales', {
      pricing_mode: 'component', color_box_size_in: { length: 17.25, width: 11.25, height: 9 },
      cartons: [{ item: '主纸箱', size_unit: 'cm', qty_per_carton: 24 }],
    }))
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'sales', modelValue: payload, pricingMode: 'component' } })
    const fields = ['托板长度 mm', '托板宽度 mm', '托板高度 mm']
    expect(wrapper.get('[aria-label="每托板装箱数"]').text()).toBe('30')
    expect(fields.map(label => wrapper.get<HTMLInputElement>(`[aria-label="${label}"]`).element.value)).toEqual(['1000', '1150', '1300'])
    for (const [i, value] of [1400, 1000, 800].entries()) await wrapper.get(`[aria-label="${fields[i]}"]`).setValue(String(value))
    expect(wrapper.get('[aria-label="每托板装箱数"]').text()).toBe('27')
    expect(wrapper.get('[aria-label="纸托板单件成本 HKD"]').text()).toBe('0.029')
    expect((payload as unknown as SalesPayload).cartons[0]).toMatchObject({ length_in: 18, width_in: 12, height_in: 10, size_unit: 'cm' })
    expect((payload as unknown as SalesPayload).justplay_packaging).toMatchObject({ pallet_length_mm: 1400, pallet_width_mm: 1000, pallet_height_mm: 800 })
    await wrapper.get('[aria-label="托板宽度 mm"]').setValue('')
    expect(wrapper.get('[aria-label="每托板装箱数"]').text()).toBe('0')
    expect(wrapper.get('.justplay-packaging [role="alert"]').text()).toContain('托板长、宽、高')
    await wrapper.get('[aria-label="托板宽度 mm"]').setValue('10')
    expect(wrapper.get('.justplay-packaging [role="alert"]').text()).toContain('所填写的托板空间')
    await wrapper.setProps({ disabled: true })
    for (const label of fields) expect(wrapper.get(`[aria-label="${label}"]`).attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('shows only molds assigned to the selected component and removes the correct source row', async () => {
    const modelValue = reactive(normalizeInternalQuotePayload('engineering', { molds: [
      { item: 'A模具', pricing_component_id: 'component-01', cost_rmb: 1000 },
      { item: 'B模具', pricing_component_id: 'component-02', cost_rmb: 2000 },
    ] }))
    const wrapper = mount(InternalQuoteSectionForm, { props: {
      code: 'engineering', modelValue, pricingMode: 'component', pricingComponents, activePricingComponentId: 'component-02',
    } })
    expect(wrapper.findAll('[aria-label="模具名称"]')).toHaveLength(1)
    expect((wrapper.get('[aria-label="模具名称"]').element as HTMLTextAreaElement).value).toBe('B模具')
    await wrapper.get('.engineeringMolds tbody button.icon').trigger('click')
    expect((modelValue as unknown as EngineeringPayload).molds.map(m => m.item)).toEqual(['A模具'])
    wrapper.unmount()
  })
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
    expect(wrapper.find('.pdq-dimensions').exists()).toBe(false)
    expect(wrapper.find('[aria-label="长度方向个数"]').exists()).toBe(false)
  })

  it.each(['inch', 'cm'])('uses counts or PDQ in %s, preserves input when switching, and never changes packing quantity', async (unit) => {
    const modelValue = reactive(normalizeInternalQuotePayload('sales', {
      pricing_mode: 'component', pricing_components: pricingComponents,
      color_box_size_in: { length: 8.625, width: 3.75, height: 2.25 },
      product_size_in: { length: 5, width: 4, height: 3 },
      cartons: [{ item: '主纸箱', qty_per_carton: 24 }],
    })) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, { props: {
      code: 'sales', modelValue: modelValue as unknown as Record<string, unknown>, pricingMode: 'component',
    } })
    expect((wrapper.get('[aria-label="主纸箱尺寸来源"]').element as HTMLSelectElement).value).toBe('color_box')
    for (const [label, value] of [['长度', 2], ['宽度', 3], ['高度', 4]]) {
      await wrapper.get(`[aria-label="${label}方向个数"]`).setValue(String(value))
    }
    expect(modelValue.cartons[0]).toMatchObject({ length_in: 18, width_in: 12, height_in: 10, qty_per_carton: 24 })
    await wrapper.get('[aria-label="主纸箱尺寸来源"]').setValue('product')
    expect(modelValue.cartons[0]).toMatchObject({ length_in: 10.75, width_in: 12.75, height_in: 13 })
    await wrapper.get('[aria-label="PDQ 尺寸单位"]').setValue(unit)
    const factor = unit === 'cm' ? 2.54 : 1
    await wrapper.get(`[aria-label="PDQ 长度 ${unit}"]`).setValue(String(17.25 * factor))
    expect(modelValue.cartons[0]!.length_in).toBe(0)
    expect(wrapper.text()).toContain('请补齐PDQ长、宽、高')
    await wrapper.get(`[aria-label="PDQ 宽度 ${unit}"]`).setValue(String(11.25 * factor))
    await wrapper.get(`[aria-label="PDQ 高度 ${unit}"]`).setValue(String(9 * factor))
    expect(modelValue.cartons[0]).toMatchObject({ length_in: 18, width_in: 12, height_in: 10, qty_per_carton: 24 })
    expect(wrapper.get('[aria-label="每托板装箱数"]').text()).toBe('30')
    expect((wrapper.get('[aria-label="长度方向个数"]').element as HTMLInputElement).disabled).toBe(true)
    const cloned = normalizeInternalQuotePayload('sales', JSON.parse(JSON.stringify(modelValue))) as unknown as SalesPayload
    expect(cloned.pdq_size_in).toEqual({ length: 17.25, width: 11.25, height: 9 })
    expect(cloned.justplay_carton).toEqual({ dimension_source: 'product', length_count: 2, width_count: 3, height_count: 4 })
    for (const label of ['长度', '宽度', '高度']) await wrapper.get(`[aria-label="PDQ ${label} ${unit}"]`).setValue('0')
    expect(modelValue.cartons[0]).toMatchObject({ length_in: 10.75, width_in: 12.75, height_in: 13, qty_per_carton: 24 })
    expect((wrapper.get('[aria-label="长度方向个数"]').element as HTMLInputElement).disabled).toBe(false)
    await wrapper.get('[aria-label="宽度方向个数"]').setValue('1.5')
    expect(wrapper.text()).toContain('方向个数必须为正整数')
    expect(modelValue.cartons[0]!.length_in).toBe(0)
    await wrapper.setProps({ disabled: true })
    expect(wrapper.findAll('.pdq-dimensions input').every(input => (input.element as HTMLInputElement).disabled)).toBe(true)
    wrapper.unmount()
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
    expect((special.get('[aria-label="胶纸附加金额 HKD/件"]').element as HTMLInputElement).value).toBe('0.0')
    expect((special.get('[aria-label="纸托板附加金额 HKD/件"]').element as HTMLInputElement).value).toBe('0.0')
    expect(special.get('output[aria-label="每托板装箱数"]').text()).toBe('12')
    expect(special.get('[aria-label="胶纸单件成本 HKD"]').text()).toBe('0.088')
    expect(special.get('[aria-label="纸托板单件成本 HKD"]').text()).toBe('0.792')
    await special.get('[aria-label="胶纸附加金额 HKD/件"]').setValue('0.12')
    await special.get('[aria-label="纸托板附加金额 HKD/件"]').setValue('0.07')
    await special.get('[aria-label="胶纸附加金额 HKD/件"]').trigger('blur')
    await special.get('[aria-label="纸托板附加金额 HKD/件"]').trigger('blur')
    expect(modelValue.justplay_packaging).toMatchObject({ adhesive_extra_hkd: .1, paper_pallet_extra_hkd: .1 })
    expect(special.get('[aria-label="胶纸单件成本 HKD"]').text()).toBe('0.188')
    expect(special.get('[aria-label="纸托板单件成本 HKD"]').text()).toBe('0.892')
    for (const label of ['胶纸附加金额 HKD/件', '纸托板附加金额 HKD/件']) {
      const input = special.get(`[aria-label="${label}"]`)
      expect(input.attributes('step')).toBe('0.1')
      await input.trigger('focus')
      await input.setValue('0.049')
      await input.trigger('blur')
      expect((input.element as HTMLInputElement).value).toBe('0.0')
    }
    expect(modelValue.justplay_packaging).toMatchObject({ adhesive_extra_hkd: 0, paper_pallet_extra_hkd: 0 })
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

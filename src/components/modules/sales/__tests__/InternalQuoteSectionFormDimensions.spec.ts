import { reactive } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteSectionForm from '@/components/modules/sales/internal-quote/InternalQuoteSectionForm.vue'
import { calculateCartonCuft, normalizeInternalQuotePayload, type SalesPayload, type SewingPayload } from '@/lib/internalQuoteSectionPayload'

describe('InternalQuoteSectionForm dimension units', () => {
  it('keeps ordinary-customer carton fields visible while clearing and retyping the paper factor', async () => {
    const payload = reactive(normalizeInternalQuotePayload('sales', {
      cartons: [{ item: '主纸箱', length_in: 10, width_in: 5, height_in: 4, qty_per_carton: 10, flat_cards: [] }],
    }))
    const errors: unknown[] = []
    const wrapper = mount(InternalQuoteSectionForm, {
      props: { code: 'sales', customer: '普通客户', pricingMode: 'standard', modelValue: payload, disabled: false },
      global: { config: { errorHandler: (error) => errors.push(error) } },
    })
    expect(wrapper.find('.justplay-packaging').exists()).toBe(false)
    const factor = wrapper.get('input[aria-label="主纸箱纸价系数"]')
    await factor.setValue('')
    expect(errors).toEqual([])
    expect(wrapper.text()).toContain('纸箱计算与包装尺寸部分')
    expect(wrapper.find('.sales-packaging-materials').exists()).toBe(true)
    expect(payload.paper_price_factor).toBe('')
    expect((payload.cartons as SalesPayload['cartons'])[0].length_in).toBe(10)
    await wrapper.get('input[aria-label="主纸箱纸价系数"]').setValue('3.5')
    expect(payload.paper_price_factor).toBe(3.5)
    expect(wrapper.get('.carton-card .calculation-strip').text()).toContain('纸价系数 3.5000')
    expect(errors).toEqual([])
    wrapper.unmount()
  })

  it('keeps the main carton fixed and unlocks the inner-carton factor only after adding an inner carton', async () => {
    const payload = normalizeInternalQuotePayload('sales', {}) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
      },
    })

    expect(payload.cartons).toHaveLength(1)
    expect(payload.cartons[0]).toMatchObject({ item: '主纸箱', size_unit: 'inch', qty_per_carton: 1 })
    expect(wrapper.text()).toContain('主纸箱')
    expect(wrapper.get('input[aria-label="主纸箱纸价系数"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('input[aria-label="内纸箱纸价系数"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="删除纸箱 1"]').attributes('disabled')).toBeDefined()

    const addButton = wrapper.get('[data-testid="add-sales-carton"]')
    await addButton.trigger('click')

    expect(payload.cartons).toHaveLength(2)
    expect(payload.cartons[1].item).toBe('内纸箱 1')
    expect(payload.inner_paper_price_factor).toBe(2.75)
    expect(wrapper.get('input[aria-label="内纸箱纸价系数"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('button[aria-label="删除纸箱 1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="删除纸箱 2"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('input[aria-label="内纸箱纸价系数"]').setValue('1.5')
    expect(payload.inner_paper_price_factor).toBe(1.5)

    await wrapper.get('button[aria-label="删除纸箱 2"]').trigger('click')
    expect(payload.cartons).toHaveLength(1)
    expect(payload.cartons[0].item).toBe('主纸箱')
    expect(payload).not.toHaveProperty('inner_paper_price_factor')
    expect(wrapper.get('input[aria-label="内纸箱纸价系数"]').attributes('disabled')).toBeDefined()
  })

  it('uses separate main and inner carton factors in the live price preview', () => {
    const payload = normalizeInternalQuotePayload('sales', {
      paper_price_factor: 2.75,
      inner_paper_price_factor: 1.5,
      cartons: [
        { item: '主纸箱', length_in: 10, width_in: 5, height_in: 4, qty_per_carton: 10, flat_cards: [] },
        { item: '内纸箱 1', length_in: 8, width_in: 4, height_in: 3, qty_per_carton: 2, flat_cards: [] },
      ],
    }) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
      },
    })

    const strips = wrapper.findAll('.carton-card .calculation-strip')
    expect(strips).toHaveLength(2)
    expect(strips[0].text()).toContain('纸价系数 2.7500')
    expect(strips[0].text()).toContain('箱价 HKD 0.935')
    expect(strips[1].text()).toContain('纸价系数 1.5000')
    expect(strips[1].text()).toContain('箱价 HKD 0.336')
  })

  it('edits imported sewing HKD prices without dividing them by the RMB rate', async () => {
    const payload = normalizeInternalQuotePayload('sewing', { groups: [{ name: '衣服', materials: [
      { item: '布标', usage: 1, unit_price_hkd: .235294117647059, unit_price_source_currency: 'HKD', markup: 1.1 },
    ] }] }) as unknown as SewingPayload
    const wrapper = mount(InternalQuoteSectionForm, { props: {
      code: 'sewing', modelValue: payload as unknown as Record<string, unknown>, disabled: false, rmbHkdRate: .85,
    } })
    expect(wrapper.get('input[aria-label="车缝单价 HKD"]').element).toHaveProperty('value', '0.235294117647059')
    expect(wrapper.find('input[aria-label="车缝单价 RMB"]').exists()).toBe(false)
    expect(wrapper.get('.sewing-summary-card').text()).toContain('0.259')
    await wrapper.get('input[aria-label="车缝单价 HKD"]').setValue('2')
    expect(payload.groups[0].materials[0].unit_price_hkd).toBe(2)
    expect(wrapper.get('.sewing-summary-card').text()).toContain('2.200')
    await wrapper.get('input[aria-label="车缝汇率 RMB 转 HKD"]').setValue('.8')
    expect(wrapper.get('.sewing-summary-card').text()).toContain('2.200')
    await wrapper.setProps({ disabled: true })
    expect(wrapper.get('input[aria-label="车缝单价 HKD"]').attributes('disabled')).toBeDefined()
  })

  it('offers screen printing as a sewing craft and preserves the selection', async () => {
    const payload = normalizeInternalQuotePayload('sewing', {
      groups: [{
        name: '衣服',
        category: 'clothes',
        materials: [{ item: '网布', part: '正面', craft: '', pieces: 1, usage: 1, unit_price_rmb: 2, markup: 1 }],
      }],
    }) as unknown as SewingPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sewing',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
      },
    })

    const craftSelect = wrapper.get('select[aria-label="车缝工艺"]')
    expect(craftSelect.findAll('option').map((option) => option.text())).toEqual(['常规', '电绣', '丝印'])
    await craftSelect.setValue('丝印')
    expect(payload.groups[0].materials[0].craft).toBe('丝印')
    expect((normalizeInternalQuotePayload('sewing', payload as unknown as Record<string, unknown>) as unknown as SewingPayload).groups[0].materials[0].craft).toBe('丝印')
  })

  it('edits flat-card quantity and recalculates the price with exact dimensions', async () => {
    const payload = normalizeInternalQuotePayload('sales', {
      paper_price_factor: 2.75,
      cartons: [{
        item: '主纸箱',
        length_in: 10,
        width_in: 5,
        height_in: 4,
        qty_per_carton: 10,
        flat_cards: [{ name: '平卡1', length_in: 10, width_in: 5, quantity: 1 }],
      }],
    }) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
      },
    })

    const quantityInput = wrapper.get('input[aria-label="平卡 1 用量"]')
    expect(quantityInput.element).toHaveProperty('value', '1')
    expect(wrapper.text()).toContain('0.138')

    await quantityInput.setValue('2')

    expect(payload.cartons[0].flat_cards[0].quantity).toBe(2)
    expect(wrapper.text()).toContain('0.275')
  })

  it('adds business testing-fee MOQ tiers and calculates each USD unit price', async () => {
    const payload = normalizeInternalQuotePayload('sales', {}) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
      },
    })

    expect(wrapper.get('[aria-label="业务部测试费单价 USD 1"]').text()).toBe('0.0000')
    await wrapper.get('button[aria-label="新增业务部测试费 MOQ"]').trigger('click')
    await wrapper.get('input[aria-label="业务部测试费用 USD"]').setValue('1250')
    await wrapper.get('input[aria-label="业务部测试费 MOQ 1"]').setValue('5000')
    await wrapper.get('input[aria-label="业务部测试费 MOQ 2"]').setValue('10000')

    expect(payload.testing_fee_total_usd).toBe(1250)
    expect(payload.testing_fee_moqs).toEqual([5000, 10000])
    expect(wrapper.get('[aria-label="业务部测试费单价 USD 1"]').text()).toBe('0.2500')
    expect(wrapper.get('[aria-label="业务部测试费单价 USD 2"]').text()).toBe('0.1250')

    await wrapper.get('input[aria-label="启用测试费计算"]').setValue(false)
    expect(payload.testing_fee_enabled).toBe(false)
    expect(wrapper.text()).toContain('本单不计算测试费')
    expect(wrapper.find('input[aria-label="业务部测试费用 USD"]').exists()).toBe(false)
    expect(payload.testing_fee_total_usd).toBe(1250)
    expect(payload.testing_fee_moqs).toEqual([5000, 10000])

    await wrapper.get('input[aria-label="启用测试费计算"]').setValue(true)
    expect(wrapper.get('[aria-label="业务部测试费单价 USD 2"]').text()).toBe('0.1250')

    await wrapper.get('button[aria-label="删除业务部测试费 MOQ 2"]').trigger('click')
    expect(payload.testing_fee_moqs).toEqual([5000])
  })

  it('edits color-box and carton dimensions in cm while preserving canonical inch calculations', async () => {
    const payload = normalizeInternalQuotePayload('sales', {
      color_box_size_in: { length: 10, width: 5, height: 4 },
      cartons: [{ item: '主纸箱', length_in: 20, width_in: 10, height_in: 8, qty_per_carton: 2, flat_cards: [] }],
    }) as unknown as SalesPayload
    const originalCuft = calculateCartonCuft(payload.cartons[0])
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
      },
    })

    expect(wrapper.get('input[aria-label="彩盒长度 inch"]').element).toHaveProperty('value', '10')
    await wrapper.get('select[aria-label="彩盒尺寸单位"]').setValue('cm')
    expect(payload.color_box_size_unit).toBe('cm')
    expect(wrapper.get('input[aria-label="彩盒长度 cm"]').element).toHaveProperty('value', '25.4')
    await wrapper.get('input[aria-label="彩盒长度 cm"]').setValue('30.48')
    expect(payload.color_box_size_in.length).toBe(12)

    await wrapper.get('select[aria-label="纸箱 1 尺寸单位"]').setValue('cm')
    expect(payload.cartons[0].size_unit).toBe('cm')
    expect(wrapper.get('input[aria-label="纸箱长度 cm"]').element).toHaveProperty('value', '50.8')
    expect(calculateCartonCuft(payload.cartons[0])).toBeCloseTo(originalCuft)
    await wrapper.get('input[aria-label="纸箱长度 cm"]').setValue('25.4')
    expect(payload.cartons[0].length_in).toBe(10)
    expect(calculateCartonCuft(payload.cartons[0])).toBeCloseTo(originalCuft / 2)
  })

  it('shows freight and lifting HKD from the frozen pricing baseline and lets the quote select output routes', async () => {
    const payload = normalizeInternalQuotePayload('sales', {
      cartons: [{ item: '主纸箱', length_in: 14, width_in: 9.25, height_in: 23.875, qty_per_carton: 2, flat_cards: [] }],
    }) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
        referenceSnapshot: {
          freight: {
            routes: [{ route_key: 'sz40', route_name: '深圳 40 柜', capacity_key: 'cap_40', freight_hkd: '6500', lifting_hkd: '1100' }],
          },
        },
      },
    })

    expect(wrapper.get('output[aria-label="深圳 40 柜运费"]').text()).toBe('6500')
    expect(wrapper.get('output[aria-label="深圳 40 柜吊柜费"]').text()).toBe('1100')
    expect(wrapper.find('input[aria-label="深圳 40 柜运费"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="深圳 40 柜吊柜费"]').exists()).toBe(false)
    expect(wrapper.find('output[aria-label="HK 20 尺柜运费"]').exists()).toBe(false)
    expect(payload.freight_calc).not.toHaveProperty('hk40')
    const outputToggle = wrapper.get<HTMLInputElement>('input[aria-label="输出运输规格 深圳 40 柜"]')
    expect(outputToggle.element.checked).toBe(true)
    await outputToggle.setValue(false)
    expect(payload.freight_calc.selected_route_keys).toEqual([])
    await outputToggle.setValue(true)
    expect(payload.freight_calc.selected_route_keys).toEqual(['sz40'])
  })

  it('shows an editable CUFT field for a custom capacity type and uses it in freight calculation', async () => {
    const payload = normalizeInternalQuotePayload('sales', {
      freight_calc: { '8 吨车容量': 1200 },
      cartons: [{ item: '主纸箱', length_in: 12, width_in: 12, height_in: 12, qty_per_carton: 10, flat_cards: [] }],
    }) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
        referenceSnapshot: {
          freight: {
            routes: [{ route_key: 'hk8t', route_name: 'HK 8 吨车', capacity_key: '8 吨车容量', freight_hkd: '6000', lifting_hkd: '800' }],
          },
        },
      },
    })

    const capacityInput = wrapper.get('input[aria-label="8 吨车容量"]')
    expect(capacityInput.element).toHaveProperty('value', '1200')
    expect(wrapper.text()).toContain('HK 8 吨车')
    expect(wrapper.get('.freightTable tbody tr').findAll('td')[5].text()).toBe('1200')

    await capacityInput.setValue('1000')
    await capacityInput.trigger('blur')
    expect(payload.freight_calc['8 吨车容量']).toBe(1000)
    expect(wrapper.get('.freightTable tbody tr').findAll('td')[5].text()).toBe('1000')
  })

  it('switches independently between both fees, freight only, and neither fee', async () => {
    const payload = normalizeInternalQuotePayload('sales', {
      cartons: [{ item: '主纸箱', length_in: 14, width_in: 9.25, height_in: 23.875, qty_per_carton: 2, flat_cards: [] }],
    }) as unknown as SalesPayload
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'sales',
        modelValue: payload as unknown as Record<string, unknown>,
        disabled: false,
        referenceSnapshot: {
          freight: {
            routes: [{ route_key: 'sz40', route_name: '深圳 40 柜', capacity_key: 'cap_40', freight_hkd: '6500', lifting_hkd: '1100' }],
          },
        },
      },
    })

    await wrapper.get('input[aria-label="启用吊柜费计算"]').setValue(false)
    expect(payload.freight_calc).toMatchObject({ enabled: true, freight_enabled: true, lifting_enabled: false })
    expect(wrapper.get('output[aria-label="深圳 40 柜运费"]').text()).toBe('6500')
    expect(wrapper.get('output[aria-label="深圳 40 柜吊柜费"]').text()).toBe('0')

    await wrapper.get('input[aria-label="启用运费计算"]').setValue(false)
    expect(payload.freight_calc).toMatchObject({ enabled: false, freight_enabled: false, lifting_enabled: false })
    expect(wrapper.text()).toContain('本单不计算运费和吊柜费')
    expect(wrapper.find('output[aria-label="深圳 40 柜运费"]').exists()).toBe(false)

    await wrapper.get('input[aria-label="启用运费计算"]').setValue(true)
    await wrapper.get('input[aria-label="启用吊柜费计算"]').setValue(true)
    expect(payload.freight_calc).toMatchObject({ enabled: true, freight_enabled: true, lifting_enabled: true })
    expect(wrapper.get('output[aria-label="深圳 40 柜吊柜费"]').text()).toBe('1100')
  })
})

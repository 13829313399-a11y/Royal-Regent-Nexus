import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteSectionForm from '@/components/modules/sales/internal-quote/InternalQuoteSectionForm.vue'
import { calculateCartonCuft, normalizeInternalQuotePayload, type SalesPayload } from '@/lib/internalQuoteSectionPayload'

describe('InternalQuoteSectionForm dimension units', () => {
  it('always provides one base carton while keeping the add-carton action', async () => {
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
    expect(wrapper.text()).toContain('基础纸箱')
    expect(wrapper.get('button[aria-label="删除纸箱 1"]').attributes('disabled')).toBeDefined()

    const addButton = wrapper.findAll('button').find((button) => button.text().includes('新增纸箱'))!
    await addButton.trigger('click')

    expect(payload.cartons).toHaveLength(2)
    expect(payload.cartons[1].item).toBe('纸箱 2')
    expect(wrapper.get('button[aria-label="删除纸箱 1"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('button[aria-label="删除纸箱 2"]').trigger('click')
    expect(payload.cartons).toHaveLength(1)
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

  it('shows freight and lifting HKD from the frozen pricing baseline without quote-level editors', () => {
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
    expect(wrapper.get('.freightTable tbody tr').findAll('td')[4].text()).toBe('1200')

    await capacityInput.setValue('1000')
    await capacityInput.trigger('blur')
    expect(payload.freight_calc['8 吨车容量']).toBe(1000)
    expect(wrapper.get('.freightTable tbody tr').findAll('td')[4].text()).toBe('1000')
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

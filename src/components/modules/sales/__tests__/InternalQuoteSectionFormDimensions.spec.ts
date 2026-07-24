import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteSectionForm from '@/components/modules/sales/internal-quote/InternalQuoteSectionForm.vue'
import { calculateCartonCuft, normalizeInternalQuotePayload, type SalesPayload } from '@/lib/internalQuoteSectionPayload'

describe('InternalQuoteSectionForm dimension units', () => {
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

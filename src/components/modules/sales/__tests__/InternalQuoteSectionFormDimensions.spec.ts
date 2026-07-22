import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteSectionForm from '@/components/modules/sales/internal-quote/InternalQuoteSectionForm.vue'
import { calculateCartonCuft, normalizeInternalQuotePayload, type SalesPayload } from '@/lib/internalQuoteSectionPayload'

describe('InternalQuoteSectionForm dimension units', () => {
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
})

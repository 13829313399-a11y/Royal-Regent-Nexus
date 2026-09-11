import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { describe, expect, it } from 'vitest'
import { calculatePaintingRowSplit, normalizeInternalQuotePayload, type PaintingPayload } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

describe('painting paint/labor mapping', () => {
  it.each(['ordinary', 'component'] as const)('preserves fields and auto difference during %s edits', async mode => {
    const modelValue = reactive(normalizeInternalQuotePayload('painting', { rows: [{
      name: '外壳', position: '头', pricing_component_id: 'shell', cost_allocation: 'split',
      paint_cost_hkd: '2', labor_cost_hkd: null, operations: { uv: { quantity: 2, unit_price_hkd: 5 } },
    }] }))
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'painting', modelValue,
      ...(mode === 'component' ? { pricingMode: 'component' as const,
        pricingComponents: [{ id: 'shell', name: '壳', markup_x: 1.4 }], activePricingComponentId: 'shell' } : {}),
    } })
    const row = (modelValue as PaintingPayload).rows[0]!
    const paint = wrapper.get('[aria-label="喷油第 1 行油漆 HKD"]')
    const labor = wrapper.get('[aria-label="喷油第 1 行人工 HKD"]')
    expect((paint.element as HTMLInputElement).value).toBe('2')
    expect(labor.attributes('placeholder')).toBe('8.000')
    await paint.setValue('3')
    expect(labor.attributes('placeholder')).toBe('7.000')
    expect(calculatePaintingRowSplit(row)).toEqual({ paint: 3, labor: 7, valid: true })
    expect(wrapper.get('tbody .amount').text()).toBe('10.000')
    await labor.setValue('8')
    expect(calculatePaintingRowSplit(row).valid).toBe(false)
    expect(wrapper.text()).toContain('待填写或核对拆分金额')
    await paint.setValue('')
    expect(calculatePaintingRowSplit(row)).toEqual({ paint: 2, labor: 8, valid: true })
    await labor.setValue('')
    const roundtrip = normalizeInternalQuotePayload('painting', modelValue) as PaintingPayload
    expect(roundtrip.rows[0]).toMatchObject({ cost_allocation: 'split', paint_cost_hkd: null, labor_cost_hkd: null, pricing_component_id: 'shell' })
    expect(calculatePaintingRowSplit(roundtrip.rows[0]!).valid).toBe(false)
    await wrapper.setProps({ disabled: true })
    expect(paint.attributes('disabled')).toBeDefined()
    expect(labor.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('retains historical direct and old allocation unless manually changed', () => {
    const payload = normalizeInternalQuotePayload('painting', { rows: [
      { operations: { uv: { quantity: 2, unit_price_hkd: 5 } } },
      { cost_allocation: 'direct', paint_hkd: 100, spray_labor_hkd: 100,
        operations: { paint: { quantity: 1, unit_price_hkd: 1.13 } } },
    ] }) as PaintingPayload
    expect(calculatePaintingRowSplit(payload.rows[0]!)).toEqual({ paint: 3, labor: 7, valid: true })
    expect(calculatePaintingRowSplit(payload.rows[1]!)).toEqual({ paint: 1.13, labor: 0, valid: true })
  })
})

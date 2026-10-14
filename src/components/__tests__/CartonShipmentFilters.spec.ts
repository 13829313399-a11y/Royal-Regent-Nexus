import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Component from '../CartonShipmentFilters.vue'
import { emptyShipmentFilters } from '@/features/carton-procurement/queryFilters'

describe('shipment keyword placement', () => {
  it('keeps local keyword search for existing warehouse callers', async () => {
    const w = mount(Component, { props: { rows: [], modelValue: emptyShipmentFilters() } })
    await w.get('[aria-label="送货单关键字"]').setValue('合同-1')
    expect(w.props('modelValue').search).toBe('合同-1')
    w.unmount()
  })

  it('hides the local field for a header-controlled model and clears its keyword while preserving sorting', async () => {
    const w = mount(Component, { props: { rows: [], hideSearch: true, modelValue: { ...emptyShipmentFilters(), search: '合同-1', customer: '客户', sort: 'ASC', dateField: 'ACCEPTANCE' } } })
    expect(w.find('[aria-label="送货单关键字"]').exists()).toBe(false)
    await w.findAll('button').find(button => button.text() === '清除筛选')!.trigger('click')
    expect(w.emitted('update:modelValue')?.[0]).toEqual([{ ...emptyShipmentFilters(), sort: 'ASC', dateField: 'ACCEPTANCE' }])
    expect(w.emitted('clear')).toHaveLength(1)
    w.unmount()
  })
})

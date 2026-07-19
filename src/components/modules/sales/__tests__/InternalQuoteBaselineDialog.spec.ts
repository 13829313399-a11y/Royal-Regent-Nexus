import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteBaselineDialog from '@/components/modules/sales/internal-quote/InternalQuoteBaselineDialog.vue'


describe('InternalQuoteBaselineDialog', () => {
  it('normalizes edited number inputs before emitting the save payload', async () => {
    const wrapper = mount(InternalQuoteBaselineDialog, {
      props: {
        open: true,
        busy: false,
        canEdit: true,
        baseline: {
          factory_id: 'huaxing',
          workshop_code: 'huaxing-workshop',
          workshop_name: '华兴',
          revision: 1,
          source_type: 'custom',
          material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '8.50' }],
          machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '940' }],
          updated_by: 'system',
          updated_by_name: '系统导入',
          updated_at: '2026-07-18 11:24:14',
        },
      },
      global: {
        stubs: { Teleport: true },
      },
    })

    await wrapper.get('[data-testid="material-price-0"]').setValue('9')
    await wrapper.get('[data-testid="machine-price-0"]').setValue('950')
    await wrapper.get('[data-testid="save-pricing-baseline"]').trigger('click')

    expect(wrapper.emitted('save')).toEqual([[
      {
        revision: 1,
        workshop_name: '华兴',
        material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '9' }],
        machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '950' }],
      },
    ]])
  })
})

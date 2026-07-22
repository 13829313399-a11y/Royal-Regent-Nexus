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

  it('saves K and PC material rows while discarding an accidentally added blank row', async () => {
    const wrapper = mount(InternalQuoteBaselineDialog, {
      props: {
        open: true,
        busy: false,
        canEdit: true,
        baseline: {
          factory_id: 'huaxing',
          workshop_code: 'huaxing-workshop',
          workshop_name: '华兴',
          revision: 5,
          source_type: 'custom',
          material_prices: [{ material: 'TPR', grade: '透明橡胶料', price_hkd_lb: '17.00' }],
          machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '940' }],
          updated_by: 'supervisor',
          updated_by_name: '业务主管',
          updated_at: '2026-07-22 18:48:21',
        },
      },
      global: {
        stubs: { Teleport: true },
      },
    })

    const addMaterialButton = wrapper.get('.quote-baseline-card-title button')
    await addMaterialButton.trigger('click')
    await addMaterialButton.trigger('click')
    await addMaterialButton.trigger('click')

    const materials = wrapper.findAll('input[aria-label="材质"]')
    const grades = wrapper.findAll('input[aria-label="料型"]')
    await materials[1].setValue('K料')
    await grades[1].setValue('KR-03NW')
    await wrapper.get('[data-testid="material-price-1"]').setValue('15.00')
    await materials[2].setValue('PC料')
    await grades[2].setValue('2605')
    await wrapper.get('[data-testid="material-price-2"]').setValue('12.50')
    await wrapper.get('[data-testid="save-pricing-baseline"]').trigger('click')

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.emitted('save')).toEqual([[
      {
        revision: 5,
        workshop_name: '华兴',
        material_prices: [
          { material: 'TPR', grade: '透明橡胶料', price_hkd_lb: '17.00' },
          { material: 'K料', grade: 'KR-03NW', price_hkd_lb: '15' },
          { material: 'PC料', grade: '2605', price_hkd_lb: '12.5' },
        ],
        machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '940' }],
      },
    ]])
    expect(wrapper.findAll('input[aria-label="材质"]')).toHaveLength(3)
  })

  it('still rejects a partially completed material row and identifies its position', async () => {
    const wrapper = mount(InternalQuoteBaselineDialog, {
      props: {
        open: true,
        busy: false,
        canEdit: true,
        baseline: {
          factory_id: 'huaxing',
          workshop_code: 'huaxing-workshop',
          workshop_name: '华兴',
          revision: 5,
          source_type: 'custom',
          material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '8.50' }],
          machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '940' }],
          updated_by: 'supervisor',
          updated_by_name: '业务主管',
          updated_at: '2026-07-22 18:48:21',
        },
      },
      global: {
        stubs: { Teleport: true },
      },
    })

    await wrapper.get('.quote-baseline-card-title button').trigger('click')
    await wrapper.findAll('input[aria-label="材质"]')[1].setValue('K料')
    await wrapper.get('[data-testid="save-pricing-baseline"]').trigger('click')

    expect(wrapper.emitted('save')).toBeUndefined()
    expect(wrapper.get('[role="alert"]').text()).toContain('第 2 项材料')
  })
})

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteBaselineDialog from '@/components/modules/sales/internal-quote/InternalQuoteBaselineDialog.vue'

const freightRoutes = [
  { route_key: 'hk40', route_name: 'HK 40 柜', capacity_key: 'cap_40' as const, freight_hkd: '8000', lifting_hkd: '1200' },
  { route_key: 'hk20', route_name: 'HK 20 柜', capacity_key: 'cap_20' as const, freight_hkd: '7100', lifting_hkd: '900' },
]

describe('InternalQuoteBaselineDialog', () => {
  it('shows one large pricing region at a time through three clickable tabs', async () => {
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
          freight_routes: freightRoutes.map((row) => ({ ...row })),
          updated_by: 'system',
          updated_by_name: '系统导入',
          updated_at: '2026-07-18 11:24:14',
        },
      },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.get('#quote-baseline-panel-materials').isVisible()).toBe(true)
    expect(wrapper.get('#quote-baseline-panel-machines').isVisible()).toBe(false)
    expect(wrapper.get('#quote-baseline-panel-freight').isVisible()).toBe(false)

    await wrapper.get('[data-testid="baseline-tab-machines"]').trigger('click')
    expect(wrapper.get('[data-testid="baseline-tab-materials"]').attributes('aria-selected')).toBe('false')
    expect(wrapper.get('[data-testid="baseline-tab-machines"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('#quote-baseline-panel-materials').attributes('style')).toContain('display: none')
    expect(wrapper.get('#quote-baseline-panel-machines').attributes('style')).toBe('')

    await wrapper.get('[data-testid="baseline-tab-freight"]').trigger('click')
    expect(wrapper.get('[data-testid="baseline-tab-machines"]').attributes('aria-selected')).toBe('false')
    expect(wrapper.get('[data-testid="baseline-tab-freight"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('#quote-baseline-panel-machines').attributes('style')).toContain('display: none')
    expect(wrapper.get('#quote-baseline-panel-freight').attributes('style')).toBe('')
  })

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
          freight_routes: freightRoutes.map((row) => ({ ...row })),
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
    await wrapper.get('[data-testid="freight-name-0"]').setValue('香港 40 柜')
    await wrapper.get('[data-testid="freight-cost-hk40"]').setValue('8200')
    await wrapper.get('[data-testid="lifting-cost-hk40"]').setValue('1300')
    await wrapper.get('[data-testid="save-pricing-baseline"]').trigger('click')

    expect(wrapper.emitted('save')).toEqual([[
      {
        revision: 1,
        workshop_name: '华兴',
        material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '9' }],
        machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '950' }],
        freight_routes: [
          { route_key: 'hk40', route_name: '香港 40 柜', capacity_key: 'cap_40', freight_hkd: '8200', lifting_hkd: '1300' },
          freightRoutes[1],
        ],
      },
    ]])
  })

  it('lets a business supervisor add and delete transport routes', async () => {
    const wrapper = mount(InternalQuoteBaselineDialog, {
      props: {
        open: true,
        busy: false,
        canEdit: true,
        baseline: {
          factory_id: 'huaxing',
          workshop_code: 'huaxing-workshop',
          workshop_name: '华兴',
          revision: 2,
          source_type: 'custom',
          material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '8.50' }],
          machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '940' }],
          freight_routes: freightRoutes.map((row) => ({ ...row })),
          updated_by: 'supervisor',
          updated_by_name: '业务主管',
          updated_at: '2026-07-23 10:00:00',
        },
      },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.get('[data-testid="freight-capacity-0"]').element.tagName).toBe('INPUT')
    expect(wrapper.get('[data-testid="freight-capacity-0"]').element).toHaveProperty('value', '40 尺柜容量')
    await wrapper.get('[data-testid="add-freight-route"]').trigger('click')
    await wrapper.get('[data-testid="freight-name-2"]').setValue('HK 8 吨车')
    await wrapper.get('[data-testid="freight-capacity-2"]').setValue('8 吨车容量')
    const newCost = wrapper.findAll('input[type="number"]').find((input) => input.attributes('aria-label') === 'HK 8 吨车运费 HKD')!
    await newCost.setValue('6500')
    const newLiftingCost = wrapper.findAll('input[type="number"]').find((input) => input.attributes('aria-label') === 'HK 8 吨车吊柜费 HKD')!
    await newLiftingCost.setValue('1100')
    await wrapper.get('[data-testid="delete-freight-hk20"]').trigger('click')
    await wrapper.get('[data-testid="save-pricing-baseline"]').trigger('click')

    const payload = wrapper.emitted('save')?.[0]?.[0] as { freight_routes: typeof freightRoutes }
    expect(payload.freight_routes).toHaveLength(2)
    expect(payload.freight_routes[0]).toEqual(freightRoutes[0])
    expect(payload.freight_routes[1]).toMatchObject({
      route_name: 'HK 8 吨车',
      capacity_key: '8 吨车容量',
      freight_hkd: '6500',
      lifting_hkd: '1100',
    })
    expect(payload.freight_routes[1].route_key).toMatch(/^route_[a-z0-9_]+$/)
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
          freight_routes: freightRoutes.map((row) => ({ ...row })),
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
        freight_routes: freightRoutes,
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
          freight_routes: freightRoutes.map((row) => ({ ...row })),
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

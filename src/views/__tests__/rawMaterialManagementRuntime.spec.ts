import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RawMaterialManagementView from '../RawMaterialManagementView.vue'

const rawMaterialApiMock = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
}))

const routerReplaceMock = vi.hoisted(() => vi.fn())
const routeState = vi.hoisted(() => ({
  path: '/modules/pmc-warehouse/raw-material-management',
  query: { factory: 'huaxing' } as Record<string, string>,
}))
const appStoreMock = vi.hoisted(() => ({
  activeProductionFactory: { id: 'huaxing', name: '华兴', shortName: '华兴' },
  setActiveDepartment: vi.fn(),
  setActiveFactory: vi.fn(),
}))

vi.mock('vue-router', () => ({
  RouterLink: {
    name: 'RouterLink',
    props: ['to'],
    template: '<a><slot /></a>',
  },
  useRoute: () => routeState,
  useRouter: () => ({ replace: routerReplaceMock }),
}))

vi.mock('@/api/rawMaterial', () => ({ rawMaterialApi: rawMaterialApiMock }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ can: () => true }),
}))

vi.mock('@/stores/app', () => ({
  useAppStore: () => appStoreMock,
}))

function mountView() {
  return mount(RawMaterialManagementView, {
    global: {
      stubs: {
        AccountMenu: true,
      },
    },
  })
}

function findButton(wrapper: ReturnType<typeof mountView>, label: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().trim() === label)
  if (!button) throw new Error(`Button not found: ${label}`)
  return button
}

describe('RawMaterialManagementView material create flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.query = { factory: 'huaxing' }
    appStoreMock.activeProductionFactory = { id: 'huaxing', name: '华兴', shortName: '华兴' }
    rawMaterialApiMock.list.mockResolvedValue([])
    rawMaterialApiMock.create.mockResolvedValue({
      id: 'RM-NEW-001',
      factory_id: '*',
      material_code: '92000031',
      material_name: '新增测试原料',
      category: 'PVC',
      spec: '',
      unit: 'KG',
      supplier: '',
      safety_stock_kg: 50,
      unit_price_hkd_per_lb: null,
      status: '启用',
      notes: '',
      created_by: 'user-test',
      created_at: '2026-07-18 03:00:00',
      updated_at: '2026-07-18 03:00:00',
    })
  })

  it('creates a material when optional price and safety stock are left blank', async () => {
    const wrapper = mountView()
    await flushPromises()

    await findButton(wrapper, '新增原料').trigger('click')
    await wrapper.get('input[placeholder="如：ABS 750NSW"]').setValue('新增测试原料')
    await wrapper.get('input[placeholder="50"]').setValue('50')
    expect((wrapper.get('[data-testid="raw-material-unit-price"]').element as HTMLInputElement).value).toBe('')

    await findButton(wrapper, '保存').trigger('click')
    await flushPromises()

    expect(rawMaterialApiMock.create).toHaveBeenCalledWith({
      factory_id: 'huaxing',
      material_name: '新增测试原料',
      category: 'PVC',
      spec: '',
      unit: 'KG',
      supplier: '',
      safety_stock_kg: 50,
      unit_price_hkd_per_lb: null,
      status: '启用',
      notes: '',
    })
    expect(wrapper.find('input[placeholder="如：ABS 750NSW"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('原料“新增测试原料”已保存到公共原料资料库，所有厂区可共用。')
    expect(wrapper.text()).toContain('92000031')
  })

  it('shows validation feedback inside the modal instead of failing silently', async () => {
    const wrapper = mountView()
    await flushPromises()

    await findButton(wrapper, '新增原料').trigger('click')
    await findButton(wrapper, '保存').trigger('click')

    expect(wrapper.get('[role="alert"]').text()).toContain('请填写原料名称')
    expect(rawMaterialApiMock.create).not.toHaveBeenCalled()
  })

  it.each([
    ['huakang-a', '华康A'],
    ['huakang-b', '华康B'],
    ['huakang-c', '华康C'],
    ['huakang-d', '华康D'],
    ['huadeng', '华登'],
  ] as const)('shows the shared material catalog for %s while keeping warehouse data isolated', async (factoryId, factoryName) => {
    routeState.query = { factory: factoryId }
    appStoreMock.activeProductionFactory = { id: factoryId, name: factoryName, shortName: factoryName }
    rawMaterialApiMock.list.mockResolvedValue([{
      id: 'RM-SHARED-001',
      factory_id: '*',
      material_code: '91000001',
      material_name: 'ABS 750NSW',
      category: 'ABS',
      spec: 'ABS塑胶料',
      unit: 'KG/包',
      supplier: '韩国锦湖',
      safety_stock_kg: null,
      unit_price_hkd_per_lb: 4.85,
      status: '启用',
      notes: '',
      created_by: 'system-baseline',
      created_at: '2026-07-14 12:00:00',
      updated_at: '2026-07-14 12:00:00',
    }])

    const wrapper = mountView()
    await flushPromises()

    expect(rawMaterialApiMock.list).toHaveBeenCalledWith(factoryId)
    expect(wrapper.text()).toContain('公共原料主数据 · 所有厂区共用')
    expect(wrapper.text()).toContain('91000001')
    expect(wrapper.text()).toContain('ABS 750NSW')
    expect(wrapper.text()).toContain(`已从公共原料资料库读取 1 条资料，${factoryName} 可直接共用。`)
    expect(wrapper.getComponent({ name: 'RouterLink' }).props('to')).toBe(
      `/modules/pmc-warehouse?factory=${factoryId}`,
    )
    expect(wrapper.getComponent({ name: 'RouterLink' }).props('to')).not.toContain('factory=huaxing')

    await findButton(wrapper, '仓库领料单').trigger('click')
    expect(wrapper.text()).not.toContain('LL-20260706-003')
    await findButton(wrapper, '库存批次').trigger('click')
    expect(wrapper.text()).not.toContain('B-20260701-01')
    await findButton(wrapper, '库存流水').trigger('click')
    expect(wrapper.text()).not.toContain('LL-20260706-002')

    wrapper.unmount()
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RawMaterialManagementView from '../RawMaterialManagementView.vue'

const rawMaterialApiMock = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
}))

const routerReplaceMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  RouterLink: {
    props: ['to'],
    template: '<a><slot /></a>',
  },
  useRoute: () => ({
    path: '/modules/pmc-warehouse/raw-material-management',
    query: { factory: 'huaxing' },
  }),
  useRouter: () => ({ replace: routerReplaceMock }),
}))

vi.mock('@/api/rawMaterial', () => ({ rawMaterialApi: rawMaterialApiMock }))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ can: () => true }),
}))

vi.mock('@/stores/app', () => ({
  useAppStore: () => ({
    activeProductionFactory: { id: 'huaxing', name: '华兴', shortName: '华兴' },
    setActiveDepartment: vi.fn(),
    setActiveFactory: vi.fn(),
  }),
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
    rawMaterialApiMock.list.mockResolvedValue([])
    rawMaterialApiMock.create.mockResolvedValue({
      id: 'RM-NEW-001',
      factory_id: 'huaxing',
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
    expect(wrapper.text()).toContain('原料“新增测试原料”已保存到 华兴 数据库。')
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
})

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { nextTick } from 'vue'
import { moldingSampleApi } from '@/api/moldingSample'
import { useAuthStore } from '@/stores/auth'
import MoldingSampleProductionTaskView from '../MoldingSampleProductionTaskView.vue'
import MoldingSampleView from '../MoldingSampleView.vue'

const routerReplace = vi.hoisted(() => vi.fn())
const routeState = vi.hoisted(() => ({
  path: '/modules/molding-sample',
  params: {},
  query: {
    factory: 'huaxing',
  },
}))

const moldingSampleApiMock = vi.hoisted(() => ({
  listOrders: vi.fn(),
  getOrder: vi.fn(),
  createOrder: vi.fn(),
  editOrder: vi.fn(),
  deleteOrder: vi.fn(),
  exportOrderExcel: vi.fn(),
  importOrderExcel: vi.fn(),
  updateStatus: vi.fn(),
  updateItems: vi.fn(),
  listNotifications: vi.fn(),
  updateNotification: vi.fn(),
  createProblem: vi.fn(),
  updateProblemStatus: vi.fn(),
  listProblems: vi.fn(),
  createRequisition: vi.fn(),
  updateRequisitionStatus: vi.fn(),
  createInventoryBatch: vi.fn(),
  listInventoryBatches: vi.fn(),
  listInventoryMovements: vi.fn(),
  listSensitiveAuditLogs: vi.fn(),
  getMaterialPrices: vi.fn(),
  updateMaterialPrices: vi.fn(),
  listInjectionCosts: vi.fn(),
}))

vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')

  return {
    ...actual,
    RouterLink: {
      name: 'RouterLink',
      props: ['to'],
      template: '<a><slot /></a>',
    },
    useRoute: () => routeState,
    useRouter: () => ({
      replace: routerReplace,
    }),
  }
})

vi.mock('@/api/moldingSample', () => ({
  MOLDING_SAMPLE_XLSX_MIME: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  moldingSampleApi: moldingSampleApiMock,
}))

const mockedMoldingSampleApi = vi.mocked(moldingSampleApi)

function createRuntimeError(statusCode: number) {
  return new Error(`Request failed with status code ${statusCode}`)
}

async function mountRuntimeView(component: Component) {
  const pinia = createPinia()
  setActivePinia(pinia)

  useAuthStore().applySession({
    id: 'tester',
    username: 'tester',
    display_name: '测试账号',
    roles: ['系统管理员'],
    permissions: [
      'molding_sample:create',
      'molding_sample:edit_draft',
      'molding_sample:supervisor_review',
      'molding_sample:manager_review',
    ],
    factory_scopes: ['*'],
    department_scopes: ['*'],
    force_password_change: false,
  })

  const wrapper = mount(component, {
    global: {
      plugins: [pinia],
    },
  })

  await flushPromises()
  await nextTick()

  return wrapper
}

function getButtonByText(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(text))

  expect(button, `button containing "${text}"`).toBeTruthy()

  return button!
}

describe('molding sample runtime error handling', () => {
  beforeEach(() => {
    routeState.path = '/modules/molding-sample'
    routeState.query = { factory: 'huaxing' }
    routerReplace.mockReset()
    vi.clearAllMocks()
    window.localStorage.clear()
    mockedMoldingSampleApi.listOrders.mockResolvedValue([])
    mockedMoldingSampleApi.listNotifications.mockResolvedValue([])
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('shows formal data failure on the engineering page without rendering sample orders', async () => {
    mockedMoldingSampleApi.listOrders.mockRejectedValueOnce(createRuntimeError(403))

    const wrapper = await mountRuntimeView(MoldingSampleView)
    const text = wrapper.text()

    expect(text).toContain('正式数据读取失败')
    expect(text).toContain('不会显示本地示例单据')
    expect(text).not.toContain('BP-56206')
    expect(text).not.toContain('软弹枪配色')
    expect(text).not.toContain('Prime Kids')
  })

  it('shows production task failure without rendering or operating on sample tasks', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    mockedMoldingSampleApi.listOrders.mockRejectedValueOnce(createRuntimeError(500))
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([])

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)
    const text = wrapper.text()

    expect(text).toContain('真实任务读取失败')
    expect(text).toContain('不会显示本地示例任务')
    expect(text).not.toContain('BP-56206')
    expect(text).not.toContain('软弹枪配色')
    expect(text).not.toContain('Prime Kids')
    expect(mockedMoldingSampleApi.updateItems).not.toHaveBeenCalled()
    expect(mockedMoldingSampleApi.updateStatus).not.toHaveBeenCalled()
    expect(mockedMoldingSampleApi.createProblem).not.toHaveBeenCalled()
  })

  it('restores a partially filled new-order draft after leaving the page and clears it after submit', async () => {
    const wrapper = await mountRuntimeView(MoldingSampleView)

    await getButtonByText(wrapper, '工程部 · 新建开单').trigger('click')
    await wrapper.get('[data-testid="create-product-no"]').setValue('260705-01')
    await wrapper.get('[data-testid="create-client-name"]').setValue('Bright Kids')
    await wrapper.get('[data-testid="create-product-name"]').setValue('透明灯罩')
    await wrapper.get('[data-testid="create-supervisor"]').setValue('华兴主管')
    await wrapper.get('[data-testid="create-engineer"]').setValue('华兴工程师')
    await wrapper.get('[data-testid="create-line-mold-id"]').setValue('BK-01')
    await wrapper.get('[data-testid="create-line-mold-name"]').setValue('主灯罩')
    await wrapper.get('[data-testid="create-line-material"]').setValue('PC 110')
    await wrapper.get('[data-testid="create-line-color"]').setValue('透明蓝')
    await wrapper.get('[data-testid="create-line-quantity"]').setValue('1')
    await wrapper.get('[data-testid="create-line-shoot-qty"]').setValue('50')
    await wrapper.get('[data-testid="create-line-gross-weight"]').setValue('125.5')
    await wrapper.get('[data-testid="create-line-required-material"]').setValue('2.25')
    await wrapper.get('[data-testid="create-line-required-date"]').setValue('2026-07-10')
    await flushPromises()

    expect(window.localStorage.getItem('rr:molding-sample:create-draft:huaxing')).toContain('透明灯罩')

    await getButtonByText(wrapper, '看板总览').trigger('click')
    wrapper.unmount()

    const restoredWrapper = await mountRuntimeView(MoldingSampleView)
    await getButtonByText(restoredWrapper, '工程部 · 新建开单').trigger('click')
    await nextTick()

    expect((restoredWrapper.get('[data-testid="create-product-name"]').element as HTMLInputElement).value).toBe('透明灯罩')
    expect((restoredWrapper.get('[data-testid="create-line-mold-id"]').element as HTMLInputElement).value).toBe('BK-01')
    expect((restoredWrapper.get('[data-testid="create-line-gross-weight"]').element as HTMLInputElement).value).toBe('125.5')
    expect((restoredWrapper.get('[data-testid="create-line-required-material"]').element as HTMLInputElement).value).toBe('2.25')

    mockedMoldingSampleApi.createOrder.mockImplementationOnce(async (payload) => ({
      order: payload.order,
      items: payload.items,
      audit_logs: [],
      problems: [],
    }))

    await getButtonByText(restoredWrapper, '提交主管审核').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.createOrder).toHaveBeenCalledTimes(1)
    expect(mockedMoldingSampleApi.createOrder.mock.calls[0][0].items[0]).toMatchObject({
      gross_weight_g: 125.5,
      required_material_kg: 2.25,
    })
    expect(window.localStorage.getItem('rr:molding-sample:create-draft:huaxing')).toBeNull()
    expect(restoredWrapper.text()).toContain('新建成功')

    restoredWrapper.unmount()
  })
})

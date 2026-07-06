import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { nextTick } from 'vue'
import { moldingSampleApi } from '@/api/moldingSample'
import type { MoldingSampleCreateRequest, MoldingSampleDetailResponse } from '@/api/moldingSample'
import { useAuthStore } from '@/stores/auth'
import type { MoldingSampleStatus } from '@/types/moldingSample'
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
  previewOrderExcel: vi.fn(),
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

async function mountRuntimeView(
  component: Component,
  options: {
    roles?: string[]
    permissions?: string[]
    displayName?: string
  } = {},
) {
  const pinia = createPinia()
  setActivePinia(pinia)

  const permissions = options.permissions ?? [
    'molding_sample:create',
    'molding_sample:edit_draft',
    'molding_sample:delete_draft',
    'molding_sample:supervisor_review',
    'molding_sample:manager_review',
    'system:user_manage',
  ]

  useAuthStore().applySession({
    id: 'tester',
    username: 'tester',
    display_name: options.displayName ?? '测试账号',
    roles: options.roles ?? ['系统管理员'],
    permissions,
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

function getButtonByExactText(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().trim() === text)

  expect(button, `button with exact text "${text}"`).toBeTruthy()

  return button!
}

function createMoldingSampleRecord(
  status: MoldingSampleStatus = '待审核',
  id = 'BP-WITHDRAW-UI',
  sequence = 1,
): MoldingSampleDetailResponse {
  const day = String(sequence).padStart(2, '0')

  return {
    order: {
      id,
      factory_id: 'huaxing',
      order_number: '62437',
      doc_number: 'W-G026-00',
      product_name: `链条枪${sequence}`,
      client_name: 'BuzzBee',
      date: `2026-07-${day}`,
      stage: 'T0',
      order_type: '啤办',
      workshop: 'A车间',
      send_to: '',
      supervisor: '华兴工程主管',
      eng_name: '测试账号',
      reason: '对办颜色和试啤。',
      status,
      reject_reason: '',
      completed_date: '',
      created_at: `2026-07-${day} 08:00`,
      updated_at: `2026-07-${day} 08:00`,
    },
    items: [],
    audit_logs: [],
    notifications: [],
    problems: [],
  }
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

  it('lets the opening engineer withdraw a pending review order from the detail page', async () => {
    const pendingRecord = createMoldingSampleRecord()
    const withdrawnRecord = {
      ...pendingRecord,
      order: {
        ...pendingRecord.order,
        status: '已撤回',
      },
      audit_logs: [
        {
          id: 'audit-withdraw',
          order_id: pendingRecord.order.id,
          action: '工程撤回',
          actor_name: '测试账号',
          actor_role: '工程部',
          decision: '撤回',
          from_status: '待审核',
          to_status: '已撤回',
          reason: '测试账号撤回主管审核。',
          created_at: '2026-07-01 09:00',
          tone: 'amber',
        },
      ],
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([pendingRecord])
    mockedMoldingSampleApi.updateStatus.mockResolvedValueOnce(withdrawnRecord)

    const wrapper = await mountRuntimeView(MoldingSampleView)

    await getButtonByText(wrapper, 'BP-WITHDRAW-UI').trigger('click')
    await nextTick()
    await getButtonByText(wrapper, '撤回审核').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.updateStatus).toHaveBeenCalledWith('BP-WITHDRAW-UI', {
      action: '工程撤回',
      reason: '测试账号撤回主管审核。',
      today: '2026-07-06',
    })
    expect(wrapper.text()).toContain('已撤回')

    wrapper.unmount()
  })

  it('lets the submitting account withdraw even when the displayed engineer name differs', async () => {
    const pendingRecord = createMoldingSampleRecord()
    pendingRecord.order.eng_name = '工程部协作'
    const withdrawnRecord = {
      ...pendingRecord,
      order: {
        ...pendingRecord.order,
        status: '已撤回',
      },
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([pendingRecord])
    mockedMoldingSampleApi.updateStatus.mockResolvedValueOnce(withdrawnRecord)

    const wrapper = await mountRuntimeView(MoldingSampleView)

    await getButtonByText(wrapper, 'BP-WITHDRAW-UI').trigger('click')
    await nextTick()
    await getButtonByText(wrapper, '撤回审核').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.updateStatus).toHaveBeenCalledWith('BP-WITHDRAW-UI', {
      action: '工程撤回',
      reason: '测试账号撤回主管审核。',
      today: '2026-07-06',
    })

    wrapper.unmount()
  })

  it('lets an administrator delete the selected molding sample order after confirmation', async () => {
    const completedRecord = createMoldingSampleRecord('已完成')

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([completedRecord])
    mockedMoldingSampleApi.deleteOrder.mockResolvedValueOnce(undefined)

    const wrapper = await mountRuntimeView(MoldingSampleView)

    await getButtonByText(wrapper, 'BP-WITHDRAW-UI').trigger('click')
    await nextTick()
    await getButtonByText(wrapper, '删除啤办单').trigger('click')
    await nextTick()

    expect(mockedMoldingSampleApi.deleteOrder).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('再次点击确认删除')

    await getButtonByText(wrapper, '确认删除').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.deleteOrder).toHaveBeenCalledWith('BP-WITHDRAW-UI')
    expect(wrapper.text()).toContain('啤办单 BP-WITHDRAW-UI 已删除')
    expect(wrapper.text()).toContain('当前厂区单据0')
    expect(wrapper.text()).not.toContain('链条枪')

    wrapper.unmount()
  })

  it('lets an engineer delete a withdrawn molding sample order after confirmation', async () => {
    const withdrawnRecord = createMoldingSampleRecord('已撤回')

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([withdrawnRecord])
    mockedMoldingSampleApi.deleteOrder.mockResolvedValueOnce(undefined)

    const wrapper = await mountRuntimeView(MoldingSampleView, {
      roles: ['工程部'],
      permissions: [
        'molding_sample:create',
        'molding_sample:edit_draft',
        'molding_sample:delete_draft',
      ],
      displayName: '测试账号',
    })

    await getButtonByText(wrapper, 'BP-WITHDRAW-UI').trigger('click')
    await nextTick()
    await getButtonByText(wrapper, '删除啤办单').trigger('click')
    await nextTick()

    expect(mockedMoldingSampleApi.deleteOrder).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('再次点击确认删除')

    await getButtonByText(wrapper, '确认删除').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.deleteOrder).toHaveBeenCalledWith('BP-WITHDRAW-UI')
    expect(wrapper.text()).toContain('啤办单 BP-WITHDRAW-UI 已删除')

    wrapper.unmount()
  })

  it('lazy-paginates overview and material balance rows at ten records per page', async () => {
    const records = Array.from({ length: 12 }, (_, index) =>
      createMoldingSampleRecord('待审核', `BP-PAGE-${String(index + 1).padStart(3, '0')}`, index + 1),
    )

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce(records)

    const wrapper = await mountRuntimeView(MoldingSampleView)

    expect(wrapper.text()).toContain('每页 10 条')
    expect(wrapper.text()).toContain('BP-PAGE-010')
    expect(wrapper.text()).not.toContain('BP-PAGE-011')

    await getButtonByText(wrapper, '下一页').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('BP-PAGE-011')
    expect(wrapper.text()).toContain('BP-PAGE-012')
    expect(wrapper.text()).not.toContain('BP-PAGE-010')

    await getButtonByExactText(wrapper, '列表').trigger('click')
    await nextTick()

    expect(wrapper.text()).toContain('BP-PAGE-010')
    expect(wrapper.text()).not.toContain('BP-PAGE-011')

    await getButtonByText(wrapper, '物料结余').trigger('click')
    await nextTick()

    const periodTableText = wrapper.get('table[aria-label="物料周期结余"]').text()
    const detailTableText = wrapper.get('table[aria-label="物料结余明细"]').text()

    expect(periodTableText).toContain('BP-PAGE-003')
    expect(periodTableText).not.toContain('BP-PAGE-002')
    expect(detailTableText).toContain('BP-PAGE-010')
    expect(detailTableText).not.toContain('BP-PAGE-011')

    wrapper.unmount()
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

  it('imports Excel into the new-order draft before formal submission', async () => {
    const previewPayload = {
      order: {
        id: 'BP-XLSX-DRAFT-001',
        factory_id: 'huaxing',
        order_number: 'P50002008',
        doc_number: 'W-G026-00',
        product_name: '30寸黑武士',
        client_name: 'ShuShuPaPa',
        date: '2026-02-03',
        stage: 'T0',
        order_type: '啤办',
        workshop: '工程部',
        send_to: '内部',
        supervisor: '',
        eng_name: '杨敬作',
        reason: '工程部啤办通知单导入',
      },
      items: [
        {
          id: 'BP-XLSX-DRAFT-001-001',
          mold_id: 'P50002008-01-01',
          mold_name: '30寸黑武士-头盔',
          material: 'PP（AV161）',
          color: '黑色 / PMS Black C',
          pigment_no: '黑种',
          quantity: '2',
          shoot_qty: 30,
          required_material_kg: 15,
          mold_return_time: '2026-02-10',
          completion_time: '2026-02-10',
          notes: '报价周期：3天；要求：加急；备注：第一次试模',
        },
      ],
    } satisfies MoldingSampleCreateRequest

    mockedMoldingSampleApi.previewOrderExcel.mockResolvedValueOnce(previewPayload)

    const wrapper = await mountRuntimeView(MoldingSampleView)
    const input = wrapper.get('input[type="file"]')
    const file = new File([new Uint8Array([1, 2, 3])], '华兴啤办.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    Object.defineProperty(input.element, 'files', {
      value: [file],
      configurable: true,
    })

    await input.trigger('change')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.previewOrderExcel).toHaveBeenCalledWith(expect.any(ArrayBuffer), {
      factory_id: 'huaxing',
    })
    expect(mockedMoldingSampleApi.importOrderExcel).not.toHaveBeenCalled()
    expect(mockedMoldingSampleApi.createOrder).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Excel已导入到新建开单草稿')
    expect(wrapper.text()).toContain('提交主管审核')
    expect((wrapper.get('[data-testid="create-order-id"]').element as HTMLInputElement).value).toBe('BP-XLSX-DRAFT-001')
    expect((wrapper.get('[data-testid="create-product-no"]').element as HTMLInputElement).value).toBe('P50002008')
    expect((wrapper.get('[data-testid="create-product-name"]').element as HTMLInputElement).value).toBe('30寸黑武士')
    expect((wrapper.get('[data-testid="create-line-mold-id"]').element as HTMLInputElement).value).toBe('P50002008-01-01')
    expect((wrapper.get('[data-testid="create-line-color"]').element as HTMLInputElement).value).toBe('黑色')
    expect((wrapper.get('[data-testid="create-line-required-material"]').element as HTMLInputElement).value).toBe('15')

    wrapper.unmount()
  })
})

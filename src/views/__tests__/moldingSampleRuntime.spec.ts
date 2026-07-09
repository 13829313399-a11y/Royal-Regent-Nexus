import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { nextTick } from 'vue'
import { moldingSampleApi } from '@/api/moldingSample'
import type {
  MoldingSampleCreateRequest,
  MoldingSampleDetailResponse,
  MoldingSampleNotificationResponse,
} from '@/api/moldingSample'
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
  exportOrdersExcel: vi.fn(),
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
    factoryScopes?: string[]
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
    grants: [],
    factory_scopes: options.factoryScopes ?? ['*'],
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

function getCurrentDateText(date = new Date()) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')

  return `${date.getFullYear()}-${month}-${day}`
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

function createProductionTaskNotification(
  orderId: string,
  sequence = 1,
): MoldingSampleNotificationResponse {
  const day = String(sequence).padStart(2, '0')

  return {
    id: `N-${orderId}`,
    order_id: orderId,
    factory_id: 'huaxing',
    target_module: 'production_molding_sample_task',
    target_role: '啤机部',
    event_type: '主管通过',
    title: `生产任务 ${orderId}`,
    message: '主管审核通过，进入啤机部任务队列。',
    from_status: '待审核',
    to_status: '待生产',
    status: '未读',
    actor_name: '华兴工程主管',
    read_at: '',
    handled_at: '',
    created_at: `2026-07-${day} 09:00`,
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
    mockedMoldingSampleApi.getMaterialPrices.mockResolvedValue({
      prices: [],
      rmb_to_hkd_rate: 1.08,
    })
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

  it('opens an in-app print preview before printing the current molding sample order', async () => {
    const printSpy = vi.fn()
    vi.stubGlobal('print', printSpy)
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([
      createMoldingSampleRecord('待审核', 'BP-PRINT-CURRENT', 1),
    ])

    const wrapper = await mountRuntimeView(MoldingSampleView)

    await getButtonByExactText(wrapper, '打印').trigger('click')
    await flushPromises()
    await nextTick()

    expect(printSpy).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="molding-sample-print-preview"]').text()).toContain('BP-PRINT-CURRENT')
    expect(wrapper.get('[data-testid="molding-sample-print-area"]').text()).toContain('BP-PRINT-CURRENT')

    await getButtonByExactText(wrapper, '确认打印').trigger('click')
    expect(printSpy).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('keeps out-of-scope factory orders readable while disabling molding sample writes', async () => {
    routeState.query = { factory: 'huadeng' }
    const huadengRecord = createMoldingSampleRecord('待审核', 'BP-READONLY-HD-001')
    huadengRecord.order.factory_id = 'huadeng'
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([huadengRecord])

    const wrapper = await mountRuntimeView(MoldingSampleView, {
      roles: ['工程主管'],
      permissions: [
        'molding_sample:create',
        'molding_sample:edit_draft',
        'molding_sample:delete_draft',
        'molding_sample:supervisor_review',
      ],
      factoryScopes: ['huaxing'],
      displayName: '华兴工程主管',
    })

    expect(wrapper.text()).toContain('BP-READONLY-HD-001')
    expect(wrapper.text()).toContain('当前厂区为只读，仅可查看数据')
    expect(getButtonByText(wrapper, '工程部 · 新建开单').attributes('disabled')).toBeDefined()

    await getButtonByText(wrapper, 'BP-READONLY-HD-001').trigger('click')
    await nextTick()

    expect(getButtonByText(wrapper, '撤回审核').attributes('disabled')).toBeDefined()
    expect(getButtonByExactText(wrapper, '通过').attributes('disabled')).toBeDefined()
    expect(getButtonByExactText(wrapper, '驳回').attributes('disabled')).toBeDefined()

    await getButtonByExactText(wrapper, '通过').trigger('click')
    await flushPromises()

    expect(mockedMoldingSampleApi.updateStatus).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  it('exports one combined Excel workbook for multiple checked molding sample orders', async () => {
    const records = [
      createMoldingSampleRecord('待审核', 'BP-BATCH-001', 1),
      createMoldingSampleRecord('待生产', 'BP-BATCH-002', 2),
      createMoldingSampleRecord('已完成', 'BP-BATCH-003', 3),
    ]
    const createObjectUrl = vi.fn(() => 'blob:molding-sample-export')
    const revokeObjectUrl = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    vi.stubGlobal('URL', Object.assign(URL, {
      createObjectURL: createObjectUrl,
      revokeObjectURL: revokeObjectUrl,
    }))

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce(records)
    mockedMoldingSampleApi.exportOrdersExcel.mockResolvedValue(new Uint8Array([1, 2, 3]).buffer)

    const wrapper = await mountRuntimeView(MoldingSampleView)

    await wrapper.get('[aria-label="选择单据 BP-BATCH-001"]').setValue(true)
    await wrapper.get('[aria-label="选择单据 BP-BATCH-003"]').setValue(true)
    await getButtonByExactText(wrapper, '导出Excel').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.exportOrderExcel).not.toHaveBeenCalled()
    expect(mockedMoldingSampleApi.exportOrdersExcel).toHaveBeenCalledTimes(1)
    expect(mockedMoldingSampleApi.exportOrdersExcel).toHaveBeenCalledWith(['BP-BATCH-001', 'BP-BATCH-003'])
    expect(wrapper.text()).toContain('已导出 2 张啤办单到一个Excel文件')

    wrapper.unmount()
  })

  it('prints detailed content for all checked molding sample orders', async () => {
    const printSpy = vi.fn()
    vi.stubGlobal('print', printSpy)
    const records = [
      createMoldingSampleRecord('待审核', 'BP-PRINT-001', 1),
      createMoldingSampleRecord('待生产', 'BP-PRINT-002', 2),
    ]

    records[0].items = [{
      id: 'BP-PRINT-001-001',
      order_id: 'BP-PRINT-001',
      sort_order: 1,
      mold_id: 'MOLD-A',
      mold_name: '打印模具A',
      machine_type: '160T',
      production_machine: '啤办机台-08',
      material: 'ABS 750NSW',
      color: '黑色',
      pigment_no: 'PMS',
      quantity: '1',
      shoot_qty: 30,
      gross_weight_g: 11,
      required_material_kg: 1.5,
      mold_return_time: '2026-07-10',
      completion_time: '',
      notes: '打印明细备注',
      receipt_no: 'REC-001',
      collected_weight_kg: 1.7,
      actual_weight_kg: 1.42,
      actual_amount_hkd: 8.5,
      injection_cost: 120,
      injection_cost_hkd: 111.11,
      exchange_rate_at_save: 1.08,
    }]
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce(records)

    const wrapper = await mountRuntimeView(MoldingSampleView)

    await getButtonByExactText(wrapper, '全选当前筛选单据').trigger('click')
    await getButtonByExactText(wrapper, '打印').trigger('click')
    await flushPromises()
    await nextTick()

    const printArea = wrapper.get('[data-testid="molding-sample-print-area"]').text()
    const printPreview = wrapper.get('[data-testid="molding-sample-print-preview"]').text()
    expect(printSpy).not.toHaveBeenCalled()
    expect(printPreview).toContain('打印预览')
    expect(printPreview).toContain('BP-PRINT-001')
    expect(printPreview).toContain('BP-PRINT-002')
    expect(printArea).toContain('BP-PRINT-001')
    expect(printArea).toContain('打印模具A')
    expect(printArea).toContain('啤机确认机台')
    expect(printArea).toContain('啤办机台-08')
    expect(printArea).toContain('ABS 750NSW')
    expect(printArea).not.toContain('160T')
    expect(printArea).not.toContain('REC-001')
    expect(printArea).toContain('1.42 kg')
    expect(printArea).toContain('预计料费')
    expect(printArea).toContain('HKD 16.04')
    expect(printArea).toContain('HKD 8.50')
    expect(printArea).toContain('RMB 120.00')
    expect(printArea).toContain('1.08')
    expect(printArea).toContain('BP-PRINT-002')
    expect(printArea).toContain('Royal Regent Nexus')
    expect(printArea).toContain('工程啤办通知单')
    expect(printArea).toContain('单据资料')
    expect(printArea).toContain('签核栏')
    expect(printArea).toContain('经办确认')
    expect(printArea).toContain('主管审核')
    expect(printArea).toContain('啤机确认')
    expect(printArea).toContain('T0 阶段')
    expect(printArea).toContain('共 1 条模具明细')
    expect(printArea).toContain('模具明细（一行一模具，节省纸张）')
    expect(printArea).toContain('扫码查看单据')
    expect(printArea).toContain('第 1 / 1 页')

    await getButtonByExactText(wrapper, '确认打印').trigger('click')
    expect(printSpy).toHaveBeenCalledTimes(1)

    wrapper.unmount()
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

  it('keeps out-of-scope production tasks readable while disabling production writes', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huadeng', order_id: 'BP-PROD-READONLY-HD-001' }
    const huadengTask = createMoldingSampleRecord('待生产', 'BP-PROD-READONLY-HD-001')
    huadengTask.order.factory_id = 'huadeng'
    const huadengNotification = createProductionTaskNotification(huadengTask.order.id)
    huadengNotification.factory_id = 'huadeng'

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([huadengTask])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([huadengNotification])

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView, {
      roles: ['啤机部文员'],
      permissions: [
        'molding_sample:production_read',
        'molding_sample:production_start',
        'molding_sample:production_fillback',
        'molding_sample:production_complete',
        'molding_sample:notification_read',
      ],
      factoryScopes: ['huaxing'],
      displayName: '华兴啤机部文员',
    })

    expect(wrapper.text()).toContain('BP-PROD-READONLY-HD-001')
    expect(wrapper.text()).toContain('当前厂区为只读，仅可查看数据')
    expect(getButtonByText(wrapper, '开始生产').attributes('disabled')).toBeDefined()

    await getButtonByText(wrapper, '开始生产').trigger('click')
    await flushPromises()

    expect(mockedMoldingSampleApi.updateStatus).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  it('paginates the production task board and list at ten tasks per page', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing' }
    const records = Array.from({ length: 12 }, (_, index) => {
      const id = `BP-PROD-${String(index + 1).padStart(3, '0')}`
      return createMoldingSampleRecord('待生产', id, index + 1)
    })
    const notifications = records.map((record, index) =>
      createProductionTaskNotification(record.order.id, index + 1),
    )

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce(records)
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce(notifications)

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)
    const queue = () => wrapper.get('[aria-label="啤办生产任务队列"]')

    expect(wrapper.text()).toContain('看板')
    expect(wrapper.text()).toContain('列表')
    expect(queue().text()).toContain('每页 10 条')
    expect(queue().text()).toContain('BP-PROD-010')
    expect(queue().text()).not.toContain('BP-PROD-011')

    await getButtonByText(wrapper, '下一页').trigger('click')
    await nextTick()

    expect(queue().text()).toContain('BP-PROD-011')
    expect(queue().text()).toContain('BP-PROD-012')
    expect(queue().text()).not.toContain('BP-PROD-010')

    await getButtonByExactText(wrapper, '列表').trigger('click')
    await nextTick()

    expect(queue().text()).toContain('BP-PROD-010')
    expect(queue().text()).not.toContain('BP-PROD-011')

    wrapper.unmount()
  })

  it('expands the production task page to show the full molding sample order data', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-FULL-001' }
    const detailedRecord = {
      ...createMoldingSampleRecord('待生产', 'BP-PROD-FULL-001'),
      order: {
        ...createMoldingSampleRecord('待生产', 'BP-PROD-FULL-001').order,
        order_number: 'P50002008',
        doc_number: 'W-G026-00',
        product_name: '30寸黑武士',
        client_name: 'ShuShuPaPa',
        workshop: '工程部',
        reason: '生产回填前需要查看完整啤办资料。',
      },
      items: [
        {
          id: 'BP-PROD-FULL-001-001',
          order_id: 'BP-PROD-FULL-001',
          sort_order: 1,
          mold_id: 'P50002008-01-01',
          mold_name: '头盔',
          machine_type: '160T',
          production_machine: '啤办机台-08',
          material: 'PP (AV161)',
          color: '黑色',
          pigment_no: 'PMS 黑色',
          quantity: '1/1',
          shoot_qty: 30,
          gross_weight_g: 82,
          required_material_kg: 15,
          mold_return_time: '2026-02-03',
          completion_time: '2026-02-04',
          notes: '啤机回填前核对完整资料。',
          receipt_no: 'RC-20260203-01',
          collected_weight_kg: 14.5,
          actual_weight_kg: null,
          actual_amount_hkd: null,
          injection_cost: null,
          injection_cost_hkd: null,
          exchange_rate_at_save: null,
        },
      ],
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([detailedRecord])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(detailedRecord.order.id),
    ])

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)

    expect(wrapper.text()).not.toContain('完整单据数据')
    expect(wrapper.text()).not.toContain('整啤毛重(g)')
    expect(wrapper.text()).not.toContain('RC-20260203-01')

    await getButtonByText(wrapper, '展开完整数据').trigger('click')
    await nextTick()

    const text = wrapper.text()
    expect(text).toContain('完整单据数据')
    expect(text).toContain('产品编号')
    expect(text).toContain('P50002008')
    expect(text).toContain('文件编号')
    expect(text).toContain('W-G026-00')
    expect(text).toContain('整啤毛重(g)')
    expect(text).toContain('82.00 g')
    expect(text).toContain('PMS 黑色')
    expect(text).not.toContain('160T')
    expect(text).not.toContain('RC-20260203-01')
    expect(text).toContain('啤机确认机台')
    expect(text).toContain('啤办机台-08')
    expect(text).toContain('啤机回填前核对完整资料。')

    wrapper.unmount()
  })

  it('saves the production machine from the production fillback page', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-MACHINE-001' }
    const runningRecord = {
      ...createMoldingSampleRecord('生产中', 'BP-PROD-MACHINE-001'),
      items: [
        {
          id: 'BP-PROD-MACHINE-001-001',
          order_id: 'BP-PROD-MACHINE-001',
          sort_order: 1,
          mold_id: 'P50002008-01-01',
          mold_name: '头盔',
          machine_type: '160T',
          production_machine: '',
          material: 'PP (AV161)',
          color: '黑色',
          pigment_no: 'PMS 黑色',
          quantity: '1/1',
          shoot_qty: 30,
          gross_weight_g: 82,
          required_material_kg: 15,
          mold_return_time: '2026-02-03',
          completion_time: '2026-02-04',
          notes: '确认机台回填。',
          receipt_no: 'RC-20260203-01',
          collected_weight_kg: 14.5,
          actual_weight_kg: null,
          actual_amount_hkd: null,
          injection_cost: null,
          injection_cost_hkd: null,
          exchange_rate_at_save: null,
        } as MoldingSampleDetailResponse['items'][number],
      ],
    } satisfies MoldingSampleDetailResponse
    const updatedRecord = {
      ...runningRecord,
      items: [
        {
          ...runningRecord.items[0],
          actual_weight_kg: 14.2,
          injection_cost: 120,
          production_machine: '啤办机台-08',
        },
      ],
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([runningRecord])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(runningRecord.order.id),
    ])
    mockedMoldingSampleApi.updateItems.mockResolvedValueOnce(updatedRecord)

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)

    await wrapper.get('input[aria-label="实际用料"]').setValue('14.2')
    await wrapper.get('input[aria-label="啤办费"]').setValue('120')
    await wrapper.get('input[aria-label="啤机确认机台"]').setValue('啤办机台-08')
    await getButtonByText(wrapper, '保存回填').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.updateItems).toHaveBeenCalledWith('BP-PROD-MACHINE-001', {
      items: [
        {
          id: 'BP-PROD-MACHINE-001-001',
          actual_weight_kg: 14.2,
          injection_cost: 120,
          production_machine: '啤办机台-08',
        },
      ],
    })
    expect(wrapper.text()).toContain('啤机确认机台')
    expect((wrapper.get('input[aria-label="啤机确认机台"]').element as HTMLInputElement).value).toBe('啤办机台-08')

    wrapper.unmount()
  })

  it('lets the molding clerk withdraw a started production task', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-START-ROLLBACK-001' }
    const runningRecord = createMoldingSampleRecord('生产中', 'BP-PROD-START-ROLLBACK-001')
    const rollbackRecord = {
      ...runningRecord,
      order: {
        ...runningRecord.order,
        status: '待生产',
        completed_date: '',
      },
      audit_logs: [
        {
          id: 'audit-production-start-rollback',
          order_id: runningRecord.order.id,
          action: '撤回开始生产',
          actor_user_id: 'tester',
          actor_name: '测试账号',
          actor_role: '啤机部',
          actor_roles: '啤机部文员',
          factory_scope: 'huaxing',
          decision: '撤回',
          from_status: '生产中',
          to_status: '待生产',
          reason: '啤机部撤回开始生产，任务回到待生产。',
          created_at: '2026-07-03 15:10',
          tone: 'amber',
        },
      ],
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([runningRecord])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(runningRecord.order.id),
    ])
    mockedMoldingSampleApi.updateStatus.mockResolvedValueOnce(rollbackRecord)

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)

    await getButtonByText(wrapper, '撤回开始生产').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.updateStatus).toHaveBeenCalledWith('BP-PROD-START-ROLLBACK-001', {
      action: '撤回开始生产',
      reason: '啤机部撤回开始生产，任务回到待生产。',
      today: '2026-07-03',
    })
    expect(wrapper.text()).toContain('已撤回开始生产，任务回到待生产。')
    expect(wrapper.text()).toContain('待生产')

    wrapper.unmount()
  })

  it('lets the molding clerk withdraw a completed production handoff', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-ROLLBACK-001' }
    const completedRecord = {
      ...createMoldingSampleRecord('已完成', 'BP-PROD-ROLLBACK-001'),
      order: {
        ...createMoldingSampleRecord('已完成', 'BP-PROD-ROLLBACK-001').order,
        completed_date: '2026-07-03',
      },
    } satisfies MoldingSampleDetailResponse
    const rollbackRecord = {
      ...completedRecord,
      order: {
        ...completedRecord.order,
        status: '生产中',
        completed_date: '',
      },
      audit_logs: [
        {
          id: 'audit-production-rollback',
          order_id: completedRecord.order.id,
          action: '撤回完成',
          actor_user_id: 'tester',
          actor_name: '测试账号',
          actor_role: '啤机部',
          actor_roles: '啤机部文员',
          factory_scope: 'huaxing',
          decision: '撤回',
          from_status: '已完成',
          to_status: '生产中',
          reason: '啤机部撤回完成回传，回到生产中继续修正。',
          created_at: '2026-07-03 15:00',
          tone: 'amber',
        },
      ],
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([completedRecord])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(completedRecord.order.id),
    ])
    mockedMoldingSampleApi.updateStatus.mockResolvedValueOnce(rollbackRecord)

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)

    expect(wrapper.text()).toContain('已回传')
    await getButtonByText(wrapper, '撤回完成').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.updateStatus).toHaveBeenCalledWith('BP-PROD-ROLLBACK-001', {
      action: '撤回完成',
      reason: '啤机部撤回完成回传，回到生产中继续修正。',
      today: '2026-07-03',
    })
    expect(wrapper.text()).toContain('生产完成已撤回，可继续修正回填后重新完成。')
    expect(wrapper.text()).toContain('生产中')
    expect(wrapper.text()).toContain('待回传')

    wrapper.unmount()
  })

  it('lets the molding clerk withdraw a started production task back to pending production', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-START-ROLLBACK-001' }
    const runningRecord = createMoldingSampleRecord('生产中', 'BP-PROD-START-ROLLBACK-001')
    const rollbackRecord = {
      ...runningRecord,
      order: {
        ...runningRecord.order,
        status: '待生产',
      },
      audit_logs: [
        {
          id: 'audit-production-start-rollback',
          order_id: runningRecord.order.id,
          action: '撤回开始生产',
          actor_user_id: 'tester',
          actor_name: '测试账号',
          actor_role: '啤机部',
          actor_roles: '啤机部文员',
          factory_scope: 'huaxing',
          decision: '撤回',
          from_status: '生产中',
          to_status: '待生产',
          reason: '啤机部撤回开始生产，任务回到待生产。',
          created_at: '2026-07-03 15:10',
          tone: 'amber',
        },
      ],
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([runningRecord])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(runningRecord.order.id),
    ])
    mockedMoldingSampleApi.updateStatus.mockResolvedValueOnce(rollbackRecord)

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)

    await getButtonByText(wrapper, '撤回开始生产').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.updateStatus).toHaveBeenCalledWith('BP-PROD-START-ROLLBACK-001', {
      action: '撤回开始生产',
      reason: '啤机部撤回开始生产，任务回到待生产。',
      today: '2026-07-03',
    })
    expect(wrapper.text()).toContain('已撤回开始生产，任务回到待生产。')
    expect(wrapper.text()).toContain('待生产')

    wrapper.unmount()
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
      today: getCurrentDateText(),
    })
    expect(wrapper.text()).toContain('已撤回')

    wrapper.unmount()
  })

  it('expands the detail page to show the full molding sample order data', async () => {
    const detailedRecord = {
      ...createMoldingSampleRecord('待审核', 'BP-DETAIL-FULL-001'),
      order: {
        ...createMoldingSampleRecord('待审核', 'BP-DETAIL-FULL-001').order,
        order_number: 'P50002008',
        doc_number: 'W-G026-00',
        product_name: '30寸黑武士',
        client_name: 'ShuShuPaPa',
        workshop: '工程部',
        send_to: '',
        reason: '试啤确认颜色、PMS 与啤办用料。',
      },
      items: [
        {
          id: 'BP-DETAIL-FULL-001-001',
          order_id: 'BP-DETAIL-FULL-001',
          sort_order: 1,
          mold_id: 'P50002008-01-01',
          mold_name: '头盔',
          machine_type: '160T',
          production_machine: '啤办机台-08',
          material: 'PP (AV161)',
          color: '黑色',
          pigment_no: 'PMS 黑色',
          quantity: '1/1',
          shoot_qty: 30,
          gross_weight_g: 82,
          required_material_kg: 15,
          mold_return_time: '2026-02-03',
          completion_time: '2026-02-04',
          notes: '确认披锋与缩水。',
          receipt_no: 'RC-20260203-01',
          collected_weight_kg: 14.5,
          actual_weight_kg: 14.2,
          actual_amount_hkd: 98.76,
          injection_cost: 120,
          injection_cost_hkd: 129.6,
          exchange_rate_at_save: 1.08,
        },
      ],
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([detailedRecord])

    const wrapper = await mountRuntimeView(MoldingSampleView)

    await getButtonByText(wrapper, 'BP-DETAIL-FULL-001').trigger('click')
    await nextTick()

    expect(wrapper.text()).not.toContain('完整单据数据')
    expect(wrapper.text()).not.toContain('整啤毛重(g)')
    expect(wrapper.text()).not.toContain('RC-20260203-01')

    await getButtonByText(wrapper, '展开完整数据').trigger('click')
    await nextTick()

    const text = wrapper.text()
    expect(text).toContain('完整单据数据')
    expect(text).toContain('产品编号')
    expect(text).toContain('P50002008')
    expect(text).toContain('文件编号')
    expect(text).toContain('W-G026-00')
    expect(text).toContain('整啤毛重(g)')
    expect(text).toContain('82.00 g')
    expect(text).toContain('PMS 黑色')
    expect(text).not.toContain('160T')
    expect(text).not.toContain('RC-20260203-01')
    expect(text).toContain('啤办费(HKD)')
    expect(text).toContain('HKD 129.60')
    expect(text).toContain('啤机确认机台')
    expect(text).toContain('啤办机台-08')
    expect(text).toContain('确认披锋与缩水。')

    wrapper.unmount()
  })

  it('shows the current RMB to HKD rate when an item has no saved exchange rate', async () => {
    const detailedRecord = {
      ...createMoldingSampleRecord('生产中', 'BP-RATE-LIVE-001'),
      items: [
        {
          id: 'BP-RATE-LIVE-001-001',
          order_id: 'BP-RATE-LIVE-001',
          sort_order: 1,
          mold_id: 'P50002008-01-01',
          mold_name: '头盔',
          machine_type: '160T',
          production_machine: '啤办机台-08',
          material: 'PP (AV161)',
          color: '黑色',
          pigment_no: 'PMS 黑色',
          quantity: '1/1',
          shoot_qty: 30,
          gross_weight_g: 82,
          required_material_kg: 15,
          mold_return_time: '2026-02-03',
          completion_time: '2026-02-04',
          notes: '待保存啤办费。',
          receipt_no: '',
          collected_weight_kg: null,
          actual_weight_kg: 14.2,
          actual_amount_hkd: null,
          injection_cost: null,
          injection_cost_hkd: null,
          exchange_rate_at_save: null,
        },
      ],
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([detailedRecord])
    mockedMoldingSampleApi.getMaterialPrices.mockResolvedValueOnce({
      prices: [],
      rmb_to_hkd_rate: 1.1234,
    })

    const wrapper = await mountRuntimeView(MoldingSampleView)

    await getButtonByText(wrapper, 'BP-RATE-LIVE-001').trigger('click')
    await nextTick()
    await getButtonByText(wrapper, '展开完整数据').trigger('click')
    await flushPromises()
    await nextTick()

    const text = wrapper.text()
    expect(text).toContain('当前汇率(RMB→HKD)')
    expect(text).toContain('1.1234')
    expect(text).not.toContain('汇率待填写')

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
      today: getCurrentDateText(),
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
    const materialInput = wrapper.get('[data-testid="create-line-material"]')
    await materialInput.trigger('focus')
    await materialInput.setValue('ABS 750NSW')
    await materialInput.trigger('keydown.enter')
    expect(wrapper.get('[data-testid="create-line-material-price"]').text()).toContain('HKD 4.85')
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

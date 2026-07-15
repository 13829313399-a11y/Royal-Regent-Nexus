import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { nextTick } from 'vue'
import { moldingSampleApi } from '@/api/moldingSample'
import { rawMaterialApi } from '@/api/rawMaterial'
import type { AuthEffectiveAccess, AuthzMode } from '@/api/auth'
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
const rawMaterialApiMock = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
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

vi.mock('@/api/rawMaterial', () => ({
  rawMaterialApi: rawMaterialApiMock,
}))

const mockedMoldingSampleApi = vi.mocked(moldingSampleApi)
const mockedRawMaterialApi = vi.mocked(rawMaterialApi)

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
    department?: string
    authzMode?: AuthzMode
    effectiveAccess?: AuthEffectiveAccess[]
    grantPermissions?: string[]
    primaryFactoryId?: string
  } = {},
) {
  const pinia = createPinia()
  setActivePinia(pinia)

  const permissions = options.permissions ?? [
    'molding_sample:read',
    'molding_sample:export',
    'molding_sample:create',
    'molding_sample:edit_draft',
    'molding_sample:delete_draft',
    'molding_sample:supervisor_review',
    'molding_sample:manager_review',
    'molding_sample:production_read',
    'molding_sample:production_start',
    'molding_sample:production_fillback',
    'molding_sample:production_complete',
    'molding_sample:notification_read',
    'system:user_manage',
  ]
  const factoryScopes = options.factoryScopes ?? ['*']
  const administrator = (options.roles ?? ['系统管理员']).includes('系统管理员')

  useAuthStore().applySession({
    id: 'tester',
    username: 'tester',
    display_name: options.displayName ?? '测试账号',
    roles: options.roles ?? ['系统管理员'],
    permissions,
    grants: [{
      role_id: administrator ? 'admin' : 'test-role',
      role_code: administrator ? 'admin' : 'test-role',
      role_name: administrator ? '系统管理员' : '测试角色',
      factory_id: factoryScopes.includes('*') ? '*' : factoryScopes[0] ?? 'huaxing',
      department: administrator ? 'system' : options.department ?? '*',
      permissions: options.grantPermissions ?? permissions,
      data_scope: administrator ? 'all' : 'department',
    }],
    factory_scopes: factoryScopes,
    department_scopes: ['*'],
    authz_mode: options.authzMode,
    profile: options.primaryFactoryId
      ? {
          primary_factory_id: options.primaryFactoryId,
          primary_department: options.department ?? 'engineering',
          position: '测试岗位',
          confirmation_status: 'confirmed',
        }
      : undefined,
    effective_access: options.effectiveAccess,
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

function createKpiRecord(
  status: MoldingSampleStatus,
  id: string,
  actualWeightKg: number | null,
  problemStatuses: Array<'待处理' | '已解决'> = [],
  sendTo: '' | '发至模厂' = '',
): MoldingSampleDetailResponse {
  const record = createMoldingSampleRecord(status, id)
  record.order.send_to = sendTo
  record.items = [{
    id: `${id}-ITEM-1`,
    order_id: id,
    sort_order: 1,
    mold_id: 'M-001',
    mold_name: '测试模具',
    mold_dimensions: '',
    mold_presence_status: 'unknown',
    machine_type: '160T',
    production_machine: '',
    material: 'HIPS 425',
    color: '黑色',
    pigment_no: '',
    quantity: '1',
    shoot_qty: 30,
    gross_weight_g: 82,
    required_material_kg: 2.46,
    mold_return_time: '',
    completion_time: '',
    notes: '',
    receipt_no: '',
    collected_weight_kg: null,
    actual_weight_kg: actualWeightKg,
    actual_amount_hkd: null,
    injection_cost: null,
    injection_cost_hkd: null,
    exchange_rate_at_save: null,
  }]
  record.problems = problemStatuses.map((problemStatus, index) => ({
    id: `${id}-PROBLEM-${index + 1}`,
    factory_id: 'huaxing',
    order_type: 'injection',
    order_id: id,
    order_number: record.order.order_number,
    description: `测试问题 ${index + 1}`,
    reported_by: '啤机部',
    status: problemStatus,
    created_at: '2026-07-11 08:00',
    resolved_at: problemStatus === '已解决' ? '2026-07-11 09:00' : '',
  }))

  return record
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
      prices: [{ material: 'ABS 750NSW', unit_price: 4.85 }],
      rmb_to_hkd_rate: 1.08,
    })
    mockedRawMaterialApi.list.mockResolvedValue([{
      id: 'RM-BASELINE-huaxing-91000001',
      factory_id: 'huaxing',
      material_code: '91000001',
      material_name: 'ABS 750NSW',
      category: 'ABS',
      spec: 'ABS塑胶料',
      unit: 'KG/包',
      supplier: '韩国锦湖',
      safety_stock_kg: null,
      status: '启用',
      notes: '',
      created_by: 'system-baseline',
      created_at: '2026-07-14 12:00:00',
      updated_at: '2026-07-14 12:00:00',
    }])
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

  it('keeps order reading usable when protected material prices are forbidden', async () => {
    const record = createKpiRecord('待审核', 'BP-PRICE-FORBIDDEN-001', null)
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([record])
    mockedMoldingSampleApi.getMaterialPrices.mockRejectedValueOnce(createRuntimeError(403))

    const wrapper = await mountRuntimeView(MoldingSampleView)

    expect(mockedMoldingSampleApi.getMaterialPrices).toHaveBeenCalledWith('huaxing')
    expect(wrapper.text()).toContain('BP-PRICE-FORBIDDEN-001')
    expect(wrapper.text()).not.toContain('正式数据读取失败')

    wrapper.unmount()
  })

  it('loads only the active factory orders and reports an empty factory accurately', async () => {
    routeState.query = { factory: 'huadeng' }
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([])

    const wrapper = await mountRuntimeView(MoldingSampleView)

    expect(mockedMoldingSampleApi.listOrders).toHaveBeenCalledWith('huadeng')
    expect(wrapper.text()).toContain('华登暂无正式啤办单')
    expect(wrapper.text()).toContain('当前厂区单据')
    expect(wrapper.text()).toContain('华登 · 按状态分列')

    wrapper.unmount()
  })

  it('separates returned orders, unresolved problems, and missing production data', async () => {
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([
      createKpiRecord('已驳回', 'BP-KPI-REJECTED', null),
      createKpiRecord('已撤回', 'BP-KPI-WITHDRAWN', null, ['已解决']),
      createKpiRecord('生产中', 'BP-KPI-PROD-MISSING', null, ['待处理', '待处理']),
      createKpiRecord('生产中', 'BP-KPI-PROD-COMPLETE', 1.2, ['已解决']),
      createKpiRecord('待生产', 'BP-KPI-PENDING-PROD', null),
      createKpiRecord('待审核', 'BP-KPI-PENDING-REVIEW', null),
      createKpiRecord('生产中', 'BP-KPI-EXTERNAL', null, [], '发至模厂'),
    ])

    const wrapper = await mountRuntimeView(MoldingSampleView)

    expect(wrapper.get('[data-testid="molding-kpi-grid"]').findAll('article')).toHaveLength(7)
    expect(wrapper.get('[data-testid="molding-kpi-returned-withdrawn-value"]').text()).toBe('2')
    expect(wrapper.get('[data-testid="molding-kpi-returned-withdrawn"]').text()).toContain('已驳回 1 · 已撤回 1')
    expect(wrapper.get('[data-testid="molding-kpi-unresolved-problems-value"]').text()).toBe('1')
    expect(wrapper.get('[data-testid="molding-kpi-production-data-pending-value"]').text()).toBe('1')
    expect(wrapper.text()).not.toContain('卡点 / 退回')

    await wrapper.get('[data-testid="molding-sample-search-input"]').setValue('BP-KPI-PROD-MISSING')
    await nextTick()

    expect(wrapper.get('[data-testid="molding-kpi-factory-orders-value"]').text()).toBe('1')
    expect(wrapper.get('[data-testid="molding-kpi-returned-withdrawn-value"]').text()).toBe('0')
    expect(wrapper.get('[data-testid="molding-kpi-unresolved-problems-value"]').text()).toBe('1')
    expect(wrapper.get('[data-testid="molding-kpi-production-data-pending-value"]').text()).toBe('1')

    wrapper.unmount()
  })

  it('fuzzy searches orders across normalized order, mold, client, and material fields', async () => {
    const searchableRecord = createKpiRecord('待审核', 'BP-SEARCH-MIXED-001', null)
    Object.assign(searchableRecord.order, {
      doc_number: 'WG-026',
      product_name: 'Helmet Shell',
      client_name: 'ShuShuPaPa',
    })
    Object.assign(searchableRecord.items[0]!, {
      mold_id: 'JP-5678',
      mold_name: 'Head Mold Alpha',
      material: 'legacy material text',
      material_components: [
        { material: 'ABS PA-757', source_type: 'virgin', ratio_percent: 70 },
        { material: 'PVC 90度（本白,普通）', source_type: 'runner', ratio_percent: 30 },
      ],
    })
    const unrelatedRecord = createKpiRecord('待生产', 'BP-SEARCH-OTHER-002', null)
    unrelatedRecord.order.client_name = 'Another Client'
    unrelatedRecord.order.doc_number = 'DOC-OTHER-002'

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([searchableRecord, unrelatedRecord])

    const wrapper = await mountRuntimeView(MoldingSampleView)
    const searchInput = wrapper.get('[data-testid="molding-sample-search-input"]')

    expect(searchInput.attributes('type')).toBe('search')
    expect(searchInput.attributes('aria-label')).toBe('模糊搜索啤办单')

    for (const keyword of ['jp 5678', 'shushupapa pvc', 'ｗｇ ０２６']) {
      await searchInput.setValue(keyword)
      await nextTick()

      expect(wrapper.get('[data-testid="molding-kpi-factory-orders-value"]').text()).toBe('1')
      expect(wrapper.text()).toContain('BP-SEARCH-MIXED-001')
      expect(wrapper.text()).not.toContain('BP-SEARCH-OTHER-002')
    }

    await searchInput.setValue('jp 5678')
    await wrapper.get('button[aria-label="清除搜索"]').trigger('click')
    await nextTick()

    expect(searchInput.element).toHaveProperty('value', '')
    expect(wrapper.get('[data-testid="molding-kpi-factory-orders-value"]').text()).toBe('2')
    expect(wrapper.text()).toContain('BP-SEARCH-OTHER-002')

    wrapper.unmount()
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
    expect(wrapper.findAll('button').some((button) => button.text().includes('工程部 · 新建开单'))).toBe(false)

    await getButtonByText(wrapper, 'BP-READONLY-HD-001').trigger('click')
    await nextTick()

    expect(wrapper.findAll('button').some((button) => button.text().includes('撤回审核'))).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text().trim() === '通过')).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text().trim() === '驳回')).toBe(false)

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
      mold_dimensions: '500 × 400 × 300 mm',
      mold_presence_status: 'in_factory',
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
      completion_time: '2026-07-11',
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
    expect(printArea).not.toContain('啤机确认机台')
    expect(printArea).not.toContain('啤办机台-08')
    expect(printArea).toContain('ABS 750NSW')
    expect(printArea).toContain('500 × 400 × 300 mm')
    expect(printArea).not.toContain('适配机型')
    expect(printArea).not.toContain('160T')
    expect(printArea).not.toContain('11.00 g')
    expect(printArea).toContain('模具是否在厂：在厂')
    expect(printArea).toContain('需办日期')
    expect(printArea).toContain('2026-07-11')
    expect(printArea).not.toContain('模具回厂时间')
    expect(printArea).not.toContain('REC-001')
    expect(printArea).toContain('1.42 kg')
    expect(printArea).toContain('预计料费')
    expect(printArea).toContain('HKD 16.04')
    expect(printArea).toContain('HKD 8.50')
    expect(printArea).not.toContain('RMB 120.00')
    expect(printArea).not.toContain('HKD 111.11')
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

  it('does not load another factory production queue from flat legacy permissions', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huadeng', order_id: 'BP-PROD-READONLY-HD-001' }
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

    expect(wrapper.text()).not.toContain('BP-PROD-READONLY-HD-001')
    expect(wrapper.text()).toContain('没有该厂区的啤办生产任务查看权限')
    expect(mockedMoldingSampleApi.listOrders).not.toHaveBeenCalled()
    expect(mockedMoldingSampleApi.listNotifications).not.toHaveBeenCalled()
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

  it('fuzzy searches the production queue across order, mold, client, and material fields', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing' }
    const searchableRecord = createKpiRecord('待生产', 'BP-PROD-SEARCH-001', null)
    Object.assign(searchableRecord.order, {
      doc_number: 'WG-026',
      product_name: 'Helmet Shell',
      client_name: 'ShuShuPaPa',
    })
    Object.assign(searchableRecord.items[0]!, {
      mold_id: 'JP-5678',
      mold_name: 'Head Mold Alpha',
      material: 'legacy material text',
      material_components: [
        { material: 'ABS PA-757', source_type: 'virgin', ratio_percent: 70 },
        { material: 'PVC 90度（本白,普通）', source_type: 'runner', ratio_percent: 30 },
      ],
    })
    const unrelatedRecord = createKpiRecord('生产中', 'BP-PROD-SEARCH-OTHER-002', null)
    unrelatedRecord.order.client_name = 'Another Client'
    unrelatedRecord.order.doc_number = 'DOC-OTHER-002'

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([searchableRecord, unrelatedRecord])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(searchableRecord.order.id, 1),
      createProductionTaskNotification(unrelatedRecord.order.id, 2),
    ])

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)
    const queue = wrapper.get('[aria-label="啤办生产任务队列"]')
    const searchInput = wrapper.get('[data-testid="production-task-search-input"]')

    for (const keyword of ['jp 5678', 'shushupapa pvc', 'ｗｇ ０２６']) {
      await searchInput.setValue(keyword)
      await nextTick()

      expect(queue.text()).toContain('BP-PROD-SEARCH-001')
      expect(queue.text()).not.toContain('BP-PROD-SEARCH-OTHER-002')
    }

    await wrapper.get('button[aria-label="清除生产任务搜索"]').trigger('click')
    await nextTick()

    expect(searchInput.element).toHaveProperty('value', '')
    expect(queue.text()).toContain('BP-PROD-SEARCH-OTHER-002')

    wrapper.unmount()
  })

  it('prints engineering molding-sample details without production fillback fields', async () => {
    const printSpy = vi.fn()
    vi.stubGlobal('print', printSpy)
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-PRINT-001' }
    const record = {
      ...createMoldingSampleRecord('待生产', 'BP-PROD-PRINT-001'),
      order: {
        ...createMoldingSampleRecord('待生产', 'BP-PROD-PRINT-001').order,
        doc_number: 'W-G026-00',
        product_name: '30寸黑武士',
      },
      items: [{
        ...createMoldingSampleRecord('待生产', 'BP-PROD-PRINT-001').items[0],
        production_machine: '啤办机台-08',
        mold_id: 'P50002008-01-01',
        mold_name: '30寸黑武士头盔',
        mold_dimensions: '650 × 450 × 380 mm',
        mold_presence_status: 'in_factory',
        material: 'legacy material text',
        material_components: [
          { material: 'ABS PA-757', source_type: 'virgin', ratio_percent: 70 },
          { material: 'PVC 90度（本白,普通）', source_type: 'runner', ratio_percent: 30 },
        ],
        material_usage_type: 'trial',
        color: '黑色',
        pigment_no: 'PMS Black',
        quantity: '1/1',
        shoot_qty: 30,
        required_material_kg: 15,
        mold_return_time: '2026-07-18',
        completion_time: '2026-07-22',
        notes: '工程首件确认',
        actual_weight_kg: 14.2,
      }],
    } satisfies MoldingSampleDetailResponse
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([record])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(record.order.id),
    ])

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)

    await getButtonByExactText(wrapper, '打印任务单').trigger('click')
    await nextTick()

    const preview = wrapper.get('[data-testid="molding-sample-task-print-preview"]').text()
    const printArea = wrapper.get('[data-testid="molding-sample-task-print-area"]').text()
    expect(printSpy).not.toHaveBeenCalled()
    expect(preview).toContain('BP-PROD-PRINT-001')
    expect(preview).toContain('70%ABS PA-757 + 30%PVC 90度（本白,普通）水口料')
    expect(preview).toContain('试料 · 不计结余')
    expect(printArea).toContain('70%ABS PA-757 + 30%PVC 90度（本白,普通）水口料')
    expect(printArea).not.toContain('legacy material text')
    expect(printArea).toContain('试料 · 不计结余')
    expect(printArea).toContain('650 × 450 × 380 mm')
    expect(printArea).toContain('在厂')
    expect(printArea).toContain('2026-07-18')
    expect(printArea).toContain('黑色 / PMS Black')
    expect(printArea).toContain('1/1 · 30 啤')
    expect(printArea).toContain('15.00 kg')
    expect(printArea).toContain('工程首件确认')
    expect(printArea).not.toContain('工程审核通过后下发至啤机部执行；打印内容仅包含工程部填写资料。')
    expect(printArea).toContain('工程部下发 · 啤机部执行')
    expect(printArea).not.toContain('14.20 kg')
    expect(printArea).not.toContain('啤机接收')
    expect(preview).not.toContain('文件编号')
    expect(preview).not.toContain('W-G026-00')
    expect(preview).not.toContain('啤机确认机台')
    expect(preview).not.toContain('啤办机台-08')

    vi.useFakeTimers()
    await getButtonByExactText(wrapper, '确认打印').trigger('click')
    expect(printSpy).toHaveBeenCalledTimes(1)
    expect(document.body.classList.contains('molding-sample-task-printing')).toBe(true)
    expect(document.getElementById('molding-sample-active-print-page')).not.toBeNull()
    vi.runAllTimers()
    expect(document.body.classList.contains('molding-sample-task-printing')).toBe(false)
    expect(document.getElementById('molding-sample-active-print-page')).toBeNull()
    vi.useRealTimers()

    wrapper.unmount()
  })

  it('expands the production task page to show the full molding sample order data', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-FULL-001' }
    const detailedRecord = {
      ...createMoldingSampleRecord('生产中', 'BP-PROD-FULL-001'),
      order: {
        ...createMoldingSampleRecord('生产中', 'BP-PROD-FULL-001').order,
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
          mold_dimensions: '650 × 450 × 380 mm',
          mold_presence_status: 'in_factory',
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
        ...Array.from({ length: 5 }, (_, index) => {
          const sortOrder = index + 2

          return {
            ...createMoldingSampleRecord('生产中', 'BP-PROD-FULL-001').items[0],
            id: `BP-PROD-FULL-001-00${sortOrder}`,
            order_id: 'BP-PROD-FULL-001',
            sort_order: sortOrder,
            mold_id: `P50002008-01-0${sortOrder}`,
            mold_name: sortOrder === 6 ? '最后一套护面罩' : `护面罩 ${sortOrder}`,
            material: 'ABS (PA-757)',
            required_material_kg: 6 + sortOrder,
            actual_weight_kg: null,
            notes: sortOrder === 6 ? '第六套模具完整资料。' : `第 ${sortOrder} 套模具资料。`,
          }
        }),
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
    expect(wrapper.findAll('[data-testid="production-fillback-item"]')).toHaveLength(6)
    const actualWeightInputs = wrapper.findAll('[data-testid="production-actual-weight-input"]')
    expect(actualWeightInputs).toHaveLength(6)
    expect(wrapper.findAll('[data-testid="production-fillback-expected-cost-panel"]')).toHaveLength(6)
    expect(wrapper.findAll('[data-testid="production-fillback-actual-cost-panel"]')).toHaveLength(6)
    const fillbackScroll = wrapper.get('.production-fillback-scroll')
    const fillbackSummary = wrapper.get('[data-testid="production-fillback-summary"]')
    expect(fillbackScroll.element.contains(fillbackSummary.element)).toBe(false)
    Object.defineProperties(fillbackScroll.element, {
      clientHeight: { configurable: true, value: 300 },
      scrollHeight: { configurable: true, value: 700 },
      scrollTop: { configurable: true, value: 400, writable: true },
    })
    const productionScrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {})
    await fillbackScroll.trigger('wheel', { deltaMode: 0, deltaY: 120 })
    expect(productionScrollBy).toHaveBeenCalledWith({ behavior: 'auto', top: 120 })
    productionScrollBy.mockClear()
    fillbackScroll.element.dispatchEvent(new WheelEvent('wheel', {
      bubbles: true,
      cancelable: true,
      ctrlKey: true,
      deltaMode: 0,
      deltaY: 120,
    }))
    await nextTick()
    expect(productionScrollBy).not.toHaveBeenCalled()
    productionScrollBy.mockRestore()
    await actualWeightInputs[0].setValue('12.34')

    await getButtonByText(wrapper, '展开完整数据').trigger('click')
    await nextTick()

    expect(wrapper.findAll('[data-testid="production-full-item-card"]')).toHaveLength(1)
    const indexButtons = wrapper.findAll('[data-testid="production-full-item-index-button"]')
    expect(indexButtons).toHaveLength(6)
    expect(indexButtons[0].attributes('aria-pressed')).toBe('true')

    let fullItemCard = wrapper.get('[data-testid="production-full-item-card"]')
    expect(fullItemCard.text()).toContain('P50002008-01-01')
    expect(fullItemCard.get('[data-testid="production-full-item-material-section"]').text()).toContain('原料与颜色')
    expect(fullItemCard.get('[data-testid="production-full-item-timing-section"]').text()).toContain('生产数量与时点')
    expect(fullItemCard.get('[data-testid="production-full-item-usage-section"]').text()).toContain('实际用量')
    expect(fullItemCard.get('[data-testid="production-full-item-cost-grid"]').text()).toContain('预计料费(HKD)')
    expect(fullItemCard.get('[data-testid="production-full-item-cost-grid"]').text()).toContain('实际料费(HKD)')

    const fullItemPane = wrapper.get('.production-full-item-pane')
    fullItemPane.element.scrollTop = 180
    await indexButtons[5].trigger('click')
    await nextTick()
    expect(fullItemPane.element.scrollTop).toBe(0)
    fullItemCard = wrapper.get('[data-testid="production-full-item-card"]')
    expect(fullItemCard.text()).toContain('P50002008-01-06')
    expect(fullItemCard.text()).toContain('第六套模具完整资料。')
    expect(wrapper.findAll('[data-testid="production-full-item-card"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="production-actual-weight-input"]')).toHaveLength(6)
    await indexButtons[0].trigger('click')
    await nextTick()
    expect((wrapper.findAll('[data-testid="production-actual-weight-input"]')[0].element as HTMLInputElement).value).toBe('12.34')

    const text = wrapper.text()
    expect(text).toContain('完整单据数据')
    expect(text).toContain('产品编号')
    expect(text).toContain('P50002008')
    expect(text).not.toContain('文件编号')
    expect(text).not.toContain('W-G026-00')
    expect(text).not.toContain('整啤毛重(g)')
    expect(text).not.toContain('82.00 g')
    expect(text).toContain('PMS 黑色')
    expect(text).not.toContain('160T')
    expect(text).not.toContain('RC-20260203-01')
    expect(text).not.toContain('啤机确认机台')
    expect(text).not.toContain('啤办机台-08')
    expect(text).toContain('啤机回填前核对完整资料。')

    wrapper.unmount()
  })

  it('saves actual material from the production fillback page without a production-machine field', async () => {
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
          mold_dimensions: '650 × 450 × 380 mm',
          mold_presence_status: 'in_factory',
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
        },
      ],
    } satisfies MoldingSampleDetailResponse

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([runningRecord])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(runningRecord.order.id),
    ])
    mockedMoldingSampleApi.updateItems.mockResolvedValueOnce(updatedRecord)

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)

    await wrapper.get('[data-testid="production-actual-weight-input"]').setValue('14.2')
    expect(wrapper.find('input[aria-label="啤办费"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="啤机确认机台"]').exists()).toBe(false)
    await getButtonByText(wrapper, '保存回填').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.updateItems).toHaveBeenCalledWith('BP-PROD-MACHINE-001', {
      items: [
        {
          id: 'BP-PROD-MACHINE-001-001',
          actual_weight_kg: 14.2,
        },
      ],
    })
    expect(wrapper.text()).not.toContain('啤机确认机台')
    expect(wrapper.text()).toContain('实际料费(HKD)')
    expect(wrapper.text()).not.toContain('啤办费(RMB)')
    expect(wrapper.text()).not.toContain('啤办费(HKD)')
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
          mold_dimensions: '650 × 450 × 380 mm',
          mold_presence_status: 'in_factory',
          production_machine: '啤办机台-08',
          material: '70%ABS PA-757 + 配比待确认',
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

    const detailTable = wrapper.get('[data-testid="molding-sample-detail-table"]')
    expect(detailTable.classes()).toContain('min-w-[920px]')
    expect(detailTable.findAll('[data-testid="molding-sample-detail-row"]')).toHaveLength(1)
    expect(detailTable.findAll('thead th')).toHaveLength(5)
    expect(detailTable.text()).toContain('模具资料')
    expect(detailTable.text()).toContain('原料 / 颜色')
    expect(detailTable.text()).toContain('70%ABS PA-757 + 配比待确认')
    expect(detailTable.text()).toContain('预计用料 / 料费')
    expect(detailTable.text()).toContain('实际用料 / 料费')
    expect(detailTable.find('[data-testid="expected-material-cost-panel"]').exists()).toBe(true)
    expect(detailTable.find('[data-testid="actual-material-cost-panel"]').exists()).toBe(true)
    expect(detailTable.text()).toContain('工模尺寸')
    expect(detailTable.text()).toContain('650 × 450 × 380 mm')
    expect(detailTable.text()).not.toContain('适配机型')
    expect(detailTable.text()).not.toContain('160T')
    expect(detailTable.text()).toContain('模具在厂')
    expect(detailTable.text()).toContain('在厂')
    expect(detailTable.text()).toContain('需办日期')
    expect(detailTable.text()).toContain('2026-02-04')
    expect(detailTable.text()).not.toContain('回厂时间')
    expect(detailTable.text()).toContain('分项按当前原料价估算')
    expect(detailTable.text()).toContain('合计 HKD 98.76')
    expect(wrapper.text()).not.toContain('完整单据数据')
    expect(wrapper.text()).not.toContain('整啤毛重(g)')
    expect(wrapper.text()).not.toContain('RC-20260203-01')

    await getButtonByText(wrapper, '展开完整数据').trigger('click')
    await nextTick()

    const fullItemCard = wrapper.get('[data-testid="molding-full-item-card"]')
    expect(fullItemCard.get('[data-testid="molding-full-item-metadata-section"]').text()).toContain('模具资料')
    expect(fullItemCard.get('[data-testid="molding-full-item-material-section"]').text()).toContain('原料与颜色')
    expect(fullItemCard.get('[data-testid="molding-full-item-usage-section"]').text()).toContain('用量概览')
    expect(fullItemCard.get('[data-testid="molding-full-item-cost-grid"]').text()).toContain('预计料费(HKD)')
    expect(fullItemCard.get('[data-testid="molding-full-item-cost-grid"]').text()).toContain('实际料费(HKD)')

    const text = wrapper.text()
    expect(text).toContain('完整单据数据')
    expect(text).toContain('产品编号')
    expect(text).toContain('P50002008')
    expect(text).not.toContain('文件编号')
    expect(text).not.toContain('W-G026-00')
    expect(text).not.toContain('整啤毛重(g)')
    expect(text).not.toContain('82.00 g')
    expect(text).toContain('PMS 黑色')
    expect(text).toContain('650 × 450 × 380 mm')
    expect(text).not.toContain('160T')
    expect(text).toContain('在厂')
    expect(text).toContain('需办日期')
    expect(text).toContain('2026-02-04')
    expect(text).not.toContain('模具回厂时间')
    expect(text).not.toContain('RC-20260203-01')
    expect(text).toContain('实际料费(HKD)')
    expect(text).not.toContain('啤机确认机台')
    expect(text).not.toContain('啤办机台-08')
    expect(text).toContain('确认披锋与缩水。')
    expect(text).not.toContain('啤办费(RMB)')
    expect(text).not.toContain('啤办费(HKD)')
    expect(text).not.toContain('当前汇率(RMB→HKD)')

    wrapper.unmount()
  })

  it('keeps multi-mold engineering details in a bounded master-detail workspace', async () => {
    const createDenseRecord = (id: string, prefix: string, itemCount: number) => {
      const record = createMoldingSampleRecord('待审核', id)
      record.order.order_number = `${prefix}-PRODUCT`
      record.order.product_name = `${prefix} 多模具产品`
      record.items = Array.from({ length: itemCount }, (_, index) => ({
        id: `${id}-${index + 1}`,
        order_id: id,
        sort_order: index + 1,
        mold_id: `${prefix}-MOLD-${index + 1}`,
        mold_name: `${prefix} 模具 ${index + 1}`,
        mold_dimensions: `${600 + index} × 450 × 380 mm`,
        mold_presence_status: 'in_factory' as const,
        machine_type: '',
        production_machine: '',
        material: `${100 - index}%ABS 750NSW`,
        material_components: [{ material: 'ABS 750NSW', source_type: 'virgin' as const, ratio_percent: 100 }],
        material_usage_type: 'production' as const,
        color: `颜色 ${index + 1}`,
        pigment_no: `PMS ${index + 1}`,
        quantity: '1/1',
        shoot_qty: 30 + index,
        gross_weight_g: null,
        required_material_kg: 10 + index,
        mold_return_time: '',
        completion_time: `2026-08-${String(index + 1).padStart(2, '0')}`,
        notes: `${prefix} 第 ${index + 1} 项备注`,
        receipt_no: '',
        collected_weight_kg: 9 + index,
        actual_weight_kg: 8 + index,
        actual_amount_hkd: 40 + index,
        injection_cost: null,
        injection_cost_hkd: null,
        exchange_rate_at_save: null,
      }))
      return record
    }

    const firstRecord = createDenseRecord('BP-DENSE-A', 'A', 6)
    const secondRecord = createDenseRecord('BP-DENSE-B', 'B', 2)
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([firstRecord, secondRecord])

    const wrapper = await mountRuntimeView(MoldingSampleView)
    await getButtonByText(wrapper, firstRecord.order.id).trigger('click')
    await nextTick()

    const summaryRegion = wrapper.get('[data-testid="molding-sample-detail-scroll-region"]')
    expect(summaryRegion.attributes('role')).toBe('region')
    expect(summaryRegion.attributes('tabindex')).toBe('0')
    expect(summaryRegion.attributes('aria-label')).toContain('6 项')
    expect(summaryRegion.classes()).toContain('md:max-h-[min(62vh,640px)]')
    expect(summaryRegion.findAll('[data-testid="molding-sample-detail-row"]')).toHaveLength(6)
    Object.defineProperties(summaryRegion.element, {
      clientHeight: { configurable: true, value: 300 },
      scrollHeight: { configurable: true, value: 300 },
      scrollTop: { configurable: true, value: 0, writable: true },
    })
    const engineeringScrollBy = vi.spyOn(window, 'scrollBy').mockImplementation(() => {})
    await summaryRegion.trigger('wheel', { deltaMode: 0, deltaY: 100 })
    expect(engineeringScrollBy).toHaveBeenCalledWith({ behavior: 'auto', top: 100 })
    engineeringScrollBy.mockClear()
    await summaryRegion.trigger('wheel', { deltaMode: 0, deltaX: 140, deltaY: 40 })
    expect(engineeringScrollBy).not.toHaveBeenCalled()
    summaryRegion.element.dispatchEvent(new WheelEvent('wheel', {
      bubbles: true,
      cancelable: true,
      deltaMode: 0,
      deltaY: 100,
      shiftKey: true,
    }))
    await nextTick()
    expect(engineeringScrollBy).not.toHaveBeenCalled()
    engineeringScrollBy.mockRestore()

    const expandButton = getButtonByText(wrapper, '展开完整数据')
    expect(expandButton.attributes('aria-expanded')).toBe('false')
    await expandButton.trigger('click')
    await nextTick()

    expect(getButtonByText(wrapper, '收起完整数据').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-testid="molding-full-data-workspace"]').classes()).toContain('lg:h-[min(70vh,680px)]')
    expect(wrapper.get('[data-testid="molding-full-item-index"]').classes()).toEqual(expect.arrayContaining([
      'overflow-x-auto',
      'lg:overflow-y-auto',
    ]))
    const selectors = wrapper.findAll('[data-testid="molding-full-item-selector"]')
    expect(selectors).toHaveLength(6)
    expect(selectors[0]?.attributes('aria-pressed')).toBe('true')
    expect(wrapper.findAll('[data-testid="molding-full-item-card"]')).toHaveLength(1)
    expect(wrapper.get('[data-testid="molding-full-item-card"]').text()).toContain('A-MOLD-1')
    expect(wrapper.get('[data-testid="molding-full-item-card"]').text()).not.toContain('A-MOLD-6')

    const detailPane = wrapper.get('[data-testid="molding-full-item-detail-pane"]')
    detailPane.element.scrollTop = 160
    await selectors[5]!.trigger('click')
    await nextTick()

    expect(wrapper.findAll('[data-testid="molding-full-item-selector"]')[5]?.attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-testid="molding-full-item-card"]').text()).toContain('A-MOLD-6')
    expect(wrapper.get('[data-testid="molding-full-item-card"]').text()).not.toContain('A-MOLD-1')
    expect((wrapper.get('[data-testid="molding-full-item-detail-pane"]').element as HTMLElement).scrollTop).toBe(0)

    await getButtonByText(wrapper, '返回看板').trigger('click')
    await nextTick()
    await getButtonByText(wrapper, secondRecord.order.id).trigger('click')
    await nextTick()
    expect(wrapper.find('[data-testid="molding-full-data-workspace"]').exists()).toBe(false)
    await getButtonByText(wrapper, '展开完整数据').trigger('click')
    await nextTick()

    const nextSelectors = wrapper.findAll('[data-testid="molding-full-item-selector"]')
    expect(nextSelectors).toHaveLength(2)
    expect(nextSelectors[0]?.attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-testid="molding-full-item-card"]').text()).toContain('B-MOLD-1')

    wrapper.unmount()
  })

  it('shows persisted actual material cost components for a completed production task', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-SNAPSHOT-001' }
    const completedRecord = createKpiRecord('已完成', 'BP-PROD-SNAPSHOT-001', 10)
    completedRecord.order.completed_date = '2026-07-12'
    completedRecord.items[0] = {
      ...completedRecord.items[0],
      material: '80%ABS 750NSW + 20%ABS 750NSW水口料',
      material_components: [
        { material: 'ABS 750NSW', source_type: 'virgin', ratio_percent: 80 },
        { material: 'ABS 750NSW', source_type: 'runner', ratio_percent: 20 },
      ],
      actual_amount_hkd: 70,
      actual_material_cost_components: [
        { material: 'ABS 750NSW', source_type: 'virgin', ratio_percent: 80, weight_kg: 8, unit_price: 3, amount_hkd: 60 },
        { material: 'ABS 750NSW', source_type: 'runner', ratio_percent: 20, weight_kg: 2, unit_price: 3, amount_hkd: 10 },
      ],
    }

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([completedRecord])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(completedRecord.order.id),
    ])

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)
    const actualCostSource = wrapper.get('[data-testid="production-actual-material-cost-source"]')
    const actualCostPanelText = actualCostSource.element.closest('[data-testid="production-fillback-actual-cost-panel"]')?.textContent ?? ''

    expect(actualCostSource.text()).toContain('实际结算快照')
    expect(actualCostPanelText).toContain('$ 60.00')
    expect(actualCostPanelText).toContain('$ 10.00')
    expect(actualCostPanelText).toContain('实际合计')
    expect(wrapper.get('[data-testid="production-fillback-actual-total"]').text()).toBe('$ 70.00')
    expect(actualCostPanelText).not.toContain('按当前原料价估算')

    wrapper.unmount()
  })

  it('recalculates the row breakdown while actual weight is edited without labeling the preview as settled', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-SNAPSHOT-PREVIEW-001' }
    const runningRecord = createKpiRecord('生产中', 'BP-PROD-SNAPSHOT-PREVIEW-001', 10)
    runningRecord.items[0] = {
      ...runningRecord.items[0],
      material: '80%ABS 750NSW + 20%ABS 750NSW水口料',
      material_components: [
        { material: 'ABS 750NSW', source_type: 'virgin', ratio_percent: 80 },
        { material: 'ABS 750NSW', source_type: 'runner', ratio_percent: 20 },
      ],
      actual_amount_hkd: 70,
      actual_material_cost_components: [
        { material: 'ABS 750NSW', source_type: 'virgin', ratio_percent: 80, weight_kg: 8, unit_price: 3, amount_hkd: 60 },
        { material: 'ABS 750NSW', source_type: 'runner', ratio_percent: 20, weight_kg: 2, unit_price: 3, amount_hkd: 10 },
      ],
    }

    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([runningRecord])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(runningRecord.order.id),
    ])

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)
    await wrapper.get('[data-testid="production-actual-weight-input"]').setValue('20')
    await nextTick()

    const actualCostSource = wrapper.get('[data-testid="production-actual-material-cost-source"]')
    const actualCostPanelText = actualCostSource.element.closest('[data-testid="production-fillback-actual-cost-panel"]')?.textContent ?? ''
    const reportTotalText = wrapper.get('[data-testid="production-fillback-summary"]').text()

    expect(actualCostSource.text()).toContain('按本次实际用料预览，保存后结算')
    expect(actualCostSource.text()).not.toContain('实际结算快照')
    expect(actualCostPanelText).toContain('16.00 kg')
    expect(actualCostPanelText).toContain('4.00 kg')
    expect(actualCostPanelText).toContain('$ 171.08')
    expect(actualCostPanelText).toContain('$ 42.77')
    expect(actualCostPanelText).toContain('实际合计')
    expect(wrapper.get('[data-testid="production-fillback-actual-total"]').text()).toBe('$ 213.85')
    expect(reportTotalText).toContain('$ 213.85')
    expect(reportTotalText).toContain('全部模具已回填实际用料')

    wrapper.unmount()
  })

  it('shows local production tasks without notification access and keeps every write disabled', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-READONLY-001' }
    const record = createMoldingSampleRecord('待生产', 'BP-PROD-READONLY-001')
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([record])

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView, {
      roles: ['啤机任务只读'],
      permissions: ['molding_sample:production_read'],
      factoryScopes: ['huaxing'],
      department: 'production',
      authzMode: 'enforce',
      primaryFactoryId: 'huaxing',
      effectiveAccess: [{
        permission_code: 'molding_sample:production_read',
        factory_id: 'huaxing',
        department: 'production',
        effect: 'allow',
        allowed: true,
        source_type: 'role_binding',
        source_ids: ['production-readonly-binding'],
      }],
    })

    expect(wrapper.text()).toContain('BP-PROD-READONLY-001')
    expect(wrapper.text()).toContain('当前账号没有通知处理权限')
    expect(mockedMoldingSampleApi.listNotifications).not.toHaveBeenCalled()
    expect(getButtonByText(wrapper, '开始生产').attributes('disabled')).toBeDefined()
    expect(getButtonByText(wrapper, '保存回填').attributes('disabled')).toBeDefined()
    expect(mockedMoldingSampleApi.updateStatus).not.toHaveBeenCalled()
    expect(mockedMoldingSampleApi.updateItems).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  it('keeps the production queue usable when protected material prices are forbidden', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-NO-COST-001' }
    const record = createMoldingSampleRecord('待生产', 'BP-PROD-NO-COST-001')
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([record])
    mockedMoldingSampleApi.listNotifications.mockResolvedValueOnce([
      createProductionTaskNotification(record.order.id),
    ])
    mockedMoldingSampleApi.getMaterialPrices.mockRejectedValueOnce(createRuntimeError(403))

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView)

    expect(mockedMoldingSampleApi.getMaterialPrices).toHaveBeenCalledWith('huaxing')
    expect(wrapper.text()).toContain('BP-PROD-NO-COST-001')
    expect(wrapper.text()).not.toContain('真实任务读取失败')

    wrapper.unmount()
  })

  it('honors a local override-only production start permission without unlocking other actions', async () => {
    routeState.path = '/modules/production/molding-sample-tasks'
    routeState.query = { factory: 'huaxing', order_id: 'BP-PROD-OVERRIDE-001' }
    const pendingRecord = createMoldingSampleRecord('待生产', 'BP-PROD-OVERRIDE-001')
    const runningRecord = {
      ...pendingRecord,
      order: { ...pendingRecord.order, status: '生产中' },
    } satisfies MoldingSampleDetailResponse
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([pendingRecord])
    mockedMoldingSampleApi.updateStatus.mockResolvedValueOnce(runningRecord)

    const wrapper = await mountRuntimeView(MoldingSampleProductionTaskView, {
      roles: ['基础员工'],
      permissions: ['molding_sample:production_read', 'molding_sample:production_start'],
      grantPermissions: [],
      factoryScopes: ['huaxing'],
      department: 'production',
      authzMode: 'enforce',
      primaryFactoryId: 'huaxing',
      effectiveAccess: [
        {
          permission_code: 'molding_sample:production_read',
          factory_id: 'huaxing',
          department: 'production',
          effect: 'allow',
          allowed: true,
          source_type: 'user_override',
          source_ids: ['override-read'],
        },
        {
          permission_code: 'molding_sample:production_start',
          factory_id: 'huaxing',
          department: 'production',
          effect: 'allow',
          allowed: true,
          source_type: 'user_override',
          source_ids: ['override-start'],
        },
      ],
    })

    expect(getButtonByText(wrapper, '开始生产').attributes('disabled')).toBeUndefined()
    expect(getButtonByText(wrapper, '保存回填').attributes('disabled')).toBeDefined()
    await getButtonByText(wrapper, '开始生产').trigger('click')
    await flushPromises()

    expect(mockedMoldingSampleApi.updateStatus).toHaveBeenCalledWith('BP-PROD-OVERRIDE-001', {
      action: '开始处理',
      reason: '啤办生产任务单接收后开始执行。',
      today: '2026-07-03',
    })
    expect(mockedMoldingSampleApi.updateItems).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  it('renders cross-factory access as read-only and omits cost content by default', async () => {
    routeState.query = { factory: 'huadeng' }
    const crossFactoryRecord = createKpiRecord('待审核', 'BP-CROSS-READONLY-HD-001', 1.25)
    crossFactoryRecord.order.factory_id = 'huadeng'
    crossFactoryRecord.items[0]!.actual_amount_hkd = 98.76
    crossFactoryRecord.items[0]!.injection_cost = 120
    crossFactoryRecord.items[0]!.injection_cost_hkd = 129.6
    crossFactoryRecord.items[0]!.exchange_rate_at_save = 1.08
    Object.assign(crossFactoryRecord, {
      read_source: 'cross',
      can_view_cost: false,
      read_only: true,
    })
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([crossFactoryRecord])

    const wrapper = await mountRuntimeView(MoldingSampleView, {
      roles: ['集团啤办只读'],
      permissions: ['molding_sample:cross_factory_read'],
      factoryScopes: ['*'],
      displayName: '集团啤办访客',
    })

    expect(wrapper.text()).toContain('跨厂只读')
    expect(wrapper.text()).toContain('成本信息已隐藏')
    for (const hiddenAction of ['工程部 · 新建开单', '打印', '导入Excel', '导出Excel']) {
      expect(wrapper.findAll('button').some((button) => button.text().includes(hiddenAction))).toBe(false)
    }

    await getButtonByText(wrapper, '物料结余').trigger('click')
    await nextTick()
    expect(wrapper.text()).not.toContain('结余金额')
    expect(wrapper.text()).not.toContain('折算状态')

    await getButtonByText(wrapper, '看板总览').trigger('click')
    await getButtonByText(wrapper, 'BP-CROSS-READONLY-HD-001').trigger('click')
    await nextTick()

    for (const hiddenAction of ['撤回审核', '删除啤办单', '通过', '驳回']) {
      expect(wrapper.findAll('button').some((button) => button.text().trim() === hiddenAction)).toBe(false)
    }
    expect(wrapper.text()).not.toContain('预计料费')
    expect(wrapper.text()).not.toContain('实际料费')
    expect(wrapper.text()).not.toContain('HKD 98.76')

    await getButtonByText(wrapper, '展开完整数据').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-testid="molding-full-item-cost-grid"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('does not expose printing to a local reader without export permission', async () => {
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([
      createMoldingSampleRecord('待审核', 'BP-LOCAL-NO-EXPORT-001'),
    ])

    const wrapper = await mountRuntimeView(MoldingSampleView, {
      roles: ['工程只读'],
      permissions: ['molding_sample:read'],
      factoryScopes: ['huaxing'],
    })

    expect(wrapper.text()).toContain('BP-LOCAL-NO-EXPORT-001')
    expect(wrapper.findAll('button').some((button) => button.text().trim() === '打印')).toBe(false)

    wrapper.unmount()
  })

  it('honors a local override-only create permission and blocks the same override outside the primary factory', async () => {
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([])
    const access: AuthEffectiveAccess[] = [
      {
        permission_code: 'molding_sample:create',
        factory_id: 'huaxing',
        department: 'engineering',
        effect: 'allow',
        allowed: true,
        source_type: 'user_override',
        source_ids: ['override-create-local'],
      },
      {
        permission_code: 'molding_sample:create',
        factory_id: 'huadeng',
        department: 'engineering',
        effect: 'allow',
        allowed: true,
        source_type: 'user_override',
        source_ids: ['override-create-misconfigured'],
      },
    ]

    const localWrapper = await mountRuntimeView(MoldingSampleView, {
      roles: ['基础员工'],
      permissions: ['molding_sample:create'],
      grantPermissions: [],
      factoryScopes: ['huaxing'],
      department: 'engineering',
      authzMode: 'enforce',
      primaryFactoryId: 'huaxing',
      effectiveAccess: access,
    })

    expect(localWrapper.findAll('button').some((button) => button.text().includes('工程部 · 新建开单'))).toBe(true)
    expect(localWrapper.findAll('button').some((button) => button.text().trim() === '新建啤办单')).toBe(true)
    localWrapper.unmount()

    routeState.query = { factory: 'huadeng' }
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([])
    const externalWrapper = await mountRuntimeView(MoldingSampleView, {
      roles: ['基础员工'],
      permissions: ['molding_sample:create'],
      grantPermissions: [],
      factoryScopes: ['huaxing'],
      department: 'engineering',
      authzMode: 'enforce',
      primaryFactoryId: 'huaxing',
      effectiveAccess: access,
    })

    expect(externalWrapper.findAll('button').some((button) => button.text().includes('工程部 · 新建开单'))).toBe(false)
    expect(externalWrapper.findAll('button').some((button) => button.text().trim() === '新建啤办单')).toBe(false)
    externalWrapper.unmount()
  })

  it('recognizes QA-scoped cross-factory cost overrides without treating QA as a molding department', async () => {
    routeState.query = { factory: 'huadeng' }
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([])

    const wrapper = await mountRuntimeView(MoldingSampleView, {
      roles: ['品质部跨厂访客'],
      permissions: [
        'molding_sample:cross_factory_read',
        'molding_sample:cross_factory_cost_read',
      ],
      grantPermissions: [],
      factoryScopes: ['huaxing'],
      department: 'qa',
      authzMode: 'enforce',
      primaryFactoryId: 'huaxing',
      effectiveAccess: [
        {
          permission_code: 'molding_sample:cross_factory_read',
          factory_id: 'huadeng',
          department: 'qa',
          effect: 'allow',
          allowed: true,
          source_type: 'user_override',
          source_ids: ['qa-cross-read'],
        },
        {
          permission_code: 'molding_sample:cross_factory_cost_read',
          factory_id: 'huadeng',
          department: 'qa',
          effect: 'allow',
          allowed: true,
          source_type: 'user_override',
          source_ids: ['qa-cross-cost'],
        },
      ],
    })

    expect(wrapper.text()).toContain('华登暂无正式啤办单')
    await getButtonByText(wrapper, '物料结余').trigger('click')
    await nextTick()
    expect(wrapper.text()).toContain('结余金额')
    expect(wrapper.text()).toContain('折算状态')

    wrapper.unmount()
  })

  it('lets a manager approve through a management-scoped permission', async () => {
    const pendingManagerRecord = createMoldingSampleRecord('待经理审核', 'BP-MANAGER-SCOPE-001')
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([pendingManagerRecord])

    const wrapper = await mountRuntimeView(MoldingSampleView, {
      roles: ['经理'],
      permissions: ['molding_sample:manager_review'],
      factoryScopes: ['huaxing'],
      department: 'management',
      authzMode: 'enforce',
      effectiveAccess: [{
        permission_code: 'molding_sample:manager_review',
        factory_id: 'huaxing',
        department: 'management',
        effect: 'allow',
        allowed: true,
        source_type: 'role',
        source_ids: ['manager-role'],
      }],
    })

    await getButtonByText(wrapper, 'BP-MANAGER-SCOPE-001').trigger('click')
    await nextTick()

    expect(getButtonByExactText(wrapper, '通过').attributes('disabled')).toBeUndefined()
    expect(getButtonByExactText(wrapper, '驳回').attributes('disabled')).toBeUndefined()

    wrapper.unmount()
  })

  it('shows cross-factory costs only when the backend grants cost visibility', async () => {
    routeState.query = { factory: 'huadeng' }
    const crossFactoryRecord = createKpiRecord('待审核', 'BP-CROSS-COST-HD-001', 1.25)
    crossFactoryRecord.order.factory_id = 'huadeng'
    crossFactoryRecord.items[0]!.actual_amount_hkd = 98.76
    Object.assign(crossFactoryRecord, {
      read_source: 'cross',
      can_view_cost: true,
      read_only: true,
    })
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([crossFactoryRecord])

    const wrapper = await mountRuntimeView(MoldingSampleView, {
      roles: ['集团啤办成本只读'],
      permissions: [
        'molding_sample:cross_factory_read',
        'molding_sample:cross_factory_cost_read',
      ],
      factoryScopes: ['*'],
    })

    expect(wrapper.text()).toContain('已额外授权查看成本')
    await getButtonByText(wrapper, 'BP-CROSS-COST-HD-001').trigger('click')
    await nextTick()
    expect(wrapper.text()).toContain('预计料费')
    expect(wrapper.text()).toContain('实际料费')
    expect(wrapper.text()).toContain('HKD 98.76')
    expect(wrapper.findAll('button').some((button) => button.text().includes('导出Excel'))).toBe(false)

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
    const lineHeaders = wrapper.findAll('[aria-label="模具明细录入表"] [role="columnheader"]').map((node) => node.text())
    expect(lineHeaders).not.toContain('适配机型')
    expect(lineHeaders).not.toContain('整啤毛重(g)')
    expect(lineHeaders.slice(-4)).toEqual(['模具状态（是否在厂）', '用料用途', '备注', '操作'])
    expect(wrapper.find('[data-testid="create-line-machine-type"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="create-line-gross-weight"]').exists()).toBe(false)
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
      gross_weight_g: null,
      machine_type: '',
      required_material_kg: 2.25,
    })
    expect(window.localStorage.getItem('rr:molding-sample:create-draft:huaxing')).toBeNull()
    expect(restoredWrapper.text()).toContain('新建成功')

    restoredWrapper.unmount()
  })

  it('rejects disabled and duplicate material components before saving a composition', async () => {
    const wrapper = await mountRuntimeView(MoldingSampleView)

    await getButtonByText(wrapper, '工程部 · 新建开单').trigger('click')
    const materialInput = wrapper.get('[data-testid="create-line-material"]')
    await materialInput.trigger('focus')
    await materialInput.setValue('ABS 750NSW')
    await materialInput.trigger('keydown.enter')
    await wrapper.get('[data-testid="create-line-material-composition-0"]').trigger('click')
    await wrapper.get('[data-testid="material-component-percentage-0"]').setValue('50')
    await getButtonByText(wrapper, '添加组分').trigger('click')
    await wrapper.get('[data-testid="material-component-name-1"]').setValue('停用 PVC')
    await wrapper.get('[data-testid="material-component-percentage-1"]').setValue('50')
    await wrapper.get('[data-testid="save-material-composition"]').trigger('click')

    expect(wrapper.get('[data-testid="material-composition-dialog"]').text()).toContain('不是已启用的原料')

    await wrapper.get('[data-testid="material-component-name-1"]').setValue(' abs 750nsw ')
    await wrapper.get('[data-testid="save-material-composition"]').trigger('click')

    expect(wrapper.get('[data-testid="material-composition-dialog"]').text()).toContain('原料 + 来源类型')

    await wrapper.get('[data-testid="material-component-source-1"]').setValue('runner')
    await wrapper.get('[data-testid="save-material-composition"]').trigger('click')

    expect(wrapper.find('[data-testid="material-composition-dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="create-line-material-price"]').text()).toContain('HKD 4.85')

    wrapper.unmount()
  })

  it('excludes trial material money from balance while retaining its weight', async () => {
    const record = createKpiRecord('已完成', 'BP-TRIAL-BALANCE-001', 8)
    record.items[0] = {
      ...record.items[0],
      required_material_kg: 10,
      actual_weight_kg: 8,
      actual_amount_hkd: 80,
      material_usage_type: 'production',
    }
    record.items.push({
      ...record.items[0],
      id: 'BP-TRIAL-BALANCE-001-ITEM-2',
      sort_order: 2,
      mold_id: 'M-TRIAL',
      required_material_kg: 5,
      actual_weight_kg: 4,
      actual_amount_hkd: null,
      material_usage_type: 'trial',
    })
    mockedMoldingSampleApi.listOrders.mockResolvedValueOnce([record])

    const wrapper = await mountRuntimeView(MoldingSampleView)
    await getButtonByText(wrapper, '物料结余').trigger('click')
    await nextTick()

    const summaryCards = wrapper.findAll('article')
    const expectedCard = summaryCards.find((card) => card.text().includes('预计用料'))
    const actualCard = summaryCards.find((card) => card.text().includes('实际用料'))
    const balanceCard = summaryCards.find((card) => card.text().includes('物料结余'))
    const amountCard = summaryCards.find((card) => card.text().includes('结余金额'))
    const periodTableText = wrapper.get('table[aria-label="物料周期结余"]').text()

    expect(expectedCard?.text()).toContain('15.00 kg')
    expect(actualCard?.text()).toContain('12.00 kg')
    expect(balanceCard?.text()).toContain('+3.00 kg')
    expect(amountCard?.text()).toContain('+HKD 20.00')
    expect(amountCard?.text()).toContain('1 项试料已排除金额')
    expect(periodTableText).toContain('1 项试料金额不计结余')
    expect(periodTableText).not.toContain('待计价')

    wrapper.unmount()
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
        supervisor: '华兴主管',
        eng_name: '杨敬作',
        reason: '工程部啤办通知单导入',
      },
      items: [
        {
          id: 'BP-XLSX-DRAFT-001-001',
          mold_id: 'P50002008-01-01',
          mold_name: '30寸黑武士-头盔',
          material: '70%ABS PA-757 + 30%PVC 90度（本白,普通）水口料',
          material_components: [
            { material: 'ABS PA-757', source_type: 'virgin', ratio_percent: 70 },
            { material: 'PVC 90度（本白,普通）', source_type: 'runner', ratio_percent: 30 },
          ],
          material_usage_type: 'trial',
          color: '黑色 / PMS 2487',
          pigment_no: '黑种-11',
          quantity: '5/10',
          shoot_qty: 10,
          required_material_kg: 15,
          mold_dimensions: '207*789',
          mold_presence_status: 'in_factory',
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
    expect(wrapper.find('[data-testid="create-order-id"]').exists()).toBe(false)
    expect((wrapper.get('[data-testid="create-product-no"]').element as HTMLInputElement).value).toBe('P50002008')
    expect((wrapper.get('[data-testid="create-product-name"]').element as HTMLInputElement).value).toBe('30寸黑武士')
    expect((wrapper.get('[data-testid="create-line-mold-id"]').element as HTMLInputElement).value).toBe('P50002008-01-01')
    expect((wrapper.get('[data-testid="create-line-color"]').element as HTMLInputElement).value).toBe('黑色')
    expect((wrapper.get('[data-testid="create-line-required-material"]').element as HTMLInputElement).value).toBe('15')
    expect((wrapper.get('[data-testid="create-line-mold-presence-status"]').element as HTMLSelectElement).value).toBe('in_factory')
    expect((wrapper.get('[data-testid="create-line-material-usage-type"]').element as HTMLSelectElement).value).toBe('trial')
    expect((wrapper.get('[data-testid="create-line-material"]').element as HTMLInputElement).value).toBe('70%ABS PA-757 + 30%PVC 90度（本白,普通）水口料')
    expect((wrapper.get('input[placeholder="PMS"]').element as HTMLInputElement).value).toBe('2487')

    await wrapper.get('[data-testid="create-line-material-composition-0"]').trigger('click')
    expect((wrapper.get('[data-testid="material-component-name-0"]').element as HTMLInputElement).value).toBe('ABS PA-757')
    expect((wrapper.get('[data-testid="material-component-percentage-0"]').element as HTMLInputElement).value).toBe('70')
    expect((wrapper.get('[data-testid="material-component-name-1"]').element as HTMLInputElement).value).toBe('PVC 90度（本白,普通）')
    expect((wrapper.get('[data-testid="material-component-source-1"]').element as HTMLSelectElement).value).toBe('runner')
    expect((wrapper.get('[data-testid="material-component-percentage-1"]').element as HTMLInputElement).value).toBe('30')
    await wrapper.get('button[aria-label="关闭原料配比弹窗"]').trigger('click')

    mockedMoldingSampleApi.createOrder.mockImplementationOnce(async (payload) => ({
      order: payload.order,
      items: payload.items,
      audit_logs: [],
      problems: [],
    }))

    await getButtonByText(wrapper, '提交主管审核').trigger('click')
    await flushPromises()
    await nextTick()

    expect(mockedMoldingSampleApi.createOrder).toHaveBeenCalledTimes(1)
    expect(mockedMoldingSampleApi.createOrder.mock.calls[0][0].order.doc_number).toBe('W-G026-00')
    expect(mockedMoldingSampleApi.createOrder.mock.calls[0][0].items[0]).toMatchObject({
      mold_id: 'P50002008-01-01',
      mold_name: '30寸黑武士-头盔',
      material: '70%ABS PA-757 + 30%PVC 90度（本白,普通）水口料',
      material_components: [
        { material: 'ABS PA-757', source_type: 'virgin', ratio_percent: 70 },
        { material: 'PVC 90度（本白,普通）', source_type: 'runner', ratio_percent: 30 },
      ],
      material_usage_type: 'trial',
      color: '黑色 / PMS 2487',
      pigment_no: '黑种-11',
      quantity: '5/10',
      shoot_qty: 10,
      required_material_kg: 15,
      mold_dimensions: '207*789',
      mold_presence_status: 'in_factory',
      completion_time: '2026-02-10',
    })

    wrapper.unmount()
  })
})

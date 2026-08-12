import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonProcurementView from '../CartonProcurementView.vue'

const routerReplaceMock = vi.hoisted(() => vi.fn())
const routeState = vi.hoisted(() => ({
  query: { factory: 'huaxing' } as Record<string, string>,
}))
const appStoreMock = vi.hoisted(() => ({
  activeProductionFactory: { id: 'huaxing', name: '华兴', shortName: '华兴' },
  setActiveFactory: vi.fn(),
}))
const authStoreMock = vi.hoisted(() => ({
  can: vi.fn(() => true),
}))
const cartonApiMock = vi.hoisted(() => ({
  listCustomers: vi.fn(),
  createCustomer: vi.fn(),
  updateCustomer: vi.fn(),
  deleteCustomer: vi.fn(),
  listOrders: vi.fn(),
  listMovements: vi.fn(),
  listInventoryBalances: vi.fn(),
  createInventoryMovement: vi.fn(),
  reverseInventoryMovement: vi.fn(),
  listClosings: vi.fn(),
  listExceptions: vi.fn(),
  createOrder: vi.fn(),
  updateOrder: vi.fn(),
  cancelOrder: vi.fn(),
  uploadHistoryOrders: vi.fn(),
  uploadHistoryInventory: vi.fn(),
  exportPurchaseOrder: vi.fn(),
  uploadReceipt: vi.fn(),
  latestReceiptImport: vi.fn(),
  listImports: vi.fn(),
  listReceipts: vi.fn(),
  uploadWeeklySchedule: vi.fn(),
  uploadInspectionSchedule: vi.fn(),
  createReceipt: vi.fn(),
  confirmReceipt: vi.fn(),
  generateClosings: vi.fn(),
  updateClosingStatus: vi.fn(),
  updateException: vi.fn(),
}))

vi.mock('@/api/cartonProcurement', () => ({
  cartonProcurementApi: cartonApiMock,
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

vi.mock('@/stores/app', () => ({
  useAppStore: () => appStoreMock,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => authStoreMock,
}))

function mountView(tab?: string) {
  routeState.query = tab
    ? { factory: 'huaxing', tab }
    : { factory: 'huaxing' }

  return mount(CartonProcurementView, {
    global: {
      stubs: {
        AccountMenu: true,
      },
    },
  })
}

function findButton(wrapper: ReturnType<typeof mountView>, label: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(label))
  if (!button) throw new Error(`Button not found: ${label}`)
  return button
}

function businessDateOffset(days: number) {
  const current = new Date(`${new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })}T00:00:00Z`)
  current.setUTCDate(current.getUTCDate() + days)
  return current.toISOString().slice(0, 10)
}

function orderFixture(orderNo: string, dueDate: string, status = 'CONFIRMED') {
  return {
    id: `ID-${orderNo}`,
    factory_id: 'huaxing',
    order_no: orderNo,
    customer_code: 'DICKIE',
    customer_name: 'Dickie',
    supplier_id: 'CSP-huaxing-HEYUAN-DONGKANG',
    supplier_name: '河源东康纸品有限公司',
    contract_no: `SC-${orderNo}`,
    item_no: `ITEM-${orderNo}`,
    product_name: '',
    product_order_quantity: '100',
    order_date: businessDateOffset(-7),
    due_date: dueDate,
    status,
    note: '',
    revision: 1,
    created_by: 'admin',
    created_by_name: '系统管理员',
    updated_by: 'admin',
    updated_by_name: '系统管理员',
    created_at: `${businessDateOffset(-7)}T10:00:00+08:00`,
    updated_at: `${businessDateOffset(-7)}T10:00:00+08:00`,
    lines: [{
      id: `LINE-${orderNo}`,
      line_no: 1,
      packaging_type: '外箱',
      paper_quality: 'A33+B',
      specification: '12*11*5',
      dimension_unit: 'in',
      usage_quantity: '1',
      required_quantity: '100',
      received_quantity: status === 'COMPLETED' ? '100' : '0',
      remaining_quantity: status === 'COMPLETED' ? '0' : '100',
      unit: '个',
      unit_price: '3.46',
      currency: 'HKD',
      price_source: 'manual',
      note: '',
    }],
  }
}

describe('CartonProcurementView frontend workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    appStoreMock.activeProductionFactory = { id: 'huaxing', name: '华兴', shortName: '华兴' }
    authStoreMock.can.mockReturnValue(true)
    cartonApiMock.listCustomers.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listOrders.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listMovements.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listImports.mockResolvedValue([])
    cartonApiMock.listReceipts.mockResolvedValue([])
    cartonApiMock.listClosings.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listExceptions.mockRejectedValue(new Error('offline test'))
    cartonApiMock.latestReceiptImport.mockResolvedValue(null)
    cartonApiMock.exportPurchaseOrder.mockResolvedValue(new Blob(['xlsx']))
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:carton-purchase-order'),
    })
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
    cartonApiMock.createOrder.mockImplementation(async (payload: any) => ({
      id: 'CTO-TEST',
      factory_id: payload.factory_id,
      order_no: 'CT-260805-ABC123',
      customer_code: payload.customer_code || 'CUST-AUTO',
      customer_name: payload.customer_name,
      supplier_id: 'CSP-huaxing-HEYUAN-DONGKANG',
      supplier_name: '河源东康纸品有限公司',
      contract_no: payload.contract_no,
      item_no: payload.item_no,
      product_name: '',
      product_order_quantity: String(payload.product_order_quantity),
      order_date: payload.order_date,
      due_date: payload.due_date,
      status: 'CONFIRMED',
      note: payload.note,
      revision: 1,
      created_by: 'user-test',
      created_by_name: '测试用户',
      updated_by: 'user-test',
      updated_by_name: '测试用户',
      created_at: '2026-08-05T10:00:00+08:00',
      updated_at: '2026-08-05T10:00:00+08:00',
      lines: payload.lines.map((line: any, index: number) => ({
        id: `CTL-${index + 1}`,
        line_no: index + 1,
        packaging_type: line.packaging_type,
        paper_quality: line.paper_quality,
        specification: line.specification,
        dimension_unit: line.dimension_unit,
        usage_quantity: String(line.usage_quantity),
        required_quantity: String(line.usage_quantity * payload.product_order_quantity),
        received_quantity: '0',
        remaining_quantity: String(line.usage_quantity * payload.product_order_quantity),
        unit: line.unit,
        unit_price: '0',
        currency: 'CNY',
        price_source: 'manual',
        note: '',
      })),
    }))
  })

  it('exposes the seven V2.1 work areas and clearly labels the offline fallback', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('纸箱采购协同看板')
    expect(wrapper.text()).toContain('纸箱订单管理')
    expect(wrapper.text()).toContain('每周核对与交期提醒')
    expect(wrapper.text()).toContain('收料反馈平台')
    expect(wrapper.text()).toContain('库存台账与交易流水')
    expect(wrapper.text()).toContain('库存月结与对账报表')
    expect(wrapper.text()).toContain('异常中心')
    expect(wrapper.text()).toContain('只读演示 · 后端不可用')
    expect(wrapper.text()).toContain('周排期核对漏单；下周查货合同倒推纸箱最迟交货日')

    await findButton(wrapper, '订单管理').trigger('click')
    expect(routerReplaceMock).toHaveBeenCalledWith({
      query: {
        factory: 'huaxing',
        tab: 'orders',
      },
    })
  })

  it('separates missing-order checks from advance delivery reminders', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.uploadInspectionSchedule.mockResolvedValue({
      id: 'CIB-INSPECTION-1',
      factory_id: 'huaxing',
      import_type: 'INSPECTION_SCHEDULE',
      import_profile: '{"advance_days":3}',
      original_filename: '下周查货合同.xlsx',
      source_sha256: 'hash',
      status: 'REQUIRES_REVIEW',
      duplicate: false,
      parse_summary: {
        row_count: 1,
        matched_count: 1,
        issue_count: 0,
        reminder_count: 1,
        overdue_count: 0,
        due_soon_count: 0,
        rows: [{
          source_sheet: '排期',
          source_row: 2,
          reference: 'SC700145365',
          po_numbers: 'PO-001',
          customer_name: 'Dickie',
          item_no: '203302044',
          product_name: '多文盒',
          quantity: 3600,
          inspection_window: '8月10日-8月13日',
          inspection_start_date: '2026-08-10',
          required_delivery_date: '2026-08-07',
          advance_days: 3,
          days_until_delivery: 2,
          reminder_status: 'UPCOMING',
          match_status: 'MATCHED',
          order_status: 'CONFIRMED',
          order_no: 'CT-260805-006',
          suggestion: '请在 2026-08-07 前完成纸箱交货，距最迟交货日 2 天',
        }],
      },
    })

    const wrapper = mountView('weekly-check')
    await flushPromises()

    expect(wrapper.text()).toContain('下单防漏核对')
    expect(wrapper.text()).toContain('下周查货提醒')
    expect(wrapper.text()).toContain('导入本周排期')

    await findButton(wrapper, '下周查货提醒').trigger('click')
    await wrapper.get('input[aria-label="提前交货天数"]').setValue('3')
    const input = wrapper.get('input[aria-label="选择下周查货合同文件"]')
    const file = new File(['xlsx'], '下周查货合同.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(cartonApiMock.uploadInspectionSchedule).toHaveBeenCalledWith('huaxing', file, 3)
    expect(wrapper.text()).toContain('最迟交货日')
    expect(wrapper.text()).toContain('2026-08-07')
    expect(wrapper.text()).toContain('待提前交货')
    expect(wrapper.text()).toContain('不会修改订单或库存')
  })

  it('highlights order due dates and sorts urgent open orders first', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([
      orderFixture('CT-FUTURE', businessDateOffset(8)),
      orderFixture('CT-COMPLETED', businessDateOffset(-5), 'COMPLETED'),
      orderFixture('CT-SOON', businessDateOffset(2)),
      orderFixture('CT-OVERDUE', businessDateOffset(-2)),
    ])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])

    const wrapper = mountView('orders')
    await flushPromises()

    const summary = wrapper.get('[aria-label="订单交期提醒汇总"]')
    expect(summary.text()).toContain('逾期 1')
    expect(summary.text()).toContain('今日 0')
    expect(summary.text()).toContain('未来 3 天 1')
    expect(wrapper.get('[data-order-no="CT-OVERDUE"]').text()).toContain('已逾期 2 天')
    expect(wrapper.get('[data-order-no="CT-SOON"]').text()).toContain('剩 2 天')
    expect(wrapper.get('[data-order-no="CT-FUTURE"]').text()).toContain('距交期 8 天')
    expect(wrapper.get('[data-order-no="CT-COMPLETED"]').text()).toContain('交付已完成')
    expect(wrapper.findAll('[data-order-no]').map((card) => card.attributes('data-order-no'))).toEqual([
      'CT-OVERDUE',
      'CT-SOON',
      'CT-FUTURE',
      'CT-COMPLETED',
    ])
  })

  it('groups multiple paper items under one contract and keeps paper quality separate from specification', async () => {
    const wrapper = mountView('orders')

    expect(wrapper.get('select[aria-label="客户筛选"]').element.parentElement)
      .toBe(findButton(wrapper, '客户资料维护').element.parentElement)

    expect(wrapper.text()).toContain('合同内纸品明细 · 4 行')
    expect(wrapper.text()).toContain('纸品类型')
    expect(wrapper.text()).toContain('纸质')
    expect(wrapper.text()).toContain('规格')
    expect(wrapper.text()).toContain('单件用量')
    expect(wrapper.text()).toContain('需求数量（自动）')
    expect(wrapper.text()).toContain('滑板纸')
    expect(wrapper.text()).toContain('卡纸')

    await findButton(wrapper, '新建纸箱订单').trigger('click')
    expect(wrapper.get('input[aria-label="纸箱供应商"]').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="合同号"]').setValue('SC-DEMO-001')
    await wrapper.get('input[aria-label="货号"]').setValue('203399999')
    await wrapper.get('input[aria-label="规格 1"]').setValue('30 × 20 × 15 cm')
    expect(wrapper.get('output[aria-label="需求数量 1"]').text()).toBe('30')
    await findButton(wrapper, '新增纸品明细').trigger('click')
    await wrapper.get('input[aria-label="纸质 2"]').setValue('A9A')
    await wrapper.get('input[aria-label="规格 2"]').setValue('29 × 19 cm')
    await wrapper.get('input[aria-label="单件用量 2"]').setValue('0.5')
    expect(wrapper.get('output[aria-label="需求数量 2"]').text()).toBe('1,800')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('SC-DEMO-001')
    expect(wrapper.text()).toContain('203399999')
    expect(wrapper.text()).toContain('合同内纸品明细 · 2 行')
    expect(wrapper.text()).toContain('A9A')
    expect(cartonApiMock.createOrder).toHaveBeenCalledWith(expect.objectContaining({ status: 'CONFIRMED' }))
    expect(wrapper.text()).toContain('已下单')
    expect(wrapper.text()).toContain('含 2 条纸品明细')
    expect(wrapper.text()).toContain('已自动进入排期核对、收料和库存后续流程')

    await wrapper.get('button[aria-label="导出 CT-260805-ABC123 采购单"]').trigger('click')
    await flushPromises()
    expect(cartonApiMock.exportPurchaseOrder).toHaveBeenCalledWith('huaxing', 'CT-260805-ABC123')
    expect(wrapper.text()).toContain('CT-260805-ABC123 采购单已生成并开始下载')
  })

  it('edits and cancels formal orders through reasoned revision controls', async () => {
    const order = orderFixture('CT-CONTROLLED', businessDateOffset(5))
    cartonApiMock.listCustomers.mockResolvedValue([{
      id: 'CUSTOMER-DICKIE',
      factory_id: 'huaxing',
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      country_region: '',
      contact_name: '',
      contact_phone: '',
      note: '',
      status: 'ACTIVE',
      revision: 1,
      created_by: 'admin',
      created_by_name: '系统管理员',
      updated_by: 'admin',
      updated_by_name: '系统管理员',
      created_at: '2026-08-05T10:00:00+08:00',
      updated_at: '2026-08-05T10:00:00+08:00',
    }])
    cartonApiMock.listOrders.mockResolvedValue([order])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.updateOrder.mockImplementation(async (current: any, payload: any) => ({
      ...current,
      contract_no: payload.contract_no,
      due_date: payload.due_date,
      note: payload.note,
      revision: current.revision + 1,
    }))
    cartonApiMock.cancelOrder.mockImplementation(async (_factoryId: string, current: any) => ({
      ...current,
      status: 'CANCELLED',
      revision: current.revision + 1,
    }))

    const wrapper = mountView('orders')
    await flushPromises()

    await wrapper.get('button[aria-label="修改 CT-CONTROLLED 订单"]').trigger('click')
    expect(wrapper.text()).toContain('修改纸箱合同订单 CT-CONTROLLED')
    await wrapper.get('input[aria-label="合同号"]').setValue('SC-CT-CONTROLLED-R1')
    await wrapper.get('input[aria-label="计划交期"]').setValue(businessDateOffset(7))
    await wrapper.get('textarea[aria-label="订单修改原因"]').setValue('客户确认交期及合同号修订')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(cartonApiMock.updateOrder).toHaveBeenCalledWith(
      expect.objectContaining({ order_no: 'CT-CONTROLLED', revision: 1 }),
      expect.objectContaining({
        contract_no: 'SC-CT-CONTROLLED-R1',
        reason: '客户确认交期及合同号修订',
      }),
    )
    expect(wrapper.text()).toContain('已按原因完成第 2 版修订')

    await wrapper.get('button[aria-label="取消 CT-CONTROLLED 订单"]').trigger('click')
    await wrapper.get('textarea[aria-label="订单取消原因"]').setValue('客户正式取消该合同')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(cartonApiMock.cancelOrder).toHaveBeenCalledWith(
      'huaxing',
      expect.objectContaining({ order_no: 'CT-CONTROLLED', revision: 2 }),
      '客户正式取消该合同',
    )
    expect(wrapper.text()).toContain('已取消，并保留审计记录')
    expect(wrapper.get('[data-order-no="CT-CONTROLLED"]').text()).toContain('已取消')
  })

  it('downloads the mapping template and imports grouped history orders', async () => {
    const importedOrder = {
      id: 'CTO-HISTORY',
      factory_id: 'huaxing',
      order_no: 'HIST-2025-001',
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      supplier_id: 'CSP-huaxing-HEYUAN-DONGKANG',
      supplier_name: '河源东康纸品有限公司',
      contract_no: 'SC700145365',
      item_no: '203302044',
      product_name: '产品示例',
      product_order_quantity: '3600',
      order_date: '2025-08-05',
      due_date: '2025-08-12',
      status: 'CONFIRMED',
      note: '历史订单补录',
      revision: 1,
      created_by: 'warehouse_keeper',
      created_by_name: '仓管员',
      updated_by: 'warehouse_keeper',
      updated_by_name: '仓管员',
      created_at: '2026-08-10T10:00:00+08:00',
      updated_at: '2026-08-10T10:00:00+08:00',
      lines: [{
        id: 'CTL-HISTORY-1',
        line_no: 1,
        packaging_type: '外箱',
        paper_quality: 'A33+B',
        specification: '31.5 × 11.125 × 11.25',
        dimension_unit: 'in',
        usage_quantity: '0.00833333',
        required_quantity: '30',
        received_quantity: '0',
        remaining_quantity: '30',
        unit: '个',
        unit_price: '3.46',
        currency: 'CNY',
        price_source: '历史合同',
        note: '',
      }],
    }
    cartonApiMock.listCustomers.mockResolvedValue([{ customer_code: 'DICKIE', customer_name: 'Dickie', status: 'ACTIVE' }])
    cartonApiMock.listOrders.mockResolvedValueOnce([]).mockResolvedValueOnce([importedOrder])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.uploadHistoryOrders.mockResolvedValue({
      factory_id: 'huaxing',
      original_filename: '历史订单.xlsx',
      row_count: 4,
      group_count: 1,
      imported_count: 1,
      imported_line_count: 4,
      skipped_count: 0,
      imported_orders: ['HIST-2025-001'],
      skipped_orders: [],
      warnings: [],
    })

    const wrapper = mountView('orders')
    await flushPromises()

    const template = wrapper.get('a[download="纸箱历史订单导入模板.xlsx"]')
    expect(template.text()).toContain('下载历史订单模板')
    expect(template.attributes('href')).toBe('/templates/carton-history-order-import-template.xlsx')
    expect(findButton(wrapper, '导入历史订单').attributes('disabled')).toBeUndefined()

    const input = wrapper.get('input[aria-label="选择历史订单文件"]')
    const file = new File(['xlsx'], '历史订单.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(cartonApiMock.uploadHistoryOrders).toHaveBeenCalledWith('huaxing', file)
    expect(wrapper.text()).toContain('新增 1 张订单、4 条纸品明细')
    expect(wrapper.text()).toContain('HIST-2025-001')
  })

  it('calculates effective receipts from manual unusable quantities without posting inventory', async () => {
    const wrapper = mountView('receipts')

    expect(findButton(wrapper, '导入送货单').exists()).toBe(true)
    expect(findButton(wrapper, '查找').exists()).toBe(true)
    expect(wrapper.text()).toContain('送货单 DN26061301')
    expect(wrapper.text()).toContain('有效收料 = 实收 − 破损 − 拒收 − 其他不可用')
    await wrapper.get('input[aria-label="RC-DN26061301-01 破损"]').setValue('2')
    await findButton(wrapper, '保存待确认收料单').trigger('click')

    expect(wrapper.text()).toContain('有效收料45')
    expect(wrapper.text()).toContain('请先导入送货单并完成订单纸品匹配')
  })

  it('creates a manual receipt and confirms a fully received order', async () => {
    const openOrder = {
      id: 'CTO-MANUAL-001',
      factory_id: 'huaxing',
      order_no: 'CT-260805-76C698',
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      supplier_id: 'CSP-huaxing-HEYUAN-DONGKANG',
      supplier_name: '河源东康纸品有限公司',
      contract_no: '3722111',
      item_no: '20330022444',
      product_name: '',
      product_order_quantity: '3600',
      order_date: '2026-08-05',
      due_date: '2026-08-12',
      status: 'CONFIRMED',
      note: '',
      revision: 1,
      created_by: 'admin',
      created_by_name: '系统管理员',
      updated_by: 'admin',
      updated_by_name: '系统管理员',
      created_at: '2026-08-05T10:00:00+08:00',
      updated_at: '2026-08-05T10:00:00+08:00',
      lines: [{
        id: 'CTL-MANUAL-001',
        line_no: 1,
        packaging_type: '外箱',
        paper_quality: 'A33+B',
        specification: '12*11*5',
        dimension_unit: 'in',
        usage_quantity: '1',
        required_quantity: '3600',
        received_quantity: '0',
        remaining_quantity: '3600',
        unit: '个',
        unit_price: '3.46',
        currency: 'HKD',
        price_source: 'manual',
        note: '',
      }],
    }
    cartonApiMock.listCustomers.mockResolvedValue([{
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      status: 'ACTIVE',
    }])
    cartonApiMock.listOrders.mockResolvedValue([openOrder])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.latestReceiptImport.mockResolvedValue(null)
    cartonApiMock.createReceipt.mockResolvedValue({
      id: 'CTR-MANUAL-001',
      receipt_no: 'RC-260811-ABC123',
      status: 'PENDING_CONFIRMATION',
      revision: 1,
      lines: [],
    })
    cartonApiMock.confirmReceipt.mockImplementation(async () => {
      cartonApiMock.listOrders.mockResolvedValue([{
        ...openOrder,
        status: 'COMPLETED',
        revision: 2,
        lines: openOrder.lines.map((line) => ({
          ...line,
          received_quantity: '3600',
          remaining_quantity: '0',
        })),
      }])
      return {
        id: 'CTR-MANUAL-001',
        receipt_no: 'RC-260811-ABC123',
        status: 'POSTED',
        revision: 2,
        lines: [],
      }
    })

    const wrapper = mountView('receipts')
    await flushPromises()
    await findButton(wrapper, '人工录入收料').trigger('click')

    expect(wrapper.text()).toContain('人工录入订单收料')
    expect(wrapper.text()).toContain('CT-260805-76C698')
    expect(wrapper.text()).toContain('全部收齐，确认后完成订单')
    await findButton(wrapper, '保存待确认收料单').trigger('click')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').attributes('role')).toBe('alert')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('请先填写送货单号')
    expect(wrapper.get('input[aria-label="人工送货单号"]').attributes('aria-invalid')).toBe('true')

    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-MANUAL-260811-001')
    await wrapper.get('input[aria-label="MANUAL-CTL-MANUAL-001 仓位"]').setValue('A-01')
    await findButton(wrapper, '保存待确认收料单').trigger('click')
    await flushPromises()

    expect(cartonApiMock.createReceipt).toHaveBeenCalledWith(expect.objectContaining({
      factory_id: 'huaxing',
      delivery_note_no: 'DN-MANUAL-260811-001',
      import_batch_id: null,
      lines: [expect.objectContaining({
        order_line_id: 'CTL-MANUAL-001',
        delivered_quantity: 3600,
        received_quantity: 3600,
        location: 'A-01',
      })],
    }))
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').attributes('role')).toBe('status')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('保存成功')
    expect(wrapper.text()).toContain('确认入库并完成订单')

    await findButton(wrapper, '确认入库并完成订单').trigger('click')
    await flushPromises()
    expect(cartonApiMock.confirmReceipt).toHaveBeenCalledWith('huaxing', 'CTR-MANUAL-001', 1)
    expect(wrapper.text()).toContain('全部明细已收齐并自动完成')
  })

  it('searches receipt details by delivery note, contract or item number', async () => {
    const wrapper = mountView('receipts')

    await wrapper.get('input[aria-label="查找送货单"]').setValue('203302028')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.text()).toContain('找到 1 条送货明细')
    expect(wrapper.text()).toContain('SC700142616/Z00-203302028')
    expect(wrapper.text()).not.toContain('SC700145011/3600-203302044')
  })

  it('shows a visible OCR result when a real delivery image has no matching formal orders', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.uploadReceipt.mockResolvedValue({
      id: 'CIB-REAL-IMAGE',
      factory_id: 'huaxing',
      import_type: 'DELIVERY_NOTE',
      original_filename: 'DN26061301.jpg',
      source_sha256: 'abc123',
      status: 'REQUIRES_REVIEW',
      duplicate: false,
      parse_summary: {
        engine: 'rapidocr-pp-ocrv6',
        row_count: 18,
        matched_count: 0,
        issue_count: 18,
        warnings: ['图片/PDF 仅作为 OCR 预览，数量和纸品字段必须逐行人工复核'],
        document: { delivery_note_no: 'DN26061301', delivery_date: '2013-06-26' },
        rows: [{
          source_sheet: 'OCR',
          source_row: 1,
          delivery_note_no: 'DN26061301',
          contract_no: 'SC700145011/3600',
          item_no: '203302038',
          packaging_type: '待复核',
          paper_quality: '待复核',
          delivered_quantity: 0,
          match_status: 'MISSING_ORDER',
          suggestion: '未找到可关联的正式订单明细',
        }],
      },
    })

    const wrapper = mountView('receipts')
    await flushPromises()
    const input = wrapper.get('input[aria-label="选择送货单文件"]')
    const file = new File(['delivery-note-image'], 'DN26061301.jpg', { type: 'image/jpeg' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(cartonApiMock.uploadReceipt).toHaveBeenCalledWith('huaxing', file)
    expect(wrapper.text()).toContain('送货单识别完成')
    expect(wrapper.text()).toContain('识别总行数18 行')
    expect(wrapper.text()).toContain('已匹配正式订单0 行')
    expect(wrapper.text()).toContain('需要人工处理18 行')
    expect(wrapper.text()).toContain('文件已成功导入，但没有找到可关联的正式纸箱订单')
    expect(wrapper.text()).toContain('SC700145011/3600')
    expect(wrapper.text()).toContain('前往异常中心')
    expect(wrapper.text()).not.toContain('等待导入并复核送货单')
  })

  it('separates realtime inventory operations from period-end reconciliation', () => {
    const inventoryWrapper = mountView('inventory')
    expect(inventoryWrapper.text()).toContain('实时库存作业页')
    expect(inventoryWrapper.text()).toContain('实时库存结存台账')
    expect(inventoryWrapper.text()).toContain('逐笔交易流水')
    expect(inventoryWrapper.text()).toContain('纸品类型')
    expect(inventoryWrapper.text()).toContain('纸质')

    const closingWrapper = mountView('closing')
    expect(closingWrapper.text()).toContain('期间月结与供应商对账页')
    expect(closingWrapper.text()).toContain('客户月结汇总快照')
    expect(closingWrapper.text()).toContain('不承担日常收发记录')
    expect(closingWrapper.text()).not.toContain('逐笔交易流水')
  })

  it('downloads the history inventory template and imports immutable opening movements', async () => {
    const movement = {
      id: 'CIM-HISTORY-1',
      factory_id: 'huaxing',
      order_line_id: null,
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      contract_no: '',
      item_no: '209999999',
      packaging_type: '卡纸',
      paper_quality: '250g 灰底白',
      specification: '8.5 × 5.5',
      movement_type: 'ADJUSTMENT',
      quantity: '100.0000',
      balance: '100.0000',
      unit: '张',
      unit_price: '0.450000',
      currency: 'CNY',
      location: '纸箱仓 B-02',
      document_no: 'STOCKTAKE-20250805',
      source_type: 'HISTORY_INVENTORY',
      source_id: 'CHI-TEST',
      source_line_id: 'CHI-LINE-TEST',
      reversal_of_movement_id: null,
      reason: '系统上线前盘点',
      actor_user_id: 'warehouse_keeper',
      actor_name: '仓管员',
      occurred_at: '2025-08-05T00:00:00+08:00',
    }
    cartonApiMock.listCustomers.mockResolvedValue([{ customer_code: 'DICKIE', customer_name: 'Dickie', status: 'ACTIVE' }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValueOnce([]).mockResolvedValueOnce([movement])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.uploadHistoryInventory.mockResolvedValue({
      factory_id: 'huaxing',
      original_filename: '历史库存.xlsx',
      row_count: 1,
      imported_count: 1,
      skipped_count: 0,
      matched_order_line_count: 0,
      standalone_count: 1,
      total_quantity: '100.0000',
      duplicate: false,
      movement_ids: ['CIM-HISTORY-1'],
      warnings: [],
    })

    const wrapper = mountView('inventory')
    await flushPromises()

    const template = wrapper.get('a[download="纸箱历史库存导入模板.xlsx"]')
    expect(template.text()).toContain('下载历史库存模板')
    expect(template.attributes('href')).toBe('/templates/carton-history-inventory-import-template.xlsx')
    expect(findButton(wrapper, '导入历史库存').attributes('disabled')).toBeUndefined()

    const input = wrapper.get('input[aria-label="选择历史库存文件"]')
    const file = new File(['xlsx'], '历史库存.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(cartonApiMock.uploadHistoryInventory).toHaveBeenCalledWith('huaxing', file)
    expect(wrapper.text()).toContain('新增 1 笔期初流水')
    expect(wrapper.text()).toContain('独立旧库存 1 行')
    expect(wrapper.text()).toContain('历史库存导入')
    expect(wrapper.text()).toContain('期初')
    expect(wrapper.text()).toContain('209999999')
  })

  it('lets an authorized carton supervisor maintain factory customer data', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.createCustomer.mockImplementation(async (payload: any) => ({
      id: 'CCU-NEW',
      ...payload,
      revision: 1,
      created_by: 'supervisor',
      created_by_name: '纸箱部主管',
      updated_by: 'supervisor',
      updated_by_name: '纸箱部主管',
      created_at: '2026-08-05T10:00:00+08:00',
      updated_at: '2026-08-05T10:00:00+08:00',
    }))

    const wrapper = mountView('orders')
    await flushPromises()
    await findButton(wrapper, '客户资料维护').trigger('click')

    expect(wrapper.text()).toContain('仅维护 华兴 客户')
    await wrapper.get('input[aria-label="客户名称"]').setValue('新客户')
    await wrapper.get('input[aria-label="客户国家地区"]').setValue('德国')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(cartonApiMock.createCustomer).toHaveBeenCalledWith(expect.objectContaining({
      factory_id: 'huaxing',
      customer_code: '',
      customer_name: '新客户',
      country_region: '德国',
      status: 'ACTIVE',
    }))
    expect(wrapper.text()).toContain('客户 新客户 已加入 华兴 客户主数据')
    expect(wrapper.text()).not.toContain('NEW-CUSTOMER')
  })

  it('switches to formal ledger state when the backend responds', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([{
      id: 'CCU-DICKIE',
      factory_id: 'huaxing',
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      country_region: '德国',
      contact_name: '',
      contact_phone: '',
      note: '',
      status: 'ACTIVE',
      revision: 1,
      created_by: 'admin',
      created_by_name: '管理员',
      updated_by: 'admin',
      updated_by_name: '管理员',
      created_at: '2026-08-05T10:00:00+08:00',
      updated_at: '2026-08-05T10:00:00+08:00',
    }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])

    const wrapper = mountView('orders')
    await flushPromises()

    expect(wrapper.text()).toContain('正式台账 · 后端已连接')
    expect(wrapper.text()).toContain('订单、收料导入、库存流水和月结均由后端保存')
    expect(wrapper.text()).not.toContain('CT-260805-006')
  })

  it('keeps balances for different contracts and specifications instead of taking only the latest item row', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([{
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      status: 'ACTIVE',
    }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([
      {
        factory_id: 'huaxing',
        customer_code: 'DICKIE',
        customer_name: 'Dickie',
        contract_no: 'SC700144661/900',
        item_no: '203307002',
        order_line_id: null,
        packaging_type: '外箱',
        paper_quality: 'A33+B',
        specification: '30.375*9.125*17.25',
        unit: '个',
        balance: '96',
        latest_location: 'B1',
        latest_movement_at: '2026-08-05T00:00:00+08:00',
      },
      {
        factory_id: 'huaxing',
        customer_code: 'DICKIE',
        customer_name: 'Dickie',
        contract_no: 'SC700144592/100',
        item_no: '203307002',
        order_line_id: null,
        packaging_type: '外箱',
        paper_quality: 'A33+B',
        specification: '30.375*9.125*0',
        unit: '个',
        balance: '80',
        latest_location: 'B1',
        latest_movement_at: '2026-08-05T00:00:00+08:00',
      },
    ])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])

    const wrapper = mountView('inventory')
    await flushPromises()

    expect(wrapper.text()).toContain('176 箱')
    expect(wrapper.text()).toContain('SC700144661/900')
    expect(wrapper.text()).toContain('SC700144592/100')
    expect(wrapper.text()).toContain('30.375*9.125*17.25')
    expect(wrapper.text()).toContain('30.375*9.125*0')
    expect(wrapper.text()).toContain('不同合同、货号、纸品类型、纸质、规格和单位分别结存，不互相覆盖。')
  })

  it('renders month-end amounts with the currency returned by the backend', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([{
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      status: 'ACTIVE',
    }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([{
      id: 'CCL-HKD-202608',
      factory_id: 'huaxing',
      period: '2026-08',
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      opening_quantity: '0',
      inbound_quantity: '0',
      outbound_quantity: '0',
      adjustment_quantity: '1852',
      ending_quantity: '1852',
      ending_amount: '4400.89',
      currency: 'HKD',
      status: 'LOCKED',
      revision: 4,
      generated_by: 'warehouse_keeper',
      generated_at: '2026-08-05T10:35:00+08:00',
      confirmed_by: 'warehouse_keeper',
      confirmed_at: '2026-08-05T10:40:00+08:00',
      locked_by: 'warehouse_keeper',
      locked_at: '2026-08-05T10:45:00+08:00',
    }])
    cartonApiMock.listExceptions.mockResolvedValue([])

    const wrapper = mountView('closing')
    await flushPromises()

    expect(wrapper.text()).toContain('HK$4,400.89')
    expect(wrapper.text()).toContain('HKD')
    expect(wrapper.text()).not.toContain('¥4,400.89')
  })

  it('registers outbound inventory and reverses the immutable movement from the ledger', async () => {
    const inbound = {
      id: 'CIM-IN-1', factory_id: 'huaxing', order_line_id: 'LINE-1', customer_code: 'DICKIE',
      customer_name: 'Dickie', contract_no: 'SC-001', item_no: 'ITEM-001', packaging_type: '外箱',
      paper_quality: 'A33+B', specification: '12*11*5', movement_type: 'INBOUND', quantity: '100',
      balance: '100', unit: '个', unit_price: '3.46', currency: 'HKD', location: 'A-01',
      document_no: 'DN-001', source_type: 'RECEIPT', source_id: 'RC-001', source_line_id: 'RCL-001',
      reversal_of_movement_id: null, reason: '确认收料', actor_user_id: 'keeper', actor_name: '仓管员',
      occurred_at: '2026-08-11T09:00:00+08:00',
    }
    const outbound = {
      ...inbound,
      id: 'CIM-OUT-1',
      movement_type: 'OUTBOUND',
      quantity: '-10',
      balance: '90',
      document_no: 'OUT-001',
      source_type: 'MANUAL',
      source_id: 'CIM-OUT-1',
      source_line_id: 'CIM-OUT-1',
      reason: '生产领料',
      occurred_at: '2026-08-11T10:00:00+08:00',
    }
    const balance = {
      factory_id: 'huaxing', customer_code: 'DICKIE', customer_name: 'Dickie', contract_no: 'SC-001',
      item_no: 'ITEM-001', order_line_id: 'LINE-1', packaging_type: '外箱', paper_quality: 'A33+B',
      specification: '12*11*5', unit: '个', balance: '100', latest_location: 'A-01',
      latest_movement_id: 'CIM-IN-1', latest_movement_at: '2026-08-11T09:00:00+08:00',
    }
    cartonApiMock.listCustomers.mockResolvedValue([{ customer_code: 'DICKIE', customer_name: 'Dickie', status: 'ACTIVE' }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValueOnce([inbound]).mockResolvedValueOnce([outbound, inbound]).mockResolvedValueOnce([])
    cartonApiMock.listInventoryBalances.mockResolvedValueOnce([balance]).mockResolvedValueOnce([{ ...balance, balance: '90', latest_movement_id: 'CIM-OUT-1' }]).mockResolvedValueOnce([balance])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.createInventoryMovement.mockResolvedValue(outbound)
    cartonApiMock.reverseInventoryMovement.mockResolvedValue({
      ...outbound,
      id: 'CIM-REV-1',
      movement_type: 'REVERSAL',
      quantity: '10',
      balance: '100',
      reversal_of_movement_id: 'CIM-OUT-1',
    })

    const wrapper = mountView('inventory')
    await flushPromises()
    await wrapper.get('select[aria-label="库存作业记录"]').setValue('LINE-1')
    await wrapper.get('input[aria-label="库存作业数量"]').setValue('10')
    await wrapper.get('input[aria-label="库存作业单据号"]').setValue('OUT-001')
    await wrapper.get('input[aria-label="库存作业原因"]').setValue('生产领料')
    const inventoryForm = wrapper.findAll('form').find((form) => form.text().includes('登记库存作业'))
    if (!inventoryForm) throw new Error('Inventory form not found')
    await inventoryForm.trigger('submit')
    await flushPromises()

    expect(cartonApiMock.createInventoryMovement).toHaveBeenCalledWith(expect.objectContaining({
      order_line_id: 'LINE-1',
      reference_movement_id: null,
      movement_type: 'OUTBOUND',
      quantity: 10,
      document_no: 'OUT-001',
    }))
    expect(wrapper.text()).toContain('出库已登记')

    await findButton(wrapper, '冲销').trigger('click')
    await wrapper.get('textarea[aria-label="库存冲销原因"]').setValue('领料单作废')
    const reversalForm = wrapper.findAll('form').find((form) => form.text().includes('冲销库存流水'))
    if (!reversalForm) throw new Error('Reversal form not found')
    await reversalForm.trigger('submit')
    await flushPromises()
    expect(cartonApiMock.reverseInventoryMovement).toHaveBeenCalledWith('huaxing', 'CIM-OUT-1', '领料单作废')
  })

  it('restores persisted weekly reconciliation results and exposes import history', async () => {
    const weeklyBatch = {
      id: 'CIB-WEEKLY-1', factory_id: 'huaxing', import_type: 'WEEKLY_SCHEDULE',
      original_filename: '每周排期-第32周.xlsx', source_sha256: 'sha', import_profile: '', content_type: 'application/xlsx',
      source_size_bytes: 1024, status: 'REQUIRES_REVIEW', imported_by: 'keeper', imported_by_name: '仓管员',
      created_at: '2026-08-11T09:30:00+08:00', duplicate: false,
      parse_summary: { row_count: 1, matched_count: 0, issue_count: 1, rows: [{
        source_sheet: '排期', source_row: 2, reference: 'SC-MISSING', customer_name: 'Dickie',
        item_no: 'ITEM-MISSING', product_name: '消防车', quantity: 120, match_status: 'MISSING_ORDER',
        suggestion: '请补建正式纸箱订单',
      }] },
    }
    cartonApiMock.listCustomers.mockResolvedValue([{ customer_code: 'DICKIE', customer_name: 'Dickie', status: 'ACTIVE' }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.listImports.mockImplementation(async (_factory: string, type: string) => type === 'WEEKLY_SCHEDULE' ? [weeklyBatch] : [])

    const wrapper = mountView('weekly-check')
    await flushPromises()
    expect(wrapper.text()).toContain('核对历史')
    expect(wrapper.text()).toContain('每周排期-第32周.xlsx')
    expect(wrapper.text()).toContain('疑似漏单')
    expect(wrapper.text()).toContain('SC-MISSING')
  })

  it('shows persisted receipt history and filters it with the receipt search', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([{ customer_code: 'DICKIE', customer_name: 'Dickie', status: 'ACTIVE' }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.listReceipts.mockResolvedValue([{
      id: 'CTR-1', factory_id: 'huaxing', receipt_no: 'RC-260811-001', delivery_note_no: 'DN-260811-001',
      delivery_date: '2026-08-11', supplier_id: 'SUP-1', supplier_name: '河源东康纸品有限公司', import_batch_id: null,
      status: 'POSTED', note: '', revision: 2, created_by: 'keeper', created_by_name: '仓管员',
      confirmed_by: 'keeper', confirmed_by_name: '仓管员', created_at: '2026-08-11T09:00:00+08:00',
      updated_at: '2026-08-11T09:05:00+08:00', confirmed_at: '2026-08-11T09:05:00+08:00',
      lines: [{ id: 'CRL-1', line_no: 1, order_line_id: 'LINE-1', customer_code: 'DICKIE', customer_name: 'Dickie',
        contract_no: 'SC-HISTORY-001', item_no: 'ITEM-HISTORY-001', packaging_type: '外箱', paper_quality: 'A33+B',
        specification: '12*11*5', delivered_quantity: '50', received_quantity: '50', damaged_quantity: '0',
        rejected_quantity: '0', unusable_quantity: '0', effective_quantity: '50', unit: '个', unit_price: '3.46',
        currency: 'HKD', location: 'A-01', feedback_note: '' }],
    }])

    const wrapper = mountView('receipts')
    await flushPromises()
    expect(wrapper.text()).toContain('收料历史台账')
    expect(wrapper.text()).toContain('RC-260811-001')
    expect(wrapper.text()).toContain('SC-HISTORY-001')
    await wrapper.get('input[aria-label="查找送货单"]').setValue('ITEM-HISTORY-001')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.text()).toContain('ITEM-HISTORY-001')
  })
})

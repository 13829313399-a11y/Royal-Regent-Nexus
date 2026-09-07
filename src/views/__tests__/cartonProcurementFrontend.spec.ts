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
  relocateInventory: vi.fn(),
  createInventoryMovementsBulk: vi.fn(),
  reverseInventoryMovement: vi.fn(),
  listInventorySummary: vi.fn(),
  listAuditEvents: vi.fn(),
  listClosings: vi.fn(),
  listExceptions: vi.fn(),
  createOrder: vi.fn(),
  updateOrder: vi.fn(),
  submitOrderToSupplier: vi.fn(),
  bulkSubmitOrdersToSupplier: vi.fn(),
  cancelOrder: vi.fn(),
  appendOrder: vi.fn(),
  reduceOrder: vi.fn(),
  returnOrder: vi.fn(),
  bulkCancelOrders: vi.fn(),
  uploadHistoryOrders: vi.fn(),
  searchOrderHistoryItems: vi.fn(),
  uploadHistoryInventory: vi.fn(),
  exportPurchaseOrder: vi.fn(),
  getPurchaseOrderContext: vi.fn(),
  issuePurchaseOrder: vi.fn(),
  downloadPurchaseOrderIssue: vi.fn(),
  issuePurchaseOrders: vi.fn(),
  exportPurchaseOrders: vi.fn(),
  uploadReceipt: vi.fn(),
  deleteReceiptImport: vi.fn(),
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
        PopoverPortal: { template: '<slot />' },
      },
    },
  })
}

function findButton(wrapper: ReturnType<typeof mountView>, label: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(label))
  if (!button) throw new Error(`Button not found: ${label}`)
  return button
}

async function clickCalendarDate(wrapper: ReturnType<typeof mountView>, date: string) {
  const selector = `[data-reka-calendar-cell-trigger][data-value="${date}"]:not([data-outside-view])`
  for (let attempt = 0; !wrapper.find(selector).exists() && attempt < 24; attempt += 1) {
    const firstVisible = wrapper.get('[data-reka-calendar-cell-trigger]:not([data-outside-view])').attributes('data-value') ?? ''
    await wrapper.get(`button[aria-label="${date < firstVisible ? '上个月' : '下个月'}"]`).trigger('click')
    await flushPromises()
  }
  const day = wrapper.get(selector)
  await day.trigger('mouseenter')
  await day.trigger('click')
  await flushPromises()
}

async function openOrderMoreActions(card: any, orderNo: string) {
  await card.get(`button[aria-label="更多 ${orderNo} 订单操作"]`).trigger('click')
}

function businessDateOffset(days: number) {
  const current = new Date(`${new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })}T00:00:00Z`)
  current.setUTCDate(current.getUTCDate() + days)
  return current.toISOString().slice(0, 10)
}

function dateOffsetFrom(value: string, days: number) {
  const current = new Date(`${value}T00:00:00Z`)
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
    customer_due_date: dateOffsetFrom(dueDate, 3),
    safety_lead_days: 3,
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

function mockReceiptWorkspace(orders: ReturnType<typeof orderFixture>[]) {
  cartonApiMock.listCustomers.mockResolvedValue([{ customer_code: 'DICKIE', customer_name: 'Dickie', status: 'ACTIVE' }])
  cartonApiMock.listOrders.mockResolvedValue(orders)
  cartonApiMock.listMovements.mockResolvedValue([])
  cartonApiMock.listClosings.mockResolvedValue([])
  cartonApiMock.listExceptions.mockResolvedValue([])
}

describe('CartonProcurementView frontend workspace', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    appStoreMock.activeProductionFactory = { id: 'huaxing', name: '华兴', shortName: '华兴' }
    authStoreMock.can.mockReturnValue(true)
    cartonApiMock.listCustomers.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listOrders.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listMovements.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listInventorySummary.mockResolvedValue([])
    cartonApiMock.listAuditEvents.mockResolvedValue([])
    cartonApiMock.listImports.mockResolvedValue([])
    cartonApiMock.listReceipts.mockResolvedValue([])
    cartonApiMock.listClosings.mockRejectedValue(new Error('offline test'))
    cartonApiMock.listExceptions.mockRejectedValue(new Error('offline test'))
    cartonApiMock.latestReceiptImport.mockResolvedValue(null)
    cartonApiMock.deleteReceiptImport.mockResolvedValue(undefined)
    cartonApiMock.exportPurchaseOrder.mockResolvedValue(new Blob(['xlsx']))
    cartonApiMock.getPurchaseOrderContext.mockResolvedValue({
      factory_id: 'huaxing',
      order_no: 'CT-DEFAULT',
      order_revision: 1,
      pending_type: 'NONE',
      pending_product_quantity: '0',
      pending_line_count: 0,
      can_generate: false,
      latest_document_no: '',
      historical_baseline: false,
      issues: [],
    })
    cartonApiMock.issuePurchaseOrder.mockResolvedValue({
      blob: new Blob(['issued-xlsx']),
      documentNo: 'CT-DEFAULT-P00',
    })
    cartonApiMock.downloadPurchaseOrderIssue.mockResolvedValue(new Blob(['issued-xlsx']))
    cartonApiMock.issuePurchaseOrders.mockResolvedValue({
      blob: new Blob(['issued-batch-xlsx']),
      issueCount: 1,
    })
    cartonApiMock.exportPurchaseOrders.mockResolvedValue(new Blob(['combined-xlsx']))
    cartonApiMock.searchOrderHistoryItems.mockResolvedValue([])
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
      customer_due_date: payload.customer_due_date,
      safety_lead_days: 3,
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
        required_quantity: String(Math.ceil(payload.product_order_quantity / line.usage_quantity)),
        received_quantity: '0',
        remaining_quantity: String(Math.ceil(payload.product_order_quantity / line.usage_quantity)),
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
      orderFixture('CT-CANCELLED', businessDateOffset(-4), 'CANCELLED'),
      orderFixture('CT-SOON', businessDateOffset(2)),
      orderFixture('CT-OVERDUE', businessDateOffset(-2)),
    ])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])

    const wrapper = mountView('orders')
    await flushPromises()

    const sort = wrapper.get<HTMLSelectElement>('select[aria-label="订单排序"]')
    expect(sort.element.value).toBe('DUE_ASC')
    expect(sort.findAll('option').map((option) => option.text())).toEqual(['交期由近到远', '交期由远到近', '下单日期最新'])
    await sort.setValue('DUE_DESC')
    await sort.setValue('DUE_ASC')

    const summary = wrapper.get('[aria-label="订单交期提醒汇总"]')
    const filterToolbar = wrapper.get('[aria-label="订单筛选与批量操作"]')
    expect(summary.classes()).toContain('!mt-2')
    expect(summary.element.nextElementSibling).toBe(filterToolbar.element)
    expect(summary.text()).toContain('逾期 1')
    expect(summary.text()).toContain('今日 0')
    expect(summary.text()).toContain('未来 3 天 1')
    expect(wrapper.get('[data-order-no="CT-OVERDUE"]').text()).toContain('已逾期 2 天')
    expect(wrapper.get('[data-order-no="CT-SOON"]').text()).toContain('剩 2 天')
    expect(wrapper.get('[data-order-no="CT-FUTURE"]').text()).toContain('距交期 8 天')
    expect(wrapper.get('[data-order-no="CT-COMPLETED"]').text()).toContain('交付已完成')
    expect(wrapper.get('[aria-label="CT-COMPLETED 到货进度"]').text()).toContain('100/100')
    expect(wrapper.get('[aria-label="CT-COMPLETED 到货进度"]').text()).toContain('已齐')
    expect(wrapper.findAll('[data-order-no]').map((card) => card.attributes('data-order-no'))).toEqual([
      'CT-OVERDUE',
      'CT-SOON',
      'CT-FUTURE',
      'CT-COMPLETED',
      'CT-CANCELLED',
    ])
  })

  it('filters orders by an inclusive range after consecutive calendar clicks', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([
      { ...orderFixture('CT-START', businessDateOffset(8)), order_date: businessDateOffset(3) },
      { ...orderFixture('CT-MIDDLE', businessDateOffset(8)), order_date: businessDateOffset(4) },
      { ...orderFixture('CT-END', businessDateOffset(8)), order_date: businessDateOffset(5) },
      { ...orderFixture('CT-OUTSIDE', businessDateOffset(8)), order_date: businessDateOffset(6) },
    ])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])

    const wrapper = mountView('orders')
    await flushPromises()
    const dateFilter = wrapper.get('button[aria-label="订单下单日期筛选"]')
    await dateFilter.trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, businessDateOffset(3))
    expect(wrapper.text()).toContain('请选择结束日期')
    expect(wrapper.findAll('[data-order-no]')).toHaveLength(4)
    await clickCalendarDate(wrapper, businessDateOffset(5))
    expect(wrapper.find('[data-testid="date-range-calendar"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-order-no]').map((card) => card.attributes('data-order-no')).sort()).toEqual([
      'CT-END', 'CT-MIDDLE', 'CT-START',
    ])
    expect(dateFilter.text()).toContain(`${businessDateOffset(3)} 至 ${businessDateOffset(5)}`)

    await dateFilter.trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, businessDateOffset(4))
    await dateFilter.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-order-no]')).toHaveLength(3)
    expect(dateFilter.text()).toContain(`${businessDateOffset(3)} 至 ${businessDateOffset(5)}`)

    await dateFilter.trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, businessDateOffset(4))
    await clickCalendarDate(wrapper, businessDateOffset(4))
    expect(wrapper.findAll('[data-order-no]').map((card) => card.attributes('data-order-no'))).toEqual(['CT-MIDDLE'])
    await dateFilter.trigger('click')
    await flushPromises()
    await findButton(wrapper, '清除日期').trigger('click')
    expect(wrapper.findAll('[data-order-no]')).toHaveLength(4)
    expect(wrapper.find('[data-testid="date-range-calendar"]').exists()).toBe(false)
    expect(dateFilter.text()).toContain('选择日期范围')
  })

  it('places an enlarged bulk selector directly above enlarged order selectors', async () => {
    const wrapper = mountView('orders')
    await flushPromises()

    const selectionToolbar = wrapper.get('[aria-label="订单批量选择"]')
    const firstOrder = wrapper.get('[data-order-no]')
    const selectAll = wrapper.get('input[aria-label="全选当前订单结果"]')
    const orderSelector = firstOrder.get('input[aria-label^="选择订单 "]')

    expect(selectionToolbar.element.nextElementSibling).toBe(firstOrder.element)
    expect(selectionToolbar.classes()).toContain('bg-slate-200/90')
    expect(selectionToolbar.get('.order-ledger-grid').exists()).toBe(true)
    expect(firstOrder.get('.order-ledger-grid').exists()).toBe(true)
    expect(firstOrder.classes()).toContain('mt-2')
    expect(firstOrder.classes()).toContain('shadow-sm')
    expect(selectAll.classes()).toContain('size-5')
    expect(orderSelector.classes()).toContain('size-5')
    expect(orderSelector.element.parentElement?.tagName).toBe('DIV')
  })

  it('derives the plan due date from the customer due date and warns on short lead time', async () => {
    const wrapper = mountView('orders')
    await flushPromises()
    await findButton(wrapper, '新建纸箱订单').trigger('click')

    const orderDate = wrapper.get('input[aria-label="下单日期"]')
    const customerDueDate = wrapper.get('input[aria-label="客户交期"]')
    const planDueDate = wrapper.get('input[aria-label="计划交期"]')
    expect(planDueDate.attributes('readonly')).toBeDefined()

    await customerDueDate.setValue(dateOffsetFrom((orderDate.element as HTMLInputElement).value, 10))
    expect((planDueDate.element as HTMLInputElement).value).toBe(
      dateOffsetFrom((orderDate.element as HTMLInputElement).value, 7),
    )
    expect(wrapper.text()).not.toContain('不足默认 3 天安全提前量')

    await customerDueDate.setValue(dateOffsetFrom((orderDate.element as HTMLInputElement).value, 1))
    expect((planDueDate.element as HTMLInputElement).value).toBe((orderDate.element as HTMLInputElement).value)
    expect(wrapper.get('[role="alert"]').text()).toContain('不足默认 3 天安全提前量')
  })

  it('groups multiple paper items under one contract and keeps paper quality separate from specification', async () => {
    const wrapper = mountView('orders')

    expect(wrapper.get('select[aria-label="客户筛选"]').element.parentElement)
      .toBe(findButton(wrapper, '客户资料维护').element.parentElement)

    const firstOrder = wrapper.get('[data-order-no="CT-260805-006"]')
    expect(firstOrder.text()).not.toContain('CT-260805-006')
    expect(firstOrder.text()).toContain('08/05')
    expect(firstOrder.text()).not.toContain('2026-08-05')
    expect(wrapper.get('[aria-label="订单批量选择"]').text()).toContain('纸品明细')
    expect(wrapper.get('[aria-label="订单批量选择"]').text()).not.toContain('产品数量')
    const materialSummary = firstOrder.get('[aria-label="CT-260805-006 纸品明细"]')
    expect(materialSummary.text()).toContain('纸品合计 7,350 件')
    expect(materialSummary.text()).toContain('外箱 30箱')
    expect(materialSummary.text()).toContain('内箱 120箱')
    expect(materialSummary.text()).toContain('滑板纸 3,600张')
    expect(materialSummary.text()).toContain('卡纸 3,600张')
    const arrivalProgress = firstOrder.get('[aria-label="CT-260805-006 到货进度"]')
    expect(arrivalProgress.text()).toContain('0/7,350')
    expect(arrivalProgress.text()).toContain('待 7,350 件')
    const detailButton = firstOrder.get('[aria-label="CT-260805-006 操作"]').get('button[aria-label="查看 CT-260805-006 完整订单明细"]')
    expect(detailButton.text()).toBe('明细')
    expect(detailButton.attributes('title')).toContain('悬停预览完整明细')
    const actionGroup = firstOrder.get('[aria-label="CT-260805-006 操作"]').get('div')
    expect(actionGroup.classes()).toContain('justify-start')
    expect(actionGroup.classes()).toContain('gap-1')
    expect(detailButton.classes()).toContain('rounded-md')
    expect(detailButton.classes()).toContain('col-start-3')
    expect(firstOrder.find('[aria-label="CT-260805-006 展开纸品明细"]').exists()).toBe(false)
    await detailButton.trigger('mouseenter')
    expect(wrapper.get('[data-testid="order-detail-overlay"]').classes()).toContain('pointer-events-none')
    expect(wrapper.text()).toContain('悬停预览 · 单击明细可固定')
    await detailButton.trigger('mouseleave')
    expect(wrapper.find('[data-testid="order-detail-overlay"]').exists()).toBe(false)
    await detailButton.trigger('click')
    await detailButton.trigger('mouseleave')
    expect(wrapper.get('[data-testid="order-detail-overlay"]').classes()).toContain('pointer-events-auto')
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(wrapper.text()).toContain('已固定显示')
    expect(wrapper.text()).toContain('订单明细 — SC700145365 / 203302044')
    expect(wrapper.text()).toContain('共 4 项纸品')
    expect(wrapper.text()).toContain('纸品类型')
    expect(wrapper.text()).toContain('纸质')
    expect(wrapper.text()).toContain('规格')
    expect(wrapper.text()).toContain('每箱个数')
    expect(wrapper.text()).toContain('纸品数量')
    expect(wrapper.text()).toContain('已入库')
    expect(wrapper.text()).toContain('待入库')
    expect(wrapper.text()).toContain('入库进度')
    expect(wrapper.text()).toContain('滑板纸')
    expect(wrapper.text()).toContain('卡纸')
    await wrapper.get('button[aria-label="关闭订单明细"]').trigger('click')

    await findButton(wrapper, '新建纸箱订单').trigger('click')
    expect(wrapper.get('input[aria-label="纸箱供应商"]').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="合同号"]').setValue('SC-DEMO-001')
    await wrapper.get('input[aria-label="货号"]').setValue('203399999')
    await wrapper.get('input[aria-label="产品名称"]').setValue('新产品')
    await wrapper.get('input[aria-label="纸质 1"]').setValue('A33+B')
    await wrapper.get('input[aria-label="规格 1"]').setValue('30 × 20 × 15 cm')
    expect(wrapper.get('output[aria-label="纸箱数量 1"]').text()).toBe('0')
    await wrapper.get('input[aria-label="订单数量"]').setValue('3601')
    expect(wrapper.get('output[aria-label="纸箱数量 1"]').text()).toBe('31')
    await wrapper.get('input[aria-label="订单数量"]').setValue('3600')
    await wrapper.get('input[aria-label="客户交期"]').setValue(businessDateOffset(8))
    expect((wrapper.get('input[aria-label="计划交期"]').element as HTMLInputElement).value).toBe(businessDateOffset(5))
    await findButton(wrapper, '新增纸品明细').trigger('click')
    await wrapper.get('input[aria-label="纸质 2"]').setValue('A9A')
    await wrapper.get('input[aria-label="规格 2"]').setValue('29 × 19 cm')
    await wrapper.get('input[aria-label="每箱个数 2"]').setValue('2')
    expect(wrapper.get('output[aria-label="纸箱数量 2"]').text()).toBe('1,800')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('SC-DEMO-001')
    expect(wrapper.text()).toContain('203399999')
    const createdOrder = wrapper.get('[data-order-no="CT-260805-ABC123"]')
    await createdOrder.get('button[aria-label="查看 CT-260805-ABC123 完整订单明细"]').trigger('click')
    expect(wrapper.text()).toContain('共 2 项纸品')
    expect(wrapper.text()).toContain('A9A')
    await wrapper.get('button[aria-label="关闭订单明细"]').trigger('click')
    expect(cartonApiMock.createOrder).toHaveBeenCalledWith(expect.objectContaining({ status: 'CONFIRMED' }))
    expect(wrapper.text()).toContain('已进入待下单')
    expect(wrapper.text()).toContain('含 2 条纸品明细')
    expect(wrapper.text()).toContain('确认锁定前仍可修改、追加或取消')

    await openOrderMoreActions(wrapper.get('[data-order-no="CT-260805-ABC123"]'), 'CT-260805-ABC123')
    await wrapper.get('button[aria-label="管理 CT-260805-ABC123 采购单"]').trigger('click')
    await flushPromises()
    await findButton(wrapper, '导出累计参考').trigger('click')
    await flushPromises()
    expect(cartonApiMock.exportPurchaseOrder).toHaveBeenCalledWith('huaxing', 'CT-260805-ABC123')
    expect(wrapper.text()).toContain('CT-260805-ABC123 采购单已生成并开始下载')
  })

  it('suggests approximate historical item numbers and reuses the selected order snapshot', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([{
      id: 'CC-DICKIE',
      factory_id: 'huaxing',
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      status: 'ACTIVE',
    }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.searchOrderHistoryItems.mockResolvedValue([{
      item_no: '203302044',
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      product_name: '消防车套装',
      latest_order_no: 'HIST-2025-ITEM-001',
      latest_contract_no: 'SC-HIST-LATEST',
      latest_order_date: '2025-08-05',
      latest_product_order_quantity: '3600',
      order_count: 3,
      match_type: 'PREFIX',
      match_score: 899,
      lines: [
        {
          line_no: 1,
          packaging_type: '外箱',
          paper_quality: 'A33+B',
          specification: '31.5 × 11.125 × 11.25',
          dimension_unit: 'in',
          usage_quantity: '120',
          unit: '个',
          unit_price: '3.46',
          currency: 'CNY',
          price_source: '历史合同',
          note: '主箱',
        },
        {
          line_no: 2,
          packaging_type: '内箱',
          paper_quality: 'B3B',
          specification: '15.5 × 10.625 × 5.25',
          dimension_unit: 'in',
          usage_quantity: '30',
          unit: '个',
          unit_price: '0.96',
          currency: 'CNY',
          price_source: '历史合同',
          note: '内盒',
        },
      ],
    }])

    const wrapper = mountView('orders')
    await flushPromises()
    await findButton(wrapper, '新建纸箱订单').trigger('click')
    await wrapper.get('input[aria-label="合同号"]').setValue('SC-NEW-ORDER')
    await wrapper.get('input[aria-label="订单数量"]').setValue('888')
    await wrapper.get('input[aria-label="货号"]').setValue('20330204')
    await new Promise((resolve) => setTimeout(resolve, 260))
    await flushPromises()

    expect(cartonApiMock.searchOrderHistoryItems).toHaveBeenCalledWith(
      'huaxing',
      '20330204',
      'DICKIE',
    )
    expect(wrapper.get('[aria-label="历史货号候选"]').text()).toContain('前缀匹配')
    await wrapper.get('button[aria-label="复用历史货号 203302044 Dickie"]').trigger('mousedown')
    await flushPromises()

    expect((wrapper.get('input[aria-label="货号"]').element as HTMLInputElement).value).toBe('203302044')
    expect((wrapper.get('input[aria-label="产品名称"]').element as HTMLInputElement).value).toBe('消防车套装')
    expect((wrapper.get('select[aria-label="订单客户"]').element as HTMLSelectElement).value).toBe('DICKIE')
    expect((wrapper.get('input[aria-label="合同号"]').element as HTMLInputElement).value).toBe('SC-NEW-ORDER')
    expect((wrapper.get('input[aria-label="订单数量"]').element as HTMLInputElement).value).toBe('888')
    expect((wrapper.get('input[aria-label="纸质 1"]').element as HTMLInputElement).value).toBe('A33+B')
    expect((wrapper.get('input[aria-label="规格 2"]').element as HTMLInputElement).value).toBe('15.5 × 10.625 × 5.25')
    expect((wrapper.get('input[aria-label="每箱个数 2"]').element as HTMLInputElement).value).toBe('30')
    expect(wrapper.text()).toContain('本次合同、数量和日期仍需单独填写')
  })

  it('exports selected orders as one cumulative reconciliation workbook', async () => {
    const first = orderFixture('CT-COMBINE-001', businessDateOffset(4), 'CONFIRMED')
    const second = orderFixture('CT-COMBINE-002', businessDateOffset(6), 'PENDING_SUPPLIER')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([first, second])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    let downloadedFilename = ''
    const downloadSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloadedFilename = this.download
    })

    const wrapper = mountView('orders')
    await flushPromises()
    await wrapper.get('input[aria-label="选择订单 CT-COMBINE-001"]').setValue(true)
    await wrapper.get('input[aria-label="选择订单 CT-COMBINE-002"]').setValue(true)
    await findButton(wrapper, '导出累计对账表').trigger('click')
    await flushPromises()

    expect(cartonApiMock.exportPurchaseOrders).toHaveBeenCalledWith(
      'huaxing',
      expect.arrayContaining(['CT-COMBINE-001', 'CT-COMBINE-002']),
    )
    expect(downloadedFilename).toMatch(/^纸箱累计对账表_\d{4}-\d{2}-\d{2}\.xlsx$/)
    expect(downloadedFilename).not.toContain('.zip')
    expect(wrapper.text()).toContain('已将 2 张订单合并导出为累计对账表')
    expect(wrapper.get('[role="status"]').text()).toContain('已将 2 张订单合并为累计对账表，文件已开始下载')
    expect(wrapper.get('[role="status"]').text()).toContain('不代表新增下单')
    downloadSpy.mockRestore()
  })

  it('issues a selected batch using only orders with pending supplier changes', async () => {
    const first = orderFixture('CT-BATCH-ISSUE-001', businessDateOffset(4), 'PENDING_SUPPLIER')
    const second = orderFixture('CT-BATCH-ISSUE-002', businessDateOffset(6), 'COMPLETED')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([first, second])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.issuePurchaseOrders.mockResolvedValue({
      blob: new Blob(['issued-batch-xlsx']),
      issueCount: 1,
    })
    let downloadedFilename = ''
    const downloadSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloadedFilename = this.download
    })

    const wrapper = mountView('orders')
    await flushPromises()
    await wrapper.get('input[aria-label="选择订单 CT-BATCH-ISSUE-001"]').setValue(true)
    await wrapper.get('input[aria-label="选择订单 CT-BATCH-ISSUE-002"]').setValue(true)
    await findButton(wrapper, '发行供应商采购单（2）').trigger('click')
    await flushPromises()

    expect(cartonApiMock.issuePurchaseOrders).toHaveBeenCalledWith(
      'huaxing',
      expect.arrayContaining([
        expect.objectContaining({ order_no: 'CT-BATCH-ISSUE-001', revision: 1 }),
        expect.objectContaining({ order_no: 'CT-BATCH-ISSUE-002', revision: 1 }),
      ]),
    )
    expect(downloadedFilename).toMatch(/^供应商采购单批次_\d{4}-\d{2}-\d{2}\.xlsx$/)
    expect(wrapper.get('[role="status"]').text()).toContain('批次文件包含 1 份供应商采购单')
    expect(wrapper.get('[role="status"]').text()).toContain('跳过 1 张既无变化也无历史采购单的订单')
    downloadSpy.mockRestore()
  })

  it('soft-confirms a selected batch that contains a non-initial supplier document', async () => {
    const initialOrder = orderFixture('CT-BATCH-INITIAL', businessDateOffset(4), 'PENDING_SUPPLIER')
    const appendOrder = orderFixture('CT-BATCH-APPEND', businessDateOffset(6), 'PARTIALLY_RECEIVED')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([initialOrder, appendOrder])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.getPurchaseOrderContext.mockImplementation(async (_factoryId: string, orderNo: string) => ({
      factory_id: 'huaxing',
      order_no: orderNo,
      order_revision: 1,
      pending_type: orderNo === appendOrder.order_no ? 'APPEND' : 'INITIAL',
      pending_product_quantity: orderNo === appendOrder.order_no ? '100' : '1000',
      pending_line_count: 1,
      can_generate: true,
      latest_document_no: orderNo === appendOrder.order_no ? `${orderNo}-P00` : '',
      historical_baseline: false,
      issues: [],
    }))
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)

    const wrapper = mountView('orders')
    await flushPromises()
    await wrapper.get(`input[aria-label="选择订单 ${initialOrder.order_no}"]`).setValue(true)
    await wrapper.get(`input[aria-label="选择订单 ${appendOrder.order_no}"]`).setValue(true)
    const issueButton = findButton(wrapper, '发行供应商采购单（2）')

    await issueButton.trigger('click')
    await flushPromises()
    expect(confirmSpy).toHaveBeenLastCalledWith(expect.stringContaining('包含 1 张非首次或已发行采购单'))
    expect(confirmSpy).toHaveBeenLastCalledWith(expect.stringContaining(`${appendOrder.order_no}（追加采购单）`))
    expect(cartonApiMock.issuePurchaseOrders).not.toHaveBeenCalled()
    expect(wrapper.get('[role="status"]').text()).toContain('已取消批量发行')

    await issueButton.trigger('click')
    await flushPromises()
    expect(cartonApiMock.issuePurchaseOrders).toHaveBeenCalledWith(
      'huaxing',
      expect.arrayContaining([initialOrder, appendOrder]),
    )
    confirmSpy.mockRestore()
  })

  it('soft-confirms and re-batches latest immutable snapshots when selected orders have no new change', async () => {
    const first = orderFixture('CT-BATCH-REUSE-001', businessDateOffset(4), 'PARTIALLY_RECEIVED')
    const second = orderFixture('CT-BATCH-REUSE-002', businessDateOffset(6), 'COMPLETED')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([first, second])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.getPurchaseOrderContext.mockImplementation(async (_factoryId: string, orderNo: string) => ({
      factory_id: 'huaxing',
      order_no: orderNo,
      order_revision: 1,
      pending_type: 'NONE',
      pending_product_quantity: '0',
      pending_line_count: 0,
      can_generate: false,
      latest_document_no: `${orderNo}-P00`,
      historical_baseline: false,
      issues: [{
        id: `ISSUE-${orderNo}`,
        factory_id: 'huaxing',
        order_no: orderNo,
        document_no: `${orderNo}-P00`,
        document_type: 'INITIAL',
        issue_sequence: 1,
        source_order_revision: 1,
        before_product_quantity: '0',
        after_product_quantity: '100',
        product_quantity_delta: '100',
        generated_by: 'admin',
        generated_by_name: '系统管理员',
        generated_at: '2026-09-04T10:00:00+08:00',
      }],
    }))
    cartonApiMock.issuePurchaseOrders.mockResolvedValue({
      blob: new Blob(['reused-batch-xlsx']),
      issueCount: 2,
    })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mountView('orders')
    await flushPromises()
    await wrapper.get(`input[aria-label="选择订单 ${first.order_no}"]`).setValue(true)
    await wrapper.get(`input[aria-label="选择订单 ${second.order_no}"]`).setValue(true)
    await findButton(wrapper, '发行供应商采购单（2）').trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('2 张没有新变化、将重新打包最近一次历史快照'))
    expect(cartonApiMock.issuePurchaseOrders).toHaveBeenCalledWith('huaxing', expect.arrayContaining([first, second]))
    expect(wrapper.get('[role="status"]').text()).toContain('重新打包历史快照 2 份')
    confirmSpy.mockRestore()
  })

  it('issues only the pending supplier delta and keeps immutable purchase-order history', async () => {
    const order = orderFixture('CT-ISSUE-001', businessDateOffset(6), 'PENDING_SUPPLIER')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([order])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    const initialIssue = {
      id: 'CPI-INITIAL',
      factory_id: 'huaxing',
      order_no: order.order_no,
      document_no: `${order.order_no}-P00`,
      document_type: 'INITIAL',
      issue_sequence: 1,
      source_order_revision: 1,
      before_product_quantity: '0',
      after_product_quantity: '2100',
      product_quantity_delta: '2100',
      generated_by: 'admin',
      generated_by_name: '系统管理员',
      generated_at: '2026-09-04T10:00:00+08:00',
    }
    const pendingContext = {
      factory_id: 'huaxing',
      order_no: order.order_no,
      order_revision: 1,
      pending_type: 'APPEND',
      pending_product_quantity: '1000',
      pending_line_count: 1,
      can_generate: true,
      latest_document_no: initialIssue.document_no,
      historical_baseline: true,
      issues: [initialIssue],
    }
    cartonApiMock.getPurchaseOrderContext
      .mockResolvedValueOnce(pendingContext)
      .mockResolvedValueOnce({
        ...pendingContext,
        pending_type: 'NONE',
        pending_product_quantity: '0',
        pending_line_count: 0,
        can_generate: false,
        latest_document_no: `${order.order_no}-A01`,
        issues: [{
          ...initialIssue,
          id: 'CPI-APPEND',
          document_no: `${order.order_no}-A01`,
          document_type: 'APPEND',
          issue_sequence: 2,
          before_product_quantity: '2100',
          after_product_quantity: '3100',
          product_quantity_delta: '1000',
        }, initialIssue],
      })
    cartonApiMock.issuePurchaseOrder.mockResolvedValue({
      blob: new Blob(['append-xlsx']),
      documentNo: `${order.order_no}-A01`,
    })

    const wrapper = mountView('orders')
    await flushPromises()
    await openOrderMoreActions(wrapper.get(`[data-order-no="${order.order_no}"]`), order.order_no)
    await wrapper.get(`button[aria-label="管理 ${order.order_no} 采购单"]`).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('系统升级前的当前累计数量已登记为历史基线')
    expect(wrapper.text()).toContain('追加采购单')
    expect(wrapper.text()).toContain('产品数量变化 +1,000')
    expect(wrapper.text()).toContain(initialIssue.document_no)
    await findButton(wrapper, '生成并下载追加采购单').trigger('click')
    await flushPromises()

    expect(cartonApiMock.issuePurchaseOrder).toHaveBeenCalledWith('huaxing', order)
    expect(wrapper.text()).toContain(`${order.order_no}-A01 追加采购单已固定生成并开始下载`)
    expect(wrapper.text()).toContain('当前累计数量与最近一次采购单快照一致')
  })

  it('explains beside the batch export control when only offline demo orders are available', async () => {
    const wrapper = mountView('orders')
    await flushPromises()
    await wrapper.get('input[aria-label="选择订单 CT-260731-018"]').setValue(true)

    const exportButton = findButton(wrapper, '导出累计对账表')
    expect(exportButton.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[role="status"]').text()).toContain('后端未连接，当前演示订单不能导出')
    expect(cartonApiMock.exportPurchaseOrders).not.toHaveBeenCalled()
  })

  it('shows a batch export failure beside the button at the current scroll position', async () => {
    const order = orderFixture('CT-EXPORT-FAIL', businessDateOffset(4), 'CONFIRMED')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([order])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.exportPurchaseOrders.mockRejectedValue(new Error('订单已不存在'))

    const wrapper = mountView('orders')
    await flushPromises()
    await wrapper.get('input[aria-label="选择订单 CT-EXPORT-FAIL"]').setValue(true)
    await findButton(wrapper, '导出累计对账表').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toContain('合并导出失败：订单已不存在')
    expect(wrapper.get('[role="status"]').text()).toContain('请刷新订单列表后重试')
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
      customer_due_date: payload.customer_due_date,
      due_date: payload.due_date,
      note: payload.note,
      revision: current.revision + 1,
    }))
    cartonApiMock.cancelOrder.mockImplementation(async (_factoryId: string, current: any) => {
      const cancelled = {
        ...current,
        status: 'CANCELLED',
        revision: current.revision + 1,
      }
      cartonApiMock.listOrders.mockResolvedValue([cancelled])
      return cancelled
    })

    const wrapper = mountView('orders')
    await flushPromises()

    await openOrderMoreActions(wrapper.get('[data-order-no="CT-CONTROLLED"]'), 'CT-CONTROLLED')
    await wrapper.get('button[aria-label="修改 CT-CONTROLLED 订单"]').trigger('click')
    expect(wrapper.text()).toContain('修改纸箱合同订单 CT-CONTROLLED')
    expect(wrapper.get('input[aria-label="合同号"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('input[aria-label="客户交期"]').setValue(businessDateOffset(10))
    await wrapper.get('textarea[aria-label="订单修改原因"]').setValue('客户确认调整计划交期')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(cartonApiMock.updateOrder).toHaveBeenCalledWith(
      expect.objectContaining({ order_no: 'CT-CONTROLLED', revision: 1 }),
      expect.objectContaining({
        contract_no: 'SC-CT-CONTROLLED',
        customer_due_date: businessDateOffset(10),
        due_date: businessDateOffset(7),
        reason: '客户确认调整计划交期',
      }),
    )
    expect(wrapper.text()).toContain('已按原因完成第 2 版修订')

    await openOrderMoreActions(wrapper.get('[data-order-no="CT-CONTROLLED"]'), 'CT-CONTROLLED')
    await wrapper.get('button[aria-label="取消 CT-CONTROLLED"]').trigger('click')
    await wrapper.get('textarea[aria-label="订单取消退单原因"]').setValue('客户正式取消该合同')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(cartonApiMock.cancelOrder).toHaveBeenCalledWith(
      'huaxing',
      expect.objectContaining({ order_no: 'CT-CONTROLLED', revision: 2 }),
      '客户正式取消该合同',
    )
    expect(wrapper.text()).toContain('已取消并保留审计记录')
    expect(wrapper.get('[data-order-no="CT-CONTROLLED"]').text()).toContain('已取消')
  })

  it('submits a confirmed order to the supplier, locks actions, and opens receipt entry', async () => {
    const confirmedOrder = orderFixture('CT-SUBMIT', businessDateOffset(5), 'CONFIRMED')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([confirmedOrder])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.submitOrderToSupplier.mockImplementation(async (_factoryId: string, current: any) => ({
      ...current,
      status: 'PENDING_SUPPLIER',
      revision: current.revision + 1,
    }))

    const wrapper = mountView('orders')
    await flushPromises()
    const orderCard = () => wrapper.get('[data-order-no="CT-SUBMIT"]')

    expect(orderCard().find('button[aria-label="登记 CT-SUBMIT 收料"]').exists()).toBe(false)
    await orderCard().get('button[aria-label="确认订单 CT-SUBMIT 并锁定"]').trigger('click')
    expect(wrapper.text()).toContain('锁定普通编辑')
    await wrapper.get('button[aria-label="执行确认订单并锁定"]').trigger('click')
    await flushPromises()

    expect(cartonApiMock.submitOrderToSupplier).toHaveBeenCalledWith(
      'huaxing',
      expect.objectContaining({ order_no: 'CT-SUBMIT', revision: 1 }),
    )
    expect(orderCard().text()).toContain('已确认锁定')
    expect(orderCard().find('button[aria-label="修改 CT-SUBMIT 订单"]').exists()).toBe(false)
    await openOrderMoreActions(orderCard(), 'CT-SUBMIT')
    expect(orderCard().find('button[aria-label="追加 CT-SUBMIT 订单"]').exists()).toBe(true)
    expect(orderCard().find('button[aria-label="减单 CT-SUBMIT"]').exists()).toBe(true)
    expect(orderCard().find('button[aria-label="取消 CT-SUBMIT"]').exists()).toBe(false)
    expect(orderCard().find('button[aria-label="登记 CT-SUBMIT 收料"]').exists()).toBe(true)
  })

  it('allows a supervisor to append, reduce, and fully return a submitted order', async () => {
    const submitted = orderFixture('CT-ADJUST', businessDateOffset(5), 'PENDING_SUPPLIER')
    const appended = { ...submitted, product_order_quantity: '4200', revision: 2 }
    const reduced = { ...appended, product_order_quantity: '3600', revision: 3 }
    const returned = {
      ...reduced,
      status: 'CANCELLED',
      revision: 4,
    }
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders
      .mockResolvedValueOnce([submitted])
      .mockResolvedValueOnce([appended])
      .mockResolvedValueOnce([reduced])
      .mockResolvedValueOnce([returned])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.appendOrder.mockResolvedValue(appended)
    cartonApiMock.reduceOrder.mockResolvedValueOnce(reduced).mockResolvedValueOnce(returned)

    const wrapper = mountView('orders')
    await flushPromises()

    await openOrderMoreActions(wrapper.get('[data-order-no="CT-ADJUST"]'), 'CT-ADJUST')
    await wrapper.get('button[aria-label="追加 CT-ADJUST 订单"]').trigger('click')
    expect((wrapper.get('textarea[aria-label="追加订单原因"]').element as HTMLTextAreaElement).value).toBe('客人追加订单')
    await wrapper.get('input[aria-label="追加订单数量"]').setValue(600)
    await wrapper.get('[data-testid="append-order-form"]').trigger('submit')
    await flushPromises()
    expect(cartonApiMock.appendOrder).toHaveBeenCalledWith(
      'huaxing',
      expect.objectContaining({ order_no: 'CT-ADJUST', status: 'PENDING_SUPPLIER' }),
      600,
      '客人追加订单',
      submitted.due_date,
      submitted.customer_due_date,
    )

    await openOrderMoreActions(wrapper.get('[data-order-no="CT-ADJUST"]'), 'CT-ADJUST')
    await wrapper.get('button[aria-label="减单 CT-ADJUST"]').trigger('click')
    expect((wrapper.get('textarea[aria-label="减单原因"]').element as HTMLTextAreaElement).value).toBe('客人退单')
    await wrapper.get('input[aria-label="减单数量"]').setValue(600)
    await wrapper.get('[data-testid="reduce-order-form"]').trigger('submit')
    await flushPromises()
    expect(cartonApiMock.reduceOrder).toHaveBeenNthCalledWith(
      1,
      'huaxing',
      expect.objectContaining({ order_no: 'CT-ADJUST', revision: 2 }),
      600,
      '客人退单',
    )
    expect(wrapper.text()).toContain('已减少 600 件')

    await openOrderMoreActions(wrapper.get('[data-order-no="CT-ADJUST"]'), 'CT-ADJUST')
    await wrapper.get('button[aria-label="减单 CT-ADJUST"]').trigger('click')
    await wrapper.get('input[aria-label="减单数量"]').setValue(3600)
    await wrapper.get('textarea[aria-label="减单原因"]').setValue('主管确认客户整张订单退单')
    await wrapper.get('[data-testid="reduce-order-form"]').trigger('submit')
    await flushPromises()
    expect(cartonApiMock.reduceOrder).toHaveBeenNthCalledWith(
      2,
      'huaxing',
      expect.objectContaining({ order_no: 'CT-ADJUST', revision: 3 }),
      3600,
      '主管确认客户整张订单退单',
    )
    expect(wrapper.get('[data-order-no="CT-ADJUST"]').text()).toContain('已取消')
  })

  it('allows supervisor append after receipt or completion and exposes only reducible balance', async () => {
    const partial = {
      ...orderFixture('CT-PARTIAL-APPEND', businessDateOffset(5), 'PARTIALLY_RECEIVED'),
      lines: [{
        ...orderFixture('CT-PARTIAL-APPEND', businessDateOffset(5), 'PARTIALLY_RECEIVED').lines[0],
        received_quantity: '40',
        remaining_quantity: '60',
      }],
    }
    const completed = orderFixture('CT-COMPLETED-APPEND', businessDateOffset(6), 'COMPLETED')
    const reopened = {
      ...completed,
      status: 'PARTIALLY_RECEIVED',
      product_order_quantity: '160',
      revision: 2,
      lines: [{
        ...completed.lines[0],
        required_quantity: '160',
        received_quantity: '100',
        remaining_quantity: '60',
      }],
    }
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders
      .mockResolvedValueOnce([partial, completed])
      .mockResolvedValueOnce([partial, reopened])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.appendOrder.mockResolvedValue(reopened)

    const wrapper = mountView('orders')
    await flushPromises()

    const partialCard = wrapper.get('[data-order-no="CT-PARTIAL-APPEND"]')
    const completedCard = wrapper.get('[data-order-no="CT-COMPLETED-APPEND"]')
    await openOrderMoreActions(partialCard, 'CT-PARTIAL-APPEND')
    expect(partialCard.find('button[aria-label="追加 CT-PARTIAL-APPEND 订单"]').exists()).toBe(true)
    expect(partialCard.get('button[aria-label="减单 CT-PARTIAL-APPEND"]').text()).toContain('减少未入库量')
    await openOrderMoreActions(completedCard, 'CT-COMPLETED-APPEND')
    expect(completedCard.find('button[aria-label="追加 CT-COMPLETED-APPEND 订单"]').exists()).toBe(true)
    expect(completedCard.find('button[aria-label="减单 CT-COMPLETED-APPEND"]').exists()).toBe(false)

    await completedCard.get('button[aria-label="追加 CT-COMPLETED-APPEND 订单"]').trigger('click')
    expect(wrapper.get('[data-testid="append-order-form"]').text()).toContain('追加后会自动恢复为“部分到货”')
    await wrapper.get('input[aria-label="追加订单数量"]').setValue(60)
    await wrapper.get('input[aria-label="追加订单客户交期"]').setValue(businessDateOffset(12))
    expect((wrapper.get('input[aria-label="追加订单计划交期"]').element as HTMLInputElement).value).toBe(businessDateOffset(9))
    await wrapper.get('textarea[aria-label="追加订单原因"]').setValue('全部到货后客户追加六十套')
    await wrapper.get('[data-testid="append-order-form"]').trigger('submit')
    await flushPromises()

    expect(cartonApiMock.appendOrder).toHaveBeenCalledWith(
      'huaxing',
      expect.objectContaining({ order_no: 'CT-COMPLETED-APPEND', status: 'COMPLETED' }),
      60,
      '全部到货后客户追加六十套',
      businessDateOffset(9),
      businessDateOffset(12),
    )
    expect(wrapper.text()).toContain('已恢复为“部分到货”')
    expect(wrapper.get('[data-order-no="CT-COMPLETED-APPEND"]').text()).toContain('部分收料')
    await openOrderMoreActions(wrapper.get('[data-order-no="CT-COMPLETED-APPEND"]'), 'CT-COMPLETED-APPEND')
    expect(wrapper.get('[data-order-no="CT-COMPLETED-APPEND"]').find('button[aria-label="减单 CT-COMPLETED-APPEND"]').exists()).toBe(true)
  })

  it('reserves pending receipt quantity when calculating the maximum reduction', async () => {
    const submitted = orderFixture('CT-PENDING-RECEIPT', businessDateOffset(5), 'PENDING_SUPPLIER')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([submitted])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.listReceipts.mockResolvedValue([{
      id: 'RECEIPT-PENDING',
      status: 'PENDING_CONFIRMATION',
      lines: [{ order_line_id: submitted.lines[0].id, effective_quantity: '40' }],
    }])

    const wrapper = mountView('orders')
    await flushPromises()
    const card = wrapper.get('[data-order-no="CT-PENDING-RECEIPT"]')
    await openOrderMoreActions(card, 'CT-PENDING-RECEIPT')
    expect(card.find('button[aria-label="追加 CT-PENDING-RECEIPT 订单"]').exists()).toBe(true)
    await card.get('button[aria-label="减单 CT-PENDING-RECEIPT"]').trigger('click')
    const quantityInput = wrapper.get('input[aria-label="减单数量"]')
    expect(quantityInput.attributes('max')).toBe('60')
    expect(wrapper.get('[data-testid="reduce-order-form"]').text()).toContain('最大可减60')
  })

  it('reduces the unreceived balance and closes a partially received order', async () => {
    const partial = {
      ...orderFixture('CT-PARTIAL-REDUCE', businessDateOffset(5), 'PARTIALLY_RECEIVED'),
      lines: [{
        ...orderFixture('CT-PARTIAL-REDUCE', businessDateOffset(5), 'PARTIALLY_RECEIVED').lines[0],
        received_quantity: '40',
        remaining_quantity: '60',
      }],
    }
    const completed = {
      ...partial,
      status: 'COMPLETED',
      product_order_quantity: '40',
      revision: 2,
      lines: [{
        ...partial.lines[0],
        required_quantity: '40',
        remaining_quantity: '0',
      }],
    }
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders
      .mockResolvedValueOnce([partial])
      .mockResolvedValueOnce([completed])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.reduceOrder.mockResolvedValue(completed)

    const wrapper = mountView('orders')
    await flushPromises()
    await openOrderMoreActions(wrapper.get('[data-order-no="CT-PARTIAL-REDUCE"]'), 'CT-PARTIAL-REDUCE')
    await wrapper.get('button[aria-label="减单 CT-PARTIAL-REDUCE"]').trigger('click')
    const form = wrapper.get('[data-testid="reduce-order-form"]')
    expect(form.text()).toContain('减少未入库量')
    expect(form.text()).toContain('最大可减60')
    await wrapper.get('input[aria-label="减单数量"]').setValue(60)
    await wrapper.get('textarea[aria-label="减单原因"]').setValue('客户取消全部未入库数量')
    await form.trigger('submit')
    await flushPromises()

    expect(cartonApiMock.reduceOrder).toHaveBeenCalledWith(
      'huaxing',
      expect.objectContaining({ order_no: 'CT-PARTIAL-REDUCE', status: 'PARTIALLY_RECEIVED' }),
      60,
      '客户取消全部未入库数量',
    )
    expect(wrapper.text()).toContain('状态转为“全部到货”')
    const completedCard = wrapper.get('[data-order-no="CT-PARTIAL-REDUCE"]')
    expect(completedCard.text()).toContain('已完成')
    expect(completedCard.find('button[aria-label="减单 CT-PARTIAL-REDUCE"]').exists()).toBe(false)
  })

  it('hides submitted-order adjustments without supervisor permission', async () => {
    const submitted = orderFixture('CT-NO-ADJUST', businessDateOffset(5), 'PENDING_SUPPLIER')
    authStoreMock.can.mockImplementation((permission: string) => permission !== 'carton_procurement:order_adjust')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([submitted])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])

    const wrapper = mountView('orders')
    await flushPromises()
    const card = wrapper.get('[data-order-no="CT-NO-ADJUST"]')
    await openOrderMoreActions(card, 'CT-NO-ADJUST')
    expect(card.find('button[aria-label="管理 CT-NO-ADJUST 采购单"]').exists()).toBe(true)
    expect(card.find('button[aria-label="追加 CT-NO-ADJUST 订单"]').exists()).toBe(false)
    expect(card.find('button[aria-label="减单 CT-NO-ADJUST"]').exists()).toBe(false)
  })

  it('bulk submits only pending orders and keeps skipped selections', async () => {
    const pendingOrder = orderFixture('CT-BULK-PENDING', businessDateOffset(5), 'CONFIRMED')
    const submittedOrder = orderFixture('CT-BULK-SUBMITTED', businessDateOffset(6), 'PENDING_SUPPLIER')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([pendingOrder, submittedOrder])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.bulkSubmitOrdersToSupplier.mockResolvedValue([{
      ...pendingOrder,
      status: 'PENDING_SUPPLIER',
      revision: pendingOrder.revision + 1,
    }])

    const wrapper = mountView('orders')
    await flushPromises()
    await wrapper.get('input[aria-label="选择订单 CT-BULK-PENDING"]').setValue(true)
    await wrapper.get('input[aria-label="选择订单 CT-BULK-SUBMITTED"]').setValue(true)

    await findButton(wrapper, '确认订单并锁定（1）').trigger('click')
    expect(wrapper.text()).toContain('批量确认并锁定 1 张待下单订单')
    await wrapper.get('button[aria-label="执行确认订单并锁定"]').trigger('click')
    await flushPromises()

    expect(cartonApiMock.bulkSubmitOrdersToSupplier).toHaveBeenCalledWith(
      'huaxing',
      expect.arrayContaining([
        expect.objectContaining({ order_no: 'CT-BULK-PENDING' }),
        expect.objectContaining({ order_no: 'CT-BULK-SUBMITTED' }),
      ]),
    )
    expect(wrapper.text()).toContain('已确认并锁定 1 张订单；跳过 1 张非待下单订单')
    expect(wrapper.get('[data-order-no="CT-BULK-PENDING"]').text()).toContain('已确认锁定')
    expect((wrapper.get('input[aria-label="选择订单 CT-BULK-SUBMITTED"]').element as HTMLInputElement).checked).toBe(true)
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
        usage_quantity: '120',
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
    expect(wrapper.find('[data-order-no="HIST-2025-001"]').exists()).toBe(true)
    expect(wrapper.get('[data-order-no="HIST-2025-001"]').text()).not.toContain('HIST-2025-001')
  })

  it('calculates effective receipts in the dialog without posting inventory', async () => {
    mockReceiptWorkspace([orderFixture('CT-DAMAGE', businessDateOffset(3), 'PENDING_SUPPLIER')])
    const wrapper = mountView('receipts')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="登记 CT-DAMAGE 收料"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('收料反馈明细')
    await wrapper.get('input[aria-label="MANUAL-LINE-CT-DAMAGE 破损"]').setValue('2')
    await wrapper.get('input[aria-label="MANUAL-LINE-CT-DAMAGE 拒收"]').setValue('3')
    expect(wrapper.get('[role="dialog"]').text()).toContain('有效收料95')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    expect(cartonApiMock.confirmReceipt).not.toHaveBeenCalled()
    await findButton(wrapper, '保存待确认收料单').trigger('click')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('请先填写送货单号')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    wrapper.unmount()
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
      status: 'PENDING_SUPPLIER',
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
    expect(wrapper.text()).toContain('待收订单 1 张')
    expect(wrapper.text()).not.toContain('收料反馈明细')
    expect(wrapper.find('input[aria-label="人工送货单号"]').exists()).toBe(false)
    expect(wrapper.get('[data-receipt-order="CT-260805-76C698"]').text()).toContain('3722111')
    expect(wrapper.get('[data-receipt-order="CT-260805-76C698"]').text()).toContain('纸品合计')
    expect(wrapper.get('[data-receipt-order="CT-260805-76C698"]').text()).toContain('3,600')
    await wrapper.get('button[aria-label="查看 CT-260805-76C698 完整订单明细"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('12*11*5')
    await wrapper.get('button[aria-label="关闭订单明细"]').trigger('click')
    await findButton(wrapper, '切换导入模式').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('人工录入订单收料')
    expect(wrapper.text()).toContain('等待导入并复核送货单')
    expect(findButton(wrapper, '导入送货单').exists()).toBe(true)
    await findButton(wrapper, '返回待收订单').trigger('click')
    expect(wrapper.findAll('button').some((button) => button.text() === '人工录入收料')).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text() === '导入送货单')).toBe(false)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="登记 CT-260805-76C698 收料"]').trigger('click')

    expect(wrapper.text()).toContain('人工录入订单收料')
    expect(wrapper.text()).toContain('CT-260805-76C698')
    expect(wrapper.text()).toContain('全部收齐，确认后自动完成')
    await findButton(wrapper, '保存待确认收料单').trigger('click')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').attributes('role')).toBe('alert')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('请先填写送货单号')
    expect(wrapper.get('input[aria-label="人工送货单号"]').attributes('aria-invalid')).toBe('true')

    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-MANUAL-260811-001')
    await wrapper.get('input[aria-label="MANUAL-CTL-MANUAL-001 仓位"]').setValue('A-01')
    await wrapper.get('button[aria-label="关闭收料录入"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('收料反馈明细')
    await findButton(wrapper, '登记所选订单收料').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="人工送货单号"]').element.value).toBe('DN-MANUAL-260811-001')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="MANUAL-CTL-MANUAL-001 仓位"]').element.value).toBe('A-01')
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

  it('sorts pending receipts by planned due date while preserving selection', async () => {
    mockReceiptWorkspace([
      { ...orderFixture('CT-LATER', businessDateOffset(8), 'PENDING_SUPPLIER'), customer_due_date: businessDateOffset(1) },
      orderFixture('CT-OVERDUE', businessDateOffset(-2), 'PENDING_SUPPLIER'),
      orderFixture('CT-SOON', businessDateOffset(2), 'PARTIALLY_RECEIVED'),
    ])
    const wrapper = mountView('receipts')
    await flushPromises()
    const orderNos = () => wrapper.findAll('[data-receipt-order]').map((row) => row.attributes('data-receipt-order'))
    expect(orderNos()).toEqual(['CT-OVERDUE', 'CT-SOON', 'CT-LATER'])
    await wrapper.get('input[aria-label="选择 CT-SOON 待收订单"]').setValue(true)
    await wrapper.get('select[aria-label="待收订单排序"]').setValue('DUE_DESC')
    expect(orderNos()).toEqual(['CT-LATER', 'CT-SOON', 'CT-OVERDUE'])
    expect(wrapper.get<HTMLInputElement>('input[aria-label="选择 CT-SOON 待收订单"]').element.checked).toBe(true)
    await wrapper.get('select[aria-label="待收订单排序"]').setValue('DEFAULT')
    expect(orderNos()).toEqual(['CT-LATER', 'CT-OVERDUE', 'CT-SOON'])
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
  })

  it('filters pending order cards and opens all selected orders in the receipt dialog', async () => {
    mockReceiptWorkspace([
      orderFixture('CT-ALPHA', businessDateOffset(3), 'PENDING_SUPPLIER'),
      { ...orderFixture('CT-BETA', businessDateOffset(4), 'PARTIALLY_RECEIVED'), customer_code: 'BETA', customer_name: 'Beta' },
      orderFixture('CT-UNSUBMITTED', businessDateOffset(3)),
    ])
    const wrapper = mountView('receipts')
    await flushPromises()
    expect(wrapper.findAll('[data-receipt-order]')).toHaveLength(2)
    await wrapper.get('select[aria-label="待收订单客户筛选"]').setValue('Beta')
    expect(wrapper.find('select[aria-label="客户筛选"]').exists()).toBe(false)
    expect(wrapper.get('[data-receipt-order]').attributes('data-receipt-order')).toBe('CT-BETA')
    await wrapper.get('button[aria-label="选择计划交期范围"]').trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, businessDateOffset(0))
    expect(wrapper.text()).toContain('请选择结束日期')
    expect(wrapper.findAll('[data-receipt-order]')).toHaveLength(1)
    await clickCalendarDate(wrapper, businessDateOffset(3))
    expect(wrapper.find('[data-testid="date-range-calendar"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-receipt-order]')).toHaveLength(0)
    await findButton(wrapper, '清除筛选').trigger('click')
    await wrapper.get('button[aria-label="选择计划交期范围"]').trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, businessDateOffset(3))
    await clickCalendarDate(wrapper, businessDateOffset(3))
    expect(wrapper.find('[data-testid="date-range-calendar"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-receipt-order]')).toHaveLength(1)
    expect(wrapper.get('[data-receipt-order]').attributes('data-receipt-order')).toBe('CT-ALPHA')
    await wrapper.get('input[aria-label="全选待收订单"]').setValue(true)
    await findButton(wrapper, '登记所选订单收料').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('CT-ALPHA')
    expect(wrapper.get('[role="dialog"]').text()).not.toContain('CT-BETA')
    await wrapper.get('button[aria-label="关闭收料录入"]').trigger('click')
    await flushPromises()
    await wrapper.get('button[aria-label="选择计划交期范围"]').trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, businessDateOffset(4))
    expect(wrapper.findAll('[data-receipt-order]')).toHaveLength(1)
    await clickCalendarDate(wrapper, businessDateOffset(3))
    expect(wrapper.find('[data-testid="date-range-calendar"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-receipt-order]')).toHaveLength(2)
    await findButton(wrapper, '清除筛选').trigger('click')
    expect(wrapper.findAll('[data-receipt-order]')).toHaveLength(2)
    await wrapper.get('input[aria-label="全选待收订单"]').setValue(true)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('ITEM-CT-ALPHA')
    expect(wrapper.findAll('[data-receipt-order]')).toHaveLength(1)
    expect(wrapper.get('[data-receipt-order]').attributes('data-receipt-order')).toBe('CT-ALPHA')
    await findButton(wrapper, '登记所选订单收料').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('CT-ALPHA')
    expect(wrapper.get('[role="dialog"]').text()).toContain('CT-BETA')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    wrapper.unmount()
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
        parser_version: 'delivery-note-local-v5',
        row_count: 18,
        matched_count: 0,
        issue_count: 18,
        warnings: ['图片/PDF 仅作为 OCR 预览，数量和纸品字段必须逐行人工复核'],
        document: { delivery_note_no: 'DN26061301', delivery_date: '2013-06-26', raw_text_excerpt: 'SC700145011/3600 203302038 外箱 A33+B 31.5 x 11.125 x 11.25 10' },
        rows: [{
          source_sheet: 'OCR',
          source_row: 1,
          delivery_note_no: 'DN26061301',
          contract_no: 'SC700145011/3600',
          item_no: '203302038',
          packaging_type: '待复核',
          paper_quality: '待复核',
          specification: '31.5 × 11.125 × 11.25 in',
          delivered_quantity: 0,
          match_status: 'MISSING_ORDER',
          suggestion: '未找到可关联的正式订单明细',
        }],
      },
    })

    const wrapper = mountView('receipts')
    await flushPromises()
    await findButton(wrapper, '切换导入模式').trigger('click')
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
    expect(wrapper.text()).toContain('已识别 18 行送货明细，但没有找到可关联的正式纸箱订单')
    expect(wrapper.text()).toContain('SC700145011/3600')
    expect(wrapper.text()).toContain('31.5 × 11.125 × 11.25 in')
    expect(wrapper.text()).toContain('识别诊断详情（OCR 原文、引擎与警告）')
    expect(wrapper.text()).toContain('delivery-note-local-v5')
    expect(wrapper.text()).toContain('前往异常中心')
    expect(wrapper.text()).toContain('删除本次导入')
    expect(wrapper.text()).not.toContain('等待导入并复核送货单')

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    await findButton(wrapper, '删除本次导入').trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('DN26061301.jpg'))
    expect(cartonApiMock.deleteReceiptImport).toHaveBeenCalledWith('huaxing', 'CIB-REAL-IMAGE')
    expect(wrapper.text()).toContain('派生异常已清理，订单、收料和库存未受影响')
    expect(wrapper.text()).not.toContain('送货单识别完成')
    expect(wrapper.text()).toContain('等待导入并复核送货单')
  })

  it('turns an unmatched delivery row into a human-gated ad hoc receipt', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([{
      id: 'CCU-DICKIE',
      factory_id: 'huaxing',
      customer_code: 'DICKIE',
      customer_name: 'Dickie',
      status: 'ACTIVE',
    }])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.uploadReceipt.mockResolvedValue({
      id: 'CIB-AD-HOC',
      factory_id: 'huaxing',
      import_type: 'DELIVERY_NOTE',
      original_filename: '打板送货单.xlsx',
      source_sha256: 'ad-hoc-hash',
      status: 'REQUIRES_REVIEW',
      duplicate: false,
      parse_summary: {
        engine: 'openpyxl',
        parser_version: 'delivery-note-local-v5',
        row_count: 1,
        matched_count: 0,
        issue_count: 1,
        document: { delivery_note_no: 'DN-SAMPLE-001', delivery_date: '2026-08-05' },
        rows: [{
          source_sheet: '送货单',
          source_row: 2,
          delivery_note_no: 'DN-SAMPLE-001',
          delivery_date: '2026-08-05',
          customer_name: 'Dickie',
          contract_no: 'SAMPLE-BOARD-001',
          item_no: 'SAMPLE-203399999',
          packaging_type: '打板外箱',
          paper_quality: 'A33+B',
          specification: '12 × 10 × 5 in',
          delivered_quantity: 5,
          unit_price: 2.5,
          unit: '个',
          location: 'S-01',
          match_status: 'MISSING_ORDER',
          suggestion: '未找到正式订单，可人工确认是否为非正式打板收料',
        }],
      },
    })
    cartonApiMock.createReceipt.mockResolvedValue({
      id: 'CTR-AD-HOC',
      receipt_no: 'RC-AD-HOC-001',
      status: 'PENDING_CONFIRMATION',
      revision: 1,
      lines: [],
    })
    cartonApiMock.confirmReceipt.mockResolvedValue({
      id: 'CTR-AD-HOC',
      receipt_no: 'RC-AD-HOC-001',
      status: 'POSTED',
      revision: 2,
      lines: [],
    })

    const wrapper = mountView('receipts')
    await flushPromises()
    await findButton(wrapper, '切换导入模式').trigger('click')
    await flushPromises()
    const input = wrapper.get('input[aria-label="选择送货单文件"]')
    const file = new File(['xlsx'], '打板送货单.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    await findButton(wrapper, '作为非正式/打板收料').trigger('click')
    expect(wrapper.text()).toContain('非正式 / 打板收料')
    expect(wrapper.get('select[aria-label="CIB-AD-HOC-送货单-2 客户"]').element.value).toBe('DICKIE')
    expect(wrapper.text()).toContain('保存后仍需再次人工确认才会入库并计入月结')

    await findButton(wrapper, '保存待确认收料单').trigger('click')
    await flushPromises()
    expect(cartonApiMock.createReceipt).toHaveBeenCalledWith(expect.objectContaining({
      delivery_note_no: 'DN-SAMPLE-001',
      import_batch_id: 'CIB-AD-HOC',
      lines: [expect.objectContaining({
        source_type: 'AD_HOC',
        order_line_id: null,
        customer_code: 'DICKIE',
        contract_no: 'SAMPLE-BOARD-001',
        item_no: 'SAMPLE-203399999',
        packaging_type: '打板外箱',
        received_quantity: 5,
      })],
    }))
    expect(wrapper.text()).toContain('尚未写入库存或月结')
    expect(wrapper.text()).toContain('确认入库并计入月结')

    await findButton(wrapper, '确认入库并计入月结').trigger('click')
    await flushPromises()
    expect(cartonApiMock.confirmReceipt).toHaveBeenCalledWith('huaxing', 'CTR-AD-HOC', 1)
    expect(wrapper.text()).toContain('已生成独立入库流水，并纳入对应月份月结')
  })

  it('shows OCR raw text and warnings when an imported image has zero structured rows', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.uploadReceipt.mockResolvedValue({
      id: 'CIB-ZERO-ROWS',
      factory_id: 'huaxing',
      import_type: 'DELIVERY_NOTE',
      original_filename: '微信图片.jpg',
      source_sha256: 'zero-rows',
      status: 'REQUIRES_REVIEW',
      duplicate: false,
      parse_summary: {
        engine: 'rapidocr-pp-ocrv6+pytesseract-fallback',
        parser_version: 'delivery-note-local-v5',
        row_count: 0,
        matched_count: 0,
        issue_count: 0,
        warnings: ['未找到四列表格边界，请核对图片方向和清晰度'],
        document: {
          delivery_note_no: 'DN26061301',
          delivery_date: '2026-06-13',
          raw_text_excerpt: 'DN26061301\nSC700145011/3600-203302038\n普通箱 A33+B\n31.5 x 11.125 x 11.25\n6',
        },
        rows: [],
      },
    })

    const wrapper = mountView('receipts')
    await flushPromises()
    await findButton(wrapper, '切换导入模式').trigger('click')
    await flushPromises()
    const input = wrapper.get('input[aria-label="选择送货单文件"]')
    expect(input.attributes('accept')).toContain('.heic')
    const file = new File(['unstructured-delivery-note'], '微信图片.jpg', { type: 'image/jpeg' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(wrapper.text()).toContain('文件已成功导入，但未解析出结构化送货明细')
    expect(wrapper.text()).toContain('OCR 识别原文')
    expect(wrapper.text()).toContain('SC700145011/3600-203302038')
    expect(wrapper.text()).toContain('未找到四列表格边界')
    expect(wrapper.text()).toContain('未解析出结构化明细；请查看上方“识别诊断详情”')
    expect(wrapper.text()).toContain('删除本次导入')
  })

  it('separates realtime inventory operations from period-end reconciliation', () => {
    const inventoryWrapper = mountView('inventory')
    expect(inventoryWrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(inventoryWrapper.find('input[aria-label="库存作业数量"]').exists()).toBe(false)
    expect(inventoryWrapper.find('a[download="纸箱历史库存导入模板.xlsx"]').exists()).toBe(false)
    expect(inventoryWrapper.text()).toContain('实时库存结存台账')
    expect(inventoryWrapper.text()).toContain('逐笔交易流水')
    expect(inventoryWrapper.text()).toContain('查看统一操作日志')
    expect(inventoryWrapper.text()).toContain('纸品类型')
    expect(inventoryWrapper.text()).toContain('纸质')

    const closingWrapper = mountView('closing')
    expect(closingWrapper.text()).toContain('期间月结与供应商对账页')
    expect(closingWrapper.text()).toContain('客户月结汇总快照')
    expect(closingWrapper.text()).toContain('不承担日常收发记录')
    expect(closingWrapper.text()).not.toContain('逐笔交易流水')
  })

  it('filters realtime inventory balances using header search and the selection toolbar', async () => {
    const wrapper = mountView('inventory')
    const balanceTable = wrapper.findAll('table').find((table) => table.text().includes('最近单据 / 变动'))
    if (!balanceTable) throw new Error('Inventory balance table not found')

    expect(balanceTable.findAll('tbody tr')).toHaveLength(4)
    expect(balanceTable.text()).toContain('OUT-260805-008')

    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('OUT-260805-008')
    expect(balanceTable.findAll('tbody tr')).toHaveLength(1)
    expect(balanceTable.text()).toContain('SC700140444')

    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('')
    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('300g 白卡')
    expect(balanceTable.findAll('tbody tr')).toHaveLength(1)
    expect(balanceTable.text()).toContain('203302038')
    expect(wrapper.find('input[aria-label="结存台账单号筛选"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="结存台账物料筛选"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="清空结存台账筛选"]').trigger('click')
    expect(wrapper.get<HTMLInputElement>('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').element.value).toBe('')
    expect(balanceTable.findAll('tbody tr')).toHaveLength(4)

    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('')
    await wrapper.get('button[aria-label="结存台账入库时间范围"]').trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, '2026-08-05')
    await clickCalendarDate(wrapper, '2026-08-05')
    expect(balanceTable.findAll('tbody tr')).toHaveLength(1)
    expect(balanceTable.text()).toContain('SC700142616')

    await wrapper.get('button[aria-label="清空结存台账筛选"]').trigger('click')
    expect(balanceTable.findAll('tbody tr')).toHaveLength(4)
  })

  it('filters balances by inbound time even after later movements and excludes unknown inbound dates', async () => {
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([
      { contract: 'IN-RANGE', inbound: '2026-08-05T10:00:00+08:00' },
      { contract: 'OUTSIDE-RANGE', inbound: '2026-08-04T10:00:00+08:00' },
      { contract: 'NO-INBOUND', inbound: null },
    ].map(({ contract, inbound }) => ({
      factory_id: 'huaxing', customer_code: '360', customer_name: '360',
      contract_no: contract, item_no: 'ITEM-1', order_line_id: null,
      packaging_type: '外箱', paper_quality: 'A33', specification: '1 × 1 × 1', unit: '个',
      balance: '10', latest_location: 'A-01', latest_movement_id: `MV-${contract}`,
      latest_document_no: `OUT-${contract}`, latest_movement_at: '2026-08-10T12:00:00+08:00',
      latest_inbound_at: inbound,
    })))
    const wrapper = mountView('inventory')
    await flushPromises()
    const table = wrapper.findAll('table').find((candidate) => candidate.text().includes('最近单据 / 变动'))!
    expect(table.findAll('tbody tr')).toHaveLength(3)
    expect(wrapper.text()).toContain('入库时间')
    expect(wrapper.text()).not.toContain('最近变动日期')
    await wrapper.get('button[aria-label="结存台账入库时间范围"]').trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, '2026-08-05')
    await clickCalendarDate(wrapper, '2026-08-05')
    expect(table.findAll('tbody tr')).toHaveLength(1)
    expect(table.text()).toContain('IN-RANGE')
    expect(table.text()).not.toContain('OUTSIDE-RANGE')
    expect(table.text()).not.toContain('NO-INBOUND')
    expect(table.text()).toContain('2026-08-10 12:00')
    await wrapper.get('button[aria-label="清空结存台账筛选"]').trigger('click')
    expect(table.findAll('tbody tr')).toHaveLength(3)
  })

  it('shows a unified operation log and filters it by time, operator, and action', async () => {
    const events = [
      { sequence: 4, id: 'CAE-4', factory_id: 'huaxing', event_type: 'ORDER_UPDATED', entity_type: 'carton_order', entity_id: 'CTO-4', detail: { order_no: 'CT-004', reason: '修改交期' }, actor_user_id: 'keeper', actor_name: '仓管员', created_at: '2026-08-05T10:00:00+08:00' },
      { sequence: 3, id: 'CAE-3', factory_id: 'huaxing', event_type: 'ORDER_SUBMITTED_SUPPLIER', entity_type: 'carton_order', entity_id: 'CTO-3', detail: { order_no: 'CT-003', status: 'PENDING_SUPPLIER' }, actor_user_id: 'manager', actor_name: '纸箱主管', created_at: '2026-08-04T09:00:00+08:00' },
      { sequence: 2, id: 'CAE-2', factory_id: 'huaxing', event_type: 'ORDER_APPENDED', entity_type: 'carton_order', entity_id: 'CTO-2', detail: { order_no: 'CT-002', additional_quantity: 600 }, actor_user_id: 'keeper', actor_name: '仓管员', created_at: '2026-08-03T08:00:00+08:00' },
      { sequence: 1, id: 'CAE-1', factory_id: 'huaxing', event_type: 'ORDER_RETURNED', entity_type: 'carton_order', entity_id: 'CTO-1', detail: { order_no: 'CT-001', reason: '客户退单' }, actor_user_id: 'manager', actor_name: '纸箱主管', created_at: '2026-08-02T07:00:00+08:00' },
    ]
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.listAuditEvents.mockResolvedValue(events)

    const wrapper = mountView('audit')
    await flushPromises()
    const logTable = wrapper.findAll('table').find((table) => table.text().includes('变更内容'))
    if (!logTable) throw new Error('Unified operation log table not found')

    expect(logTable.findAll('thead th').map((cell) => cell.text())).toEqual(['时间', '操作人', '操作', '业务对象', '变更内容'])
    expect(logTable.findAll('tbody tr')).toHaveLength(4)
    expect(logTable.text()).toContain('CT-004')
    expect(logTable.text()).toContain('确认订单并锁定')
    expect(logTable.text()).toContain('追加订单')
    expect(logTable.text()).toContain('订单退单')

    await wrapper.get('select[aria-label="操作日志操作人"]').setValue('keeper')
    expect(logTable.findAll('tbody tr')).toHaveLength(2)
    expect(logTable.text()).not.toContain('纸箱主管')

    await wrapper.get('select[aria-label="操作日志操作"]').setValue('ORDER_UPDATED')
    expect(logTable.findAll('tbody tr')).toHaveLength(1)
    expect(logTable.text()).toContain('修改交期')

    await wrapper.get('button[aria-label="清空操作日志筛选"]').trigger('click')
    await wrapper.get('input[aria-label="操作日志开始日期"]').setValue('2026-08-04')
    expect(logTable.findAll('tbody tr')).toHaveLength(2)

    await wrapper.get('button[aria-label="清空操作日志筛选"]').trigger('click')
    expect(logTable.findAll('tbody tr')).toHaveLength(4)
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

    expect(wrapper.text()).not.toContain('切换导入模式')
    expect(wrapper.text()).not.toContain('期初库存管理')
    await wrapper.get('button[aria-label="库存更多操作"]').trigger('click')
    await flushPromises()
    await findButton(wrapper, '期初库存管理').trigger('click')
    expect(wrapper.text()).toContain('期初库存管理')
    expect(wrapper.text()).not.toContain('实时库存结存台账')
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
    await findButton(wrapper, '返回库存台账').trigger('click')
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

    expect(wrapper.text()).toContain('当前结存 176')
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

  it('opens selected inventory in a bulk dialog and submits only after confirmation', async () => {
    const balance = {
      factory_id: 'huaxing', customer_code: 'DICKIE', customer_name: 'Dickie', contract_no: 'SC-001',
      item_no: 'ITEM-001', order_line_id: 'LINE-1', packaging_type: '外箱', paper_quality: 'A33+B',
      specification: '12*11*5', unit: '个', balance: '100', latest_location: 'A-01',
      latest_movement_id: 'CIM-IN-1', latest_movement_at: '2026-08-11T09:00:00+08:00',
    }
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([balance, { ...balance, order_line_id: 'LINE-ZERO', balance: '0' }])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.createInventoryMovementsBulk.mockResolvedValue([])
    const wrapper = mountView('inventory')
    await flushPromises()
    await wrapper.get('input[aria-label="全选库存筛选结果"]').setValue(true)
    await findButton(wrapper, '登记所选库存出库').trigger('click')
    await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('批量出库')
    expect(dialog.text()).toContain('100 个')
    expect(wrapper.find('input[aria-label="库存作业数量"]').exists()).toBe(false)
    expect(cartonApiMock.createInventoryMovementsBulk).not.toHaveBeenCalled()
    await dialog.get('form').trigger('submit')
    expect(dialog.text()).toContain('批量出库前请填写来源单据号')
    expect(cartonApiMock.createInventoryMovementsBulk).not.toHaveBeenCalled()
    await wrapper.get('input[aria-label="库存作业单据号"]').setValue('OUT-BULK-001')
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(cartonApiMock.createInventoryMovementsBulk).toHaveBeenCalledWith({
      factory_id: 'huaxing', document_no: 'OUT-BULK-001', reason: '客户要货',
      items: [{ order_line_id: 'LINE-1', reference_movement_id: null, quantity: 100, location: 'A-01' }],
    })
    expect(cartonApiMock.createInventoryMovement).not.toHaveBeenCalled()
    expect(dialog.text()).toContain('已按全部结存批量出库 1 条记录')
    await wrapper.get('button[aria-label="关闭库存作业"]').trigger('click')
    await flushPromises()
    await findButton(wrapper, '库存调整').trigger('click')
    await flushPromises()
    expect(wrapper.get('button[type="submit"]').text()).toContain('确认调整')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="库存作业数量"]').element.value).toBe('0')
  })

  it('relocates a balance through a dedicated dialog without submitting a quantity movement', async () => {
    const balance = {
      factory_id: 'huaxing', customer_code: '360', customer_name: '360', contract_no: 'SC-001',
      item_no: 'ITEM-001', order_line_id: 'LINE-1', packaging_type: '外箱', paper_quality: 'A33',
      specification: '1*1*1', unit: '个', balance: '17', latest_location: 'A-01',
      latest_movement_id: 'IN-1', latest_document_no: 'DN-1', latest_movement_at: '2026-09-04T09:00:00+08:00',
      latest_inbound_at: '2026-09-04T09:00:00+08:00', location_revision: 4,
    }
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([balance])
    cartonApiMock.relocateInventory.mockImplementation(async () => {
      const relocated = { ...balance, latest_location: 'B-02', location_revision: 5 }
      cartonApiMock.listInventoryBalances.mockResolvedValue([relocated])
      return relocated
    })
    const wrapper = mountView('inventory')
    await flushPromises()
    expect(wrapper.find('button[aria-label="调整 LINE-1"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="调仓 LINE-1"]').trigger('click')
    await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('库存调仓')
    expect(dialog.text()).toContain('A-01')
    expect(dialog.text()).toContain('17 个')
    expect(dialog.find('input[aria-label="库存作业数量"]').exists()).toBe(false)
    await dialog.get('form').trigger('submit')
    expect(dialog.text()).toContain('请填写目标仓位')
    await dialog.get('input[aria-label="调仓目标仓位"]').setValue('A-01')
    await dialog.get('form').trigger('submit')
    expect(dialog.text()).toContain('目标仓位与当前仓位相同')
    expect(cartonApiMock.relocateInventory).not.toHaveBeenCalled()
    await dialog.get('input[aria-label="调仓目标仓位"]').setValue(' B-02 ')
    await dialog.get('textarea[aria-label="调仓备注"]').setValue('整理库位')
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(cartonApiMock.relocateInventory).toHaveBeenCalledWith({
      factory_id: 'huaxing', reference_movement_id: 'IN-1', expected_location_revision: 4,
      location: 'B-02', note: '整理库位',
    })
    expect(cartonApiMock.createInventoryMovement).not.toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-inventory-balance="LINE-1"]').text()).toContain('B-02')
    expect(wrapper.get('[data-inventory-balance="LINE-1"]').text()).toContain('17 个')
    expect(wrapper.text()).toContain('调仓完成')
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
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="出库 LINE-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="库存作业记录"]').element.value).toBe('LINE-1')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="库存作业数量"]').element.value).toBe('100')
    await wrapper.get('input[aria-label="库存作业数量"]').setValue('10')
    await wrapper.get('input[aria-label="库存作业单据号"]').setValue('OUT-001')
    const outboundReason = wrapper.get('select[aria-label="库存作业原因"]')
    expect(outboundReason.element.value).toBe('客户要货')
    expect(outboundReason.findAll('option').map((option) => option.text())).toEqual([
      '客户要货',
      '补货',
      '借出',
      '调拨',
      '损耗',
      '其他',
    ])
    await outboundReason.setValue('借出')
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
      reason: '借出',
    }))
    expect(wrapper.text()).toContain('出库已登记')

    await wrapper.get('button[aria-label="关闭库存作业"]').trigger('click')
    await flushPromises()
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

  it('shows persisted business order alerts with direct create, append, and return entry points', async () => {
    const increasedOrder = {
      ...orderFixture('CT-BUSINESS-ADD', businessDateOffset(5), 'CONFIRMED'),
      contract_no: 'SC-BUSINESS-ADD',
      item_no: 'ITEM-ADD',
      product_name: '追加产品',
      product_order_quantity: '100',
    }
    const returnedOrder = {
      ...orderFixture('CT-BUSINESS-RETURN', businessDateOffset(-2), 'COMPLETED'),
      contract_no: 'SC-BUSINESS-RETURN',
      item_no: 'ITEM-RETURN',
      product_name: '退单产品',
      product_order_quantity: '100',
    }
    const weeklyBatch = {
      id: 'CIB-BUSINESS-1', factory_id: 'huaxing', import_type: 'WEEKLY_SCHEDULE',
      original_filename: '业务接单员-第35周排期.xlsx', source_sha256: 'business-sha', import_profile: '', content_type: 'application/xlsx',
      source_size_bytes: 2048, status: 'REQUIRES_REVIEW', imported_by: 'sales-clerk', imported_by_name: '业务接单员-小陈',
      created_at: '2026-08-29T09:30:00+08:00', duplicate: false,
      parse_summary: { row_count: 3, matched_count: 0, issue_count: 3, rows: [
        { source_sheet: '排期', source_row: 2, reference: 'SC-BUSINESS-MISSING', customer_code: 'DICKIE', customer_name: 'Dickie', item_no: 'ITEM-MISSING', product_name: '漏单产品', quantity: 120, match_status: 'MISSING_ORDER', suggestion: '未找到正式纸箱订单，仅生成异常待办' },
        { source_sheet: '排期', source_row: 3, reference: 'SC-BUSINESS-ADD', contract_no: 'SC-BUSINESS-ADD', customer_code: 'DICKIE', customer_name: 'Dickie', item_no: 'ITEM-ADD', product_name: '追加产品', quantity: 160, match_status: 'QUANTITY_MISMATCH', order_id: increasedOrder.id, order_no: increasedOrder.order_no, order_status: 'CONFIRMED', suggestion: '排期数量 160 与订单数量 100 不一致，请人工确认' },
        { source_sheet: '排期', source_row: 4, reference: 'SC-BUSINESS-RETURN', contract_no: 'SC-BUSINESS-RETURN', customer_code: 'DICKIE', customer_name: 'Dickie', item_no: 'ITEM-RETURN', product_name: '退单产品', quantity: 0, match_status: 'QUANTITY_MISMATCH', order_id: returnedOrder.id, order_no: returnedOrder.order_no, order_status: 'COMPLETED', suggestion: '客户排期已取消，请核对退单' },
      ] },
    }
    const exception = (id: string, category: string, contractNo: string, itemNo: string, createdAt: string) => ({
      id: `ID-${id}`, factory_id: 'huaxing', exception_no: id, source_type: 'WEEKLY_SCHEDULE', source_id: weeklyBatch.id,
      category, severity: category === 'MISSING_ORDER' ? 'HIGH' : 'MEDIUM', customer_code: 'DICKIE', customer_name: 'Dickie',
      contract_no: contractNo, item_no: itemNo, title: category === 'MISSING_ORDER' ? '周排期未找到正式纸箱订单' : '排期数量与纸箱订单数量不一致',
      description: '请人工复核业务排期', owner_department: '纸箱下单', status: 'OPEN', resolution_note: '', revision: 1,
      created_at: createdAt, updated_at: createdAt,
    })

    cartonApiMock.listCustomers.mockResolvedValue([{
      id: 'CUS-DICKIE', factory_id: 'huaxing', customer_code: 'DICKIE', customer_name: 'Dickie', country_region: '',
      contact_name: '', contact_phone: '', note: '', status: 'ACTIVE', revision: 1, created_by: 'admin', created_by_name: '管理员',
      updated_by: 'admin', updated_by_name: '管理员', created_at: '2026-08-01T08:00:00+08:00', updated_at: '2026-08-01T08:00:00+08:00',
    }])
    cartonApiMock.listOrders.mockResolvedValue([increasedOrder, returnedOrder])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([
      exception('EX-MISSING', 'MISSING_ORDER', 'SC-BUSINESS-MISSING', 'ITEM-MISSING', '2026-08-29T09:31:00+08:00'),
      exception('EX-INCREASE', 'QUANTITY_MISMATCH', 'SC-BUSINESS-ADD', 'ITEM-ADD', '2026-08-29T09:32:00+08:00'),
      exception('EX-DECREASE', 'QUANTITY_MISMATCH', 'SC-BUSINESS-RETURN', 'ITEM-RETURN', '2026-08-29T09:33:00+08:00'),
    ])
    cartonApiMock.listImports.mockImplementation(async (_factory: string, type: string) => type === 'WEEKLY_SCHEDULE' ? [weeklyBatch] : [])

    const wrapper = mountView('dashboard')
    await flushPromises()
    const panel = wrapper.get('[data-testid="business-order-collaboration-panel"]')
    expect(panel.text()).toContain('业务下单协同面板')
    expect(panel.text()).toContain('业务接单员-小陈')
    expect(panel.text()).toContain('业务接单员-第35周排期.xlsx')
    expect(panel.text()).toContain('漏下单')
    expect(panel.text()).toContain('订单增加')
    expect(panel.text()).toContain('订单减少 / 退单')
    expect(panel.text()).toContain('订单 100 → 排期 160 （+60）')

    await panel.get('button[aria-label="追加订单 EX-INCREASE"]').trigger('click')
    expect(wrapper.get('input[aria-label="追加订单数量"]').element.value).toBe('60')
    expect(wrapper.get('textarea[aria-label="追加订单原因"]').element.value).toContain('EX-INCREASE')
    await wrapper.get('button[aria-label="关闭追加订单"]').trigger('click')

    await panel.get('button[aria-label="按提醒新建 EX-MISSING"]').trigger('click')
    expect(wrapper.text()).toContain('新建纸箱合同订单')
    expect(wrapper.get('input[aria-label="合同号"]').element.value).toBe('SC-BUSINESS-MISSING')
    expect(wrapper.get('input[aria-label="货号"]').element.value).toBe('ITEM-MISSING')
    expect(wrapper.get('input[aria-label="订单数量"]').element.value).toBe('120')
    expect(wrapper.get('textarea[aria-label="订单备注"]').element.value).toContain('EX-MISSING')
    await wrapper.get('button[aria-label="关闭新建订单"]').trigger('click')

    await panel.get('button[aria-label="退单 EX-DECREASE"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已经入库，禁止追加、减单或退单')
    expect(wrapper.find('textarea[aria-label="订单取消退单原因"]').exists()).toBe(false)
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
    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('ITEM-HISTORY-001')
    expect(wrapper.text()).toContain('ITEM-HISTORY-001')
  })
})

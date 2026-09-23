import { reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonProcurementView from '../CartonProcurementView.vue'
import { cartonMasterApi, emptyMaster } from '@/api/cartonMaster'

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
  deleteHistoryOrder: vi.fn(),
  bulkDeleteHistoryOrders: vi.fn(),
  undoScheduleImport: vi.fn(),
  bulkUpdateExceptions: vi.fn(),
  appendOrder: vi.fn(),
  replenishOrder: vi.fn(),
  reduceOrder: vi.fn(),
  returnOrder: vi.fn(),
  bulkCancelOrders: vi.fn(),
  uploadHistoryOrders: vi.fn(),
  previewHistoryOrders: vi.fn(),
  searchOrderHistoryItems: vi.fn(),
  uploadHistoryInventory: vi.fn(),
  previewHistoryInventory: vi.fn(),
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
  reverseReceipt: vi.fn(),
  generateClosings: vi.fn(),
  updateClosingStatus: vi.fn(),
  unlockClosing: vi.fn(),
  confirmInventoryPrice: vi.fn(),
  updateException: vi.fn(),
}))

const positionsMock = vi.hoisted(() => ({ locations: vi.fn(), create: vi.fn(), transfer: vi.fn() }))
vi.mock('@/api/cartonPositions', () => ({ cartonPositionsApi: positionsMock }))

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

function mountView(tab?: string, extraStubs: Record<string, boolean> = {}, inventoryClosing = true) {
  routeState.query = reactive(tab
    ? { factory: 'huaxing', tab, ...(tab === 'closing' && inventoryClosing ? { closing_view: 'inventory' } : {}) }
    : { factory: 'huaxing' })

  return mount(CartonProcurementView, {
    global: {
      stubs: {
        AccountMenu: true,
        CartonSupplierSettlement: true,
        PopoverPortal: { template: '<slot />' },
        ...extraStubs,
      },
    },
  })
}

it('opens supplier reconciliation by default and preserves its mounted form across inventory month-end tabs', async () => {
  const w = mountView('closing', {}, false); await flushPromises()
  const tabs = w.get('[aria-label="月结对账子页面"]')
  expect(tabs.findAll('button')[0]!.attributes('aria-pressed')).toBe('true')
  const supplier = w.get('carton-supplier-settlement-stub').element
  await tabs.findAll('button')[1]!.trigger('click')
  expect(w.get('carton-supplier-settlement-stub').element).toBe(supplier)
  expect(w.get('carton-supplier-settlement-stub').attributes('style')).toContain('display: none')
  await tabs.findAll('button')[0]!.trigger('click')
  expect(w.get('carton-supplier-settlement-stub').element).toBe(supplier)
  w.unmount()
})

function findButton(wrapper: ReturnType<typeof mountView>, label: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(label))
  if (!button) throw new Error(`Button not found: ${label}`)
  return button
}

// Explicitly select and enter a full arrival for legacy receipt scenarios.
async function fillAllManualReceiptPapers(wrapper: ReturnType<typeof mountView>) {
  const dialog = wrapper.get('[role="dialog"]')
  for (const checkbox of dialog.findAll<HTMLInputElement>('input[aria-label^="选择纸品 "]')) {
    if (checkbox.element.checked) continue
    const id = checkbox.attributes('aria-label')!.replace('选择纸品 ', '')
    await checkbox.setValue(true)
    const quantity = dialog.get<HTMLInputElement>(`input[aria-label="MANUAL-${id} 实收"]`)
    await quantity.setValue(quantity.attributes('max') || '100')
  }
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
  it('shows unified ITEM provenance, review rows and procurement status separately', async () => {
    mockReceiptWorkspace([])
    cartonApiMock.listImports.mockResolvedValue([{
      id: 'ITEM-BATCH', import_type: 'WEEKLY_SCHEDULE', status: 'REQUIRES_REVIEW',
      original_filename: '统一业务.xlsx', created_at: '2026-09-21',
      parse_summary: {
        engine: 'unified-item-header-mapping', row_count: 2, review_count: 1,
        field_mappings: [{ sheet: '水枪ITEM表', header_row: 3, fields: { contract_no: 'Contract No.', quantity: '數量' } }],
        rows: [
          { template: 'unified-item', source_sheet: '水枪ITEM表', source_row: 4, order_type: '正单',
            contract_no: '53148', item_no: '57520-3', customer_po: '00123', po_numbers: '00123',
            customer_name: 'BUZZ BEE', source_customer_name: 'COOP', quantity: 12624,
            customer_due_date: '2026-10-25', match_status: 'DATE_MISMATCH', procurement_state: 'ORDERED',
            source_inspection_window: '9/1-10% 9/14-100%', inspection_window: '', date_review_required: true,
            order_no: 'CT-TEST', suggestion: '请确认交期' },
          { template: 'unified-item', source_sheet: '水枪ITEM表', source_row: 5, order_type: '样板单',
            item_no: '57520-3', quantity: null, match_status: 'REVIEW_REQUIRED', suggestion: '样板单待确认' },
        ],
      },
    }])
    const wrapper = mountView('weekly-check')
    await flushPromises()
    expect(wrapper.text()).toContain('统一业务模板 · ITEM 表')
    expect(wrapper.text()).toContain('正单 1 行')
    expect(wrapper.text()).toContain('待人工确认 2 行')
    expect(wrapper.text()).toContain('交期差异')
    expect(wrapper.text()).toContain('已下单')
    expect(wrapper.text()).toContain('走货 2026-10-25')
    expect(wrapper.text()).toContain('9/1-10% 9/14-100%')
    expect(wrapper.text()).toContain('日期原文待确认')
    expect(wrapper.text()).toContain('水枪ITEM表 · 第 4 行')
    expect(wrapper.text()).toContain('COOP')
    expect(wrapper.text()).toContain('00123')
    expect(cartonApiMock.createOrder).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('receives supplier-responsible replacements without asking for a payable price', async () => {
    const seed = orderFixture('CT-FREE-REPLACE', businessDateOffset(5), 'PARTIALLY_RECEIVED')
    const row = { ...seed, lines: [{ ...seed.lines[0]!, received_quantity: '90', remaining_quantity: '10',
      replenishment_options: [{ replenishment_issue_id: 'ISSUE-B01', document_no: 'CT-FREE-REPLACE-B01', responsibility: 'SUPPLIER', remaining_quantity: '10' }] }] }
    mockReceiptWorkspace([row])
    cartonApiMock.createReceipt.mockRejectedValueOnce(new Error('测试停止提交'))
    const wrapper = mountView('receipts'); await flushPromises()
    await wrapper.get('button[aria-label="登记 CT-FREE-REPLACE 收料"]').trigger('click'); await flushPromises()
    await fillAllManualReceiptPapers(wrapper)
    expect(wrapper.text()).toContain('供应商责任 · 免费补货')
    expect(wrapper.find(`input[aria-label="MANUAL-${row.lines[0]!.id} 单价"]`).exists()).toBe(false)
    expect(wrapper.get<HTMLSelectElement>(`select[aria-label="MANUAL-${row.lines[0]!.id} 收料来源"]`).element.value).toBe('ISSUE-B01')
    await wrapper.get('input[aria-label="人工送货单号"]').setValue('FREE-DN')
    await wrapper.get('input[aria-label="仓库及仓位"]').setValue('A-01')
    await findButton(wrapper, '确认入库').trigger('click'); await flushPromises()
    expect(cartonApiMock.createReceipt).toHaveBeenCalledWith(expect.objectContaining({ lines: [expect.objectContaining({
      replenishment_issue_id: 'ISSUE-B01', received_quantity: 10, unit_price: undefined,
    })] }))
    wrapper.unmount()
  })

  it('requires a choice when normal stock and replacement stock are both outstanding', async () => {
    const seed = orderFixture('CT-MIX-REPLACE', businessDateOffset(5), 'PARTIALLY_RECEIVED')
    const row = { ...seed, lines: [{ ...seed.lines[0]!, received_quantity: '70', remaining_quantity: '30',
      replenishment_options: [{ replenishment_issue_id: 'ISSUE-B01', document_no: 'CT-MIX-REPLACE-B01', responsibility: 'SUPPLIER', remaining_quantity: '10' }] }] }
    mockReceiptWorkspace([row])
    const wrapper = mountView('receipts'); await flushPromises()
    await wrapper.get('button[aria-label="登记 CT-MIX-REPLACE 收料"]').trigger('click'); await flushPromises()
    await fillAllManualReceiptPapers(wrapper)
    expect(wrapper.find(`input[aria-label="MANUAL-${row.lines[0]!.id} 单价"]`).exists()).toBe(true)
    await wrapper.get(`select[aria-label="MANUAL-${row.lines[0]!.id} 收料来源"]`).setValue('ISSUE-B01')
    expect(wrapper.get<HTMLInputElement>(`input[aria-label="MANUAL-${row.lines[0]!.id} 实收"]`).element.value).toBe('10')
    expect(wrapper.text()).toContain('应付 0，不计月结')
    wrapper.unmount()
  })

  it('requires responsibility and posts replacement quantities against the selected physical stock', async () => {
    const row = orderFixture('CT-REPLACE', businessDateOffset(3), 'COMPLETED')
    mockReceiptWorkspace([row])
    cartonApiMock.listInventoryBalances.mockResolvedValue([{
      factory_id: 'huaxing', customer_code: 'DICKIE', customer_name: 'Dickie', contract_no: row.contract_no,
      item_no: row.item_no, order_line_id: row.lines[0]!.id, position_key: 'POS-REPLACE', location_id: 'LOC-A',
      packaging_type: '外箱', paper_quality: 'A33', specification: '12*11*5', unit: '个', balance: '100',
      latest_location: '默认仓／A-01', latest_movement_id: 'MV-1', latest_movement_at: '2026-09-16T10:00:00',
    }])
    cartonApiMock.replenishOrder.mockResolvedValue({ order: row, issue: { document_no: 'CT-REPLACE-B01' } })
    const wrapper = mountView('orders'); await flushPromises()
    await wrapper.get('[aria-label="更多 CT-REPLACE 订单操作"]').trigger('click')
    await wrapper.get('[aria-label="补单 CT-REPLACE"]').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="补单数量 POS-REPLACE"]').setValue('10')
    await wrapper.get('[aria-label="补单责任方"]').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(cartonApiMock.replenishOrder).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请选择责任方')
    await wrapper.get('[aria-label="补单责任方"]').setValue('SUPPLIER')
    await wrapper.get('[aria-label="补单责任方"]').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(cartonApiMock.replenishOrder).toHaveBeenCalledWith('huaxing', expect.objectContaining({ order_no: 'CT-REPLACE', product_order_quantity: '100' }), 'SUPPLIER', '', [{ order_line_id: row.lines[0]!.id, location_id: 'LOC-A', quantity: 10 }])
    expect(wrapper.text()).toContain('CT-REPLACE-B01')
    expect(wrapper.find('[aria-label="补单责任方"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('resolves a single exception without a mandatory note', async () => {
    mockReceiptWorkspace([])
    const row = { id: 'EX-ID', exception_no: 'EX-NOTE', factory_id: 'huaxing', source_type: 'WEEKLY_SCHEDULE', source_id: 'S', category: 'MISSING_ORDER', severity: 'MEDIUM', customer_name: 'Dickie', customer_code: 'DICKIE', contract_no: 'SC', item_no: 'ITEM', title: '待核对', description: '', owner_department: '纸箱仓', status: 'IN_PROGRESS', resolution_note: '', revision: 1, created_at: '2026-09-16T10:00:00', updated_at: '2026-09-16T10:00:00' }
    cartonApiMock.listExceptions.mockResolvedValue([row]); cartonApiMock.updateException.mockResolvedValue({ ...row, status: 'RESOLVED', revision: 2 })
    const wrapper = mountView('exceptions'); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '标记已解决')!.trigger('click'); await flushPromises()
    expect(cartonApiMock.updateException).toHaveBeenCalledWith('huaxing', expect.objectContaining({ id: row.id }), 'RESOLVED', '')
    wrapper.unmount()
  })

  it('selects filtered exceptions while preserving hidden selections and submits all selected records', async () => {
    mockReceiptWorkspace([])
    const records = ['A', 'B'].map((id, index) => ({
      id, exception_no: `EX-${id}`, factory_id: 'huaxing', source_type: 'WEEKLY_SCHEDULE', source_id: id,
      category: index ? 'QUANTITY_MISMATCH' : 'MISSING_ORDER', severity: 'MEDIUM',
      customer_code: 'DICKIE', customer_name: 'Dickie', contract_no: id, item_no: id,
      title: `异常 ${id}`, description: '', owner_department: '纸箱仓', status: 'OPEN',
      resolution_note: '', revision: 1, created_at: '2026-09-10T10:00:00', updated_at: '2026-09-10T10:00:00',
    }))
    cartonApiMock.listExceptions.mockResolvedValue(records)
    cartonApiMock.bulkUpdateExceptions.mockResolvedValue(records.map(row => ({ ...row, status: 'IN_PROGRESS', revision: 2 })))
    const wrapper = mountView('exceptions'); await flushPromises()
    await wrapper.get('[aria-label="选择异常 EX-A"]').setValue(true)
    expect((wrapper.get('[aria-label="全选当前筛选异常"]').element as HTMLInputElement).indeterminate).toBe(true)
    await wrapper.get('[aria-label="异常类型筛选"]').setValue('数量差异')
    expect(wrapper.text()).toContain('其中 1 条不在当前筛选内')
    await wrapper.get('[aria-label="全选当前筛选异常"]').setValue(true)
    expect(wrapper.get('[aria-label="批量已选范围"]').text()).toContain('已选 2 条')
    await wrapper.findAll('button').find(b => b.text() === '批量开始处理')!.trigger('click')
    await flushPromises()
    expect(cartonApiMock.bulkUpdateExceptions).toHaveBeenCalledWith('huaxing', records, 'IN_PROGRESS', '')
    expect(wrapper.get('[aria-label="批量已选范围"]').text()).toContain('已选 0 条')
    wrapper.unmount()
  })

  it('requires explicit history deletion confirmation and hides it for received history', async () => {
    const row = { ...orderFixture('CT-HISTORY', businessDateOffset(3), 'PENDING_SUPPLIER'), can_delete_history: true }
    mockReceiptWorkspace([row])
    cartonApiMock.deleteHistoryOrder.mockResolvedValue(undefined)
    const wrapper = mountView('orders'); await flushPromises()
    await wrapper.get('[aria-label="更多 CT-HISTORY 订单操作"]').trigger('click')
    await wrapper.get('[aria-label="删除历史订单 CT-HISTORY"]').trigger('click')
    await flushPromises()
    expect(cartonApiMock.deleteHistoryOrder).not.toHaveBeenCalled()
    const reason = document.querySelector('[aria-label="历史订单删除原因"]') as HTMLTextAreaElement | null
    // Reka renders a controlled dialog in the mounted wrapper.
    const input = wrapper.find('[aria-label="历史订单删除原因"]')
    expect(input.exists() || Boolean(reason)).toBe(true)
    cartonApiMock.listOrders.mockResolvedValue([{ ...row, can_delete_history: false }])
    if (input.exists()) {
      await input.setValue('重复导入需重新整理')
      await input.element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    } else {
      reason!.value = '重复导入需重新整理'
      reason!.dispatchEvent(new Event('input', { bubbles: true }))
      reason!.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    }
    await flushPromises()
    expect(cartonApiMock.deleteHistoryOrder).toHaveBeenCalledWith('huaxing', expect.objectContaining({ order_no: row.order_no }), '重复导入需重新整理')
    await wrapper.get('[aria-label="更多 CT-HISTORY 订单操作"]').trigger('click')
    expect(wrapper.find('[aria-label="删除历史订单 CT-HISTORY"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('deletes all selected eligible history only after confirmation and rejects a mixed UI selection', async () => {
    const rows = ['H-A', 'H-B'].map(id => ({ ...orderFixture(id, businessDateOffset(3), 'PENDING_SUPPLIER'), can_delete_history: true }))
    const ordinary = orderFixture('NORMAL', businessDateOffset(3))
    mockReceiptWorkspace([...rows, ordinary])
    const wrapper = mountView('orders'); await flushPromises()
    await wrapper.get('[aria-label="选择订单 H-A"]').setValue(true)
    await wrapper.get('[aria-label="选择订单 NORMAL"]').setValue(true)
    expect(findButton(wrapper, '批量删除历史订单').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('普通订单、已有收料记录')
    await wrapper.get('[aria-label="选择订单 NORMAL"]').setValue(false)
    await wrapper.get('[aria-label="选择订单 H-B"]').setValue(true)
    await findButton(wrapper, '批量删除历史订单').trigger('click'); await flushPromises()
    expect(cartonApiMock.bulkDeleteHistoryOrders).not.toHaveBeenCalled()
    const reason = wrapper.get('[aria-label="历史订单删除原因"]')
    await reason.setValue('历史导入整批重复')
    cartonApiMock.bulkDeleteHistoryOrders.mockImplementation(async () => {
      cartonApiMock.listOrders.mockResolvedValue([ordinary])
    })
    await reason.element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(cartonApiMock.bulkDeleteHistoryOrders).toHaveBeenCalledExactlyOnceWith('huaxing', rows, '历史导入整批重复')
    expect(wrapper.get('[aria-label="批量已选范围"]').text()).toContain('已选 0 张')
    expect(wrapper.find('[aria-label="选择订单 H-A"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it.each(['single', 'bulk'])('supersedes an in-flight refresh after %s history deletion and ignores its late response', async (mode) => {
    const row = { ...orderFixture('H-STALE', businessDateOffset(3), 'PENDING_SUPPLIER'), can_delete_history: true }
    mockReceiptWorkspace([row])
    const wrapper = mountView('orders'); await flushPromises()
    let releaseOld!: (rows: typeof row[]) => void
    const oldResponse = new Promise<typeof row[]>(resolve => { releaseOld = resolve })
    cartonApiMock.listOrders.mockReturnValueOnce(oldResponse)
    await findButton(wrapper, '刷新').trigger('click'); await flushPromises()
    await findButton(wrapper, '刷新').trigger('click'); await flushPromises()
    expect(cartonApiMock.listOrders).toHaveBeenCalledTimes(2) // Ordinary refreshes still coalesce.
    if (mode === 'single') {
      await wrapper.get('[aria-label="更多 H-STALE 订单操作"]').trigger('click')
      await wrapper.get('[aria-label="删除历史订单 H-STALE"]').trigger('click')
    } else {
      await wrapper.get('[aria-label="选择订单 H-STALE"]').setValue(true)
      await findButton(wrapper, '批量删除历史订单').trigger('click')
    }
    await flushPromises()
    const deleted = async () => { cartonApiMock.listOrders.mockResolvedValue([]) }
    cartonApiMock.deleteHistoryOrder.mockImplementation(deleted)
    cartonApiMock.bulkDeleteHistoryOrders.mockImplementation(deleted)
    await wrapper.get('[aria-label="历史订单删除原因"]').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(cartonApiMock.listOrders).toHaveBeenCalledTimes(3)
    expect(wrapper.text()).toContain('1 张历史订单已删除')
    expect(wrapper.find('[aria-label="选择订单 H-STALE"]').exists()).toBe(false)
    releaseOld([row]); await flushPromises()
    expect(wrapper.find('[aria-label="选择订单 H-STALE"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('1 张历史订单已删除')
    expect(wrapper.get('[aria-label="批量已选范围"]').text()).toContain('已选 0 张')
    wrapper.unmount()
  })

  it.each(['WEEKLY_SCHEDULE', 'INSPECTION_SCHEDULE'])('supersedes an in-flight refresh after %s undo without reviving results or exceptions', async (kind) => {
    mockReceiptWorkspace([])
    const batch = { id: 'B-STALE', import_type: kind, status: 'REQUIRES_REVIEW', original_filename: '旧响应排期.xlsx',
      created_at: '2026-09-17T10:00:00', imported_by_name: '业务员', parse_summary: { row_count: 1, rows: [{
        source_sheet: '排期', source_row: 2, reference: 'SC-STALE-RESULT', contract_no: 'SC-STALE-RESULT',
        customer_name: 'Dickie', item_no: 'ITEM-STALE', product_name: '旧排期产品', quantity: 120,
        match_status: 'MISSING_ORDER', reminder_status: 'MISSING_ORDER', suggestion: '请复核旧结果',
      }] } }
    const exception = { id: 'EX-ID-STALE', exception_no: 'EX-STALE', factory_id: 'huaxing', source_type: kind,
      source_id: batch.id, category: 'MISSING_ORDER', severity: 'MEDIUM', customer_name: 'Dickie', customer_code: 'DICKIE',
      contract_no: 'SC-STALE-RESULT', item_no: 'ITEM-STALE', title: '旧排期待办', description: '', owner_department: '纸箱仓',
      status: 'OPEN', resolution_note: '', revision: 1, created_at: batch.created_at, updated_at: batch.created_at }
    cartonApiMock.listExceptions.mockResolvedValue([exception])
    cartonApiMock.listImports.mockImplementation(async (_factory: string, type: string) => type === kind ? [batch] : [])
    const wrapper = mountView('weekly-check'); await flushPromises()
    if (kind === 'INSPECTION_SCHEDULE') {
      await findButton(wrapper, '下周查货提醒').trigger('click'); await flushPromises()
    }
    expect(wrapper.text()).toContain('SC-STALE-RESULT')
    let releaseOld!: (rows: never[]) => void
    const oldResponse = new Promise<never[]>(resolve => { releaseOld = resolve })
    cartonApiMock.listOrders.mockReturnValueOnce(oldResponse)
    await findButton(wrapper, '刷新').trigger('click'); await flushPromises()
    expect(cartonApiMock.listOrders).toHaveBeenCalledTimes(2)
    await wrapper.get('[aria-label="撤销本次导入 旧响应排期.xlsx"]').trigger('click'); await flushPromises()
    cartonApiMock.undoScheduleImport.mockImplementation(async () => {
      const updated = { ...batch, status: 'REJECTED' }
      cartonApiMock.listExceptions.mockResolvedValue([])
      cartonApiMock.listImports.mockImplementation(async (_factory: string, type: string) => type === kind ? [updated] : [])
      return updated
    })
    await wrapper.get('[aria-label="导入批次撤销原因"]').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(cartonApiMock.listOrders).toHaveBeenCalledTimes(3)
    releaseOld([]); await flushPromises()
    expect(wrapper.text()).toContain('已整批撤销 旧响应排期.xlsx 的核对结果和异常工作项')
    expect(wrapper.text()).not.toContain('SC-STALE-RESULT')
    expect(wrapper.find('[aria-label="撤销本次导入 旧响应排期.xlsx"]').exists()).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text() === '查看结果')).toBe(false)
    await findButton(wrapper, '异常处理').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('旧排期待办')
    expect(wrapper.find('[aria-label="选择异常 EX-STALE"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('retains selection after the server blocks an atomic history deletion', async () => {
    const row = { ...orderFixture('H-BLOCKED', businessDateOffset(3), 'PENDING_SUPPLIER'), can_delete_history: true }
    mockReceiptWorkspace([row])
    cartonApiMock.bulkDeleteHistoryOrders.mockRejectedValue(new Error('已有收料记录'))
    const wrapper = mountView('orders'); await flushPromises()
    await wrapper.get('[aria-label="选择订单 H-BLOCKED"]').setValue(true)
    await findButton(wrapper, '批量删除历史订单').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="历史订单删除原因"]').element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(wrapper.text()).toContain('历史订单未删除')
    expect(wrapper.get('[aria-label="批量已选范围"]').text()).toContain('已选 1 张')
    expect(wrapper.find('[aria-label="历史订单删除原因"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it.each(['WEEKLY_SCHEDULE', 'INSPECTION_SCHEDULE'])('confirms whole %s undo once and shows the retained inactive batch', async (kind) => {
    mockReceiptWorkspace([])
    const batch = { id: 'B-UNDO', import_type: kind, status: 'REQUIRES_REVIEW', original_filename: '待撤销排期.xlsx',
      created_at: '2026-09-17T10:00:00', imported_by_name: '业务员', parse_summary: { row_count: 2, rows: [] } }
    cartonApiMock.listImports.mockImplementation(async (_factory: string, type: string) => type === kind ? [batch] : [])
    const wrapper = mountView('weekly-check'); await flushPromises()
    if (kind === 'INSPECTION_SCHEDULE') {
      await findButton(wrapper, '下周查货提醒').trigger('click'); await flushPromises()
    }
    await wrapper.get('[aria-label="撤销本次导入 待撤销排期.xlsx"]').trigger('click'); await flushPromises()
    expect(cartonApiMock.undoScheduleImport).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('不支持单条删除')
    const reason = wrapper.get('[aria-label="导入批次撤销原因"]')
    await reason.setValue('本次文件上传错误')
    cartonApiMock.undoScheduleImport.mockImplementation(async () => {
      const updated = { ...batch, status: 'REJECTED' }
      cartonApiMock.listImports.mockImplementation(async (_factory: string, type: string) => type === kind ? [updated] : [])
      return updated
    })
    await reason.element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(cartonApiMock.undoScheduleImport).toHaveBeenCalledExactlyOnceWith('huaxing', batch.id, '本次文件上传错误')
    expect(wrapper.text()).toContain('已整批撤销')
    expect(wrapper.find('[aria-label="撤销本次导入 待撤销排期.xlsx"]').exists()).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text() === '查看结果')).toBe(false)
    wrapper.unmount()
  })

  it('hides deletion and undo controls without their scoped permissions', async () => {
    mockReceiptWorkspace([{ ...orderFixture('H-NO-PERM', businessDateOffset(3)), can_delete_history: true }])
    authStoreMock.can.mockImplementation(((permission: string) => !['carton_procurement:order_write', 'carton_procurement:import'].includes(permission)) as () => boolean)
    cartonApiMock.listImports.mockResolvedValue([{ id: 'B', status: 'REQUIRES_REVIEW', import_type: 'WEEKLY_SCHEDULE', original_filename: 'read-only.xlsx', created_at: '', parse_summary: { rows: [] } }])
    const orders = mountView('orders'); await flushPromises()
    expect(orders.text()).not.toContain('批量删除历史订单')
    orders.unmount()
    const weekly = mountView('weekly-check'); await flushPromises()
    expect(weekly.find('[aria-label="撤销本次导入 read-only.xlsx"]').exists()).toBe(false)
    weekly.unmount()
  })

  beforeEach(() => {
    vi.resetAllMocks()
    positionsMock.locations.mockResolvedValue([{ id: 'LOC-A', factory_id: 'huaxing', warehouse: '默认仓', bin_code: 'A-01', label: 'A-01' }, { id: 'LOC-B', factory_id: 'huaxing', warehouse: '默认仓', bin_code: 'B-02', label: 'B-02' }])
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

  it('keeps customer PO but exposes no offline supplement action', async () => {
    mockReceiptWorkspace([orderFixture('CT-PO-NORMAL', businessDateOffset(3))])
    const wrapper = mountView('orders'); await flushPromises()
    await openOrderMoreActions(wrapper.get('[data-order-no="CT-PO-NORMAL"]'), 'CT-PO-NORMAL')
    expect(wrapper.text()).not.toContain('补单')
    wrapper.unmount()
  })

  it('switches receipt ledgers without stacking them or discarding manual entry', async () => {
    mockReceiptWorkspace([orderFixture('KEEP', businessDateOffset(3), 'PENDING_SUPPLIER')])
    const wrapper = mountView('receipts'); await flushPromises()
    const pages = wrapper.get('nav[aria-label="收料入库子页面"]')
    expect(pages.findAll('button').map(b => b.text())).toEqual(['待收订单', '送货单导入', '收料历史'])
    expect(wrapper.find('table[aria-label="收料历史台账明细"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="登记 KEEP 收料"]').trigger('click'); await flushPromises()
    await fillAllManualReceiptPapers(wrapper)
    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-KEEP')
    await findButton(wrapper, '返回待收订单').trigger('click'); await flushPromises()
    await pages.findAll('button')[2]!.trigger('click')
    expect(wrapper.find('table[aria-label="收料历史台账明细"]').exists()).toBe(true)
    expect(wrapper.find('[data-receipt-order="KEEP"]').exists()).toBe(false)
    await pages.findAll('button')[1]!.trigger('click')
    expect(wrapper.find('input[aria-label="选择送货单文件"]').exists()).toBe(true)
    expect(wrapper.find('table[aria-label="收料历史台账明细"]').exists()).toBe(false)
    await pages.findAll('button')[0]!.trigger('click')
    await wrapper.get('button[aria-label="登记 KEEP 收料"]').trigger('click'); await flushPromises()
    await fillAllManualReceiptPapers(wrapper)
    expect(wrapper.get<HTMLInputElement>('input[aria-label="人工送货单号"]').element.value).toBe('DN-KEEP')
    wrapper.unmount()
  })

  it('exposes eight grouped work areas and clearly labels the offline fallback', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('工作看板')
    expect(wrapper.text()).toContain('订单管理')
    expect(wrapper.get('nav[aria-label="纸箱采购协同功能"]').findAll('button').map(button => button.text())).toEqual(['工作看板', '订单管理', '收料入库', '库存管理', '异常处理', '月结对账', '基础资料', '操作日志'])
    expect(wrapper.text()).toContain('收料入库')
    expect(wrapper.text()).toContain('库存管理')
    expect(wrapper.text()).toContain('月结对账')
    expect(wrapper.text()).toContain('异常处理')
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
    expect(wrapper.text()).toContain('导入业务排期')

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
    expect(summary.element.nextElementSibling).toBe(filterToolbar.element.parentElement)
    expect(filterToolbar.element.parentElement).toBe(wrapper.get('[aria-label="订单批量选择"]').element.parentElement)
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
    expect(selectionToolbar.get('.order-ledger-grid').exists()).toBe(true)
    expect(firstOrder.get('.order-ledger-grid').exists()).toBe(true)
    expect(selectAll.classes()).toContain('size-5')
    expect(orderSelector.classes()).toContain('size-5')
    expect(orderSelector.element.parentElement?.tagName).toBe('DIV')
  })

  it('derives the plan due date from the customer due date and warns on short lead time', async () => {
    const wrapper = mountView('orders')
    await flushPromises()
    await findButton(wrapper, '新建纸箱订单').trigger('click')
    expect((wrapper.get('input[aria-label="订单客户"]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('input[aria-label="订单客户"]').trigger('focus')
    await wrapper.get('[aria-label="选择客户 Dickie"]').trigger('click')

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

    expect(wrapper.findAll('select[aria-label="客户筛选"]')).toHaveLength(1)
    expect(wrapper.get('[aria-label="订单筛选与批量操作"]').find('select[aria-label="客户筛选"]').exists()).toBe(true)

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
    expect((wrapper.get('input[aria-label="订单客户"]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('input[aria-label="订单客户"]').trigger('focus')
    await wrapper.get('[aria-label="选择客户 Dickie"]').trigger('click')
    expect(wrapper.get('input[aria-label="纸箱供应商"]').attributes('disabled')).toBeDefined()
    await wrapper.get('input[aria-label="合同号"]').setValue('SC-DEMO-001')
    await wrapper.get('input[aria-label="客户 PO"]').setValue('PO-CUSTOMER-001')
    await wrapper.get('input[aria-label="货号"]').setValue('203399999')
    await wrapper.get('input[aria-label="产品名称"]').setValue('新产品')
    for (const label of ['纸品类型 1', '纸质 1', '规格 1']) expect(wrapper.get<HTMLInputElement>(`input[aria-label="${label}"]`).element.value).toBe('')
    await wrapper.get('input[aria-label="纸品类型 1"]').setValue('外箱')
    await wrapper.get('input[aria-label="纸质 1"]').setValue('A33+B')
    await wrapper.get('input[aria-label="规格 1"]').setValue('30 × 20 × 15 cm')
    expect(wrapper.get('output[aria-label="纸箱数量 1"]').text()).toBe('0')
    await wrapper.get('input[aria-label="订单数量"]').setValue('3601')
    expect(wrapper.get('output[aria-label="纸箱数量 1"]').text()).toBe('31')
    await wrapper.get('input[aria-label="订单数量"]').setValue('3600')
    await wrapper.get('input[aria-label="客户交期"]').setValue(businessDateOffset(8))
    expect((wrapper.get('input[aria-label="计划交期"]').element as HTMLInputElement).value).toBe(businessDateOffset(5))
    await findButton(wrapper, '新增纸品明细').trigger('click')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="纸品类型 2"]').element.value).toBe('')
    await wrapper.get('input[aria-label="纸品类型 2"]').setValue('滑板纸')
    await wrapper.get('input[aria-label="纸质 2"]').setValue('A9A')
    await wrapper.get('input[aria-label="规格 2"]').setValue('29 × 19 cm')
    await wrapper.get('input[aria-label="每箱个数 2"]').setValue('2')
    expect(wrapper.get('output[aria-label="纸箱数量 2"]').text()).toBe('1,800')
    await wrapper.get('[data-testid="order-form-overlay"]').trigger('click')
    expect((wrapper.get('input[aria-label="合同号"]').element as HTMLInputElement).value).toBe('SC-DEMO-001')
    expect((wrapper.get('input[aria-label="纸质 2"]').element as HTMLInputElement).value).toBe('A9A')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('SC-DEMO-001')
    expect(wrapper.text()).toContain('203399999')
    const createdOrder = wrapper.get('[data-order-no="CT-260805-ABC123"]')
    await createdOrder.get('button[aria-label="查看 CT-260805-ABC123 完整订单明细"]').trigger('click')
    expect(wrapper.text()).toContain('共 2 项纸品')
    expect(wrapper.text()).toContain('A9A')
    await wrapper.get('button[aria-label="关闭订单明细"]').trigger('click')
    expect(cartonApiMock.createOrder).toHaveBeenCalledWith(expect.objectContaining({ status: 'CONFIRMED', customer_po: 'PO-CUSTOMER-001' }))
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
    expect((wrapper.get('input[aria-label="订单客户"]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('input[aria-label="订单客户"]').trigger('focus')
    await wrapper.get('[aria-label="选择客户 Dickie"]').trigger('click')
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
    expect((wrapper.get('input[aria-label="订单客户"]').element as HTMLInputElement).value).toBe('Dickie')
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
    expect(confirmSpy).not.toHaveBeenCalled()
    let confirmation = wrapper.get('[aria-label="批量采购单确认"]')
    expect(confirmation.text()).toContain('包含 1 张非首次或已发行采购单')
    expect(confirmation.text()).toContain(`${appendOrder.order_no}（追加采购单）`)
    expect(cartonApiMock.issuePurchaseOrders).not.toHaveBeenCalled()
    await confirmation.findAll('button').find(button => button.text() === '取消')!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('已取消批量发行')

    await issueButton.trigger('click')
    await flushPromises()
    confirmation = wrapper.get('[aria-label="批量采购单确认"]')
    await confirmation.findAll('button').find(button => button.text() === '确认并下载')!.trigger('click')
    await flushPromises()
    expect(cartonApiMock.issuePurchaseOrders).toHaveBeenCalledWith(
      'huaxing',
      expect.arrayContaining([initialOrder, appendOrder]),
    )
    confirmSpy.mockRestore()
  })

  it('soft-confirms and re-batches latest immutable snapshots when selected orders have no new change', async () => {
    const first = orderFixture('CT-BATCH-REUSE-001', businessDateOffset(4), 'COMPLETED')
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

    expect(confirmSpy).not.toHaveBeenCalled()
    const confirmation = wrapper.get('[aria-label="批量采购单确认"]')
    expect(confirmation.text()).toContain('2 张没有新变化、将重新打包最近一次历史快照')
    expect(cartonApiMock.issuePurchaseOrders).not.toHaveBeenCalled()
    await confirmation.findAll('button').find(button => button.text() === '确认并下载')!.trigger('click')
    await flushPromises()
    expect(cartonApiMock.issuePurchaseOrders).toHaveBeenCalledWith('huaxing', expect.arrayContaining([first, second]))
    expect(wrapper.get('[role="status"]').text()).toContain('重新打包历史快照 2 份')
    confirmSpy.mockRestore()
  })

  it('dismisses batch confirmation without issuing when leaving the orders page', async () => {
    const order = orderFixture('CT-BATCH-LEAVE', businessDateOffset(4), 'PARTIALLY_RECEIVED')
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([order])
    cartonApiMock.getPurchaseOrderContext.mockResolvedValue({
      factory_id: 'huaxing', order_no: order.order_no, order_revision: 1,
      pending_type: 'APPEND', pending_product_quantity: '100', pending_line_count: 1,
      can_generate: true, latest_document_no: '', historical_baseline: false, issues: [],
    })
    const wrapper = mountView('orders')
    await flushPromises()
    await wrapper.get(`input[aria-label="选择订单 ${order.order_no}"]`).setValue(true)
    await findButton(wrapper, '发行供应商采购单（1）').trigger('click')
    await flushPromises()
    expect(wrapper.find('[aria-label="批量采购单确认"]').exists()).toBe(true)
    routeState.query.tab = 'inventory'
    await flushPromises()
    expect(wrapper.find('[aria-label="批量采购单确认"]').exists()).toBe(false)
    expect(cartonApiMock.issuePurchaseOrders).not.toHaveBeenCalled()
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

    expect(wrapper.text()).toContain('历史已下单数量已登记为历史基线')
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

  it('edits imported demand without deriving missing product or packing quantities or replacing the planned date', async () => {
    const seed = orderFixture('CT-HISTORY-EDIT', businessDateOffset(8))
    const order = { ...seed, quantity_basis: 'EXPLICIT', product_order_quantity: null,
      lines: [{ ...seed.lines[0], usage_quantity: null, required_quantity: '100' }] }
    cartonApiMock.listOrders.mockResolvedValue([order])
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.updateOrder.mockResolvedValue({ ...order, revision: 2 })
    const wrapper = mountView('orders'); await flushPromises()
    await openOrderMoreActions(wrapper.get('[data-order-no="CT-HISTORY-EDIT"]'), 'CT-HISTORY-EDIT')
    await wrapper.get('button[aria-label="修改 CT-HISTORY-EDIT 订单"]').trigger('click')
    expect((wrapper.get('input[aria-label="订单数量"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('input[aria-label="每箱个数 1"]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('input[aria-label="纸品需求数量 1"]').setValue(110)
    await wrapper.get('textarea[aria-label="订单修改原因"]').setValue('按原表核实箱数')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(cartonApiMock.updateOrder).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
      quantity_basis: 'EXPLICIT', product_order_quantity: null, due_date: order.due_date,
      lines: [expect.objectContaining({ usage_quantity: null, required_quantity: 110 })],
    }))
  })

  it('adjusts explicit paper demand without inventing a product delta and protects pending receipts', async () => {
    const seed = orderFixture('CT-EXPLICIT', businessDateOffset(5), 'PARTIALLY_RECEIVED')
    const order = { ...seed, quantity_basis: 'EXPLICIT', product_order_quantity: null,
      lines: [{ ...seed.lines[0], usage_quantity: null, required_quantity: '100', received_quantity: '20', pending_received_quantity: '10', remaining_quantity: '80', maximum_reducible_quantity: '70' }] }
    cartonApiMock.listOrders.mockResolvedValue([order])
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.appendOrder.mockResolvedValue(order)
    cartonApiMock.reduceOrder.mockResolvedValue(order)
    const wrapper = mountView('orders'); await flushPromises()
    await openOrderMoreActions(wrapper.get('[data-order-no="CT-EXPLICIT"]'), 'CT-EXPLICIT')
    await wrapper.get('button[aria-label="追加 CT-EXPLICIT 订单"]').trigger('click')
    expect(wrapper.find('input[aria-label="追加订单数量"]').exists()).toBe(false)
    await wrapper.get(`input[aria-label="追加后纸品需求 ${order.lines[0]!.id}"]`).setValue(120)
    await wrapper.get('[data-testid="append-order-form"]').trigger('submit'); await flushPromises()
    expect(cartonApiMock.appendOrder).toHaveBeenCalledWith('huaxing', expect.anything(), null, '客人追加订单', order.due_date, order.customer_due_date,
      [{ order_line_id: order.lines[0]!.id, required_quantity: 120 }])
    await openOrderMoreActions(wrapper.get('[data-order-no="CT-EXPLICIT"]'), 'CT-EXPLICIT')
    await wrapper.get('button[aria-label="减单 CT-EXPLICIT"]').trigger('click')
    expect(wrapper.find('input[aria-label="减单数量"]').exists()).toBe(false)
    const input = wrapper.get(`input[aria-label="减少后纸品需求 ${order.lines[0]!.id}"]`)
    await input.setValue(25)
    await wrapper.get('[data-testid="reduce-order-form"]').trigger('submit'); await flushPromises()
    expect(cartonApiMock.reduceOrder).not.toHaveBeenCalled()
    await input.setValue(30)
    await wrapper.get('[data-testid="reduce-order-form"]').trigger('submit'); await flushPromises()
    expect(cartonApiMock.reduceOrder).toHaveBeenCalledWith('huaxing', expect.anything(), null, '客人退单',
      [{ order_line_id: order.lines[0]!.id, required_quantity: 30 }])
  })

  it('uses the server reduction floor while replacement goods are still outstanding', async () => {
    const seed = orderFixture('CT-REPLACE-FLOOR', businessDateOffset(5), 'PARTIALLY_RECEIVED')
    const order = { ...seed, quantity_basis: 'EXPLICIT', product_order_quantity: null,
      lines: [{ ...seed.lines[0], usage_quantity: null, required_quantity: '100', received_quantity: '70', pending_received_quantity: '0', remaining_quantity: '30', maximum_reducible_quantity: '20' }] }
    mockReceiptWorkspace([order as ReturnType<typeof orderFixture>])
    const wrapper = mountView('orders'); await flushPromises()
    await openOrderMoreActions(wrapper.get('[data-order-no="CT-REPLACE-FLOOR"]'), 'CT-REPLACE-FLOOR')
    await wrapper.get('button[aria-label="减单 CT-REPLACE-FLOOR"]').trigger('click')
    const input = wrapper.get(`input[aria-label="减少后纸品需求 ${order.lines[0]!.id}"]`)
    expect(input.attributes('min')).toBe('80')
    await input.setValue(70)
    await wrapper.get('[data-testid="reduce-order-form"]').trigger('submit'); await flushPromises()
    expect(cartonApiMock.reduceOrder).not.toHaveBeenCalled()
    wrapper.unmount()
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

  it.each(['carton', 'pmc-warehouse'])('shows warehouse order operations with scoped permissions in %s', async (department) => {
    authStoreMock.can.mockImplementation((permission: string, factory?: string, scope?: string) =>
      factory === 'huaxing' && scope === department
      && ['carton_procurement:order_write', 'carton_procurement:inventory_write'].includes(permission))
    const rows = ['CONFIRMED', 'PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED']
      .map(status => orderFixture(`CT-${status}`, businessDateOffset(5), status))
    mockReceiptWorkspace(rows)
    const wrapper = mountView('orders'); await flushPromises()
    for (const row of rows) {
      const card = wrapper.get(`[data-order-no="${row.order_no}"]`)
      await openOrderMoreActions(card, row.order_no)
      expect(card.find(`[aria-label="追加 ${row.order_no} 订单"]`).exists()).toBe(true)
      expect(card.find(`[aria-label="减单 ${row.order_no}"]`).exists())
        .toBe(['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(row.status))
      expect(card.find(`[aria-label="补单 ${row.order_no}"]`).exists())
        .toBe(['PARTIALLY_RECEIVED', 'COMPLETED'].includes(row.status))
    }
    wrapper.unmount()
  })

  it('hides submitted-order adjustments and replenishment without inventory or supervisor permission', async () => {
    const submitted = orderFixture('CT-NO-ADJUST', businessDateOffset(5), 'PARTIALLY_RECEIVED')
    authStoreMock.can.mockImplementation((permission: string) =>
      !['carton_procurement:order_adjust', 'carton_procurement:inventory_write'].includes(permission))
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
    expect(card.find('button[aria-label="补单 CT-NO-ADJUST"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it.each(['foreign-factory', 'other-department', 'read-only'])('hides order operations for %s access', async (access) => {
    authStoreMock.can.mockImplementation((permission: string, factory?: string, department?: string) => {
      if (permission === 'carton_procurement:read') return true
      return access !== 'read-only' && factory === (access === 'foreign-factory' ? 'huadeng' : 'huaxing')
        && department === (access === 'other-department' ? 'qc' : 'pmc-warehouse')
    })
    mockReceiptWorkspace(['CONFIRMED', 'PARTIALLY_RECEIVED'].map(status => orderFixture(`CT-${status}`, businessDateOffset(5), status)))
    const wrapper = mountView('orders'); await flushPromises()
    for (const status of ['CONFIRMED', 'PARTIALLY_RECEIVED']) {
      const card = wrapper.get(`[data-order-no="CT-${status}"]`)
      const more = card.find(`[aria-label="更多 CT-${status} 订单操作"]`)
      if (more.exists()) await more.trigger('click')
      expect(card.find(`[aria-label="追加 CT-${status} 订单"]`).exists()).toBe(false)
      expect(card.find(`[aria-label="减单 CT-${status}"]`).exists()).toBe(false)
      expect(card.find(`[aria-label="补单 CT-${status}"]`).exists()).toBe(false)
    }
    wrapper.unmount()
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

    expect(cartonApiMock.uploadHistoryOrders).not.toHaveBeenCalled()
    wrapper.getComponent({ name: 'CartonHistoryImportDialog' }).vm.$emit('imported', await cartonApiMock.uploadHistoryOrders())
    await flushPromises()
    expect(wrapper.text()).toContain('已导入 1 张、4 条纸品')
    expect(wrapper.find('[data-order-no="HIST-2025-001"]').exists()).toBe(true)
    expect(wrapper.get('[data-order-no="HIST-2025-001"]').text()).not.toContain('HIST-2025-001')
  })

  it('selects a customer contract and posts only checked paper lines across distinct POs without completing unreceived siblings', async () => {
    const first = { ...orderFixture('PAPER-A', businessDateOffset(3), 'PENDING_SUPPLIER'), contract_no: 'SC-SHARED', customer_po: 'PO-A', item_no: 'SAME-ITEM' }
    first.lines.push({ ...first.lines[0]!, id: 'INNER-A', line_no: 2, packaging_type: '内箱', specification: '8*6*3' },
      { ...first.lines[0]!, id: 'CARD-A', line_no: 3, packaging_type: '平卡', unit: '张', paper_quality: '', specification: '', unit_price: '0' })
    const second = { ...orderFixture('PAPER-B', businessDateOffset(3), 'PENDING_SUPPLIER'), contract_no: 'SC-SHARED', customer_po: 'PO-B', item_no: 'SAME-ITEM' }
    const otherCustomer = { ...orderFixture('PAPER-C', businessDateOffset(3), 'PENDING_SUPPLIER'), contract_no: 'SC-SHARED', customer_code: 'BETA', customer_name: 'Beta' }
    mockReceiptWorkspace([first, second, otherCustomer])
    cartonApiMock.createReceipt.mockImplementation(async payload => ({ ...payload, id: 'RC-PAPER', receipt_no: 'RC-PAPER', status: 'POSTED', revision: 2 }))
    const wrapper = mountView('receipts'); await flushPromises()
    await wrapper.get('select[aria-label="选择收料合同"]').setValue(JSON.stringify(['DICKIE', 'SC-SHARED']))
    expect(wrapper.findAll('[data-receipt-order]')).toHaveLength(2)
    expect(wrapper.find('[aria-label="PAPER-C 选择收料纸品"]').exists()).toBe(false)
    const firstGroup = wrapper.get('[aria-label="PAPER-A 选择收料纸品"]')
    expect(firstGroup.text()).toContain('客户 PO：PO-A')
    expect(wrapper.get('[aria-label="PAPER-B 选择收料纸品"]').text()).toContain('客户 PO：PO-B')
    expect(firstGroup.get<HTMLInputElement>('input[aria-label="选择纸品 LINE-PAPER-A"]').element.checked).toBe(false)
    expect(firstGroup.get('input[aria-label="LINE-PAPER-A 本次实际收到"]').attributes('disabled')).toBeDefined()
    await firstGroup.get('input[aria-label="选择纸品 LINE-PAPER-A"]').setValue(true)
    await firstGroup.get('input[aria-label="LINE-PAPER-A 本次实际收到"]').setValue('100')
    await findButton(wrapper, '登记所选订单收料').trigger('click'); await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).not.toContain('全部收齐，确认后自动完成')
    await dialog.get('input[aria-label="选择纸品 INNER-A"]').setValue(true)
    await dialog.get('input[aria-label="MANUAL-INNER-A 实收"]').setValue('25')
    await dialog.get('input[aria-label="选择纸品 LINE-PAPER-B"]').setValue(true)
    await dialog.get('input[aria-label="MANUAL-LINE-PAPER-B 实收"]').setValue('15')
    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-PAPERS')
    for (const picker of dialog.findAll('input[aria-label="仓库及仓位"]')) await picker.setValue('A-01')
    const review = dialog.get('[data-testid="receipt-review-table"]')
    expect(review.text()).toContain('PO-A'); expect(review.text()).toContain('PO-B')
    expect(review.text()).toContain('平卡')
    expect(review.get<HTMLInputElement>('input[aria-label="选择纸品 CARD-A"]').element.checked).toBe(false)
    expect(review.get('input[aria-label="MANUAL-CARD-A 实收"]').attributes('disabled')).toBeDefined()
    expect(dialog.find('[aria-label$="选择收料纸品"]').exists()).toBe(false)
    expect(dialog.find('input[aria-label$="本次实际收到"]').exists()).toBe(false)
    expect(review.findAll('input[aria-label="MANUAL-INNER-A 实收"]')).toHaveLength(1)
    await findButton(wrapper, '确认入库').trigger('click'); await flushPromises()
    expect(cartonApiMock.createReceipt).toHaveBeenCalledTimes(1)
    expect(cartonApiMock.createReceipt).toHaveBeenCalledWith(expect.objectContaining({
      post_immediately: true,
      lines: [expect.objectContaining({ order_line_id: 'LINE-PAPER-A', received_quantity: 100, delivered_quantity: 100 }),
        expect.objectContaining({ order_line_id: 'INNER-A', received_quantity: 25, delivered_quantity: 25 }),
        expect.objectContaining({ order_line_id: 'LINE-PAPER-B', received_quantity: 15, delivered_quantity: 15 })],
    }))
    expect(dialog.text()).not.toContain('全部明细已收齐并自动完成')
    expect(cartonApiMock.confirmReceipt).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('preserves paper inputs when adding contracts and excludes unchecked values from all receipt validation', async () => {
    const orders = ['KEEP-A', 'KEEP-B'].map(no => orderFixture(no, businessDateOffset(3), 'PENDING_SUPPLIER'))
    mockReceiptWorkspace(orders)
    cartonApiMock.createReceipt.mockImplementation(async payload => ({ ...payload, id: 'RC-KEEP', receipt_no: 'RC-KEEP', status: 'POSTED', revision: 2 }))
    const wrapper = mountView('receipts'); await flushPromises()
    await wrapper.get('select[aria-label="选择收料合同"]').setValue(JSON.stringify(['DICKIE', 'SC-KEEP-A']))
    await wrapper.get('input[aria-label="选择纸品 LINE-KEEP-A"]').setValue(true)
    await wrapper.get('input[aria-label="LINE-KEEP-A 本次实际收到"]').setValue('12')
    await findButton(wrapper, '登记所选订单收料').trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-KEEP-PAPERS')
    await wrapper.get('input[aria-label="实际验收日期"]').setValue('2026-09-20')
    await wrapper.get('button[aria-label="关闭收料录入"]').trigger('click')
    await wrapper.get('select[aria-label="选择收料合同"]').setValue(JSON.stringify(['DICKIE', 'SC-KEEP-B']))
    await findButton(wrapper, '登记所选订单收料').trigger('click'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="MANUAL-LINE-KEEP-A 实收"]').element.value).toBe('12')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="人工送货单号"]').element.value).toBe('DN-KEEP-PAPERS')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="实际验收日期"]').element.value).toBe('2026-09-20')
    await wrapper.get('input[aria-label="选择纸品 LINE-KEEP-B"]').setValue(true)
    await wrapper.get('input[aria-label="MANUAL-LINE-KEEP-B 实收"]').setValue('999')
    await wrapper.get('input[aria-label="MANUAL-LINE-KEEP-B 单价"]').setValue('0')
    await wrapper.get('input[aria-label="选择纸品 LINE-KEEP-B"]').setValue(false)
    await wrapper.get('input[aria-label="仓库及仓位"]').setValue('A-01')
    await findButton(wrapper, '确认入库').trigger('click'); await flushPromises()
    expect(cartonApiMock.createReceipt).toHaveBeenCalledWith(expect.objectContaining({
      lines: [expect.objectContaining({ order_line_id: 'LINE-KEEP-A', received_quantity: 12 })],
    }))
    wrapper.unmount()
  })

  it('requires positive entered quantities and retains a failed manual paper submission for correction', async () => {
    mockReceiptWorkspace([orderFixture('VALIDATE', businessDateOffset(3), 'PENDING_SUPPLIER')])
    cartonApiMock.createReceipt.mockRejectedValue(new Error('当前订单待收数量已变更，请刷新核对'))
    const wrapper = mountView('receipts'); await flushPromises()
    await wrapper.get('button[aria-label="登记 VALIDATE 收料"]').trigger('click'); await flushPromises()
    await wrapper.get('input[aria-label="选择纸品 LINE-VALIDATE"]').setValue(true)
    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-VALIDATE')
    await findButton(wrapper, '确认入库').trigger('click')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('大于 0 的本次实际收到数量')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    await wrapper.get('input[aria-label="MANUAL-LINE-VALIDATE 实收"]').setValue('101')
    await findButton(wrapper, '确认入库').trigger('click')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('不能大于该订单明细当前待收数量')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    await wrapper.get('input[aria-label="MANUAL-LINE-VALIDATE 实收"]').setValue('30')
    await wrapper.get('input[aria-label="仓库及仓位"]').setValue('A-01')
    await findButton(wrapper, '确认入库').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('当前订单待收数量已变更')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="MANUAL-LINE-VALIDATE 实收"]').element.value).toBe('30')
    expect(wrapper.get('input[aria-label="MANUAL-LINE-VALIDATE 实收"]').attributes('disabled')).toBeUndefined()
    expect(cartonApiMock.confirmReceipt).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('calculates effective receipts in the dialog without posting inventory', async () => {
    mockReceiptWorkspace([orderFixture('CT-DAMAGE', businessDateOffset(3), 'PENDING_SUPPLIER')])
    const wrapper = mountView('receipts')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="登记 CT-DAMAGE 收料"]').trigger('click')
    await flushPromises()
    await fillAllManualReceiptPapers(wrapper)
    expect(wrapper.get('[role="dialog"]').text()).toContain('收料反馈明细')
    await wrapper.get('input[aria-label="MANUAL-LINE-CT-DAMAGE 破损"]').setValue('2')
    await wrapper.get('input[aria-label="MANUAL-LINE-CT-DAMAGE 拒收"]').setValue('3')
    expect(wrapper.get('[role="dialog"]').text()).toContain('有效收料95')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    expect(cartonApiMock.confirmReceipt).not.toHaveBeenCalled()
    await findButton(wrapper, '确认入库').trigger('click')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('请先填写送货单号')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps actual acceptance independent from September order/delivery dates through reopening and posting', async () => {
    const order = { ...orderFixture('CT-ACCEPTANCE', businessDateOffset(3), 'PENDING_SUPPLIER'), order_date: '2026-09-30' }
    mockReceiptWorkspace([order])
    cartonApiMock.createReceipt.mockImplementation(async (payload) => ({ ...payload,
      id: 'CTR-ACCEPTANCE', receipt_no: 'RC-ACCEPTANCE', status: 'POSTED', revision: 2,
    }))
    const wrapper = mountView('receipts')
    await flushPromises()
    await wrapper.get('button[aria-label="登记 CT-ACCEPTANCE 收料"]').trigger('click')
    await flushPromises()
    await fillAllManualReceiptPapers(wrapper)
    expect(wrapper.get<HTMLInputElement>('input[aria-label="实际验收日期"]').element.value).toBe(businessDateOffset(0))
    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-ACCEPTANCE')
    await wrapper.get('input[aria-label="人工送货日期"]').setValue('2026-09-30')
    await wrapper.get('input[aria-label="实际验收日期"]').setValue('2026-10-02')
    await wrapper.get('input[aria-label="仓库及仓位"]').setValue('A-01')
    await wrapper.get('button[aria-label="关闭收料录入"]').trigger('click')
    await findButton(wrapper, '收料历史').trigger('click')
    await findButton(wrapper, '待收订单').trigger('click')
    await wrapper.get('button[aria-label="登记 CT-ACCEPTANCE 收料"]').trigger('click')
    await flushPromises()
    await fillAllManualReceiptPapers(wrapper)
    expect(wrapper.get<HTMLInputElement>('input[aria-label="实际验收日期"]').element.value).toBe('2026-10-02')
    await findButton(wrapper, '确认入库').trigger('click')
    await flushPromises()
    expect(cartonApiMock.createReceipt).toHaveBeenCalledWith(expect.objectContaining({
      delivery_date: '2026-09-30', acceptance_date: '2026-10-02', post_immediately: true,
    }))
    expect(wrapper.get<HTMLInputElement>('input[aria-label="实际验收日期"]').element.value).toBe('2026-10-02')
    expect(wrapper.get('input[aria-label="实际验收日期"]').attributes('disabled')).toBeDefined()
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
    cartonApiMock.createReceipt.mockImplementation(async () => {
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
    await findButton(wrapper, '送货单导入').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('人工录入订单收料')
    expect(wrapper.text()).toContain('等待导入并复核送货单')
    expect(findButton(wrapper, '导入送货单').exists()).toBe(true)
    await wrapper.get('[aria-label="收料入库子页面"]').findAll('button')[0]!.trigger('click')
    expect(wrapper.findAll('button').some((button) => button.text() === '人工录入收料')).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text() === '导入送货单')).toBe(false)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="登记 CT-260805-76C698 收料"]').trigger('click')
    await fillAllManualReceiptPapers(wrapper)

    expect(wrapper.text()).toContain('人工录入订单收料')
    const receiptTable = wrapper.get('[data-testid="receipt-review-table"]')
    expect(receiptTable.text()).toContain('CT-260805-76C698')
    expect(receiptTable.text()).toContain('3722111')
    expect(receiptTable.text()).toContain('人工录入')
    expect(wrapper.text()).toContain('全部收齐，确认后自动完成')
    await findButton(wrapper, '确认入库').trigger('click')
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').attributes('role')).toBe('alert')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('请先填写送货单号')
    expect(wrapper.get('input[aria-label="人工送货单号"]').attributes('aria-invalid')).toBe('true')

    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-MANUAL-260811-001')
    await wrapper.get('input[aria-label="仓库及仓位"]').setValue('A-01')
    const receiptPrice = wrapper.get<HTMLInputElement>('input[aria-label="MANUAL-CTL-MANUAL-001 单价"]')
    expect(receiptPrice.element.value).toBe('3.46')
    expect(receiptPrice.element.closest('td')?.textContent).toContain('HKD / 个')
    for (const price of ['', '0', '-1', '1.1234567', '1000000000000']) {
      await receiptPrice.setValue(price)
      await findButton(wrapper, '确认入库').trigger('click')
      expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
      expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('必须填写大于 0 的单价')
    }
    await receiptPrice.setValue('')
    expect(receiptPrice.element.closest('td')?.textContent).toContain('请填写大于 0 的单价')
    await receiptPrice.setValue('2.567891')

    await wrapper.get('button[aria-label="关闭收料录入"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('收料反馈明细')
    await findButton(wrapper, '登记所选订单收料').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="人工送货单号"]').element.value).toBe('DN-MANUAL-260811-001')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="仓库及仓位"]').element.value).toBe('A-01')
    await findButton(wrapper, '确认入库').trigger('click')
    await flushPromises()

    expect(cartonApiMock.createReceipt).toHaveBeenCalledWith(expect.objectContaining({
      factory_id: 'huaxing',
      delivery_note_no: 'DN-MANUAL-260811-001',
      import_batch_id: null,
      lines: [expect.objectContaining({
        order_line_id: 'CTL-MANUAL-001',
        delivered_quantity: 3600,
        received_quantity: 3600,
        location_allocations: [{ location_id: 'LOC-A', quantity: 3600 }],
        unit_price: 2.567891,
        currency: 'HKD',
        unit: '个',
      })],
    }))
    expect(wrapper.get('input[aria-label="MANUAL-CTL-MANUAL-001 单价"]').attributes('disabled')).toBeDefined()
    expect(openOrder.lines[0]?.unit_price).toBe('3.46')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').attributes('role')).toBe('status')
    expect(wrapper.get('[data-testid="receipt-save-feedback"]').text()).toContain('入库成功')
    expect(cartonApiMock.createReceipt).toHaveBeenCalledWith(expect.objectContaining({ post_immediately: true }))
    expect(cartonApiMock.confirmReceipt).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('全部明细已收齐并自动完成')
  })

  it.each(['row', 'selected'] as const)('starts the remaining receipt batch from %s after direct posting', async (entry) => {
    const orders = ['CT-BATCH-A', 'CT-BATCH-B'].map((number) => orderFixture(number, businessDateOffset(3), 'PENDING_SUPPLIER'))
    mockReceiptWorkspace(orders)
    cartonApiMock.createReceipt.mockResolvedValue({
      id: 'CTR-BATCH-FIRST', receipt_no: 'RC-BATCH-FIRST', status: 'PENDING_CONFIRMATION', revision: 1, lines: [],
    })
    cartonApiMock.createReceipt.mockImplementation(async () => {
      cartonApiMock.listOrders.mockResolvedValue(orders.map((order) => ({
        ...order, status: 'PARTIALLY_RECEIVED', revision: 2,
        lines: order.lines.map((line) => ({ ...line, received_quantity: '70', remaining_quantity: '30' })),
      })))
      return { id: 'CTR-BATCH-FIRST', receipt_no: 'RC-BATCH-FIRST', status: 'POSTED', revision: 2, lines: [] }
    })
    const wrapper = mountView('receipts')
    await flushPromises()
    const selected = entry === 'row' ? orders.slice(0, 1) : orders
    const open = async () => {
      if (entry === 'row') await wrapper.get('button[aria-label="登记 CT-BATCH-A 收料"]').trigger('click')
      else await findButton(wrapper, '登记所选订单收料').trigger('click')
      await flushPromises()
      await fillAllManualReceiptPapers(wrapper)
    }
    if (entry === 'selected') {
      await wrapper.get('input[aria-label="全选待收订单"]').setValue(true)
    }
    await open()
    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-FIRST')
    for (const picker of wrapper.findAll('input[aria-label="仓库及仓位"]')) await picker.setValue('A-01')
    for (const order of selected) {
      await wrapper.get(`input[aria-label="MANUAL-LINE-${order.order_no} 实收"]`).setValue('70')
      await wrapper.get(`input[aria-label="MANUAL-LINE-${order.order_no} 单价"]`).setValue('2.5')
    }
    await findButton(wrapper, '确认入库').trigger('click')
    await flushPromises()
    expect(cartonApiMock.createReceipt).toHaveBeenCalledTimes(1)
    expect(cartonApiMock.confirmReceipt).not.toHaveBeenCalled()
    await wrapper.get('button[aria-label="关闭收料录入"]').trigger('click')
    await open()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="人工送货单号"]').element.value).toBe('')
    expect(wrapper.get('[role="dialog"]').text()).not.toContain('RC-BATCH-FIRST')
    expect(wrapper.get('[role="dialog"]').text()).toContain(`已选订单 ${selected.length} 张`)
    for (const order of selected) {
      const quantity = wrapper.get<HTMLInputElement>(`input[aria-label="MANUAL-LINE-${order.order_no} 实收"]`)
      expect(quantity.element.value).toBe('30')
      expect(quantity.attributes('disabled')).toBeUndefined()
      expect(wrapper.get<HTMLInputElement>(`input[aria-label="MANUAL-LINE-${order.order_no} 送货数量"]`).element.value).toBe('30')
    }
    await wrapper.get('input[aria-label="人工送货单号"]').setValue('DN-SECOND')
    for (const picker of wrapper.findAll('input[aria-label="仓库及仓位"]')) await picker.setValue('A-01')
    await findButton(wrapper, '确认入库').trigger('click')
    await flushPromises()
    expect(cartonApiMock.createReceipt).toHaveBeenLastCalledWith(expect.objectContaining({
      delivery_note_no: 'DN-SECOND',
      lines: selected.map((order) => expect.objectContaining({ order_line_id: `LINE-${order.order_no}`, received_quantity: 30, delivered_quantity: 30 })),
    }))
    wrapper.unmount()
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
    await findButton(wrapper, '送货单导入').trigger('click')
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
    expect(wrapper.text()).toContain('前往异常处理')
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
    cartonApiMock.createReceipt.mockResolvedValue({
      id: 'CTR-AD-HOC',
      receipt_no: 'RC-AD-HOC-001',
      status: 'POSTED',
      revision: 2,
      lines: [],
    })

    const wrapper = mountView('receipts')
    await flushPromises()
    await findButton(wrapper, '送货单导入').trigger('click')
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
    expect(wrapper.text()).toContain('核对无误后点击“确认入库”即可入库并计入月结')
    await wrapper.get('input[aria-label="仓库及仓位"]').setValue('A-01')

    await findButton(wrapper, '确认入库').trigger('click')
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
    expect(cartonApiMock.createReceipt).toHaveBeenCalledWith(expect.objectContaining({ post_immediately: true }))
    expect(cartonApiMock.confirmReceipt).not.toHaveBeenCalled()
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
    await findButton(wrapper, '送货单导入').trigger('click')
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
    expect(inventoryWrapper.text()).not.toContain('逐笔交易流水')
    expect(inventoryWrapper.get('[aria-label="库存管理子页面"]').text()).toContain('库存流水')
    expect(inventoryWrapper.text()).toContain('纸品类型')
    expect(inventoryWrapper.text()).toContain('纸质')

    const closingWrapper = mountView('closing')
    expect(closingWrapper.text()).toContain('期间库存月结核对页')
    expect(closingWrapper.text()).toContain('客户月结汇总快照')
    expect(closingWrapper.text()).toContain('当月可以核对确认并继续收发货')
    expect(closingWrapper.text()).not.toContain('逐笔交易流水')
  })

  it('filters realtime inventory balances using header search and the selection toolbar', async () => {
    const wrapper = mountView('inventory')
    const balanceTable = wrapper.findAll('table').find((table) => table.classes().includes('inventory-balance-table'))
    if (!balanceTable) throw new Error('Inventory balance table not found')

    expect(balanceTable.findAll('tbody tr')).toHaveLength(4)
    expect(balanceTable.html()).toContain('OUT-260805-008')

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
    await wrapper.get('button[aria-label="结存台账最近入库日期范围"]').trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, '2026-08-05')
    await clickCalendarDate(wrapper, '2026-08-05')
    expect(balanceTable.findAll('tbody tr')).toHaveLength(1)
    expect(balanceTable.text()).toContain('SC700142616')

    await wrapper.get('button[aria-label="清空结存台账筛选"]').trigger('click')
    expect(balanceTable.findAll('tbody tr')).toHaveLength(4)
  })

  it('keeps mixed inventory units separate on the ledger and dashboard and follows visible filters', async () => {
    mockReceiptWorkspace([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([
      { contract: 'MIX-A', quantity: '100.0001', unit: '个' },
      { contract: 'MIX-B', quantity: '164.9999', unit: '个' },
      { contract: 'MIX-C', quantity: '90', unit: '张' },
      { contract: 'ZERO', quantity: '0', unit: '套' },
    ].map(({ contract, quantity, unit }) => ({
      factory_id: 'huaxing', customer_code: 'DICKIE', customer_name: 'Dickie',
      contract_no: contract, item_no: contract, order_line_id: null,
      packaging_type: unit === '张' ? '卡纸' : '外箱', paper_quality: 'A33',
      specification: '30 × 20 × 15 cm', unit, balance: quantity,
      latest_location: 'A-01', latest_movement_id: `MV-${contract}`,
      latest_document_no: `DOC-${contract}`, latest_movement_at: '2026-09-01T10:00:00+08:00',
      latest_inbound_at: '2026-09-01T10:00:00+08:00',
    })))
    const wrapper = mountView('inventory')
    await flushPromises()
    expect(wrapper.get('[aria-label="实时库存数量合计"]').text()).toBe('当前结存 265 个 · 90 张 · 显示 3 / 4 条')
    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('MIX-A')
    expect(wrapper.get('[aria-label="实时库存数量合计"]').text()).toBe('当前结存 100.0001 个 · 显示 1 / 4 条')
    routeState.query.tab = 'dashboard'
    await flushPromises()
    expect(wrapper.get('[aria-label="看板库存数量合计"]').text()).toBe('100.0001 个')
    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('')
    expect(wrapper.get('[aria-label="看板库存数量合计"]').text()).toBe('265 个 · 90 张')
    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('NO-MATCH')
    expect(wrapper.get('[aria-label="看板库存数量合计"]').text()).toBe('暂无库存')
    wrapper.unmount()
  })

  it('counts month-end records rather than customers across months and currencies', async () => {
    mockReceiptWorkspace([])
    cartonApiMock.listClosings.mockResolvedValue([
      { id: 'MONTH-9', period: '2026-09', status: 'LOCKED', currency: 'CNY' },
      { id: 'MONTH-10', period: '2026-10', status: 'DRAFT', currency: 'CNY' },
      { id: 'MONTH-10-HKD', period: '2026-10', status: 'DRAFT', currency: 'HKD' },
    ].map(row => ({ ...row, factory_id: 'huaxing', customer_code: 'DICKIE', customer_name: 'Dickie',
      revision: 1, opening_quantity: '0', inbound_quantity: '1', outbound_quantity: '0',
      adjustment_quantity: '0', ending_quantity: '1', ending_amount: '1', pricing_issues: [],
    })))
    const wrapper = mountView('closing')
    await flushPromises()
    expect(wrapper.get('[aria-label="库存月结记录统计"]').text()).toContain('月结记录3 份')
    expect(wrapper.get('[aria-label="库存月结待处理统计"]').text()).toContain('待处理记录2 份')
    await wrapper.get('[aria-label="月结查询月份"]').setValue('2026-09')
    expect(wrapper.get('[aria-label="库存月结记录统计"]').text()).toContain('月结记录1 份')
    expect(wrapper.get('[aria-label="库存月结待处理统计"]').text()).toContain('待处理记录0 份')
    wrapper.unmount()
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
    const table = wrapper.findAll('table').find((candidate) => candidate.classes().includes('inventory-balance-table'))!
    expect(table.findAll('tbody tr')).toHaveLength(3)
    expect(wrapper.text()).toContain('最近入库日期')
    expect(wrapper.text()).not.toContain('最近变动日期')
    await wrapper.get('button[aria-label="结存台账最近入库日期范围"]').trigger('click')
    await flushPromises()
    await clickCalendarDate(wrapper, '2026-08-05')
    await clickCalendarDate(wrapper, '2026-08-05')
    expect(table.findAll('tbody tr')).toHaveLength(1)
    expect(table.text()).toContain('IN-RANGE')
    expect(table.text()).not.toContain('OUTSIDE-RANGE')
    expect(table.text()).not.toContain('NO-INBOUND')
    expect(table.html()).toContain('2026-08-10 12:00')
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

  it('exposes opening-stock template and import in its own subpage without writing on entry', async () => {
    mockReceiptWorkspace([])
    const wrapper = mountView('inventory')
    await flushPromises()
    expect(findButton(wrapper, '库存盘点').exists()).toBe(true)
    expect(wrapper.find('[aria-label="库存更多操作"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('库存数量调整')
    expect(wrapper.text()).not.toContain('期初库存管理')
    expect(wrapper.find('input[aria-label="选择历史库存文件"]').exists()).toBe(false)
    await findButton(wrapper, '期初库存').trigger('click')
    expect(wrapper.text()).toContain('期初库存管理')
    expect(wrapper.get('a[download="纸箱期初库存导入模板.xlsx"]').text()).toContain('下载期初库存模板')
    expect(wrapper.find('input[aria-label="选择历史库存文件"]').exists()).toBe(true)
    expect(findButton(wrapper, '导入期初库存').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('可以先选择文件')
    expect(wrapper.text()).toContain('预览前还需填写：尺寸单位')
    expect(wrapper.text()).not.toContain('期初基准日期')
    expect(wrapper.text()).toContain('入库时间按文件每行填写')
    expect(findButton(wrapper, '期初库存').attributes('aria-current')).toBe('page')
    expect(findButton(wrapper, '实时库存').attributes('aria-current')).toBeUndefined()
    expect(cartonApiMock.uploadHistoryInventory).not.toHaveBeenCalled()
    await findButton(wrapper, '返回库存台账').trigger('click')
    expect(wrapper.text()).not.toContain('期初库存管理')
    expect(findButton(wrapper, '实时库存').attributes('aria-current')).toBe('page')
  })

  it('passes the selected physical position directly into the stocktake workspace', async () => {
    mockReceiptWorkspace([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([{
      factory_id: 'huaxing', customer_code: 'C', customer_name: '客户', contract_no: 'SC1', item_no: 'I1',
      order_line_id: 'LINE1', packaging_type: '外箱', paper_quality: 'A33', specification: '1*1*1', unit: '个',
      balance: '3', latest_location: 'A', latest_movement_id: 'M1', latest_movement_at: '2026-09-08',
      position_key: '["LINE1","LOC-A"]', location_id: 'LOC-A', position_revision: 1,
    }])
    const wrapper = mountView('inventory', { CartonStocktakeWorkspace: true })
    await flushPromises()
    await wrapper.get('[aria-label="全选库存筛选结果"]').setValue(true)
    await findButton(wrapper, '库存盘点').trigger('click')
    expect(wrapper.findComponent({ name: 'CartonStocktakeWorkspace' }).props('initialPositionKeys')).toEqual(['["LINE1","LOC-A"]'])
  })

  it('shows position stock separately from exact paper-line arrivals, including split and standalone stock', async () => {
    const order = orderFixture('PROGRESS', businessDateOffset(4), 'PARTIALLY_RECEIVED')
    order.lines[0]!.received_quantity = '60'
    order.lines[0]!.remaining_quantity = '40'
    mockReceiptWorkspace([order])
    const balance = {
      factory_id: 'huaxing', customer_code: order.customer_code, customer_name: order.customer_name,
      contract_no: order.contract_no, item_no: order.item_no, order_line_id: order.lines[0]!.id,
      packaging_type: '外箱', paper_quality: 'A33+B', specification: '12*11*5', unit: '个',
      balance: '15', latest_location: 'A', latest_movement_id: 'M1', latest_movement_at: '2026-09-08',
      position_key: 'POS-A', location_id: 'A', position_revision: 1,
      inbound_quantity: '40', outbound_quantity: '30', opening_quantity: '10', transfer_quantity: '-7', adjustment_quantity: '2',
    }
    cartonApiMock.listInventoryBalances.mockResolvedValue([
      balance, { ...balance, position_key: 'POS-B', balance: '25', location_id: 'B' },
      { ...balance, position_key: 'POS-ADHOC', order_line_id: null },
      { ...balance, position_key: 'POS-UNKNOWN', order_line_id: 'UNKNOWN' },
    ])
    const wrapper = mountView('inventory')
    await flushPromises()
    const first = wrapper.get('[data-inventory-balance="POS-A"]')
    const second = wrapper.get('[data-inventory-balance="POS-B"]')
    const stockTable = first.element.closest('table')!
    expect(stockTable.querySelector('thead')?.textContent).toContain('累计入库累计出库当前结余')
    expect(stockTable.querySelector('thead')?.textContent).not.toContain('当前结存')
    expect(first.findAll('td')).toHaveLength(11)
    expect(first.findAll('td')[6]!.text()).toBe('40 个')
    expect(first.findAll('td')[7]!.text()).toBe('30 个')
    expect(first.findAll('td')[8]!.text()).toContain('15 个')
    expect(first.text()).toContain('期初 10 个')
    expect(first.text()).toContain('调仓净额 -7 个')
    expect(first.text()).toContain('调整 +2 个')
    expect(wrapper.get('[data-inventory-balance="POS-ADHOC"]').text()).toContain('15 个')
    expect(wrapper.get('[data-inventory-balance="POS-UNKNOWN"]').text()).toContain('15 个')
    expect(first.find('[role="progressbar"]').exists()).toBe(false)
    expect(second.text()).toContain('25 个')
    for (const row of [first, second]) {
      expect(row.text()).toContain('需求 100 个')
      expect(row.text()).toContain('已到 60 / 需求 100 个')
      expect(row.text()).toContain('还差 40 个')
    }
    expect(wrapper.get('[data-inventory-balance="POS-ADHOC"]').text()).toContain('无单库存')
    expect(wrapper.get('[data-inventory-balance="POS-UNKNOWN"]').find('[role="progressbar"]').exists()).toBe(false)
    // Receipt progress stays complete after stock has been issued out.
    cartonApiMock.listOrders.mockResolvedValue([{ ...order, lines: [{ ...order.lines[0], received_quantity: '100', remaining_quantity: '0' }] }])
    await findButton(wrapper, '刷新').trigger('click')
    await flushPromises()
    expect(first.text()).toContain('已到齐')
    expect(first.find('[role="progressbar"]').exists()).toBe(false)
  })

  it('lets an authorized carton supervisor maintain factory customer data', async () => {
    const masterGet = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
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

    const ordersWrapper = mountView('orders')
    await flushPromises()
    expect(ordersWrapper.findAll('button').some(button => button.text().includes('客户资料维护'))).toBe(false)
    await findButton(ordersWrapper, '基础资料').trigger('click')
    expect(routerReplaceMock).toHaveBeenCalledWith(expect.objectContaining({ query: expect.objectContaining({ tab: 'master-data' }) }))
    ordersWrapper.unmount()
    const wrapper = mountView('master-data')
    await flushPromises()
    await findButton(wrapper, '新增客户').trigger('click')

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
    masterGet.mockRestore()
  })

  it('discards old-factory customer responses while starting the new-factory load immediately', async () => {
    const masterGet = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
    for (const method of ['listOrders', 'listMovements', 'listClosings', 'listExceptions'] as const) cartonApiMock[method].mockResolvedValue([])
    let finishOld!: (rows: any[]) => void
    const oldRequest = new Promise<any[]>(resolve => { finishOld = resolve })
    const makeCustomer = (factory: string, name: string) => ({ id: factory, factory_id: factory, customer_code: name, customer_name: name, status: 'ACTIVE', revision: 1 })
    cartonApiMock.listCustomers.mockImplementation((factory: string) => factory === 'huaxing' ? oldRequest : Promise.resolve([makeCustomer(factory, 'B厂客户')]))
    const wrapper = mountView('master-data')
    routeState.query.factory = 'huakang-a'
    await flushPromises()
    expect(cartonApiMock.listCustomers).toHaveBeenCalledWith('huakang-a')
    expect(wrapper.text()).toContain('B厂客户')
    finishOld([makeCustomer('huaxing', 'A厂旧客户')]); await flushPromises()
    expect(wrapper.text()).not.toContain('A厂旧客户')
    expect(wrapper.text()).toContain('B厂客户')
    wrapper.unmount(); masterGet.mockRestore()
  })

  it('closes customer editing on factory change and ignores a late save result', async () => {
    const masterGet = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
    for (const method of ['listOrders', 'listMovements', 'listClosings', 'listExceptions'] as const) cartonApiMock[method].mockResolvedValue([])
    const c = { id: 'A', factory_id: 'huaxing', customer_code: 'A', customer_name: 'A厂客户', status: 'ACTIVE', revision: 1, contact_name: '', contact_phone: '', country_region: '', note: '' }
    cartonApiMock.listCustomers.mockImplementation(async (factory: string) => factory === 'huaxing' ? [c] : [])
    let finishSave!: (value: any) => void
    cartonApiMock.updateCustomer.mockImplementation(() => new Promise(resolve => { finishSave = resolve }))
    const wrapper = mountView('master-data'); await flushPromises()
    await wrapper.get('[aria-label="编辑客户 A厂客户"]').trigger('click')
    await wrapper.get('[aria-label="客户状态"]').setValue('INACTIVE')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(cartonApiMock.updateCustomer).toHaveBeenCalledWith(c, expect.objectContaining({ factory_id: 'huaxing', status: 'INACTIVE' }))
    routeState.query.factory = 'huakang-a'; await flushPromises()
    expect(wrapper.find('[aria-label="编辑客户资料"]').exists()).toBe(false)
    finishSave({ ...c, status: 'INACTIVE', revision: 2 }); await flushPromises()
    expect(wrapper.text()).not.toContain('A厂客户')
    expect(cartonApiMock.createCustomer).not.toHaveBeenCalled()
    wrapper.unmount(); masterGet.mockRestore()
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
    expect(wrapper.text()).toContain('收、发、存按本仓位累计；结余 = 期初 + 入库 − 出库 + 调仓净额 + 调整。冲销抵减原收发数量。')
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

  it('shows closing quantities by unit and blocks legacy snapshots without unit evidence', async () => {
    mockReceiptWorkspace([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    const base = { id: 'CLOSE-UNITS', factory_id: 'huaxing', period: '2026-08', customer_code: 'DICKIE',
      customer_name: 'Dickie', opening_quantity: '0', inbound_quantity: '110', outbound_quantity: '0',
      adjustment_quantity: '0', ending_quantity: '110', ending_amount: '220', currency: 'CNY', status: 'PENDING', revision: 2 }
    cartonApiMock.listClosings.mockResolvedValue([{ ...base, quantities_by_unit: [
      { unit: '个', opening_quantity: '0', inbound_quantity: '10', outbound_quantity: '0', adjustment_quantity: '0', ending_quantity: '10' },
      { unit: '张', opening_quantity: '0', inbound_quantity: '100', outbound_quantity: '0', adjustment_quantity: '0', ending_quantity: '100' },
    ], quantity_snapshot_missing: false }])
    const wrapper = mountView('closing')
    await flushPromises()
    expect(wrapper.text()).toContain('10 个')
    expect(wrapper.text()).toContain('100 张')
    expect(wrapper.text()).not.toContain('110 个')
    wrapper.unmount()
    cartonApiMock.listClosings.mockResolvedValue([{ ...base, quantities_by_unit: [], quantity_snapshot_missing: true }])
    const legacy = mountView('closing')
    await flushPromises()
    expect(legacy.text()).toContain('旧月结未保存分单位数量，请重新生成草稿')
    expect(findButton(legacy, '核对确认').attributes('disabled')).toBeDefined()
  })

  it('blocks an unpriced closing and requires explicit free-price evidence before saving', async () => {
    mockReceiptWorkspace([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([])
    const row = {
      id: 'CLOSING-PRICE', factory_id: 'huaxing', period: '2026-08', customer_code: 'DICKIE',
      customer_name: 'Dickie', opening_quantity: '0', inbound_quantity: '10', outbound_quantity: '0',
      adjustment_quantity: '0', ending_quantity: '10', ending_amount: '0', currency: 'CNY',
      status: 'PENDING', revision: 2,
      pricing_issues: [{ movement_id: 'MISSING-PRICE', document_no: 'DN-PRICE', item_no: 'ITEM-PRICE',
        packaging_type: '外箱', occurred_at: '2026-08-05T09:00:00+08:00', unit: '个', currency: 'CNY',
        message: '入库单价待核实（原单价为 0）', can_price: true }],
    }
    cartonApiMock.listClosings.mockResolvedValue([row])
    const wrapper = mountView('closing')
    await flushPromises()
    expect(wrapper.text()).toContain('DN-PRICE')
    expect(findButton(wrapper, '核对确认').attributes('disabled')).toBeDefined()
    await findButton(wrapper, '核实单价').trigger('click')
    const dialog = wrapper.get('[role="dialog"]')
    await dialog.trigger('submit')
    expect(dialog.text()).toContain('请输入有效的单价')
    await dialog.get('input[aria-label="核实入库单价"]').setValue('0')
    await dialog.trigger('submit')
    expect(dialog.text()).toContain('零单价需要明确勾选')
    expect(cartonApiMock.confirmInventoryPrice).not.toHaveBeenCalled()
    await dialog.get('input[aria-label="确认免费物料"]').setValue(true)
    await dialog.get('textarea[aria-label="核价依据"]').setValue('供应商确认免费样品')
    cartonApiMock.confirmInventoryPrice.mockResolvedValue(undefined)
    cartonApiMock.listClosings.mockResolvedValue([{ ...row, pricing_issues: [], status: 'DRAFT', revision: 3 }])
    await dialog.trigger('submit')
    await flushPromises()
    expect(cartonApiMock.confirmInventoryPrice).toHaveBeenCalledWith('MISSING-PRICE', {
      factory_id: 'huaxing', unit_price: '0', zero_price_confirmed: true, reason: '供应商确认免费样品',
    })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('提交核对')
    expect(cartonApiMock.updateClosingStatus).not.toHaveBeenCalled()
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
    cartonApiMock.listInventoryBalances.mockResolvedValue([balance, { ...balance, contract_no: 'SC-002', order_line_id: 'LINE-2', balance: '50' }, { ...balance, order_line_id: 'LINE-ZERO', balance: '0' }])
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
    const firstQuantity = dialog.get('[aria-label="本次出库数量 LINE-1"]')
    const secondQuantity = dialog.get('[aria-label="本次出库数量 LINE-2"]')
    expect(dialog.findAll('input[aria-label^="本次出库数量"]').length).toBe(2)
    for (const invalid of ['', '0', '-1', '101', '1.00001']) {
      await firstQuantity.setValue(invalid)
      await dialog.get('form').trigger('submit')
      expect(cartonApiMock.createInventoryMovementsBulk).not.toHaveBeenCalled()
    }
    await firstQuantity.setValue('20')
    await secondQuantity.setValue('7.5')
    expect(dialog.text()).toContain('80 个')
    expect(dialog.text()).toContain('42.5 个')
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(cartonApiMock.createInventoryMovementsBulk).toHaveBeenCalledWith({
      factory_id: 'huaxing', document_no: 'OUT-BULK-001', reason: '客户要货', issue_kind: 'USAGE', workshop_id: '',
      items: [
        { order_line_id: 'LINE-1', reference_movement_id: null, quantity: 20, location: 'A-01', location_id: undefined, workshop_id: '' },
        { order_line_id: 'LINE-2', reference_movement_id: null, quantity: 7.5, location: 'A-01', location_id: undefined, workshop_id: '' },
      ],
    })
    expect(cartonApiMock.createInventoryMovement).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('已按填写数量批量出库 2 条记录')
    expect(wrapper.find('button[aria-label="关闭库存作业"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="库存更多操作"]').exists()).toBe(false)
  })

  it('relocates a balance through a dedicated dialog without submitting a quantity movement', async () => {
    const balance = {
      factory_id: 'huaxing', customer_code: '360', customer_name: '360', contract_no: 'SC-001',
      item_no: 'ITEM-001', order_line_id: 'LINE-1', packaging_type: '外箱', paper_quality: 'A33',
      specification: '1*1*1', unit: '个', balance: '17', latest_location: 'A-01',
      latest_movement_id: 'IN-1', latest_document_no: 'DN-1', latest_movement_at: '2026-09-04T09:00:00+08:00',
      latest_inbound_at: '2026-09-04T09:00:00+08:00', location_revision: 4, position_revision: 4, location_id: 'LOC-A', position_key: 'LINE-1',
    }
    cartonApiMock.listCustomers.mockResolvedValue([])
    cartonApiMock.listOrders.mockResolvedValue([])
    cartonApiMock.listMovements.mockResolvedValue([])
    cartonApiMock.listClosings.mockResolvedValue([])
    cartonApiMock.listExceptions.mockResolvedValue([])
    cartonApiMock.listInventoryBalances.mockResolvedValue([balance])
    positionsMock.transfer.mockImplementation(async () => {
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
    await dialog.get('input[aria-label="仓库及仓位"]').setValue('A-01')
    await dialog.get('form').trigger('submit')
    expect(dialog.text()).toContain('目标仓位与当前仓位相同')
    expect(positionsMock.transfer).not.toHaveBeenCalled()
    await dialog.get('input[aria-label="仓库及仓位"]').setValue('B-02')
    await dialog.get('textarea[aria-label="调仓备注"]').setValue('整理库位')
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(positionsMock.transfer).toHaveBeenCalledWith({
      factory_id: 'huaxing', position_key: 'LINE-1', expected_position_revision: 4,
      location_id: 'LOC-B', quantity: 17, note: '整理库位',
    })
    expect(cartonApiMock.createInventoryMovement).not.toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-inventory-balance="LINE-1"]').text()).toContain('B-02')
    expect(wrapper.get('[data-inventory-balance="LINE-1"]').text()).toContain('17 个')
    expect(wrapper.text()).toContain('调仓完成')
  })

  it.each([false, true])('registers outbound inventory without misreporting a refresh failure (%s)', async (refreshFails) => {
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
      cost_status: '已计价', cost_currency: 'HKD', cost_amount: '346.00', cost_unit_price: '3.46',
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
    expect(wrapper.find('[aria-label="库存金额汇总"]').exists()).toBe(false)
    const moneyToggle = wrapper.findAll('label').find(label => label.text() === '显示金额')
    expect(moneyToggle).toBeTruthy()
    await moneyToggle!.get('input').setValue(true)
    expect(wrapper.get('[aria-label="库存金额汇总"]').text()).toContain('HKD 346.00')

    await wrapper.get('button[aria-label="出库 LINE-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLSelectElement>('select[aria-label="库存作业记录"]').element.value).toBe('LINE-1')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="库存作业数量"]').element.value).toBe('100')
    await wrapper.get('input[aria-label="库存作业数量"]').setValue('10')
    expect(wrapper.get('[aria-label="出库预估成本"]').text()).toContain('HKD 34.60')
    await wrapper.get('input[aria-label="库存作业单据号"]').setValue('OUT-001')
    const outboundReason = wrapper.get('select[aria-label="库存作业原因"]')
    expect(outboundReason.element.value).toBe('客户要货')
    expect(outboundReason.findAll('option').map((option) => option.text())).toEqual([
      '客户要货',
      '补货',
      '生产领用',
    ])
    await wrapper.get('select[aria-label="出库用途"]').setValue('LOAN')
    expect(outboundReason.element.value).toBe('借出')
    expect(wrapper.text()).not.toContain('库存调整')
    const inventoryForm = wrapper.findAll('form').find((form) => form.text().includes('登记出库'))
    if (!inventoryForm) throw new Error('Inventory form not found')
    if (refreshFails) cartonApiMock.listInventoryBalances.mockReset().mockRejectedValue(new Error('refresh failed'))
    await inventoryForm.trigger('submit')
    await flushPromises()

    expect(cartonApiMock.createInventoryMovement).toHaveBeenCalledWith(expect.objectContaining({
      order_line_id: 'LINE-1',
      reference_movement_id: null,
      movement_type: 'OUTBOUND',
      quantity: 10,
      document_no: 'OUT-001',
      reason: '借出', issue_kind: 'LOAN',
    }))
    expect(wrapper.text()).toContain('出库已登记')

    if (refreshFails) {
      expect(wrapper.text()).toContain('结存暂未刷新')
      expect(wrapper.text()).not.toContain('出库失败')
      expect(wrapper.find('input[aria-label="库存作业数量"]').exists()).toBe(false)
      expect(cartonApiMock.createInventoryMovement).toHaveBeenCalledTimes(1)
      return
    }

    expect(wrapper.find('button[aria-label="关闭库存作业"]').exists()).toBe(false)
    routeState.query.tab = 'inventory-movements'
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
    const template = wrapper.get('a[download="纸箱每周排期核对导入模板.xlsx"]')
    expect(template.attributes('href')).toBe('/templates/carton-weekly-schedule-template.xlsx')
    expect(template.text()).toContain('旧版排期模板（兼容）')
    expect(wrapper.text()).toContain('按合同号、货号及填写的客户 PO 核对')
    expect(wrapper.text()).toContain('不按装箱数换算')
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

    await panel.get('button[aria-label="查看订单 EX-DECREASE"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('当前没有可直接减少的未入库量')
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
    await findButton(wrapper, '收料历史').trigger('click')
    expect(wrapper.text()).toContain('收料历史台账')
    expect(wrapper.text()).toContain('DN-260811-001')
    expect(wrapper.get('table[aria-label="收料历史台账明细"]').text()).not.toContain('RC-260811-001')
    expect(wrapper.get('table[aria-label="收料历史台账明细"]').text()).toContain('历史未记录')
    expect(wrapper.text()).toContain('SC-HISTORY-001')
    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('ITEM-HISTORY-001')
    expect(wrapper.text()).toContain('ITEM-HISTORY-001')
  })
  it('filters receipt history and requires a reason before whole-document correction, then permits reentry', async () => {
    mockReceiptWorkspace([])
    const doc = {
      id: 'CTR-FIX', factory_id: 'huaxing', receipt_no: 'RC-FIX', delivery_note_no: 'DN-FIX',
      delivery_date: '2026-08-11', acceptance_date: '2026-08-12', status: 'POSTED', revision: 2, note: '',
      created_by_name: '仓管', created_at: '2026-08-11T09:00:00', confirmed_at: '2026-08-11T10:00:00',
      lines: [{ id: 'CRL-FIX', source_type: 'AD_HOC', order_line_id: null, customer_code: 'DICKIE', customer_name: 'Dickie',
        contract_no: 'C-FIX', item_no: 'ITEM-FIX', packaging_type: '外箱', paper_quality: 'A33', specification: '1*1*1',
        delivered_quantity: '10', received_quantity: '10', damaged_quantity: '0', rejected_quantity: '0', unusable_quantity: '0',
        effective_quantity: '10', unit: '个', unit_price: '2.5', currency: 'CNY', location: 'A-01' }],
    }
    cartonApiMock.listReceipts.mockResolvedValue([doc])
    cartonApiMock.listCustomers.mockResolvedValue([{ customer_code: 'DICKIE', customer_name: 'Dickie', status: 'ACTIVE' }])
    const wrapper = mountView('receipts')
    await flushPromises()
    await findButton(wrapper, '收料历史').trigger('click')
    const search = wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]')
    await search.setValue('not-matching')
    expect(wrapper.text()).toContain('没有符合条件的收料历史')
    await search.setValue('C-FIX')
    expect(wrapper.text()).toContain('DN-FIX')
    await wrapper.get('select[aria-label="收料历史状态"]').setValue('PENDING_CONFIRMATION')
    expect(wrapper.text()).toContain('没有符合条件的收料历史')
    await findButton(wrapper, '清空历史筛选').trigger('click')
    await wrapper.get('button[aria-label="收料历史送货日期范围"]').trigger('click')
    await clickCalendarDate(wrapper, '2026-08-12')
    await clickCalendarDate(wrapper, '2026-08-12')
    expect(wrapper.text()).toContain('没有符合条件的收料历史')
    await findButton(wrapper, '清空历史筛选').trigger('click')
    const detail = wrapper.get('button[aria-label="查看收料单 RC-FIX"]')
    expect(detail.text()).toBe('明细')
    expect(wrapper.find('button[aria-label="更正收料单 RC-FIX"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="收料单 RC-FIX 更多操作"]').exists()).toBe(false)
    await detail.trigger('mouseenter')
    expect(wrapper.get('[data-testid="receipt-detail-overlay"]').classes()).toContain('pointer-events-none')
    expect(wrapper.get('[aria-label="收料整单明细"]').text()).toContain('2.5')
    expect(wrapper.get('[data-testid="receipt-detail-overlay"]').text()).toContain('实际验收日期 2026-08-12')
    expect(wrapper.find('input[aria-label="人工送货单号"]').exists()).toBe(false)
    await detail.trigger('mouseleave')
    expect(wrapper.find('[data-testid="receipt-detail-overlay"]').exists()).toBe(false)
    await detail.trigger('focus')
    expect(wrapper.find('[data-testid="receipt-detail-overlay"]').exists()).toBe(true)
    await detail.trigger('blur')
    expect(wrapper.find('[data-testid="receipt-detail-overlay"]').exists()).toBe(false)
    await detail.trigger('click')
    await detail.trigger('mouseleave')
    expect(wrapper.get('[data-testid="receipt-detail-overlay"] [role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(wrapper.get('[data-testid="receipt-detail-overlay"]').findAll('input')).toHaveLength(0)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[data-testid="receipt-detail-overlay"]').exists()).toBe(false)
    expect(cartonApiMock.createReceipt).not.toHaveBeenCalled()
    expect(cartonApiMock.confirmReceipt).not.toHaveBeenCalled()
    expect(wrapper.get('button[aria-label="更正收料单 RC-FIX"]').text()).toBe('冲销')
    await wrapper.get('button[aria-label="更正收料单 RC-FIX"]').trigger('click')
    expect(wrapper.get<HTMLTextAreaElement>('textarea[aria-label="收料纠错原因"]').element.value).toBe('原单录入有误，冲销重录')
    await wrapper.get('textarea[aria-label="收料纠错原因"]').setValue('')
    await findButton(wrapper, '确认整单冲销').trigger('submit')
    expect(cartonApiMock.reverseReceipt).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请填写至少 4 个字的原因')
    await wrapper.get('textarea[aria-label="收料纠错原因"]').setValue('收料数量填写错误')
    cartonApiMock.reverseReceipt.mockRejectedValueOnce(new Error('库存不足'))
    await wrapper.get('form[aria-label="收料纠错确认"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('form[aria-label="收料纠错确认"]').text()).toContain('库存不足')
    const reversed = { ...doc, status: 'REVERSED', revision: 3 }
    cartonApiMock.reverseReceipt.mockResolvedValueOnce(reversed)
    cartonApiMock.listReceipts.mockResolvedValue([reversed])
    await wrapper.get('form[aria-label="收料纠错确认"]').trigger('submit')
    await flushPromises()
    expect(cartonApiMock.reverseReceipt).toHaveBeenLastCalledWith('huaxing', 'CTR-FIX', 2, '收料数量填写错误')
    expect(wrapper.find('form[aria-label="收料纠错确认"]').exists()).toBe(false)
    await findButton(wrapper, '重新登记').trigger('click')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="人工送货单号"]').element.value).toBe('DN-FIX-更正-RC-FIX')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="HISTORY-CRL-FIX 实收"]').element.value).toBe('10')
    expect(wrapper.get('input[aria-label="HISTORY-CRL-FIX 单价"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('更正原收料单 RC-FIX')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="实际验收日期"]').element.value).toBe('2026-08-12')
  })

  it('separates review from final locking and requires a supervisor confirmation and unlock reason', async () => {
    mockReceiptWorkspace([])
    const row = { id: 'CLOSE-STEPS', factory_id: 'huaxing', customer_code: 'DICKIE', customer_name: 'Dickie',
      period: businessDateOffset(0).slice(0, 7), status: 'CONFIRMED', revision: 3, currency: 'CNY',
      opening_quantity: '0', inbound_quantity: '10', outbound_quantity: '0', adjustment_quantity: '0',
      ending_quantity: '10', ending_amount: '20', snapshot_stale: false, pricing_issues: [] }
    cartonApiMock.listClosings.mockResolvedValue([row])
    const current = mountView('closing')
    await flushPromises()
    expect(findButton(current, '最终锁账').attributes('disabled')).toBeDefined()
    expect(current.text()).toContain('月份尚未结束，可继续正常收发货')
    current.unmount()
    const past = { ...row, period: businessDateOffset(-40).slice(0, 7) }
    cartonApiMock.listClosings.mockResolvedValue([past])
    const wrapper = mountView('closing')
    await flushPromises()
    await findButton(wrapper, '最终锁账').trigger('click')
    expect(cartonApiMock.updateClosingStatus).not.toHaveBeenCalled()
    expect(wrapper.get('form[aria-label="月结最终操作确认"]').text()).toContain('最终锁账后')
    cartonApiMock.updateClosingStatus.mockResolvedValue({ ...past, status: 'LOCKED', revision: 4 })
    await wrapper.get('form[aria-label="月结最终操作确认"]').trigger('submit')
    await flushPromises()
    expect(cartonApiMock.updateClosingStatus).toHaveBeenCalledWith('huaxing', past, 'LOCKED')
    await findButton(wrapper, '解锁重核').trigger('click')
    await wrapper.get('form[aria-label="月结最终操作确认"]').trigger('submit')
    expect(cartonApiMock.unlockClosing).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请填写至少 4 个字的解锁原因')
    await wrapper.get('textarea[aria-label="月结解锁原因"]').setValue('月份未结束，误锁账')
    cartonApiMock.unlockClosing.mockResolvedValue({ ...past, status: 'DRAFT', revision: 5 })
    await wrapper.get('form[aria-label="月结最终操作确认"]').trigger('submit')
    await flushPromises()
    expect(cartonApiMock.unlockClosing).toHaveBeenCalledWith('huaxing', expect.objectContaining({ revision: 4 }), '月份未结束，误锁账')
    expect(wrapper.text()).toContain('已解锁并退回草稿')
    expect(findButton(wrapper, '提交核对').attributes('disabled')).toBeUndefined()
  })

  it('lets warehouse users review but reserves final lock and unlock for supervisors', async () => {
    mockReceiptWorkspace([])
    authStoreMock.can.mockImplementation((permission?: string) => permission !== 'carton_procurement:order_adjust')
    cartonApiMock.listClosings.mockResolvedValue([
      { id: 'PENDING', period: '2026-08', status: 'PENDING', revision: 2, customer_name: 'Dickie', currency: 'CNY', pricing_issues: [] },
      { id: 'CONFIRMED', period: '2026-08', status: 'CONFIRMED', revision: 3, customer_name: 'Dickie', currency: 'HKD', pricing_issues: [] },
      { id: 'LOCKED', period: '2026-07', status: 'LOCKED', revision: 4, customer_name: 'Dickie', currency: 'CNY', pricing_issues: [] },
    ])
    const wrapper = mountView('closing')
    await flushPromises()
    expect(findButton(wrapper, '核对确认').attributes('disabled')).toBeUndefined()
    expect(findButton(wrapper, '最终锁账').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain('解锁重核')
    expect(wrapper.text()).toContain('最终锁账须由有权限的主管执行')
  })

  it('keeps hidden order selections explicit and supports product search and clearing', async () => {
    mockReceiptWorkspace([{ ...orderFixture('FILTER-A', businessDateOffset(3)), product_name: '消防车' }, orderFixture('FILTER-B', businessDateOffset(4))])
    const wrapper = mountView('orders'); await flushPromises()
    await wrapper.get('[aria-label="选择订单 FILTER-B"]').setValue(true)
    await wrapper.get('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').setValue('消防车')
    expect(wrapper.find('[data-order-no="FILTER-A"]').exists()).toBe(true)
    expect(wrapper.find('[data-order-no="FILTER-B"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="批量已选范围"]').text()).toContain('其中 1 张不在当前筛选内')
    await wrapper.get('[aria-label="清空订单筛选"]').trigger('click')
    expect(wrapper.find('[data-order-no="FILTER-B"]').exists()).toBe(true)
    await findButton(wrapper, '清空选择').trigger('click')
    expect(wrapper.get('[aria-label="批量已选范围"]').text()).toContain('已选 0')
    wrapper.unmount()
  })

  it('includes the full ending day in movement filters and clears them together', async () => {
    mockReceiptWorkspace([])
    const date = businessDateOffset(0)
    cartonApiMock.listMovements.mockResolvedValue([0, 1].map(index => ({ id: `DATE-${index}`, factory_id: 'huaxing', movement_type: 'INBOUND', quantity: '1', balance_after: '1', unit: '个', customer_name: 'Dickie', contract_no: 'DATE', item_no: 'ITEM', packaging_type: '外箱', paper_quality: 'A33', specification: '1', location: 'A', source_type: 'MANUAL', document_no: `END-DAY-${index}`, occurred_at: `${index ? dateOffsetFrom(date, 1) : date}T23:59:00+08:00`, actor_name: '仓管' })))
    const wrapper = mountView('inventory-movements'); await flushPromises()
    await wrapper.get('[aria-label="库存流水记账时间范围"]').trigger('click')
    await clickCalendarDate(wrapper, date); await clickCalendarDate(wrapper, date)
    expect(wrapper.text()).toContain('END-DAY-0')
    expect(wrapper.text()).not.toContain('END-DAY-1')
    await wrapper.get('[aria-label="清空流水筛选"]').trigger('click')
    expect(wrapper.text()).toContain('END-DAY-1')
    wrapper.unmount()
  })

  it('queries closing months without generating and rejects stale factory generation results', async () => {
    mockReceiptWorkspace([])
    const make = (id: string, period: string) => ({ id, factory_id: 'huaxing', customer_code: 'DICKIE', customer_name: 'Dickie', period, currency: 'CNY', status: 'DRAFT', revision: 1, opening_quantity: '0', inbound_quantity: '1', outbound_quantity: '0', adjustment_quantity: '0', ending_quantity: '1', ending_amount: '1', pricing_issues: [] })
    const rows = [make('MONTH-7', '2026-07'), make('MONTH-8', '2026-08')]
    cartonApiMock.listClosings.mockResolvedValue(rows)
    const wrapper = mountView('closing'); await flushPromises()
    await wrapper.get('[aria-label="月结查询月份"]').setValue('2026-07')
    expect(wrapper.find('table')!.text()).toContain('2026-07')
    expect(wrapper.find('table')!.text()).not.toContain('2026-08')
    expect(cartonApiMock.generateClosings).not.toHaveBeenCalled()
    let finish!: (value: unknown) => void
    cartonApiMock.generateClosings.mockReturnValue(new Promise(resolve => { finish = resolve }))
    await findButton(wrapper, '生成月结草稿').trigger('click')
    cartonApiMock.listClosings.mockResolvedValue([])
    routeState.query.factory = 'huakang'; await flushPromises()
    finish([make('OLD-FACTORY', '2026-06')]); await flushPromises()
    expect(wrapper.find('table')!.text()).not.toContain('2026-06')
    wrapper.unmount()
  })

  it('hides inactive shared searches and disables closing generation for read-only users', async () => {
    mockReceiptWorkspace([])
    let wrapper = mountView('audit'); await flushPromises()
    expect(wrapper.find('input[placeholder="搜索合同 / PO / 货号 / 单据..."]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="客户筛选"]').exists()).toBe(false)
    wrapper.unmount()
    authStoreMock.can.mockReturnValue(false)
    wrapper = mountView('closing'); await flushPromises()
    expect(findButton(wrapper, '生成月结草稿').attributes('disabled')).toBeDefined()
    await findButton(wrapper, '生成月结草稿').trigger('click')
    expect(cartonApiMock.generateClosings).not.toHaveBeenCalled()
    wrapper.unmount()
  })

})


it('creates a customer through explicit review while retaining the order form', async () => {
  const masterGet = vi.spyOn(cartonMasterApi, 'get').mockResolvedValue({ ...emptyMaster(), can_manage: true })
  cartonApiMock.createCustomer.mockImplementation(async (payload: any) => ({ ...payload, id: 'NEW-CUSTOMER', customer_code: 'NEW-CODE', status: 'ACTIVE' }))
  const wrapper = mountView('orders'); await flushPromises()
  await findButton(wrapper, '新建纸箱订单').trigger('click')
  await wrapper.get('input[aria-label="合同号"]').setValue('KEEP-ORDER')
  await wrapper.get('input[aria-label="订单客户"]').setValue('新客户甲')
  expect(cartonApiMock.createCustomer).not.toHaveBeenCalled()
  await findButton(wrapper, '新增客户：新客户甲').trigger('click')
  expect((wrapper.get('input[aria-label="客户名称"]').element as HTMLInputElement).value).toBe('新客户甲')
  await wrapper.get('form[aria-label="编辑客户资料"]').trigger('submit'); await flushPromises()
  expect(cartonApiMock.createCustomer).toHaveBeenCalledTimes(1)
  expect((wrapper.get('input[aria-label="订单客户"]').element as HTMLInputElement).value).toBe('新客户甲')
  expect((wrapper.get('input[aria-label="合同号"]').element as HTMLInputElement).value).toBe('KEEP-ORDER')
  wrapper.unmount(); masterGet.mockRestore()
})

 it.each([['weekly-check', '订单管理', '订单管理子页面'], ['inventory-summary', '库存管理', '库存管理子页面'], ['inventory-movements', '库存管理', '库存管理子页面']])('keeps deep link %s under the right parent navigation', async (tab, label, childLabel) => {
    const wrapper = mountView(tab)
    await flushPromises()
    expect(wrapper.get('nav[aria-label="纸箱采购协同功能"] [aria-current="page"]').text()).toBe(label)
    expect(wrapper.get(`nav[aria-label="${childLabel}"] [aria-current="page"]`).exists()).toBe(true)
    if (tab === 'inventory-movements') {
      expect(wrapper.text()).toContain('逐笔交易流水')
      expect(wrapper.find('.inventory-balance-table').exists()).toBe(false)
    }
    wrapper.unmount()
  })

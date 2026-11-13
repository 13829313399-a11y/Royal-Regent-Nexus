import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { CalendarDate } from '@internationalized/date'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import { purchaseSearchKey } from '../purchaseSearch'
import Records from '../FabricReceivingRecords.vue'
import type { FabricReceipt, HandoverReceiptDetail } from '@/api/fabricReceiving'

const api = vi.hoisted(() => ({ receipts: vi.fn(), stock: vi.fn(), handoverDetail: vi.fn(), reversalPreview: vi.fn(), reverse: vi.fn() }))
const purchaseApi = vi.hoisted(() => ({ purchaseReview: vi.fn(), linkPurchase: vi.fn() }))
vi.mock('@/api/fabricReceiving', () => ({ fabricReceivingApi: api, materialCategoryLabels: { FABRIC: '布料', ACCESSORY: '辅料', THREAD: '线' } }))
vi.mock('@/api/materialHandover', () => ({ HANDOVER_FACTORY: 'huakang-c', handoverApi: () => purchaseApi }))
const record: FabricReceipt = {
  id: '68a72a1f9a3a4f7bb3fead135e30500b', source_line_id: 'SOURCE-0001', source_revision: 3,
  facts: { order_no: 'PO-001', supplier: '测试纺织厂', material_code: '00123', material_name: '白色平纹布', source_category: 'SUPPLEMENT', production_no: 'FC-001', contract_no: 'CT-001' } as FabricReceipt['facts'],
  quantity: '0.3', unit: '码', prior_received_quantity: null, receipt_date: '2026-10-07', accounting_month: '2026-10', delivery_reference: 'DN-001',
  material_category: 'FABRIC', difference_reason: '现场核实多到数量', note: '保留原始交货备注', actor_name: '仓管甲', occurred_at: '2026-10-07T09:10:00+08:00', stock_posted: true,
  batches: [{ id: 'B1', quantity: '0.1', location: 'A01', dye_lot: '0001', roll_no: '00002', quality_status: 'PENDING_INSPECTION' }, { id: 'B2', quantity: '0.2', location: 'A02', dye_lot: '0001', roll_no: '00003', quality_status: 'PENDING_INSPECTION' }],
}
let wrapper: VueWrapper | undefined
const headerSearch = { search: ref(''), submitted: ref(0) }
async function open(withHeader = false, url = '/') {
  const pinia = createPinia(); setActivePinia(pinia)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push(url); await router.isReady()
  wrapper = mount(Records, { props: { mode: 'receipts' }, global: { plugins: [router, pinia], provide: withHeader ? { [purchaseSearchKey as symbol]: headerSearch } : {} }, attachTo: document.body })
  await flushPromises()
  return new DOMWrapper(document.body)
}
beforeEach(() => { vi.resetAllMocks(); headerSearch.search.value = ''; headerSearch.submitted.value = 0; api.receipts.mockResolvedValue({ total: 1, items: [record], options: { suppliers: ['测试纺织厂', '另一家供应商'] } }); api.stock.mockResolvedValue({ total: 0, items: [] }) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.useRealTimers(); vi.restoreAllMocks() })

describe('fabric receipt history', () => {
  it('filters purchase review records and links the original batch from receipt history', async () => {
    const pending: FabricReceipt = { ...record, id: 'OP-1', operation_id: 'OP-1', receipt_origin: 'HANDOVER',
      purchase_status: 'PENDING', procurement_pending_reason: '合同待核对' }
    api.receipts.mockResolvedValue({ total: 1, items: [pending], can_link_purchase: true, operations_included: true })
    purchaseApi.purchaseReview.mockResolvedValue({ expected_revision: 3, operation_ids: ['OP-1', 'OP-2'],
      quantity: '0.3', unit: '码', reference: 'DN-001', reason: '合同待核对', locations: ['A01', 'A02'],
      sources: [{ id: 'SOURCE-1', order_no: 'PO-009', contract_no: 'CT-009', production_no: 'PR-009',
        remaining: '9.5', unit: '码', can_receive: true, revision: 5, receipt_count: 2 }],
    })
    purchaseApi.linkPurchase.mockResolvedValue({ purchase_order_no: 'PO-009' })
    const body = await open()
    await wrapper!.get('[aria-label="采购归属筛选"]').setValue('PENDING'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('', 0, expect.objectContaining({ purchase_status: 'PENDING' }))
    const action = wrapper!.findAll('.receipt-records-desktop button').find(button => button.text() === '补关联采购')!
    await action.trigger('click'); await flushPromises()
    expect(purchaseApi.purchaseReview).toHaveBeenCalledWith('OP-1')
    expect(body.text()).toContain('本批净实收 0.3 码')
    await body.get('[aria-label="选择补关联采购明细"]').setValue('SOURCE-1')
    expect(body.text()).toContain('采购待收 9.5 码 → 9.2 码')
    api.receipts.mockResolvedValue({ total: 0, items: [], can_link_purchase: true, operations_included: true })
    await body.get('form.purchase-review').trigger('submit'); await flushPromises()
    expect(purchaseApi.linkPurchase).toHaveBeenCalledWith('OP-1', expect.objectContaining({
      expected_revision: 3, operation_ids: ['OP-1', 'OP-2'], purchase_source_id: 'SOURCE-1',
      expected_source_revision: 5, expected_receipt_count: 2,
    }))
    expect(wrapper!.text()).toContain('已补关联采购单 PO-009')
  })
  it('shows reversal for every stock-posted receipt in unified history', async () => {
    const delivery: FabricReceipt = { ...record, id: 'OP-1', history_key: 'OPERATION:OP-1', operation_id: 'OP-1', receipt_origin: 'HANDOVER', handover_document_id: 'NOTE-1', source_version: '2' }
    const manual: FabricReceipt = { ...record, id: 'OP-2', operation_id: 'OP-2', receipt_origin: 'MANUAL' }
    const zero: FabricReceipt = { ...record, id: 'ZERO', quantity: '0', stock_posted: false, batches: [] }
    api.receipts.mockResolvedValue({ total: 4, items: [record, delivery, manual, zero], can_reverse: true, operations_included: true })
    api.handoverDetail.mockResolvedValue({ has_posting: true, original_quantity: delivery.quantity, effective_quantity: delivery.quantity,
      batches: delivery.batches, observation: null } satisfies HandoverReceiptDetail)
    const body = await open()
    const rows = wrapper!.findAll('.receipt-records-table tbody tr')
    expect(rows).toHaveLength(4)
    expect(rows[1]!.text()).toContain('送货单 / 扫码入库')
    for (const layout of ['.receipt-records-desktop', '.receipt-records-mobile']) {
      const actions = wrapper!.get(layout).findAll('.receipt-records-reverse-button')
      expect(actions.map(button => button.attributes('aria-label'))).toEqual([record, delivery, manual].map(item => `冲销入库单 ${item.id}`))
    }
    await rows[1]!.get('.receipt-records-detail-button').trigger('click'); await flushPromises()
    expect(body.get('[role="dialog"]').findAll('a').some(link => link.attributes('href')?.includes('document=NOTE-1'))).toBe(true)
    await body.get('[aria-label="关闭入库详情"]').trigger('click'); await flushPromises()
    await wrapper!.get('[aria-label="入库登记来源筛选"]').setValue('MANUAL_ENTRY'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('', 0, expect.objectContaining({ channel: 'MANUAL_ENTRY' }))
    await wrapper!.get('[aria-label="入库登记来源筛选"]').setValue('HANDOVER'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('', 0, expect.objectContaining({ channel: 'HANDOVER' }))
    expect(api.reverse).not.toHaveBeenCalled()
  })
  it('shows all bins and original observations for a delivery while correction still targets the selected batch', async () => {
    const reversal = { id: 'REV-B2', date: '2026-10-10', reason: '第二仓位录错', actor_name: '仓管乙' }
    const batches = [{ ...record.batches[0]!, reversal: null }, { ...record.batches[1]!, reversal }]
    const delivery: FabricReceipt = { ...record, id: 'B1', operation_id: 'B1', receipt_origin: 'HANDOVER',
      handover_document_id: 'NOTE-1', quantity: '0.1', batches: [batches[0]!] }
    api.receipts.mockResolvedValue({ total: 1, items: [delivery], can_reverse: true })
    api.handoverDetail.mockRejectedValueOnce(new Error('temporary read failure')).mockResolvedValue({
      has_posting: true, original_quantity: '0.3', effective_quantity: '0.1', batches,
      observation: { complete: true, delivered_quantity: '0.7', counted_quantity: '0.6', shortage_quantity: '0.1',
        damaged_quantity: '0', rejected_quantity: '0.3', other_unusable_quantity: '0', parts: [
          { location: 'A01', dye_lot: '0001', roll_no: '00002', counted_quantity: '0.1', accepted_quantity: '0.1',
            damaged_quantity: '0', rejected_quantity: '0', other_unusable_quantity: '0' },
          { location: 'A02', dye_lot: '0001', roll_no: '00003', counted_quantity: '0.5', accepted_quantity: '0.2',
            damaged_quantity: '0', rejected_quantity: '0.3', other_unusable_quantity: '0' },
        ] },
    } satisfies HandoverReceiptDetail)
    api.reversalPreview.mockResolvedValue({ can_reverse: true, expected_revision: 7 })
    const body = await open()
    await wrapper!.get('.receipt-records-detail-button').trigger('click'); await flushPromises()
    const detail = body.get('[role="dialog"]')
    expect(detail.get('[role="alert"]').text()).toContain('以下显示所选批次')
    expect(detail.findAll('.receipt-detail-batch-table tbody tr')).toHaveLength(1)
    await detail.get('[role="alert"] button').trigger('click'); await flushPromises()
    expect(api.handoverDetail).toHaveBeenLastCalledWith('B1', expect.any(AbortSignal))
    expect(detail.text()).toContain('部分批次已冲销')
    expect(detail.text()).toContain('原入库 0.3 码')
    expect(detail.get('.receipt-detail-main-metric dd').text()).toBe('0.1 码')
    expect(detail.findAll('.receipt-detail-batch-table tbody tr')).toHaveLength(2)
    expect(detail.get('a[aria-label="查看批次 B2 的入库记录"]').attributes('href')).toContain('receipt=B2')
    expect(detail.get('[aria-label="逐卷差异"]').text()).toContain('0.3')
    expect(detail.text()).not.toContain('退供应商')
    expect(detail.text()).toContain('第二仓位录错')
    await detail.get('[aria-label="关闭入库详情"]').trigger('click'); await flushPromises()
    await wrapper!.get('.receipt-records-reverse-button').trigger('click'); await flushPromises()
    expect(api.reversalPreview).toHaveBeenCalledWith('B1')
  })
  it('opens history filtered to the exact original receipt from its link', async () => {
    const exact = { ...record, id: 'FM-1', operation_id: 'OP-1', receipt_origin: 'MANUAL' }
    api.receipts.mockResolvedValue({ total: 1, items: [exact], can_reverse: true })
    api.reversalPreview.mockResolvedValue({ can_reverse: true, expected_revision: 7 })
    await open(true, '/?view=history&receipt=FM-1')
    expect(api.receipts).toHaveBeenCalledWith('FM-1', 0, expect.any(Object))
    await wrapper!.find('.receipt-records-reverse-button').trigger('click'); await flushPromises()
    expect(api.reversalPreview).toHaveBeenCalledWith('FM-1')
  })
  it('clears privileged details and ignores old responses when authorization changes', async () => {
    const body = await open()
    await wrapper!.find('.receipt-records-detail-button').trigger('click'); await flushPromises()
    let resolve!: (value: unknown) => void
    api.receipts.mockReturnValueOnce(new Promise(done => { resolve = done }))
    await wrapper!.get('[aria-label="刷新入库记录"]').trigger('click'); await flushPromises()
    api.receipts.mockResolvedValue({ total: 0, items: [], operations_included: false, can_reverse: false })
    useAuthStore().authorizationVersion++
    await flushPromises()
    resolve({ total: 1, items: [record], operations_included: true, can_reverse: true }); await flushPromises()
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper!.text()).not.toContain('白色平纹布')
    expect(wrapper!.text()).toContain('当前权限仅展示按采购单登记的入库')
    expect(wrapper!.get('option[value="HANDOVER"]').attributes('disabled')).toBeDefined()
  })
  it('requires whole receipt confirmation and freezes an uncertain correction for exact retry', async () => {
    api.receipts.mockResolvedValue({ total: 1, items: [record], can_reverse: true })
    api.reversalPreview.mockResolvedValue({ can_reverse: true, expected_revision: 7 })
    api.reverse.mockRejectedValueOnce(new Error('connection lost')).mockResolvedValueOnce({ id: 'REV' })
    const body = await open()
    await wrapper!.find('.receipt-records-reverse-button').trigger('click'); await flushPromises()
    expect(api.reverse).not.toHaveBeenCalled()
    await body.get('[aria-label="入库冲销原因"]').setValue('数量录错')
    await body.get('form.warehouse-guide-body').trigger('submit'); await flushPromises()
    expect(api.reverse).not.toHaveBeenCalled()
    await body.get('[aria-label="确认整单冲销入库"]').setValue(true)
    await body.get('form.warehouse-guide-body').trigger('submit'); await flushPromises()
    const first = JSON.parse(JSON.stringify(api.reverse.mock.calls[0]))
    expect(first).toMatchObject([record.id, { expected_revision: 7, confirmed: true, reason: '数量录错' }])
    expect(body.get('[role="dialog"] fieldset').attributes('disabled')).toBeDefined()
    expect(body.text()).toContain('用原内容重试冲销')
    await body.get('form.warehouse-guide-body').trigger('submit'); await flushPromises()
    expect(api.reverse.mock.calls[1]).toEqual(first)
    expect(wrapper!.text()).toContain('已冲销本笔入库')
    expect(body.find('[role="dialog"]').exists()).toBe(false)
  })
  it('shows immutable reversed receipt evidence and omits another reverse action', async () => {
    api.receipts.mockResolvedValue({ total: 1, items: [{ ...record, reversed: true, reversal: { id: 'REV', date: '2026-10-10', reason: '数量录错', actor_name: '主管' } }], can_reverse: true })
    const body = await open()
    expect(wrapper!.find('.receipt-records-reverse-button').exists()).toBe(false)
    expect(wrapper!.text()).toContain('已冲销 · 原单保留')
    await wrapper!.find('.receipt-records-detail-button').trigger('click'); await flushPromises()
    expect(body.get('[role="dialog"]').text()).toContain('整单冲销记录')
    expect(body.get('[role="dialog"]').text()).toContain('数量录错')
  })
  it('disables a blocked reversal before any write', async () => {
    api.receipts.mockResolvedValue({ total: 1, items: [record], can_reverse: true })
    api.reversalPreview.mockResolvedValue({ can_reverse: false, blocked_reason: '原批次已有领料' })
    const body = await open()
    await wrapper!.find('.receipt-records-reverse-button').trigger('click'); await flushPromises()
    expect(body.get('[role="dialog"]').text()).toContain('原批次已有领料')
    expect(body.get('[role="dialog"] fieldset').attributes('disabled')).toBeDefined()
    await body.get('form.warehouse-guide-body').trigger('submit'); await flushPromises()
    expect(api.reverse).not.toHaveBeenCalled()
  })
  it('opens a full read-only receipt and preserves it on a same-account session refresh', async () => {
    const body = await open()
    const auth = useAuthStore()
    auth.applySession({
      id: 'warehouse-test', username: 'warehouse-test', display_name: '测试仓管', roles: [], permissions: [],
      factory_scopes: [], department_scopes: [], grants: [], force_password_change: false,
    })
    await flushPromises()
    expect(wrapper!.get('.receipt-records-table tbody').text()).toContain('68a72a1f…500b')
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    const opener = wrapper!.get<HTMLButtonElement>('.receipt-records-detail-button')
    opener.element.focus()
    await opener.trigger('click'); await flushPromises()
    const detail = body.get('[role="dialog"]')
    for (const value of [record.id, record.source_line_id, '00002', '00003', 'A01', 'A02', '0.1', '0.2', '现场核实多到数量', '入库时质量', '2026-10-07 09:10']) expect(detail.text()).toContain(value)
    expect(detail.findAll('tbody tr')).toHaveLength(2)
    expect(detail.find('input').exists()).toBe(false)
    const requestsBeforeRefresh = api.receipts.mock.calls.length
    auth.applySession({ ...auth.currentUser! })
    await flushPromises()
    expect(body.find('[role="dialog"]').exists()).toBe(true)
    expect(api.receipts).toHaveBeenCalledTimes(requestsBeforeRefresh)
    await body.get('[aria-label="关闭入库详情"]').trigger('click'); await flushPromises()
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(opener.element)
  })
  it('keeps server pagination and resets it when a new search is submitted or cleared', async () => {
    api.receipts.mockResolvedValueOnce({ total: 51, items: Array.from({ length: 50 }, (_, index) => ({ ...record, id: `R${index}` })) })
    await open()
    await wrapper!.findAll('button').find(button => button.text() === '下一页')!.trigger('click'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('', 50, expect.objectContaining({ sort: 'RECEIPT_DESC' }))
    await wrapper!.get('[aria-label="查找实际入库记录"]').setValue('  PO-001  ')
    expect(api.receipts).toHaveBeenCalledTimes(2)
    await wrapper!.get('form').trigger('submit'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('PO-001', 0, expect.any(Object))
    expect(wrapper!.get('.receipt-records-filter').text()).toContain('PO-001')
    await wrapper!.get('[aria-label="清空入库搜索"]').trigger('click'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('', 0, expect.any(Object))
  })
  it('uses only the shared header search, debounces typing and submits immediately on Enter', async () => {
    vi.useFakeTimers()
    await open(true)
    expect(wrapper!.find('input[type="search"]').exists()).toBe(false)
    headerSearch.search.value = '  PO-001  '
    await vi.advanceTimersByTimeAsync(349)
    expect(api.receipts).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('PO-001', 0, expect.any(Object))
    headerSearch.search.value = 'DN-001'
    headerSearch.submitted.value++
    await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('DN-001', 0, expect.any(Object))
    await vi.advanceTimersByTimeAsync(350)
    expect(api.receipts).toHaveBeenCalledTimes(3)
    await wrapper!.findAll('button').find(button => button.text() === '重置筛选')!.trigger('click'); await flushPromises()
    expect(headerSearch.search.value).toBe('')
    expect(api.receipts).toHaveBeenLastCalledWith('', 0, expect.objectContaining({ sort: 'RECEIPT_DESC' }))
    await vi.advanceTimersByTimeAsync(350)
    expect(api.receipts).toHaveBeenCalledTimes(4)
  })
  it('combines server filters and sorting, resets pagination and can recover an empty filtered result', async () => {
    api.receipts.mockResolvedValueOnce({ total: 51, items: [record], options: { suppliers: ['测试纺织厂', '另一家供应商'] } })
    await open(true)
    await wrapper!.findAll('button').find(button => button.text() === '下一页')!.trigger('click'); await flushPromises()
    await wrapper!.get('[aria-label="入库供应商筛选"]').setValue('测试纺织厂'); await flushPromises()
    await wrapper!.get('[aria-label="入库物料分类筛选"]').setValue('FABRIC'); await flushPromises()
    wrapper!.getComponent(DateRangeFilter).vm.$emit('update:modelValue', { start: new CalendarDate(2026, 10, 1), end: new CalendarDate(2026, 10, 7) }); await flushPromises()
    await wrapper!.get('[aria-label="入库记录排序"]').setValue('RECEIPT_ASC'); await flushPromises()
    api.receipts.mockResolvedValueOnce({ total: 0, items: [], options: { suppliers: ['测试纺织厂', '另一家供应商'] } })
    await wrapper!.get('[aria-label="入库单据状态筛选"]').setValue('REVERSED'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('', 0, { channel: '', supplier: '测试纺织厂', category: 'FABRIC', receipt_from: '2026-10-01', receipt_to: '2026-10-07', state: 'REVERSED', sort: 'RECEIPT_ASC' })
    expect(wrapper!.text()).toContain('没有找到匹配的入库记录')
    expect(wrapper!.get('[aria-label="入库供应商筛选"]').text()).toContain('另一家供应商')
    await wrapper!.findAll('button').find(button => button.text() === '查看全部记录')!.trigger('click'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('', 0, { channel: '', supplier: '', category: '', state: '', receipt_from: '', receipt_to: '', sort: 'RECEIPT_DESC' })
    expect(wrapper!.getComponent(DateRangeFilter).props('modelValue')).toEqual({ start: undefined, end: undefined })
  })
  it('ignores an old query while new header input is waiting to search', async () => {
    vi.useFakeTimers()
    let resolve!: (result: { total: number; items: FabricReceipt[] }) => void
    api.receipts.mockReturnValueOnce(new Promise(done => { resolve = done }))
    await open(true)
    headerSearch.search.value = 'missing'
    resolve({ total: 1, items: [record] }); await flushPromises()
    expect(wrapper!.text()).not.toContain('白色平纹布')
    // Clearing back to the applied query must still release the loading state.
    headerSearch.search.value = ''
    await vi.advanceTimersByTimeAsync(350); await flushPromises()
    expect(wrapper!.text()).toContain('白色平纹布')
    expect(wrapper!.attributes('aria-busy')).toBe('false')
  })
  it('clears a previously opened receipt when a refresh fails instead of displaying stale details or empty success', async () => {
    const body = await open()
    await wrapper!.find('.receipt-records-detail-button').trigger('click'); await flushPromises()
    api.receipts.mockRejectedValueOnce({ response: { status: 403, data: { detail: '查询授权已取消' } }, isAxiosError: true })
    await wrapper!.get('[aria-label="刷新入库记录"]').trigger('click'); await flushPromises()
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper!.findAll('tbody tr')).toHaveLength(0)
    expect(wrapper!.get('[role="alert"]').text()).toContain('查询授权已取消')
    expect(wrapper!.text()).not.toContain('还没有实际入库记录')
    expect(wrapper!.text()).not.toContain('0 笔')
  })
  it('ignores a late receipt response after switching record modes', async () => {
    let resolve!: (result: { total: number; items: FabricReceipt[] }) => void
    api.receipts.mockReturnValueOnce(new Promise(done => { resolve = done }))
    await open()
    await wrapper!.setProps({ mode: 'stock' }); await flushPromises()
    resolve({ total: 1, items: [record] }); await flushPromises()
    expect(wrapper!.get('h2').text()).toBe('原始入库批次')
    expect(wrapper!.text()).not.toContain('测试纺织厂')
    expect(wrapper!.text()).toContain('还没有实际入库记录')
  })
})

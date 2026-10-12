import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ref } from 'vue'
import { CalendarDate } from '@internationalized/date'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import { purchaseSearchKey } from '../purchaseSearch'
import Records from '../FabricReceivingRecords.vue'
import type { FabricReceipt } from '@/api/fabricReceiving'

const api = vi.hoisted(() => ({ receipts: vi.fn(), stock: vi.fn(), reversalPreview: vi.fn(), reverse: vi.fn() }))
vi.mock('@/api/fabricReceiving', () => ({ fabricReceivingApi: api, materialCategoryLabels: { FABRIC: '布料', ACCESSORY: '辅料', THREAD: '线' } }))
const record: FabricReceipt = {
  id: '68a72a1f9a3a4f7bb3fead135e30500b', source_line_id: 'SOURCE-0001', source_revision: 3,
  facts: { order_no: 'PO-001', supplier: '测试纺织厂', material_code: '00123', material_name: '白色平纹布', source_category: 'SUPPLEMENT', production_no: 'FC-001', contract_no: 'CT-001' } as FabricReceipt['facts'],
  quantity: '0.3', unit: '码', prior_received_quantity: null, receipt_date: '2026-10-07', accounting_month: '2026-10', delivery_reference: 'DN-001',
  material_category: 'FABRIC', difference_reason: '现场核实多到数量', note: '保留原始交货备注', actor_name: '仓管甲', occurred_at: '2026-10-07T09:10:00+08:00', stock_posted: true,
  batches: [{ id: 'B1', quantity: '0.1', location: 'A01', dye_lot: '0001', roll_no: '00002', quality_status: 'PENDING_INSPECTION' }, { id: 'B2', quantity: '0.2', location: 'A02', dye_lot: '0001', roll_no: '00003', quality_status: 'PENDING_INSPECTION' }],
}
let wrapper: VueWrapper | undefined
const headerSearch = { search: ref(''), submitted: ref(0) }
async function open(withHeader = false) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/'); await router.isReady()
  wrapper = mount(Records, { props: { mode: 'receipts' }, global: { plugins: [router], provide: withHeader ? { [purchaseSearchKey as symbol]: headerSearch } : {} }, attachTo: document.body })
  await flushPromises()
  return new DOMWrapper(document.body)
}
beforeEach(() => { vi.resetAllMocks(); headerSearch.search.value = ''; headerSearch.submitted.value = 0; api.receipts.mockResolvedValue({ total: 1, items: [record], options: { suppliers: ['测试纺织厂', '另一家供应商'] } }); api.stock.mockResolvedValue({ total: 0, items: [] }) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.useRealTimers(); vi.restoreAllMocks() })

describe('fabric receipt history', () => {
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
    expect(wrapper!.text()).toContain('库存和采购待收量已更新')
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
  it('opens a full read-only receipt with original identities, split quantities and historical quality', async () => {
    const body = await open()
    expect(wrapper!.get('.receipt-records-table tbody').text()).toContain('68a72a1f…500b')
    expect(body.find('[role="dialog"]').exists()).toBe(false)
    await wrapper!.find('.receipt-records-detail-button').trigger('click'); await flushPromises()
    const detail = body.get('[role="dialog"]')
    for (const value of [record.id, record.source_line_id, '00002', '00003', 'A01', 'A02', '0.1', '0.2', '现场核实多到数量', '入库时质量', '2026-10-07 09:10']) expect(detail.text()).toContain(value)
    expect(detail.findAll('tbody tr')).toHaveLength(2)
    expect(detail.find('input').exists()).toBe(false)
    await body.get('[aria-label="关闭入库详情"]').trigger('click'); await flushPromises()
    expect(body.find('[role="dialog"]').exists()).toBe(false)
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
    expect(api.receipts).toHaveBeenLastCalledWith('', 0, { supplier: '测试纺织厂', category: 'FABRIC', receipt_from: '2026-10-01', receipt_to: '2026-10-07', state: 'REVERSED', sort: 'RECEIPT_ASC' })
    expect(wrapper!.text()).toContain('没有找到匹配的入库记录')
    expect(wrapper!.get('[aria-label="入库供应商筛选"]').text()).toContain('另一家供应商')
    await wrapper!.findAll('button').find(button => button.text() === '查看全部记录')!.trigger('click'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('', 0, { supplier: '', category: '', state: '', receipt_from: '', receipt_to: '', sort: 'RECEIPT_DESC' })
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

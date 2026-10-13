import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'
import { parseDate } from '@internationalized/date'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import Summary from '../FabricOrderSummary.vue'
import { inventorySearchKey } from '../inventorySearch'
import type { FabricOrderReport } from '@/api/warehouseOperations'
const api = vi.hoisted(() => ({ orderSummary: vi.fn() }))
vi.mock('@/api/warehouseOperations', () => ({ warehouseOperationsApi: api }))
const report: FabricOrderReport = {
  date_from: '', date_to: '', search: '', supplier: '', suppliers: ['纺织厂'], version: '1', basis: '记录结余，未接入历史期初',
  rows: [{ key: 'K', source_line_id: 'S', order_no: 'PO-001', production_no: 'FC-001', style_no: '', supplier: '纺织厂', item_code: '0001', item_name: '白布', unit: '码', linked: true, document_count: 2, opening: '50', inbound: '0', outbound: '4', adjustment: '1', balance: '47' }],
  totals: [{ unit: '码', opening: '50', inbound: '0', outbound: '4', adjustment: '1', balance: '47' }],
  details: [{ key: 'K', source_line_id: 'S', order_no: 'PO-001', production_no: 'FC-001', style_no: '', supplier: '纺织厂', item_code: '0001', item_name: '白布', unit: '码', linked: true, id: 'I', date: '2026-10-10', mode: 'OUTBOUND', label: '手动出库', quantity: '4', stock_change: '-4', moved_quantity: '0', source_no: 'IS-001', original_id: '', recipient: '车间一', location: 'A01', channel: 'MANUAL', actor_name: '仓管', reason: '', sequence: 1 }],
}
let wrapper: VueWrapper
beforeEach(() => { vi.resetAllMocks(); api.orderSummary.mockResolvedValue(structuredClone(report)) })
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = ''; vi.useRealTimers() })
async function open() { wrapper = mount(Summary, { attachTo: document.body }); await flushPromises() }
describe('fabric order receiving issuing and adjustments', () => {
  it('shows the carton four-view structure and original-unit balance with order timeline', async () => {
    await open()
    expect(wrapper.get('nav').text()).toBe('订单汇总入库明细出库明细调整明细')
    expect(wrapper.get('tbody').text()).toContain('PO-001')
    expect(wrapper.get('.balance').text()).toBe('47')
    await wrapper.findAll('button').find(button => button.text() === '订单流水')!.trigger('click'); await flushPromises()
    const body = new DOMWrapper(document.body)
    expect(body.get('[role="dialog"]').text()).toContain('-4 码')
    await body.findAll('button').find(button => button.text() === '关闭流水')!.trigger('click')
    await wrapper.findAll('nav button').find(button => button.text() === '出库明细')!.trigger('click')
    expect(wrapper.get('tbody').text()).toContain('IS-001')
    expect(wrapper.get('tbody').text()).toContain('车间一')
  })
  it('applies a completed date range with supplier and keyword, and clears both date bounds together', async () => {
    await open()
    await wrapper.get('[aria-label="订单收发关键字"]').setValue(' PO-001 ')
    await wrapper.get('[aria-label="订单收发供应商"]').setValue('纺织厂')
    expect(api.orderSummary).toHaveBeenCalledTimes(1)
    wrapper.getComponent(DateRangeFilter).vm.$emit('update:modelValue', { start: parseDate('2026-10-01'), end: parseDate('2026-10-13') }); await flushPromises()
    expect(api.orderSummary).toHaveBeenCalledTimes(2)
    expect(api.orderSummary).toHaveBeenLastCalledWith({ date_from: '2026-10-01', date_to: '2026-10-13', search: 'PO-001', supplier: '纺织厂' })
    wrapper.getComponent(DateRangeFilter).vm.$emit('update:modelValue', { start: undefined, end: undefined }); await flushPromises()
    expect(api.orderSummary).toHaveBeenLastCalledWith({ date_from: '', date_to: '', search: 'PO-001', supplier: '纺织厂' })
  })
  it('clears old balances on permission failure and ignores responses after unmount', async () => {
    await open()
    api.orderSummary.mockRejectedValueOnce({ isAxiosError: true, response: { status: 403, data: { detail: '无查询权限' } } })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('无查询权限')
    let resolve!: (value: FabricOrderReport) => void
    api.orderSummary.mockReturnValueOnce(new Promise(done => { resolve = done }))
    await wrapper.get('form').trigger('submit')
    wrapper.unmount(); resolve(report); await flushPromises()
    expect(document.body.textContent).not.toContain('PO-001')
  })
  it('uses the shared header query, discards stale results and cancels debounce on Enter or reset', async () => {
    vi.useFakeTimers()
    const search = ref(''), submitted = ref(0)
    let resolveOld!: (value: FabricOrderReport) => void
    api.orderSummary.mockReturnValueOnce(new Promise(done => { resolveOld = done }))
    wrapper = mount(Summary, { global: { provide: { [inventorySearchKey as symbol]: { search, submitted, active: ref(true) } } } })
    expect(wrapper.find('[aria-label="订单收发关键字"]').exists()).toBe(false)
    search.value = ' PO-002 '
    resolveOld(report); await flushPromises()
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).toContain('正在核对')
    await vi.advanceTimersByTimeAsync(349)
    expect(api.orderSummary).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1); await flushPromises()
    expect(api.orderSummary).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'PO-002' }))
    search.value = 'PO-003'; submitted.value++; await flushPromises()
    expect(api.orderSummary).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(400)
    expect(api.orderSummary).toHaveBeenCalledTimes(3)
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click'); await flushPromises()
    expect(search.value).toBe('')
    expect(api.orderSummary).toHaveBeenLastCalledWith({ date_from: '', date_to: '', search: '', supplier: '' })
    await vi.advanceTimersByTimeAsync(400)
    expect(api.orderSummary).toHaveBeenCalledTimes(4)
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Records from '../FabricReceivingRecords.vue'
import type { FabricReceipt } from '@/api/fabricReceiving'

const api = vi.hoisted(() => ({ receipts: vi.fn(), stock: vi.fn() }))
vi.mock('@/api/fabricReceiving', () => ({ fabricReceivingApi: api, materialCategoryLabels: { FABRIC: '布料', ACCESSORY: '辅料', THREAD: '线' } }))
const record: FabricReceipt = {
  id: '68a72a1f9a3a4f7bb3fead135e30500b', source_line_id: 'SOURCE-0001', source_revision: 3,
  facts: { order_no: 'PO-001', supplier: '测试纺织厂', material_code: '00123', material_name: '白色平纹布', source_category: 'SUPPLEMENT', production_no: 'FC-001', contract_no: 'CT-001' } as FabricReceipt['facts'],
  quantity: '0.3', unit: '码', prior_received_quantity: null, receipt_date: '2026-10-07', accounting_month: '2026-10', delivery_reference: 'DN-001',
  material_category: 'FABRIC', difference_reason: '现场核实多到数量', note: '保留原始交货备注', actor_name: '仓管甲', occurred_at: '2026-10-07T09:10:00+08:00', stock_posted: true,
  batches: [{ id: 'B1', quantity: '0.1', location: 'A01', dye_lot: '0001', roll_no: '00002', quality_status: 'PENDING_INSPECTION' }, { id: 'B2', quantity: '0.2', location: 'A02', dye_lot: '0001', roll_no: '00003', quality_status: 'PENDING_INSPECTION' }],
}
let wrapper: VueWrapper | undefined
async function open() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/'); await router.isReady()
  wrapper = mount(Records, { props: { mode: 'receipts' }, global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return new DOMWrapper(document.body)
}
beforeEach(() => { vi.resetAllMocks(); api.receipts.mockResolvedValue({ total: 1, items: [record] }); api.stock.mockResolvedValue({ total: 0, items: [] }) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks() })

describe('fabric receipt history', () => {
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
    expect(api.receipts).toHaveBeenLastCalledWith('', 50)
    await wrapper!.get('[aria-label="查找实际入库记录"]').setValue('  PO-001  ')
    expect(api.receipts).toHaveBeenCalledTimes(2)
    await wrapper!.get('form').trigger('submit'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('PO-001', 0)
    expect(wrapper!.get('.receipt-records-filter').text()).toContain('PO-001')
    await wrapper!.get('[aria-label="清空入库搜索"]').trigger('click'); await flushPromises()
    expect(api.receipts).toHaveBeenLastCalledWith('', 0)
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

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { reactive, ref } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import View from '../FabricMonthlyWorkspace.vue'
import type { FabricMonthlyReport } from '@/api/warehouseOperations'
import { monthlySearchKey } from '../inventorySearch'

const api = vi.hoisted(() => ({ monthly: vi.fn(), exportMonthly: vi.fn() }))
vi.mock('@/api/warehouseOperations', () => ({ warehouseOperationsApi: api }))
const auth = reactive({ currentUser: { id: 'warehouse' }, authorizationVersion: 1 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
const counts = { received: '20', receipt_reversed: '0', net_received: '20', issued: '5', issue_reversed: '0', returned: '1', net_issued: '5', net_outbound: '4', stock_change: '16', manual_received: '5', scan_received: '15', manual_outbound: '4', scan_outbound: '0' }
const fixture = (): FabricMonthlyReport => ({ month: '2026-07', direction: '', channel: '', party_key: '', version: 'snapshot', live: true, closed: false, amounts_calculated: false, cutting_interface: 'PENDING', basis: '实际业务月份',
  parties: [{ key: 'supplier:A', name: '供应商甲', direction: 'IN' }, { key: 'recipient:裁床', name: '裁床', direction: 'OUT' }],
  totals: [{ unit: '码', ...counts }], summary: [{ direction: 'IN', party_key: 'supplier:A', party_name: '供应商甲', item_code: '0001', item_name: '布料', unit: '码', document_count: 2, ...counts }],
  details: [{ id: 'FB-1', date: '2026-07-18', direction: 'IN', kind: 'RECEIPT', correction: false, original_id: '', channel: 'SCAN', channel_label: '扫码', origin: 'MATERIAL_HANDOVER', source_no: 'DN-1', source_line: '1', document_id: 'MHD-1', party_key: 'supplier:A', party_name: '供应商甲', recorded_party: '供应商甲', supplier_id: 'A', identity_basis: '基础资料编号', item_code: '0001', item_name: '布料', unit: '码', quantity: '15', actor_name: '仓库', unit_price: '0', price_unit: '码', currency: 'CNY', price_note: '免费补货' }] })
let wrapper: VueWrapper | undefined
const search = ref(''), submitted = ref(0)
async function open(view = 'monthly', factory = 'huakang-c') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: View, props: route => ({ view: route.query.view || 'monthly' }) }, { path: '/modules/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push(`/?factory=${factory}&view=${view}`); await router.isReady()
  wrapper = mount(RouterView, { attachTo: document.body, global: { plugins: [router], provide: { [monthlySearchKey as symbol]: { search, submitted, active: ref(true) } } } }); await flushPromises()
  return router
}
beforeEach(() => { vi.resetAllMocks(); search.value = ''; submitted.value = 0; auth.currentUser.id = 'warehouse'; auth.authorizationVersion = 1; api.monthly.mockResolvedValue(fixture()) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('warehouse unified month reconciliation', () => {
  it('queries supplier/recipient views with channel and party filters, retaining zero price evidence', async () => {
    const router = await open('reconciliation')
    expect(api.monthly).toHaveBeenLastCalledWith(expect.objectContaining({ direction: 'IN', channel: '', party_key: '' }))
    expect(wrapper!.text()).toContain('供应商收料对账')
    await wrapper!.findAll('.monthly-modes button')[1]!.trigger('click')
    await wrapper!.get('[aria-label="查看凭证 FB-1"]').trigger('click'); await flushPromises()
    const body = new DOMWrapper(document.body)
    expect(body.get('[role="dialog"]').text()).toContain('0 / 码')
    expect(body.get('[role="dialog"] a').attributes('href')).toBe('/modules/pmc-warehouse/material-handover?factory=huakang-c&tab=documents&document=MHD-1')
    await body.findAll('button').find(button => button.text() === '关闭')!.trigger('click')
    await wrapper!.get('[aria-label="月结登记方式"]').setValue('SCAN'); await flushPromises()
    expect(api.monthly).toHaveBeenLastCalledWith(expect.objectContaining({ direction: 'IN', channel: 'SCAN' }))
    await wrapper!.get('[aria-label="月结往来方"]').setValue('supplier:A'); await flushPromises()
    expect(api.monthly).toHaveBeenLastCalledWith(expect.objectContaining({ party_key: 'supplier:A' }))
    await router.push('/?factory=huakang-c&view=recipients'); await flushPromises()
    expect(api.monthly).toHaveBeenLastCalledWith(expect.objectContaining({ direction: 'OUT', channel: '', party_key: '' }))
    expect(wrapper!.text()).toContain('领用方发料对账')
    expect(wrapper!.text()).toContain('裁床接口领料 · 待接入')
  })
  it('clears old records immediately and ignores late reports after an account change', async () => {
    await open()
    let resolve!: (value: FabricMonthlyReport) => void
    api.monthly.mockReturnValueOnce(new Promise<FabricMonthlyReport>(done => { resolve = done }))
    await wrapper!.get('[aria-label="月结核对月份"]').setValue('2026-08')
    expect(wrapper!.text()).not.toContain('供应商甲')
    auth.currentUser.id = ''; await flushPromises()
    resolve(fixture()); await flushPromises()
    expect(wrapper!.text()).not.toContain('DN-1')
    expect(wrapper!.find('.monthly-totals').exists()).toBe(false)
  })
  it('does not fetch data in another factory and clears failures instead of retaining old totals', async () => {
    const router = await open('monthly', 'huakang-d')
    expect(api.monthly).not.toHaveBeenCalled()
    await router.push('/?factory=huakang-c&view=monthly'); await flushPromises()
    api.monthly.mockRejectedValueOnce(new Error('读取失败'))
    await wrapper!.get('[aria-label="月结核对月份"]').setValue('2026-08'); await flushPromises()
    expect(wrapper!.get('[role="alert"]').text()).toContain('读取失败')
    expect(wrapper!.find('.monthly-totals').exists()).toBe(false)
  })
  it('exports the selected filters bound to the displayed snapshot', async () => {
    await open('recipients')
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:month')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    api.exportMonthly.mockResolvedValue(new Blob(['xlsx']))
    await wrapper!.findAll('button').find(button => button.text() === '导出当前对账表')!.trigger('click'); await flushPromises()
    expect(api.exportMonthly).toHaveBeenCalledWith(expect.objectContaining({ direction: 'OUT', channel: '', party_key: '' }), 'snapshot')
  })
  it('invalidates old exports immediately on header search, cancels debounce on Enter and keeps filters in exports', async () => {
    vi.useFakeTimers()
    await open()
    let resolveOld!: (value: FabricMonthlyReport) => void
    api.monthly.mockReturnValueOnce(new Promise(done => { resolveOld = done }))
    await wrapper!.get('[aria-label="月结原单位"]').setValue('码')
    search.value = ' DN-002 '
    resolveOld(fixture()); await flushPromises()
    expect(wrapper!.find('table').exists()).toBe(false)
    expect(wrapper!.findAll('button').find(button => button.text() === '导出当前对账表')!.attributes('disabled')).toBeDefined()
    submitted.value++; await flushPromises()
    expect(api.monthly).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'DN-002', unit: '码', date_order: 'DESC' }))
    const calls = api.monthly.mock.calls.length
    await vi.advanceTimersByTimeAsync(300)
    expect(api.monthly).toHaveBeenCalledTimes(calls)
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:month')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    api.exportMonthly.mockResolvedValue(new Blob(['xlsx']))
    await wrapper!.findAll('button').find(button => button.text() === '导出当前对账表')!.trigger('click'); await flushPromises()
    expect(api.exportMonthly).toHaveBeenCalledWith(expect.objectContaining({ search: 'DN-002', unit: '码' }), 'snapshot')
  })
  it('paginates the full report without cutting totals, validates months and does not reset on same-session refresh', async () => {
    const data = fixture()
    data.details = Array.from({ length: 26 }, (_, i) => ({ ...data.details[0]!, id: `D-${i}` }))
    api.monthly.mockResolvedValue(data)
    await open()
    await wrapper!.findAll('.monthly-modes button')[1]!.trigger('click')
    expect(wrapper!.findAll('tbody tr')).toHaveLength(25)
    await wrapper!.findAll('button').find(button => button.text() === '下一页')!.trigger('click')
    expect(wrapper!.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper!.get('.monthly-totals').text()).toContain('净实收20')
    const calls = api.monthly.mock.calls.length
    auth.currentUser = { id: 'warehouse' }; await flushPromises()
    expect(api.monthly).toHaveBeenCalledTimes(calls)
    expect(wrapper!.get('tbody').text()).toContain('DN-1')
    await wrapper!.get('[aria-label="月结核对月份"]').setValue(''); await flushPromises()
    expect(api.monthly).toHaveBeenCalledTimes(calls)
    expect(wrapper!.get('[role="alert"]').text()).toContain('请选择有效的核对月份')
    expect(wrapper!.find('table').exists()).toBe(false)
  })
})

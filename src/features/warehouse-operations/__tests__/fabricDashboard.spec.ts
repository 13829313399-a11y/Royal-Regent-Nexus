import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import Dashboard from '../FabricDashboard.vue'

const api = vi.hoisted(() => ({ lines: vi.fn(), pendingDeliveries: vi.fn() }))
vi.mock('@/api/fabricProcurement', () => ({ fabricProcurementApi: api }))
vi.mock('@/api/materialHandover', () => ({ handoverApi: () => api }))
const auth = reactive({ currentUser: { id: 'staff' }, authorizationVersion: 1 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
const procurement = () => ({ summary: { outstanding: 75, overdue: 12, due_today: 3, awaiting_date: 6 }, items: [{ id: 'L1', facts: { order_no: 'PO-01', supplier: '供应商甲', material_name: '测试布料', unit: '码' }, tracking: { overdue: true }, overdue_days: 2, warehouse_outstanding_quantity: null }] })
const delivery = () => ({ total: 8, items: [{ id: 'D1', data: { source_no: 'DN-01', counterparty: '供应商甲', document_date: '2026-10-12' }, pending_line_count: 2, processing_status: 'PARTIAL', first_item_name: '布料甲' }], stock_totals: [{ quantity: '0.3', unit: '米' }, { quantity: '15.75', unit: '码' }], limit: 4, offset: 0 })
let wrapper: VueWrapper | undefined
beforeEach(() => { vi.resetAllMocks(); auth.currentUser.id = 'staff'; auth.authorizationVersion = 1; api.lines.mockResolvedValue(procurement()); api.pendingDeliveries.mockResolvedValue(delivery()) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks() })
async function open() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/modules/pmc-warehouse/fabric-warehouse/overview?factory=huakang-c'); await router.isReady()
  wrapper = mount(Dashboard, { global: { plugins: [router] } }); await flushPromises()
  return router
}

describe('fabric daily dashboard', () => {
  it('uses whole-result counts, separate units and exact existing receiving destinations', async () => {
    await open()
    expect(wrapper!.get('[aria-label="布料仓统计"]').text()).toContain('75')
    expect(wrapper!.get('[aria-label="布料仓统计"]').text()).toContain('8')
    expect(wrapper!.get('.stock-card').text()).toContain('0.3 米 · 15.75 码')
    expect(wrapper!.text()).toContain('数量待核对')
    expect(wrapper!.text()).toContain('部分已入库')
    expect(wrapper!.find('table').exists()).toBe(false)
    const links = wrapper!.findAll('a')
    expect(links.find(row => row.text() === '扫码入库')!.attributes('href')).toBe('/modules/pmc-warehouse/material-handover?factory=huakang-c&tab=scan')
    expect(links.find(row => row.text() === '核实入库')!.attributes('href')).toContain('deliveries=pending&document=D1')
    expect(links.find(row => row.text().startsWith('逾期需追货'))!.attributes('href')).toContain('tracking=OVERDUE')
    expect(links.find(row => row.text() === '查看追货')!.attributes('href')).toContain('order_no=PO-01')
  })
  it('keeps a failed source unknown while displaying the independently loaded source', async () => {
    api.pendingDeliveries.mockRejectedValue(new Error('连接中断'))
    await open()
    expect(wrapper!.get('[role="alert"]').text()).toContain('未能读取')
    expect(wrapper!.get('.stock-card strong').text()).toBe('—')
    expect(wrapper!.text()).not.toContain('暂无库存')
    expect(wrapper!.text()).toContain('待追货 75 项')
  })
  it('clears private data and ignores old requests after the viewer changes', async () => {
    let finish!: (value: unknown) => void
    api.pendingDeliveries.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await open()
    api.lines.mockResolvedValue({ summary: { outstanding: 0 }, items: [] })
    api.pendingDeliveries.mockRejectedValue(new Error('没有查询权限'))
    auth.currentUser.id = 'another'; auth.authorizationVersion++
    await flushPromises(); finish(delivery()); await flushPromises()
    expect(wrapper!.text()).not.toContain('供应商甲')
    expect(wrapper!.text()).not.toContain('15.75')
    expect(wrapper!.get('.stock-card strong').text()).toBe('—')
  })
  it('refreshes on return and removes its refresh listener on unmount', async () => {
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    await open(); api.pendingDeliveries.mockResolvedValue({ ...delivery(), total: 0, items: [] })
    window.dispatchEvent(new Event('focus')); await flushPromises()
    expect(wrapper!.text()).toContain('当前没有待入库的供应商送货单')
    expect(api.pendingDeliveries).toHaveBeenCalledTimes(2)
    wrapper!.unmount(); wrapper = undefined
    window.dispatchEvent(new Event('focus'))
    expect(api.pendingDeliveries).toHaveBeenCalledTimes(2)
  })
  it('keeps loaded counts in place during refresh, but removes them on a failed refresh', async () => {
    await open()
    let fail!: (reason: unknown) => void
    api.pendingDeliveries.mockImplementationOnce(() => new Promise((_, reject) => { fail = reject }))
    await wrapper!.get('button').trigger('click'); await flushPromises()
    expect(wrapper!.text()).toContain('15.75 码')
    expect(wrapper!.text()).not.toContain('正在读取送货进度')
    fail(new Error('没有查询权限')); await flushPromises()
    expect(wrapper!.text()).not.toContain('15.75 码')
    expect(wrapper!.get('.stock-card strong').text()).toBe('—')
  })
})

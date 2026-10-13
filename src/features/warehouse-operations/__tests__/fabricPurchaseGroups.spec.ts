import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ref } from 'vue'
import Workspace from '../FabricProcurementWorkspace.vue'
import { purchaseSearchKey } from '../purchaseSearch'
import type { PurchaseGroupResult, PurchaseMaterialGroup } from '@/api/fabricProcurement'

const api = vi.hoisted(() => ({ groups: vi.fn(), lines: vi.fn(), detail: vi.fn() }))
vi.mock('@/api/fabricProcurement', () => ({ fabricProcurementApi: api }))
const group: PurchaseMaterialGroup = { key: 'material-key', supplier: '甲厂', material_code: '001', material_name: '白布', unit: '码', line_count: 60,
  order_count: 60, production_count: 2, supplement_count: 0, remaining_quantity: '6', known_remaining_quantity: '6', unknown_quantity_count: 0,
  warehouse_received_quantity: '0', known_received_quantity: '0', unknown_received_count: 0, earliest_promise: '2026-10-01', latest_promise: '2026-10-20', overdue_count: 2, due_today_count: 1, awaiting_date_count: 3, changed_count: 1 }
const result = (value = group): PurchaseGroupResult => ({ groups: [value], total: 1, line_total: 60, summary: { outstanding: 60, partial: 0, not_arrived: 60, arrival_review: 0, changed: 1 }, can_receive: true })
let wrapper: VueWrapper | undefined
const search = ref(''), submitted = ref(0)
const button = (text: string) => wrapper!.findAll('button').find(b => b.text() === text)!
async function open() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/'); await router.isReady()
  wrapper = mount(Workspace, { props: { mode: 'pending' }, global: { plugins: [router], provide: { [purchaseSearchKey as symbol]: { search, submitted } } } })
  await flushPromises()
}
beforeEach(() => { vi.clearAllMocks(); search.value = ''; submitted.value = 0; api.groups.mockResolvedValue(result()); api.lines.mockResolvedValue({ total: 60, items: [], can_receive: true }) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers() })

describe('material follow-up grouping', () => {
  it('invalidates earlier results as soon as the search changes, before the debounce expires', async () => {
    await open(); vi.useFakeTimers()
    let resolve!: (value: PurchaseGroupResult) => void
    api.groups.mockImplementationOnce(() => new Promise(r => { resolve = r }))
    search.value = '旧查询'; submitted.value++; await flushPromises()
    search.value = '新查询'
    resolve(result({ ...group, material_name: '旧查询结果' })); await flushPromises()
    expect(wrapper!.text()).not.toContain('旧查询结果')
    expect(wrapper!.findAll('.fabric-purchase-groups tbody tr')).toHaveLength(0)
    expect(wrapper!.text()).toContain('正在查询采购资料')
    api.groups.mockResolvedValue(result({ ...group, material_name: '新查询结果' }))
    await vi.advanceTimersByTimeAsync(350); await flushPromises()
    expect(api.groups).toHaveBeenLastCalledWith('新查询', 0, 'OUTSTANDING', expect.any(Object))
    expect(wrapper!.text()).toContain('新查询结果')
  })
  it('defaults to full server groups and drills into the exact group while preserving filters and child pagination', async () => {
    await open()
    expect(wrapper!.text()).toContain('1 个物料组 · 60 条采购明细')
    expect(wrapper!.text()).toContain('60 张单 · 60 条明细')
    expect(api.lines).not.toHaveBeenCalled()
    await wrapper!.get('[aria-label="供应商筛选"]').setValue(''); await flushPromises()
    search.value = '白布'; submitted.value++; await flushPromises()
    await button('查看采购明细').trigger('click'); await flushPromises()
    expect(api.lines).toHaveBeenLastCalledWith('PENDING', '白布', 0, 'OUTSTANDING', expect.objectContaining({ group_key: 'material-key' }))
    await button('下一页').trigger('click'); await flushPromises()
    expect(api.lines).toHaveBeenLastCalledWith('PENDING', '白布', 50, 'OUTSTANDING', expect.objectContaining({ group_key: 'material-key' }))
    await button('返回物料汇总').trigger('click'); await flushPromises()
    expect(api.groups).toHaveBeenLastCalledWith('白布', 0, 'OUTSTANDING', expect.not.objectContaining({ group_key: 'material-key' }))
    expect(api.detail).not.toHaveBeenCalled()
  })

  it('shows incomplete chase totals as unknown and labels the known portion separately', async () => {
    api.groups.mockResolvedValue(result({ ...group, remaining_quantity: null, known_remaining_quantity: '0.3', unknown_quantity_count: 2,
      warehouse_received_quantity: null, known_received_quantity: '5', unknown_received_count: 1 }))
    await open()
    const row = wrapper!.get('.fabric-purchase-groups tbody tr')
    expect(row.text()).toContain('待核对')
    expect(row.text()).toContain('已明确 0.3 码')
    expect(row.text()).toContain('另有 2 条数量待核对')
    expect(row.text()).toContain('已明确 5 码')
    expect(row.text()).toContain('另有 1 条实收身份待核对')
    expect(row.text()).toContain('2 条复期已过')
  })

  it('retains original source identity for receiving and discards the group scope on clear', async () => {
    const source = { id: 'L1', revision: 2, facts: { order_no: 'PO1', material_code: '001', material_name: '白布', unit: '码', supplier: '甲厂' } }
    api.lines.mockResolvedValue({ total: 1, items: [source], can_receive: true })
    api.detail.mockResolvedValue({ ...source, can_receive: false })
    await open(); await button('查看采购明细').trigger('click'); await flushPromises()
    await wrapper!.get('[aria-label="选择 PO1 · 001"]').setValue(true)
    await button('返回物料汇总').trigger('click'); await flushPromises()
    expect(wrapper!.text()).toContain('其中 1 项不在当前筛选内')
    await wrapper!.findAll('button').find(b => b.text().startsWith('登记所选订单入库'))!.trigger('click'); await flushPromises()
    expect(api.detail).toHaveBeenCalledWith('L1')
    expect(wrapper!.get('[role="alert"]').text()).toContain('当前不能入库')
    await button('查看采购明细').trigger('click'); await flushPromises()
    await button('清空筛选').trigger('click'); await flushPromises()
    expect(button('返回物料汇总')).toBeUndefined()
    expect(api.groups).toHaveBeenLastCalledWith('', 0, 'OUTSTANDING', expect.not.objectContaining({ group_key: 'material-key' }))
  })

  it('ignores late grouped responses after switching to original rows and clears groups on denied refresh', async () => {
    await open()
    let resolve!: (value: PurchaseGroupResult) => void
    api.groups.mockImplementationOnce(() => new Promise(r => { resolve = r }))
    search.value = 'other'; submitted.value++; await flushPromises()
    // Mode/route changes can happen during a read, even while view buttons are disabled.
    await wrapper!.setProps({ mode: 'orders' }); await flushPromises()
    resolve(result()); await flushPromises()
    expect(wrapper!.find('.fabric-purchase-groups').exists()).toBe(false)
    api.groups.mockRejectedValue({ isAxiosError: true, response: { status: 403, data: { detail: '无查看权限' } } })
    await wrapper!.setProps({ mode: 'pending' }); await flushPromises()
    expect(wrapper!.get('[role="alert"]').text()).toContain('无查看权限')
    expect(wrapper!.findAll('tbody tr')).toHaveLength(0)
  })
})

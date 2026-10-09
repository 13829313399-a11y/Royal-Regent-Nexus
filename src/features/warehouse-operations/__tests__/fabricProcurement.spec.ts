import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Workspace from '../FabricProcurementWorkspace.vue'
import type { PurchasePreview } from '@/api/fabricProcurement'

const api = vi.hoisted(() => ({ preview: vi.fn(), apply: vi.fn(), lines: vi.fn(), detail: vi.fn(), imports: vi.fn(), withdrawalPreview: vi.fn(), withdraw: vi.fn(), reviewChanges: vi.fn() }))
vi.mock('@/api/fabricProcurement', () => ({ fabricProcurementApi: api }))
let wrapper: VueWrapper | undefined
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = '' })
beforeEach(() => { vi.clearAllMocks(); api.imports.mockResolvedValue([]); api.lines.mockResolvedValue({ total: 0, items: [] }) })
const counts = { total: 2, new: 1, updated: 0, unchanged: 0, blocked: 1, warnings: 0, pending: 1, returned: 1 }
const preview = { preview_token: 'a'.repeat(64), revision: 0, counts, sheets: ['未回物料', '已回料'], ignored_sheets: [], filtered_total: 2, offset: 0, limit: 100, items: [] } as PurchasePreview
async function open(mode: 'import' | 'pending' | 'orders' | 'returned' = 'import') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await router.push('/'); await router.isReady()
  wrapper = mount(Workspace, { props: { mode }, attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}
async function file() {
  const input = wrapper!.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { value: [new File(['source'], '采购.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })], configurable: true })
  await input.trigger('change')
}
function button(text: string) { return wrapper!.findAll('button').find(b => b.text() === text)! }
function dialogButton(text: string) { return [...document.querySelectorAll('button')].find(b => b.textContent?.trim() === text)! }

describe('real fabric procurement workspace', () => {
  it('shows ordered and prior quantities alongside chase remaining without treating history as system stock', async () => {
    api.lines.mockResolvedValue({ total: 1, items: [{ id: 'L1', revision: 1,
      facts: { order_no: 'CGDD014333', status: 'PENDING', ordered_quantity: '65', unit: '码' },
      starting_chase_quantity: '12', prior_received_quantity: '53', warehouse_received_quantity: '0', warehouse_outstanding_quantity: '12' }] })
    await open('pending')
    const row = wrapper!.get('.fabric-pending-table tbody tr')
    expect(row.text()).toContain('订单总量 65')
    expect(row.text()).toContain('此前已回 53')
    expect(row.findAll('td')[6]!.text()).toBe('0')
    expect(row.findAll('td')[7]!.text()).toBe('12')
  })
  it('reuses the original request identity after an unknown network outcome', async () => {
    await open(); await file(); api.preview.mockResolvedValue(preview)
    await button('读取并核对').trigger('click'); await flushPromises()
    await button('确认导入可用明细（1）').trigger('click'); await flushPromises()
    const checkbox = document.querySelector<HTMLInputElement>('input[type=checkbox]')!
    checkbox.checked = true; checkbox.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises()
    api.apply.mockRejectedValueOnce(new Error('连接中断'))
    dialogButton('保存采购来源').click(); await flushPromises()
    const request = api.apply.mock.calls[0]![3]
    api.apply.mockResolvedValueOnce({ id: 'B1', source_name: '采购.xlsx', occurred_at: '2026-10-05T10:00:00+08:00', actor_name: '仓管', counts, scope: 'ALL', stock_posted: false })
    dialogButton('保存采购来源').click(); await flushPromises()
    expect(api.apply.mock.calls[1]![3]).toBe(request)
    expect(wrapper!.text()).toContain('库存未增加')
  })
  it('requires file preview and explicit confirmation; saving never labels procurement as stock', async () => {
    await open()
    expect(button('读取并核对').attributes('disabled')).toBeDefined()
    await file(); api.preview.mockResolvedValue(preview)
    await button('读取并核对').trigger('click'); await flushPromises()
    expect(api.apply).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('待核对 1')
    await button('确认导入可用明细（1）').trigger('click'); await flushPromises()
    expect(dialogButton('保存采购来源').disabled).toBe(true)
    const checkbox = document.querySelector<HTMLInputElement>('input[type=checkbox]')!
    checkbox.checked = true; checkbox.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises()
    api.apply.mockResolvedValue({ id: 'B1', source_name: '采购.xlsx', occurred_at: '2026-10-05T10:00:00+08:00', actor_name: '仓管', counts, scope: 'ALL', stock_posted: false })
    dialogButton('保存采购来源').click(); await flushPromises()
    expect(api.apply).toHaveBeenCalledOnce()
    expect(api.apply.mock.calls[0]![2]).toBe(preview.preview_token)
    expect(wrapper!.text()).toContain('库存未增加')
  })
  it('invalidates old previews after changing scope or replacing the file', async () => {
    await open(); await file(); api.preview.mockResolvedValue(preview)
    await button('读取并核对').trigger('click'); await flushPromises()
    await wrapper!.get('select[aria-label="采购导入范围"]').setValue('RETURNED')
    expect(wrapper!.text()).not.toContain('确认导入可用明细')
    expect(api.apply).not.toHaveBeenCalled()
    await button('读取并核对').trigger('click'); await flushPromises()
    expect(api.preview.mock.calls.at(-1)![1]).toBe('RETURNED')
    await file(); expect(wrapper!.text()).not.toContain('确认导入可用明细')
  })
  it('ignores late responses when changing the workspace and clears protected data on a denied query', async () => {
    let resolve!: (v: PurchasePreview) => void
    api.preview.mockImplementation(() => new Promise(r => { resolve = r }))
    await open(); await file(); await button('读取并核对').trigger('click')
    await wrapper!.setProps({ mode: 'pending' }); await flushPromises()
    resolve(preview); await flushPromises()
    expect(wrapper!.text()).not.toContain('确认导入可用明细')
    expect(api.lines).toHaveBeenLastCalledWith('PENDING', '', 0, 'OUTSTANDING', expect.any(Object))
    api.lines.mockRejectedValue({ isAxiosError: true, response: { status: 403, data: { detail: '无查看权限' } } })
    await wrapper!.get('input[type=search]').setValue('000123'); await wrapper!.get('form').trigger('submit'); await flushPromises()
    expect(wrapper!.get('[role=alert]').text()).toContain('无查看权限')
    expect(wrapper!.findAll('tbody tr')).toHaveLength(0)
    expect(wrapper!.text()).not.toContain('共 0 条')
  })
  it('defaults to outstanding sources and can separately query reported arrivals and unread changes', async () => {
    api.lines.mockResolvedValue({ total: 0, items: [], summary: { outstanding: 3, not_arrived: 2, partial: 1, arrival_review: 2, changed: 1 } })
    await open('pending')
    expect(api.lines).toHaveBeenLastCalledWith('PENDING', '', 0, 'OUTSTANDING', expect.any(Object))
    await button('采购报到货 · 待核对 2').trigger('click'); await flushPromises()
    expect(api.lines).toHaveBeenLastCalledWith('PENDING', '', 0, 'ARRIVAL_REVIEW', expect.any(Object))
    expect(wrapper!.text()).toContain('不代表仓库已确认')
    await wrapper!.get('select[aria-label="待收料跟进范围"]').setValue('NOT_ARRIVED'); await flushPromises()
    expect(api.lines).toHaveBeenLastCalledWith('PENDING', '', 0, 'NOT_ARRIVED', expect.any(Object))
    await button('订单变更 · 未读 1').trigger('click'); await flushPromises()
    expect(api.lines).toHaveBeenLastCalledWith('PENDING', '', 0, 'CHANGED', expect.any(Object))
    expect(api.apply).not.toHaveBeenCalled()
  })
  it('uses tracking scope by default and explicitly excludes unrelated returned history', async () => {
    await open(); await file(); api.preview.mockResolvedValue({ ...preview, excluded_history: 42500 })
    await button('读取并核对').trigger('click'); await flushPromises()
    expect(api.preview).toHaveBeenLastCalledWith(expect.any(File), 'TRACKING', 0, 'ALL')
    expect(wrapper!.text()).toContain('已排除 42500 条未关联的已回历史')
  })
  it('previews withdrawal impact and requires reason plus confirmation before rolling back', async () => {
    const batch = { id: 'B1', source_name: '采购.xlsx', occurred_at: '2026-10-05T10:00:00+08:00', actor_name: '仓管', counts, scope: 'TRACKING', can_withdraw: true }
    api.imports.mockResolvedValue([batch]); api.withdrawalPreview.mockResolvedValue({ id: 'B1', source_name: '采购.xlsx', remove_count: 913, restore_count: 2, preview_token: 'w'.repeat(64) })
    await open(); await button('撤销导入').trigger('click'); await flushPromises()
    expect(document.body.textContent).toContain('移出新增来源 913 条；恢复原有来源 2 条')
    expect(api.withdraw).not.toHaveBeenCalled()
    expect(dialogButton('确认撤销导入').disabled).toBe(true)
    const reason = document.querySelector<HTMLInputElement>('[aria-label="撤销导入原因"]')!
    reason.value = '导错文件'; reason.dispatchEvent(new Event('input', { bubbles: true })); await flushPromises()
    expect(dialogButton('确认撤销导入').disabled).toBe(true)
    const checkbox = document.querySelector<HTMLInputElement>('input[type=checkbox]')!
    checkbox.checked = true; checkbox.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises()
    api.withdraw.mockResolvedValue({}); api.imports.mockResolvedValue([{ ...batch, can_withdraw: false, withdrawal: { actor_name: '仓管', occurred_at: batch.occurred_at, reason: '导错文件' } }])
    dialogButton('确认撤销导入').click(); await flushPromises()
    expect(api.withdraw).toHaveBeenCalledWith('B1', 'w'.repeat(64), '导错文件')
    expect(wrapper!.text()).toContain('已撤销本次导入')
    expect(wrapper!.text()).toContain('导错文件')
    expect(button('撤销导入')).toBeUndefined()
  })
  it('can reach older import batches after the latest twenty are withdrawn', async () => {
    const batch = { source_name: '采购.xlsx', occurred_at: '2026-10-05T10:00:00+08:00', actor_name: '仓管', counts, scope: 'TRACKING', withdrawal: { actor_name: '仓管', occurred_at: '2026-10-05T10:00:00+08:00', reason: '导错文件' } }
    api.imports.mockResolvedValue(Array.from({ length: 20 }, (_, index) => ({ ...batch, id: String(index) })))
    await open(); api.imports.mockResolvedValue([{ ...batch, id: 'old', withdrawal: undefined, can_withdraw: true }])
    await button('较早记录').trigger('click'); await flushPromises()
    expect(api.imports).toHaveBeenLastCalledWith(20)
    expect(button('撤销导入').exists()).toBe(true)
  })
  it('marking changes read uses the displayed revision and never calls receiving or import', async () => {
    api.lines.mockResolvedValue({ total: 1, items: [{ id: 'L1', revision: 3, facts: { order_no: 'CGDD1', status: 'RETURNED', ordered_quantity: '100', reported_received_quantity: '100' }, unreviewed_changes: 1, tracking: { arrival_review: true } }] })
    api.detail.mockResolvedValue({ id: 'L1', revision: 3, facts: {}, evidence: [], can_review: true, unreviewed_changes: 1, tracking: { arrival_review: true } })
    await open('pending'); await button('来源 / 核对').trigger('click'); await flushPromises()
    api.reviewChanges.mockResolvedValue({ reviewed: 1, stock_posted: false })
    dialogButton('将变更标记已读（不确认收料）').click(); await flushPromises()
    expect(api.reviewChanges).toHaveBeenCalledWith('L1', 3)
    expect(wrapper!.text()).toContain('采购报到货待核对事项继续保留')
    expect(api.apply).not.toHaveBeenCalled()
  })
})

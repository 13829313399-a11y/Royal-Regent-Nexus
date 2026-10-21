import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { mount, flushPromises, DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Dialog from '../FabricIssueGroupDialog.vue'
import { pendingGroupCommands } from '../fabricIssueGroupPending'
import type { FabricIssuePlan, WarehouseOperationsWorkspace } from '@/api/warehouseOperations'

const api = vi.hoisted(() => ({ workspace: vi.fn(), saveIssueGroup: vi.fn(), previewIssueGroup: vi.fn(), issueGroup: vi.fn(), recoverIssueGroup: vi.fn() }))
const session = reactive({ currentUser: { id: 'warehouse-1' }, authorizationVersion: 1 })
vi.mock('@/api/warehouseOperations', () => ({ warehouseOperationsApi: api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => session }))
let wrapper: VueWrapper
const group = { group_id: 'FG-1', order_no: 'O1', name: '衣身与捆条', request_ids: ['R1', 'R2'] }
const view = (): WarehouseOperationsWorkspace => ({ revision: 8, stock: [], locations: [], issue_groups: [group], permissions: { read: true, operate: true, quality: false, correct: false }, documents:
  ['R1', 'R2', 'R3'].map((id, i) => ({ id, kind: 'REQUEST', sequence: i + 1, business_date: '2026-10-01', actor_name: '仓管', occurred_at: '', issued_quantity: '0',
    data: { item_code: 'F1', item_name: '白布', unit: '米', process_state: '', material_category: 'FABRIC', quantity: '3', source_no: id, source_line: '1', production_no: 'O1', counterparty: `车间${i}`, purpose: '部件' } })) as WarehouseOperationsWorkspace['documents'] })
const proposal = (): FabricIssuePlan => ({ group, revision: 8, token: 'a'.repeat(64), items: [
  { original_id: 'R1', batch_id: 'B1', quantity: '3' }, { original_id: 'R2', batch_id: 'B1', quantity: '3' }],
  candidates: [{ id: 'B1', item_code: 'F1', item_name: '白布', unit: '米', process_state: '', material_category: 'FABRIC', quantity: '6', lot: '001', roll_no: '01', location: 'A01', received_on: '2026-10-01' }] as FabricIssuePlan['candidates'],
  demands: view().documents.slice(0, 2).map(request => ({ request, remaining: '3', recommended: '3', shortage: '0' })) })
async function open() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: Dialog }] })
  await router.push('/'); await router.isReady()
  wrapper = mount(Dialog, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return new DOMWrapper(document.body)
}
async function generate(body: DOMWrapper<Element>) {
  await body.get('[aria-label="选择配套组"]').setValue('FG-1')
  await body.findAll('button').find(b => b.text() === '生成推荐方案')!.trigger('click'); await flushPromises()
}
async function confirm(body: DOMWrapper<Element>) {
  await body.get('[aria-label="确认配套发料方案"]').setValue(true)
  await body.findAll('button').find(b => b.text() === '确认配套发料')!.trigger('click'); await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks(); pendingGroupCommands.clear(); session.currentUser = { id: 'warehouse-1' }; session.authorizationVersion = 1
  api.workspace.mockResolvedValue(view()); api.previewIssueGroup.mockResolvedValue(proposal()); api.issueGroup.mockResolvedValue({ documents: [] })
})
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = ''; vi.restoreAllMocks() })

describe('fabric coordinated issue workflow', () => {
  it('explicitly associates multiple requests before generating a proposal', async () => {
    api.workspace.mockResolvedValue({ ...view(), issue_groups: [] })
    const body = await open()
    await body.get('[aria-label="配套订单号"]').setValue('O1')
    await body.get('[aria-label="配套组名称"]').setValue('衣身与捆条')
    await body.get('[aria-label="关联领料单 R1"]').setValue(true)
    await body.get('[aria-label="关联领料单 R2"]').setValue(true)
    api.saveIssueGroup.mockResolvedValue(group)
    api.workspace.mockResolvedValue(view())
    await body.get('form').trigger('submit'); await flushPromises()
    expect(api.saveIssueGroup).toHaveBeenCalledWith(expect.objectContaining({ order_no: 'O1', name: '衣身与捆条', request_ids: ['R1', 'R2'], expected_revision: 8 }))
    expect(api.issueGroup).not.toHaveBeenCalled()
    expect(body.text()).toContain('关联已保存')
  })
  it('previews lots, permits adjustments and submits all requests together only after confirmation', async () => {
    const body = await open(); await generate(body)
    expect(body.text()).toContain('001 · 卷 01')
    expect(api.issueGroup).not.toHaveBeenCalled()
    await body.get('[aria-label="配套数量 1"]').setValue('2.5')
    expect(body.text()).toContain('本次 2.5 · 尚缺 0.5 米')
    await confirm(body)
    expect(api.issueGroup).toHaveBeenCalledWith(expect.objectContaining({ token: 'a'.repeat(64), confirmed: true, group_id: 'FG-1', items: [
      { original_id: 'R1', batch_id: 'B1', quantity: '2.5' }, { original_id: 'R2', batch_id: 'B1', quantity: '3' }] }))
    expect(body.text()).toContain('各领料单进度已更新')
  })
  it('rejects over-issue locally and requires a fresh preview when the date changes', async () => {
    const body = await open(); await generate(body)
    await body.get('[aria-label="配套数量 1"]').setValue('4'); await confirm(body)
    expect(api.issueGroup).not.toHaveBeenCalled(); expect(body.text()).toContain('累计不能超过')
    await body.get('[aria-label="配套发料日期"]').setValue('2026-10-15')
    expect(body.find('[aria-label="配套数量 1"]').exists()).toBe(false)
  })
  it('keeps an identical uncertain request for retry and never silently changes it', async () => {
    api.issueGroup.mockRejectedValueOnce(new Error('connection lost'))
    const body = await open(); await generate(body); await confirm(body)
    const original = api.issueGroup.mock.calls[0]![0]
    expect(body.get('[aria-label="配套数量 1"]').element.closest('fieldset')?.disabled).toBe(true)
    await body.findAll('button').find(b => b.text() === '用原内容重试')!.trigger('click'); await flushPromises()
    expect(api.issueGroup.mock.calls[1]![0]).toEqual(original)
    expect(pendingGroupCommands.size).toBe(0)
  })
  it('invalidates stale plans and retains account isolation for uncertain results', async () => {
    api.issueGroup.mockRejectedValueOnce({ response: { status: 409, data: { detail: '记录已变化' } } })
    const body = await open(); await generate(body); await confirm(body)
    expect(body.find('[aria-label="配套数量 1"]').exists()).toBe(false)
    await generate(body)
    api.issueGroup.mockRejectedValueOnce(new Error('offline')); await confirm(body)
    session.currentUser = { id: 'other-user' }; await flushPromises()
    expect(body.text()).not.toContain('原配套发料请求结果待确认')
    expect(pendingGroupCommands.has('warehouse-1')).toBe(true)
    session.currentUser = { id: 'warehouse-1' }; await flushPromises()
    expect(body.text()).toContain('原配套发料请求结果待确认')
  })
  it('discards a late preview after permissions change', async () => {
    let resolve!: (value: FabricIssuePlan) => void
    api.previewIssueGroup.mockImplementation(() => new Promise<FabricIssuePlan>(r => { resolve = r }))
    const body = await open(); await generate(body)
    api.workspace.mockResolvedValue({ ...view(), permissions: { read: true, operate: false, quality: false, correct: false } })
    session.authorizationVersion++; await flushPromises(); resolve(proposal()); await flushPromises()
    expect(body.find('[aria-label="配套数量 1"]').exists()).toBe(false)
  })
  it('resolves a never-executed uncertain request before allowing a fresh proposal', async () => {
    api.issueGroup.mockRejectedValueOnce(new Error('offline'))
    api.recoverIssueGroup.mockResolvedValue({ state: 'abandoned' })
    const body = await open(); await generate(body); await confirm(body)
    const original = api.issueGroup.mock.calls[0]![0]
    await body.findAll('button').find(b => b.text() === '核对结果／停止未执行请求')!.trigger('click'); await flushPromises()
    expect(api.recoverIssueGroup).toHaveBeenCalledWith({ kind: 'issue', body: original })
    expect(body.text()).toContain('原未执行请求已停止')
    expect(pendingGroupCommands.size).toBe(0)
    expect(body.find('[aria-label="配套数量 1"]').exists()).toBe(false)
  })
})

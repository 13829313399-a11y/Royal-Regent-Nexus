import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonSupplierChangeTasks.vue'
import type { SupplierChangeTask } from '@/api/cartonSupplierChanges'

const api = vi.hoisted(() => ({ list: vi.fn(), respond: vi.fn() }))
vi.mock('@/api/cartonSupplierChanges', () => ({ cartonSupplierChangesApi: api }))
const task = (patch: Partial<SupplierChangeTask> = {}): SupplierChangeTask => ({
  source_kind: 'SPECIAL', source_id: 'VERSION', factory_id: 'huaxing', order_id: 'REQ', order_no: 'SP-1', document_no: 'SP-1',
  expected_revision: 3, status: 'PENDING', is_cancellation: false, read: false, read_at: '', reason: '', responded_by: '', responded_at: '',
  promised_date: '', planned_date: '2026-10-25', before_date: '2026-10-24', created_at: '2026-10-20', age_days: 1, overdue: true,
  action: 'ADJUSTED', responsibility: '', lines: [{ id: 'PAPER', packaging_type: '普通箱', paper_quality: 'A=B', specification: '1*2*3', unit: '个', before_quantity: '10', quantity: '12' }],
  material_changed: false, pending: true, can_respond: true, ...patch,
})
const workspace = (row = task()) => ({ items: [row], pending_count: row.pending ? 1 : 0, overdue_count: row.overdue ? 1 : 0, disputed_count: 0 })
const wrappers: ReturnType<typeof mount>[] = []
function setup(props: Record<string, unknown> = {}) { const wrapper = mount(Component, { props: { factoryId: 'huaxing', viewerKey: 'USER-1', ...props } }); wrappers.push(wrapper); return wrapper }
async function click(wrapper: ReturnType<typeof mount>, text: string) { const button = wrapper.findAll('button').find(row => row.text() === text); expect(button).toBeDefined(); await button!.trigger('click'); await flushPromises() }
beforeEach(() => { vi.clearAllMocks(); api.list.mockResolvedValue(workspace()); api.respond.mockResolvedValue(task()) })
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('durable supplier change tasks', () => {
  it('submits a durable request on HTTP origins without crypto.randomUUID', async () => {
    vi.stubGlobal('crypto', { getRandomValues: (bytes: Uint8Array) => { bytes.fill(7); return bytes } })
    const wrapper = setup(); await flushPromises(); await click(wrapper, '记录已读（不代表同意）')
    expect(api.respond.mock.calls[0]![0].request_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })
  it('accepts a lifted closed-history query without changing the supplier default', async () => {
    api.list.mockResolvedValue(workspace(task({ pending: false, status: 'ACCEPTED' })))
    const wrapper = setup({ internal: true, showClosed: true }); await flushPromises()
    expect(wrapper.text()).toContain('SP-1')
    await wrapper.get('[aria-label="显示已完成回执"]').setValue(false)
    expect(wrapper.emitted('update:showClosed')).toEqual([[false]])
    await wrapper.setProps({ showClosed: false }); expect(wrapper.text()).not.toContain('SP-1')
    const supplier = setup(); await flushPromises()
    expect(supplier.get<HTMLInputElement>('[aria-label="显示已完成回执"]').element.checked).toBe(false)
    await supplier.get('[aria-label="显示已完成回执"]').setValue(true)
    expect(supplier.text()).toContain('SP-1')
  })
  it('records reading without clearing the agreement task or submitting a promise', async () => {
    const wrapper = setup(); await flushPromises()
    api.list.mockResolvedValue(workspace(task({ read: true, read_at: '2026-10-20T09:00' })))
    await click(wrapper, '记录已读（不代表同意）')
    expect(api.respond.mock.calls[0]![0]).toMatchObject({ action: 'READ', source_kind: 'SPECIAL', source_id: 'VERSION', expected_revision: 3 })
    expect(api.respond.mock.calls[0]![0]).not.toHaveProperty('promised_date')
    expect(wrapper.text()).toContain('已读，回执单独记录'); expect(wrapper.text()).toContain('同意本版本全部纸品并接单')
    expect(wrapper.text()).toContain('数量 10 → 12 个')
  })
  it('preserves unsent date and dispute text through a routine refresh and retries the same request id', async () => {
    const wrapper = setup(); await flushPromises()
    await wrapper.get('[aria-label="SP-1承诺交期"]').setValue('2026-10-28')
    await wrapper.get('[aria-label="SP-1异议说明"]').setValue('生产已开始，请协商减量')
    await click(wrapper, '刷新待办')
    expect((wrapper.get('[aria-label="SP-1承诺交期"]').element as HTMLInputElement).value).toBe('2026-10-28')
    expect((wrapper.get('[aria-label="SP-1异议说明"]').element as HTMLTextAreaElement).value).toContain('生产已开始')
    api.respond.mockRejectedValueOnce(new Error('网络尚未确认')).mockResolvedValueOnce(task())
    await click(wrapper, '提出异议并暂停执行'); await click(wrapper, '提出异议并暂停执行')
    expect(api.respond.mock.calls[0]![0].request_id).toBe(api.respond.mock.calls[1]![0].request_id)
    expect(api.respond.mock.calls[0]![0]).toMatchObject({ action: 'DISPUTE', reason: '生产已开始，请协商减量' })
  })
  it('keeps cancellation acknowledgement distinct from accepting goods and costs', async () => {
    api.list.mockResolvedValue(workspace(task({ is_cancellation: true })))
    const wrapper = setup(); await flushPromises()
    expect(wrapper.find('[aria-label="SP-1承诺交期"]').exists()).toBe(false)
    await click(wrapper, '确认收到停止通知')
    expect(api.respond.mock.calls[0]![0].action).toBe('ACK_CANCEL')
    expect(wrapper.text()).toContain('费用及赔偿仍须另行协商')
  })
  it('does not expose supplier decisions in the internal follow-up view', async () => {
    const wrapper = setup({ internal: true }); await flushPromises()
    expect(api.list).toHaveBeenCalledWith('huaxing', true, expect.any(AbortSignal))
    expect(wrapper.text()).toContain('供应商待确认跟进'); expect(wrapper.text()).toContain('SP-1')
    expect(wrapper.text()).not.toContain('同意本版本全部纸品并接单')
    expect(wrapper.text()).not.toContain('记录已读（不代表同意）')
  })
  it('keeps supplier detail evidence read-only without changing the supplier read scope', async () => {
    const wrapper = setup({ readOnly: true }); await flushPromises()
    expect(api.list).toHaveBeenCalledWith('huaxing', false, expect.any(AbortSignal))
    expect(wrapper.text()).toContain('SP-1')
    expect(wrapper.text()).toContain('本页只读')
    expect(wrapper.text()).not.toContain('同意本版本全部纸品并接单')
    expect(wrapper.text()).not.toContain('确认收到停止通知')
    expect(wrapper.find('textarea').exists()).toBe(false)
  })
  it('clears old scope data and discards a late response after factory and identity change', async () => {
    let resolve!: (value: ReturnType<typeof workspace>) => void
    api.list.mockReturnValueOnce(new Promise(r => { resolve = r })).mockResolvedValueOnce({ items: [], pending_count: 0, overdue_count: 0, disputed_count: 0 })
    const wrapper = setup(); await flushPromises()
    await wrapper.setProps({ factoryId: 'huakang-b', viewerKey: 'USER-2' }); await flushPromises()
    resolve(workspace()); await flushPromises()
    expect(wrapper.text()).not.toContain('SP-1'); expect(api.respond).not.toHaveBeenCalled()
  })
  it('does not let an older read in the same scope restore a pending task after a newer acknowledgement', async () => {
    let resolveOld!: (value: ReturnType<typeof workspace>) => void, resolveNew!: (value: ReturnType<typeof workspace>) => void
    api.list.mockReturnValueOnce(new Promise(r => { resolveOld = r })).mockReturnValueOnce(new Promise(r => { resolveNew = r }))
    const wrapper = setup(); await flushPromises()
    const refreshed = (wrapper.vm as unknown as { refresh: () => Promise<void> }).refresh()
    resolveNew(workspace(task({ status: 'ACCEPTED', pending: false, overdue: false }))); await refreshed; await flushPromises()
    resolveOld(workspace()); await flushPromises()
    expect(wrapper.text()).toContain('当前没有待明确确认的版本')
    expect(wrapper.text()).not.toContain('同意本版本全部纸品并接单')
  })
  it('shows superseded publications as readonly evidence without implying they were agreed', async () => {
    const base = { created_at: '2026-10-20', action: 'APPEND', status: 'PENDING', read: false, responded_by: '', responded_at: '', reason: '', planned_date: '2026-10-25', lines: task().lines }
    api.list.mockResolvedValue(workspace(task({ publication_history: [
      { ...base, source_id: 'PREVIOUS', document_no: 'SP-1 / 版本 2', superseded: true },
      { ...base, source_id: 'VERSION', document_no: 'SP-1 / 版本 3', superseded: false },
    ] })))
    const wrapper = setup(); await flushPromises()
    expect(wrapper.text()).toContain('上次发布不代表供应商已经同意')
    expect(wrapper.text()).toContain('已被后续版本替代，只读')
    expect(wrapper.text()).toContain('未记录明确同意')
    expect(wrapper.findAll('button').filter(row => row.text() === '同意本版本全部纸品并接单')).toHaveLength(1)
  })
  it('filters categories without reloading or losing drafts and reports pending counts for every kind', async () => {
    api.list.mockResolvedValue({ items: [task(), task({ source_kind: 'REGULAR', source_id: 'R1', document_no: 'REG-1' }), task({ source_kind: 'REPLENISHMENT', source_id: 'B1', document_no: 'REG-B01' })] })
    const wrapper = setup({ embedded: true, sourceKinds: ['REGULAR', 'SPECIAL'] }); await flushPromises()
    const originalCalls = api.list.mock.calls.length
    await wrapper.get('[aria-label="SP-1承诺交期"]').setValue('2026-10-29')
    await wrapper.get('[aria-label="SP-1异议说明"]').setValue('请核对纸质要求')
    expect(wrapper.text()).not.toContain('REG-B01')
    expect(wrapper.emitted('pending-state')!.at(-1)![0]).toEqual({ loading: false, error: '', counts: { REGULAR: 1, SPECIAL: 1, REPLENISHMENT: 1 } })
    await wrapper.setProps({ sourceKinds: ['REPLENISHMENT'] })
    expect(wrapper.text()).toContain('REG-B01'); expect(wrapper.find('[aria-label="SP-1异议说明"]').exists()).toBe(false)
    await wrapper.get('[aria-label="REG-B01异议说明"]').setValue('补单规格需重新核对')
    await click(wrapper, '提出异议并暂停执行')
    expect(api.respond.mock.calls[0]![0]).toMatchObject({ source_kind: 'REPLENISHMENT', source_id: 'B1', expected_revision: 3, action: 'DISPUTE', reason: '补单规格需重新核对' })
    await wrapper.setProps({ sourceKinds: ['REGULAR', 'SPECIAL'] })
    expect((wrapper.get('[aria-label="SP-1承诺交期"]').element as HTMLInputElement).value).toBe('2026-10-29')
    expect((wrapper.get('[aria-label="SP-1异议说明"]').element as HTMLTextAreaElement).value).toBe('请核对纸质要求')
    expect(api.list).toHaveBeenCalledTimes(originalCalls + 1)
    await wrapper.setProps({ viewerKey: 'USER-2' }); await flushPromises()
    expect((wrapper.get('[aria-label="SP-1异议说明"]').element as HTMLTextAreaElement).value).toBe('')
  })
  it('reports reading and failed reads distinctly from an empty pending queue', async () => {
    let reject!: (error: Error) => void
    api.list.mockReturnValueOnce(new Promise((_done, fail) => { reject = fail }))
    const wrapper = setup({ embedded: true }); await flushPromises()
    expect(wrapper.text()).toContain('读取中…')
    expect(wrapper.emitted('pending-state')!.at(-1)![0]).toMatchObject({ loading: true, error: '' })
    reject(new Error('无权读取该厂区')); await flushPromises()
    expect(wrapper.text()).toContain('暂不可用')
    expect(wrapper.text()).not.toContain('0 项待确认')
    expect(wrapper.text()).not.toContain('当前没有待明确确认的版本')
    expect(wrapper.emitted('pending-state')!.at(-1)![0]).toMatchObject({ loading: false, error: '无权读取该厂区' })
  })
  it('keeps replacement stop acknowledgements and read-only history in their selected category', async () => {
    api.list.mockResolvedValue({ items: [task({ source_kind: 'REPLENISHMENT', is_cancellation: true }), task({ source_kind: 'REGULAR', document_no: 'OTHER' })] })
    const wrapper = setup({ sourceKinds: ['REPLENISHMENT'], embedded: true }); await flushPromises()
    expect(wrapper.text()).not.toContain('OTHER')
    await click(wrapper, '确认收到停止通知')
    expect(api.respond.mock.calls[0]![0]).toMatchObject({ source_kind: 'REPLENISHMENT', action: 'ACK_CANCEL' })
    api.list.mockResolvedValue(workspace(task({ source_kind: 'REPLENISHMENT', pending: false, status: 'ACCEPTED', can_respond: false })))
    await click(wrapper, '刷新待办')
    await wrapper.get('[aria-label="显示已完成回执"]').setValue(true)
    expect(wrapper.text()).toContain('SP-1')
    expect(wrapper.text()).toContain('已同意接单')
    expect(wrapper.text()).not.toContain('同意本版本全部纸品并接单')
  })
})

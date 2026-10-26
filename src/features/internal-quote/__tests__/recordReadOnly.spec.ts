import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { internalQuoteApi, type ApiInternalQuote } from '@/api/internalQuote'
import { assistantSelection } from '@/features/assistant/selection'
import QuoteRecordReadOnly from '../QuoteRecordReadOnly.vue'

vi.mock('@/api/internalQuote', () => ({ internalQuoteApi: { get: vi.fn(), getSummary: vi.fn(), getReferenceSnapshot: vi.fn() } }))
function record(overrides: Partial<ApiInternalQuote> = {}) {
  return { id: 'q1', factory_id: 'huaxing', quote_no: 'SYN-QUOTE-01', product_name: '合成长名称报价', customer: '合成客户', qty: 123,
    version_label: 'A-V2', module_version: 'v4', formula_version: 'rr2-test', status: 'drafting', updated_at: '2026-10-23T08:30:00+08:00',
    header_revision: 7, sections: [{ payload: { private_cost: '99999999.88' } }], readiness: { state: 'incomplete', required_sections: 3, ready_sections: 1, blockers: [] },
    ...overrides } as ApiInternalQuote
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { promise, resolve } }
const wrappers: Array<ReturnType<typeof mount>> = []
function render() {
  const wrapper = mount(QuoteRecordReadOnly, { props: { quoteId: 'q1', factoryId: 'huaxing' }, attachTo: document.body,
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
  wrappers.push(wrapper); return wrapper
}
beforeEach(() => { vi.resetAllMocks(); vi.mocked(internalQuoteApi.get).mockResolvedValue(record()) })
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()) })

describe('native operational-only quotation source', () => {
  it('reads the actual quote header and readiness without requesting or displaying financial detail', async () => {
    const wrapper = render()
    expect(wrapper.text()).toContain('正在读取原报价')
    expect(assistantSelection('internal-quote')?.filters.scope_error).toBeTruthy()
    await flushPromises()
    expect(internalQuoteApi.get).toHaveBeenCalledWith('q1')
    expect(internalQuoteApi.getSummary).not.toHaveBeenCalled()
    expect(internalQuoteApi.getReferenceSnapshot).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('SYN-QUOTE-01 · A-V2')
    expect(wrapper.text()).toContain('直接输出 · 待补齐 / 待重算')
    expect(wrapper.text()).toContain('123（源记录未明确件/套单位）')
    expect(wrapper.text()).not.toContain('99999999.88')
    expect(assistantSelection('internal-quote')?.resources.map(r => r.resource_id)).toEqual(['q1'])
    wrapper.unmount(); wrappers.pop()
    expect(assistantSelection('internal-quote')).toBeNull()
  })

  it.each([{ id: 'wrong' }, { factory_id: 'huakang-b' }])('rejects a different native record or factory %j', async overrides => {
    vi.mocked(internalQuoteApi.get).mockResolvedValue(record(overrides))
    const wrapper = render(); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('不属于当前厂区')
    expect(wrapper.text()).not.toContain('合成长名称报价')
    expect(assistantSelection('internal-quote')?.resources).toEqual([])
  })

  it('clears failed records and supports an actual retry with heading focus', async () => {
    vi.mocked(internalQuoteApi.get).mockRejectedValueOnce(new Error('原报价不存在或已撤销权限'))
    const wrapper = render(); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('原报价不存在')
    expect(assistantSelection('internal-quote')?.filters.scope_error).toBeTruthy()
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(internalQuoteApi.get).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.get('h1').element)
    expect(assistantSelection('internal-quote')?.resources).toHaveLength(1)
  })

  it('ignores a late response from an old factory and from a disposed page', async () => {
    const old = deferred<ApiInternalQuote>(), disposed = deferred<ApiInternalQuote>()
    vi.mocked(internalQuoteApi.get).mockReturnValueOnce(old.promise).mockResolvedValueOnce(record({ id: 'q2', factory_id: 'huakang-b', product_name: '当前厂区报价' })).mockReturnValueOnce(disposed.promise)
    const wrapper = render()
    await wrapper.setProps({ quoteId: 'q2', factoryId: 'huakang-b' }); await flushPromises()
    old.resolve(record()); await flushPromises()
    expect(wrapper.text()).toContain('当前厂区报价')
    expect(wrapper.text()).not.toContain('合成长名称报价')
    expect(assistantSelection('internal-quote')?.filters.factory_id).toBe('huakang-b')
    await wrapper.get('button').trigger('click')
    wrapper.unmount(); wrappers.pop()
    disposed.resolve(record({ id: 'q2', factory_id: 'huakang-b' })); await flushPromises()
    expect(assistantSelection('internal-quote')).toBeNull()
  })
})

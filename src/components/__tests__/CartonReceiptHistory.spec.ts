import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CartonReceiptHistory from '../CartonReceiptHistory.vue'
const api = vi.hoisted(() => ({ receiptHistory: vi.fn(), receiptDetail: vi.fn() }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'operator' }, authorizationVersion: 1 }) }))
const row = { id: 'R1', receipt_no: 'CR1', delivery_note_no: 'DN1', delivery_date: '2026-10-16', acceptance_date: '2026-10-16', status: 'POSTED', line_count: 2, customers: '客户', contracts: '合同', operator: '仓管' }
function view() { return mount(CartonReceiptHistory, { props: { factoryId: 'huaxing', responsibilityScope: 'OWN', customers: [], search: '', customer: '全部客户', refreshKey: 1, canCorrect: true } }) }
describe('receipt history summaries', () => {
  beforeEach(() => { vi.resetAllMocks(); api.receiptHistory.mockResolvedValue({ items: [row], total: 26 }) })
  it('loads a bounded summary page, fetching full evidence only after an explicit action', async () => {
    const wrapper = view(); await flushPromises()
    expect(api.receiptHistory).toHaveBeenCalledWith('huaxing', expect.objectContaining({ limit: 25, offset: 0, responsibility_scope: 'OWN' }))
    expect(api.receiptDetail).not.toHaveBeenCalled()
    api.receiptDetail.mockResolvedValue({ id: 'R1', lines: [{ id: 'paper' }] })
    await wrapper.get('[aria-label="查看收料单 CR1"]').trigger('click'); await flushPromises()
    expect(wrapper.emitted('detail')?.[0]?.[0]).toEqual({ id: 'R1', lines: [{ id: 'paper' }] })
    await wrapper.findAll('button').find(button => button.text() === '下一页')!.trigger('click'); await flushPromises()
    expect(api.receiptHistory).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ offset: 25 }))
    wrapper.unmount()
  })
  it('keeps the summary visible if one detail fails and allows retry', async () => {
    const wrapper = view(); await flushPromises()
    api.receiptDetail.mockRejectedValueOnce(new Error('读取超时')).mockResolvedValueOnce({ id: 'R1', lines: [] })
    await wrapper.get('[aria-label="查看收料单 CR1"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('DN1'); expect(wrapper.get('[role="alert"]').text()).toContain('读取超时')
    await wrapper.get('[aria-label="查看收料单 CR1"]').trigger('click'); await flushPromises()
    expect(wrapper.emitted('detail')).toHaveLength(1)
    wrapper.unmount()
  })
  it('discards a late detail after the factory changes', async () => {
    let resolve!: (data: unknown) => void
    api.receiptDetail.mockImplementation(() => new Promise(done => { resolve = done }))
    const wrapper = view(); await flushPromises()
    await wrapper.get('[aria-label="查看收料单 CR1"]').trigger('click')
    await wrapper.setProps({ factoryId: 'huakang-a' }); await flushPromises()
    resolve({ id: 'old-private', lines: [] }); await flushPromises()
    expect(wrapper.emitted('detail')).toBeUndefined()
    expect(api.receiptHistory).toHaveBeenLastCalledWith('huakang-a', expect.anything())
    wrapper.unmount()
  })
})

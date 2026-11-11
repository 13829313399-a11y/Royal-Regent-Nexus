import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LocalInbox from './LocalInbox.vue'
const mock = vi.hoisted(() => ({ list: vi.fn(), receive: vi.fn() }))
vi.mock('./api', () => ({ inboxApi: mock, errorMessage: async (error: Error) => error.message }))
enableAutoUnmount(afterEach)
const item = { id: 'dispatch-1', line_id: 'line-1', factory_id: 'huaxing', recipient: 'pmc', version: 1, latest_version: 2, snapshot: { po_no: '00001', product_no: '00123', quantity: '0100' }, status: 'sent', created_at: '2026-11-09' }
beforeEach(() => { vi.resetAllMocks(); mock.list.mockResolvedValue({ items: [item], total: 1 }) })
describe('local department receipt', () => {
  it('keeps a failed receipt pending and preserves the version notice', async () => {
    mock.receive.mockRejectedValue(new Error('签收未完成'))
    const wrapper = mount(LocalInbox, { props: { factoryId: 'huaxing' } })
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '签收该版本')!.trigger('click')
    await flushPromises()
    expect(mock.receive).toHaveBeenCalledWith('huaxing', 'pmc', 'dispatch-1')
    expect(wrapper.text()).toContain('签收未完成')
    expect(wrapper.text()).toContain('此记录为历史版本')
    expect(wrapper.text()).not.toContain('已在本机签收')
    expect(wrapper.text()).toContain('待签收')
  })
  it('rejects mixed factory rows instead of showing them', async () => {
    mock.list.mockResolvedValue({ items: [{ ...item, factory_id: 'huadeng' }], total: 1 })
    const wrapper = mount(LocalInbox, { props: { factoryId: 'huaxing' } })
    await flushPromises()
    expect(wrapper.text()).toContain('收件记录与当前厂区或部门不一致')
    expect(wrapper.find('.inbox-card').exists()).toBe(false)
  })
})

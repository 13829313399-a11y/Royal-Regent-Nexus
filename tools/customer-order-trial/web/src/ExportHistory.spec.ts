import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ExportHistory from './ExportHistory.vue'
const mock = vi.hoisted(() => ({ history: vi.fn(), download: vi.fn() }))
vi.mock('./api', () => ({ api: mock, errorMessage: async (error: Error) => error.message }))
enableAutoUnmount(afterEach)
beforeEach(() => { vi.resetAllMocks() })
describe('persisted export history', () => {
  it('uses the server twenty-record page boundary and offers later records', async () => {
    mock.history.mockResolvedValue({ items: [], total: 21 })
    const wrapper = mount(ExportHistory)
    await flushPromises()
    expect(wrapper.text()).toContain('第 1 / 2 页')
    await wrapper.findAll('button').find(button => button.text() === '下一页')!.trigger('click')
    await flushPromises()
    expect(mock.history).toHaveBeenLastCalledWith(2)
  })
  it('distinguishes unreadable history from an empty successful response', async () => {
    mock.history.mockRejectedValue(new Error('本机服务未连接'))
    const wrapper = mount(ExportHistory)
    await flushPromises()
    expect(wrapper.text()).toContain('本机服务未连接')
    expect(wrapper.text()).not.toContain('暂无生成记录')
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import CuttingPurchaseProgress from '../CuttingPurchaseProgress.vue'
import { ordersApi, type PurchaseProgress } from '../ordersApi'

vi.mock('../ordersApi', () => ({ ordersApi: { purchaseProgress: vi.fn() } }))

const result: PurchaseProgress = {
  read_at: '2026-11-18T05:00:01+00:00',
  sources: [{ row: 0, id: 'p1', order_no: 'PO-1', detail_no: 'DETAIL-1', unit: '米',
    linked_revision: 1, current_revision: 1, status: 'active', received_quantity: '2', outstanding_quantity: '3' }],
  cutting: [{ row: 0, unit: '米', signed_quantity: '5', returned_quantity: '0.8' }],
}
let wrapper: VueWrapper
afterEach(() => { wrapper?.unmount(); vi.resetAllMocks() })
async function open() {
  wrapper = mount(CuttingPurchaseProgress, { props: { orderId: 'line-1' }, global: { plugins: [createPinia()] } })
  await wrapper.get('button').trigger('click')
  await flushPromises()
}

describe('cutting purchase progress', () => {
  it('keeps the same result and timestamp on failure and retries the original order', async () => {
    vi.mocked(ordersApi.purchaseProgress).mockResolvedValueOnce(result).mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ ...result, read_at: '2026-11-18T05:15:03+00:00' })
    await open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('仍显示上次结果')
    expect(wrapper.text()).toContain('布料仓实收 2 米')
    expect(wrapper.get('time').attributes('datetime')).toBe(result.read_at)
    expect(wrapper.get('button').text()).toBe('按原订单重试进度')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(vi.mocked(ordersApi.purchaseProgress).mock.calls).toEqual([['line-1'], ['line-1'], ['line-1']])
    expect(wrapper.get('time').text()).toContain('13:15:03')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('clears a denied result and never accepts a late response after switching orders', async () => {
    vi.mocked(ordersApi.purchaseProgress).mockResolvedValueOnce(result)
      .mockRejectedValueOnce({ response: { status: 403, data: { detail: '无读取权限' } } })
    await open()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('time').exists()).toBe(false)
    let respond!: (result: PurchaseProgress) => void
    vi.mocked(ordersApi.purchaseProgress).mockImplementationOnce(() => new Promise(resolve => { respond = resolve }))
    await wrapper.get('button').trigger('click')
    await wrapper.setProps({ orderId: 'line-2' })
    respond(result)
    await flushPromises()
    expect(wrapper.find('time').exists()).toBe(false)
    expect(wrapper.get('button').text()).toBe('查看到货与签收进度')
  })
})

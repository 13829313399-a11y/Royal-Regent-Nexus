import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CartonBusinessChangeDialog from '../CartonBusinessChangeDialog.vue'

const api = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/lib/http', () => ({ http: api, getApiErrorMessage: (error: Error) => error.message }))
const state = { order_no: 'PO-001', revision: 1, status: 'PENDING_SUPPLIER', product_order_quantity: '100',
  customer_due_date: '2026-12-10', due_date: '2026-12-03', plan_date_manual: true,
  lines: [{ id: 'paper-1', packaging_type: '外箱', specification: '10 × 20 × 30 cm', required_quantity: '10', unit: '个' }] }
const preview = { version: 2, customer_name: '测试客户', contract_no: 'SC-001', item_no: 'ITEM-1',
  source_before: { quantity: '100', requested_ship_date: '2026-12-10', status: 'active' },
  source_after: { quantity: '120', requested_ship_date: '2026-12-12', status: 'active' }, reason: '追加数量',
  before: state, after: { ...state, revision: 2, product_order_quantity: '120', lines: [{ ...state.lines[0], required_quantity: '12' }] },
  can_confirm: true, blocked_reason: '', fingerprint: 'a'.repeat(64), processed: null }
const wrappers: ReturnType<typeof mount>[] = []
function open() {
  const wrapper = mount(CartonBusinessChangeDialog, { props: { factoryId: 'huaxing', recipient: 'warehouse', dispatchId: 'notice-1' },
    global: { stubs: { DialogPortal: { template: '<div><slot /></div>' } } }, attachTo: document.body })
  wrappers.push(wrapper)
  return wrapper
}
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(b => b.text() === text)!
beforeEach(() => { api.post.mockReset(); api.post.mockResolvedValue({ data: structuredClone(preview) }) })
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); document.body.innerHTML = '' })

describe('CartonBusinessChangeDialog', () => {
  it('only previews on open and performs the second confirmation with the shown fingerprint', async () => {
    const wrapper = open()
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post.mock.calls[0]?.[0]).toContain('/carton-change-preview')
    expect(wrapper.text()).toContain('100 → 120')
    expect(wrapper.text()).toContain('保留手工计划日期')
    api.post.mockResolvedValueOnce({ data: { ...preview, can_confirm: false, processed: { processed_by: '仓管甲', processed_at: '2026-11-02' } } })
    await button(wrapper, '确认收到并改单').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenLastCalledWith('/customer-order-ledger/inbox/notice-1/carton-change-confirm',
      { confirmed: true, fingerprint: preview.fingerprint }, { params: { factory_id: 'huaxing', recipient: 'warehouse' } })
    expect(wrapper.emitted('applied')).toHaveLength(1)
    expect(wrapper.text()).toContain('已处理改单 · 仓管甲')
  })
  it('does not receive or amend when the user closes the preview', async () => {
    const wrapper = open(); await flushPromises()
    await button(wrapper, '暂不处理').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(api.post).toHaveBeenCalledTimes(1)
  })
  it('explains a blocked multi-order match and prevents confirmation', async () => {
    api.post.mockResolvedValueOnce({ data: { ...preview, can_confirm: false, after: null, fingerprint: '', blocked_reason: '对应多张采购单，需逐单核对分配数量' } })
    const wrapper = open(); await flushPromises()
    expect(wrapper.text()).toContain('对应多张采购单')
    expect(button(wrapper, '确认收到并改单').attributes('disabled')).toBeDefined()
    expect(api.post).toHaveBeenCalledTimes(1)
  })
  it('does not reuse a stale preview after a failed confirmation', async () => {
    const wrapper = open(); await flushPromises()
    api.post.mockRejectedValueOnce(new Error('业务或采购单已变化'))
    await button(wrapper, '确认收到并改单').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('业务或采购单已变化')
    expect(wrapper.emitted('applied')).toBeUndefined()
    expect(button(wrapper, '确认收到并改单').attributes('disabled')).toBeDefined()
    await button(wrapper, '重新核对').trigger('click'); await flushPromises()
    expect(api.post.mock.calls.at(-1)?.[0]).toContain('/carton-change-preview')
    expect(button(wrapper, '确认收到并改单').attributes('disabled')).toBeUndefined()
  })
  it('ignores a late preview response after the factory dialog is unmounted', async () => {
    let resolve!: (value: unknown) => void
    api.post.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    const wrapper = open(); wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    resolve({ data: preview }); await flushPromises()
    expect(wrapper.emitted('applied')).toBeUndefined()
    expect(api.post).toHaveBeenCalledTimes(1)
  })
})

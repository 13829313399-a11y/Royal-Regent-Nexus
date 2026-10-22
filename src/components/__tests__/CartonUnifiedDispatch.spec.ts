import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonUnifiedDispatch.vue'
import type { PortalOrder } from '@/api/cartonSupplierPortal'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'
const post = vi.hoisted(() => vi.fn())
vi.mock('@/lib/http', () => ({ http: { post }, getApiErrorMessage: (error: Error) => error.message }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: () => true }) }))
const order = { factory_id: 'huaxing', id: 'PO', order_no: 'PO1', issue_id: 'ISSUE', customer_name: '客户', item_no: 'ITEM', status: 'PENDING_SUPPLIER', awaiting_issue: false,
  lines: [{ id: 'PL', packaging_type: '外箱', paper_quality: 'A33', specification: '10×20×30', remaining_to_ship: '10', accepted: true, unit: '个' }] } as PortalOrder & { factory_id: string }
const special = { factory_id: 'huaxing', id: 'SP', request_no: 'SP1', kind: 'SAMPLE', status: 'SENT', revision: 2, current_version_id: 'VERSION', permissions: { can_ship: true },
  lines: [{ id: 'SL', packaging_type: '样板箱', paper_quality: 'A33', specification: '10×20×30', quantity: '3', remaining_to_ship: '3', unit: '个', mark_mode: 'NONE', mark_ready: true }] } as SpecialRequest
const setup = (requests = [special]) => mount(Component, { props: { factories: [{ factory_id: 'huaxing', supplier_name: '供应商' }], orders: [order], requests, viewerKey: 'u1' } })
async function base(wrapper: ReturnType<typeof setup>) { await wrapper.get('[aria-label="统一送货单号"]').setValue('DN1'); await wrapper.get('[aria-label="统一送货日期"]').setValue('2026-10-20') }
async function submit(wrapper: ReturnType<typeof setup>) { await wrapper.findAll('button').find(button => button.text() === '确认本单发货')!.trigger('click'); await flushPromises() }
beforeEach(() => { post.mockReset(); post.mockResolvedValue({ data: {} }) })
describe('one supplier note for all carton purposes', () => {
  it('requires a real price and explicit free evidence, then atomically submits regular and sample lines', async () => {
    const wrapper = setup(); await base(wrapper)
    const cards = wrapper.findAll('article')
    for (const card of cards) await card.get('input[type="checkbox"]').setValue(true)
    await submit(wrapper); expect(post).not.toHaveBeenCalled()
    await cards[0]!.findAll('input[type="number"]')[1]!.setValue('2.5')
    await cards[1]!.findAll('input[type="number"]')[1]!.setValue('0')
    await submit(wrapper); expect(post).not.toHaveBeenCalled()
    await cards[1]!.findAll('input[type="checkbox"]')[1]!.setValue(true)
    await submit(wrapper)
    expect(post).toHaveBeenCalledWith('/carton-supplier/unified-deliveries', expect.objectContaining({ delivery_note_no: 'DN1', formal_lines: [{ order_line_id: 'PL', issue_id: 'ISSUE', quantity: '10', unit_price: '2.5', free_confirmed: false }], special_requests: [{ id: 'SP', expected_revision: 2, version_id: 'VERSION', lines: [{ line_id: 'SL', quantity: '3', unit_price: '0', free_confirmed: true }] }] }))
    expect(wrapper.emitted('saved')).toHaveLength(1); wrapper.unmount()
  })
  it('allows samples without mark declarations and does not let search discard selected lines', async () => {
    const wrapper = setup([{ ...special, lines: special.lines.map(line => ({ ...line, mark_mode: 'PENDING', mark_ready: false })) }]); await base(wrapper)
    expect(wrapper.findAll('article')[1]!.get('input[type="checkbox"]').attributes('disabled')).toBeUndefined()
    await wrapper.findAll('article')[1]!.get('input[type="checkbox"]').setValue(true)
    await wrapper.findAll('article')[1]!.findAll('input[type="number"]')[1]!.setValue('2')
    await wrapper.findAll('article')[0]!.get('input[type="checkbox"]').setValue(true)
    await wrapper.findAll('article')[0]!.findAll('input[type="number"]')[1]!.setValue('1')
    await wrapper.get('[aria-label="选择送货纸品"]').setValue('不存在')
    await submit(wrapper); expect(post.mock.calls[0]![1].formal_lines).toHaveLength(1); expect(post.mock.calls[0]![1].special_requests).toHaveLength(1); wrapper.unmount()
  })
  it('reuses an unchanged request key after an unknown outcome, but discards drafts on access context change', async () => {
    const wrapper = setup(); await base(wrapper)
    await wrapper.findAll('article')[0]!.get('input[type="checkbox"]').setValue(true)
    await wrapper.findAll('article')[0]!.findAll('input[type="number"]')[1]!.setValue('1')
    post.mockRejectedValue(new Error('暂未收到响应'))
    await submit(wrapper); await submit(wrapper)
    expect(post.mock.calls[0]![1].request_id).toBe(post.mock.calls[1]![1].request_id)
    await wrapper.setProps({ viewerKey: 'u2' }); await submit(wrapper)
    expect(post).toHaveBeenCalledTimes(2); expect((wrapper.get('[aria-label="统一送货单号"]').element as HTMLInputElement).value).toBe(''); wrapper.unmount()
  })
  it('clears old quantities and selections when factories are replaced', async () => {
    const wrapper = setup(); await base(wrapper)
    await wrapper.findAll('article')[0]!.get('input[type="checkbox"]').setValue(true)
    await wrapper.findAll('article')[0]!.findAll('input[type="number"]')[0]!.setValue('7')
    await wrapper.setProps({ factories: [{ factory_id: 'huakang_a', supplier_name: '另一厂区' }] })
    expect(wrapper.get<HTMLSelectElement>('[aria-label="送货单厂区"]').element.value).toBe('huakang_a')
    expect(wrapper.get<HTMLInputElement>('[aria-label="统一送货单号"]').element.value).toBe('')
    await wrapper.setProps({ factories: [{ factory_id: 'huaxing', supplier_name: '供应商' }] })
    await wrapper.findAll('article')[0]!.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.findAll('article')[0]!.findAll<HTMLInputElement>('input[type="number"]')[0]!.element.value).toBe('10')
    wrapper.unmount()
  })
  it('does not emit completion into another user context after a late write response', async () => {
    let resolve!: (value: unknown) => void; post.mockReturnValue(new Promise(r => { resolve = r }))
    const wrapper = setup(); await base(wrapper)
    await wrapper.findAll('article')[0]!.get('input[type="checkbox"]').setValue(true)
    await wrapper.findAll('article')[0]!.findAll('input[type="number"]')[1]!.setValue('1')
    await submit(wrapper); await wrapper.setProps({ viewerKey: 'u2' }); resolve({ data: {} }); await flushPromises()
    expect(wrapper.emitted('saved')).toBeUndefined(); wrapper.unmount()
  })
})

import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Component from '../CartonSpecialOrderActions.vue'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'

const request = { id: 'REQ', request_no: 'SP-EXAMPLE', kind: 'SAMPLE', status: 'SENT', lines: [{ quantity: '10', received_quantity: '0' }],
  permissions: { can_receive: true, can_adjust: true, can_cancel: true, can_delete: true } } as SpecialRequest

describe('sample and miscellaneous order actions', () => {
  it.each(['SAMPLE', 'WORKSHOP_MISC'] as const)('keeps %s secondary actions in the shared More menu', async kind => {
    const wrapper = mount(Component, { props: { request: { ...request, kind } }, attachTo: document.body })
    expect(wrapper.findAll('button').map(row => row.text())).toEqual(['登记收料', '更多', '明细'])
    const more = wrapper.get('[aria-label="更多 SP-EXAMPLE 订单操作"]')
    await more.trigger('keydown', { key: 'Enter' }); await flushPromises()
    const body = new DOMWrapper(document.body)
    expect(body.findAll('[role="menuitem"]').map(row => row.text())).toEqual(['采购单', '修改未送货纸品', '复制订单信息', '调整交期', '追加订单', '减少未入库量', '调整订单', '取消订单', '删除订单'])
    await body.get('[role="menu"]').trigger('keydown', { key: 'Escape' }); await flushPromises()
    expect(body.find('[role="menu"]').exists()).toBe(false)
    await more.trigger('keydown', { key: 'Enter' }); await flushPromises()
    await body.findAll('[role="menuitem"]').find(row => row.text() === '追加订单')!.trigger('click'); await flushPromises()
    expect(wrapper.emitted('action')).toEqual([['append']])
    wrapper.unmount()
  })
  it('respects server flags and disables the complete action group while loading', async () => {
    const wrapper = mount(Component, { props: { request: { ...request, permissions: {} } } })
    expect(wrapper.findAll('button').map(row => row.text())).toEqual(['采购单', '更多', '明细'])
    await wrapper.setProps({ request, disabled: true })
    expect(wrapper.findAll('button').every(row => row.attributes('disabled') !== undefined)).toBe(true)
    wrapper.unmount()
  })
  it('previews details on hover or focus and closes the preview on leaving', async () => {
    const wrapper = mount(Component, { props: { request } })
    const detail = wrapper.get('[aria-label="查看订单 SP-EXAMPLE 明细"]')
    await detail.trigger('mouseenter'); await detail.trigger('mouseleave')
    await detail.trigger('focus'); await detail.trigger('blur')
    expect(wrapper.emitted('preview')).toHaveLength(2)
    expect(wrapper.emitted('close-preview')).toHaveLength(2)
    expect(wrapper.emitted('action')).toBeUndefined()
    wrapper.unmount()
  })
  it('replaces order confirmation with receiving after locking even if old flags remain', async () => {
    const permissions = { ...request.permissions, can_confirm: true, can_send: true }
    const wrapper = mount(Component, { props: { request: { ...request, status: 'SUBMITTED', permissions } } })
    expect(wrapper.findAll('button').map(row => row.text())).toContain('确认并锁单')
    await wrapper.setProps({ request: { ...request, status: 'SENT', permissions } })
    expect(wrapper.findAll('button').map(row => row.text())).not.toContain('确认并锁单')
    await wrapper.get('[aria-label="登记 SP-EXAMPLE 收料"]').trigger('click')
    expect(wrapper.emitted('action')).toEqual([['receive']])
    wrapper.unmount()
  })
  it.each(['COMPLETED', 'CANCELLED'])('keeps %s source operations read-only even with stale edit flags', async status => {
    const wrapper = mount(Component, { props: { request: { ...request, status, permissions: { can_edit: true, can_adjust: true, can_cancel: true } } }, attachTo: document.body })
    const more = wrapper.get('[aria-label="更多 SP-EXAMPLE 订单操作"]')
    await more.trigger('keydown', { key: 'Enter' }); await flushPromises()
    const body = new DOMWrapper(document.body)
    expect(body.findAll('[role="menuitem"]').map(row => row.text())).toEqual(['采购单', '复制订单信息'])
    expect(body.text()).not.toMatch(/合单|拆单|补单|整单退货/)
    wrapper.unmount()
  })
  it('hides material changes for shipped paper identities and does not infer reduce permission from append', async () => {
    const shipped = { ...request, lines: [{ ...request.lines[0]!, id: 'PAPER', quantity: '10', received_quantity: '10' }], shipments: [{ id: 'SHIP', version_id: 'V', delivery_note_no: 'DN', delivery_date: '2026-10-22', lines: [{ id: 'SL', request_line_id: 'PAPER', quantity: '10', received_quantity: '10', remaining_quantity: '0' }], receipts: [] }] }
    const wrapper = mount(Component, { props: { request: shipped }, attachTo: document.body })
    await wrapper.get('[aria-label="更多 SP-EXAMPLE 订单操作"]').trigger('keydown', { key: 'Enter' }); await flushPromises()
    const labels = new DOMWrapper(document.body).findAll('[role="menuitem"]').map(row => row.text())
    expect(labels).toContain('追加订单'); expect(labels).not.toContain('减少未入库量'); expect(labels).not.toContain('修改未送货纸品')
    wrapper.unmount()
  })

  it('retains gift history without offering an unsupported internal gift adjustment', async () => {
    const wrapper = mount(Component, { props: { request: { ...request, kind: 'SUPPLIER_GIFT' } }, attachTo: document.body })
    await wrapper.get('[aria-label="更多 SP-EXAMPLE 订单操作"]').trigger('keydown', { key: 'Enter' }); await flushPromises()
    const labels = new DOMWrapper(document.body).findAll('[role="menuitem"]').map(row => row.text())
    expect(labels).toContain('复制订单信息'); expect(labels).not.toContain('操作历史')
    expect(labels).not.toContain('追加订单'); expect(labels).not.toContain('调整订单')
    wrapper.unmount()
  })

  it.each(['SAMPLE', 'WORKSHOP_MISC'] as const)('offers completed %s append/stock actions and routes both stock operations', async kind => {
    const row = { ...request, kind, status: 'COMPLETED', permissions: { can_append: true, can_adjust: true, can_replenish: true, can_return_stock: true } }
    const wrapper = mount(Component, { props: { request: row }, attachTo: document.body })
    await wrapper.get('[aria-label="更多 SP-EXAMPLE 订单操作"]').trigger('keydown', { key: 'Enter' }); await flushPromises()
    const menu = new DOMWrapper(document.body)
    expect(menu.findAll('[role="menuitem"]').map(row => row.text())).toEqual(['采购单', '复制订单信息', '补单（原数量不变）', '追加订单', '退货'])
    expect(menu.findAll('[role="menuitem"]').find(row => row.text() === '追加订单')!.classes()).toContain('text-amber-700')
    expect(menu.findAll('[role="menuitem"]').find(row => row.text() === '退货')!.classes()).toContain('text-red-700')
    await menu.findAll('[role="menuitem"]').find(row => row.text() === '补单（原数量不变）')!.trigger('click'); await flushPromises()
    expect(wrapper.emitted('action')).toEqual([['replenish']])
    await wrapper.get('[aria-label="更多 SP-EXAMPLE 订单操作"]').trigger('keydown', { key: 'Enter' }); await flushPromises()
    await menu.findAll('[role="menuitem"]').find(row => row.text() === '退货')!.trigger('click'); await flushPromises()
    expect(wrapper.emitted('action')).toEqual([['replenish'], ['return-stock']])
    wrapper.unmount()
  })
  it('freezes replacement structure while retaining server-authorized stock actions and dedicated undo', async () => {
    const row = { ...request, origin: 'REPLENISHMENT', replacement: { parent_request_id: 'PARENT', parent_request_no: 'SP-PARENT', responsibility: 'SUPPLIER' as const, can_undo: true, blockers: [] },
      permissions: { can_edit: true, can_adjust: true, can_append: true, can_confirm: true, can_cancel: true, can_delete: true, can_return_stock: true, can_replenish: true, can_undo_replenish: true } }
    const wrapper = mount(Component, { props: { request: row }, attachTo: document.body })
    await wrapper.get('[aria-label="更多 SP-EXAMPLE 订单操作"]').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(new DOMWrapper(document.body).findAll('[role="menuitem"]').map(row => row.text())).toEqual(['采购单', '复制订单信息', '补单（原数量不变）', '退货', '撤销未发货补单'])
    wrapper.unmount()
  })

})

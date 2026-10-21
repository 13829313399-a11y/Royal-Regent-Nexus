import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Component from '../CartonSpecialOrderActions.vue'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'

const request = { id: 'REQ', request_no: 'SP-EXAMPLE', status: 'SENT', lines: [{ quantity: '10', received_quantity: '0' }],
  permissions: { can_receive: true, can_adjust: true, can_cancel: true, can_delete: true } } as SpecialRequest

describe('sample and miscellaneous order actions', () => {
  it('keeps secondary actions inside the accessible More menu and restores focus on Escape', async () => {
    const wrapper = mount(Component, { props: { request }, attachTo: document.body })
    expect(wrapper.findAll('button').map(row => row.text())).toEqual(['登记收料', '更多', '明细'])
    const more = wrapper.get('[aria-label="更多 SP-EXAMPLE 订单操作"]')
    await more.trigger('keydown', { key: 'Enter' }); await flushPromises()
    const body = new DOMWrapper(document.body)
    expect(body.findAll('[role="menuitem"]').map(row => row.text())).toEqual(['调整订单', '取消订单', '删除订单'])
    await body.get('[role="menu"]').trigger('keydown', { key: 'Escape' }); await flushPromises()
    expect(body.find('[role="menu"]').exists()).toBe(false)
    await more.trigger('keydown', { key: 'Enter' }); await flushPromises()
    await body.findAll('[role="menuitem"]')[0]!.trigger('click'); await flushPromises()
    expect(wrapper.emitted('action')).toEqual([['adjust']])
    wrapper.unmount()
  })
  it('respects server flags and disables the complete action group while loading', async () => {
    const wrapper = mount(Component, { props: { request: { ...request, permissions: {} } } })
    expect(wrapper.findAll('button').map(row => row.text())).toEqual(['明细'])
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
})

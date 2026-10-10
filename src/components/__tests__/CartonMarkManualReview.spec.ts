import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import CartonMarkManualReview from '../CartonMarkManualReview.vue'

const api = vi.hoisted(() => ({ submitManualReview: vi.fn() }))
const context = reactive({ allowed: true, release: true, revision: 1 })
vi.mock('@/api/cartonMark', () => ({ cartonMarkApi: api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: (permission: string) => context.allowed && (permission !== 'carton_mark:template_release' || context.release), currentUser: { id: 'supplier' }, get authorizationVersion() { return context.revision } }) }))
const order = { id: 'O1', customer_name: '客户', contract_no: 'C1', item_no: 'I1', issue_id: 'ISSUE1' }
const source = { id: 'S1', factory_id: 'huaxing', file_name: '正唛.png', kind: 'image', revision: 3, orders: [order] }
beforeEach(() => { vi.clearAllMocks(); context.allowed = true; context.release = true; context.revision = 1; api.submitManualReview.mockResolvedValue({ id: 'T1' }) })

it('submits original identities and current issued order without granting release', async () => {
  const wrapper = mount(CartonMarkManualReview, { props: { sources: [source], supplier: true } })
  expect(wrapper.find('textarea').exists()).toBe(false)
  expect(wrapper.find('select').exists()).toBe(false)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.submitManualReview).toHaveBeenCalledWith({ factory_id: 'huaxing', order_id: 'O1', issue_id: 'ISSUE1', assets: [{ id: 'S1', revision: 3 }], approve: false }, true, expect.any(AbortSignal))
  expect(wrapper.emitted('saved')).toEqual([['T1']])
  expect(wrapper.text()).toContain('内部审核人')
  wrapper.unmount()
})

it('blocks disjoint source orders and clears stale submission on scope changes', async () => {
  const other = { ...source, id: 'S2', orders: [{ ...order, issue_id: 'OLD' }] }
  const wrapper = mount(CartonMarkManualReview, { props: { sources: [source, other], supplier: true } })
  expect(wrapper.text()).toContain('没有共同的明确订单关联')
  await wrapper.get('form').trigger('submit'); expect(api.submitManualReview).not.toHaveBeenCalled()
  await wrapper.setProps({ sources: [source] })
  let finish!: (value: { id: string }) => void
  api.submitManualReview.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  await wrapper.get('form').trigger('submit')
  await wrapper.setProps({ sources: [] })
  finish({ id: 'OLD-TEMPLATE' }); await flushPromises()
  expect(wrapper.emitted('saved')).toBeUndefined()
  wrapper.unmount()
})

it('offers direct approval only to internal releasers and requires a choice for multiple orders', async () => {
  const wrapper = mount(CartonMarkManualReview, { props: { sources: [{ ...source, orders: [order, { ...order, id: 'O2' }] }] } })
  expect(wrapper.get('button[type="submit"]').text()).toBe('审核通过')
  await wrapper.get('form').trigger('submit'); expect(api.submitManualReview).not.toHaveBeenCalled()
  await wrapper.get('select').setValue('O2')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.submitManualReview).toHaveBeenCalledWith(expect.objectContaining({ order_id: 'O2', approve: true }), false, expect.any(AbortSignal))
  context.release = false; await flushPromises()
  expect(wrapper.get('button[type="submit"]').text()).toBe('提交内部审核')
  wrapper.unmount()
})

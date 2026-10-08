import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Responsibilities from '../CartonCustomerResponsibilities.vue'
import type { CartonCustomerResponsibilities } from '@/api/cartonCustomerResponsibilities'

const api = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn() }))
const actor = reactive({ currentUser: { id: 'manager' }, authorizationVersion: 1 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => actor }))
vi.mock('@/api/cartonCustomerResponsibilities', () => ({ cartonCustomerResponsibilitiesApi: api,
  emptyResponsibilities: () => ({ can_manage: false, unrestricted: false, own_customer_codes: [], users: [], customers: [] }) }))
const scope: CartonCustomerResponsibilities = { can_manage: true, unrestricted: true, own_customer_codes: [],
  users: [{ id: 'one', name: '甲' }, { id: 'two', name: '乙' }],
  customers: [{ id: 'customer', code: 'DICKIE', name: '迪奇', revision: 4, status: 'ACTIVE', users: [{ id: 'one', name: '甲' }] }] }
beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue(scope); api.save.mockResolvedValue(scope); actor.currentUser.id = 'manager'; actor.authorizationVersion = 1 })

describe('carton customer responsibilities', () => {
  it('saves multiple responsible users with the displayed revision and an explicit reason', async () => {
    const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.get('[aria-label="分配客户 迪奇"]').trigger('click')
    await wrapper.findAll('input[type=checkbox]')[1]!.setValue(true)
    await wrapper.get('[aria-label="客户责任分配原因"]').setValue('客户订单交接安排')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', 'customer', ['one', 'two'], 4, '客户订单交接安排', expect.any(AbortSignal))
    expect(wrapper.emitted('changed')).toHaveLength(1); wrapper.unmount()
  })
  it('clears the previous factory and rejects a late response', async () => {
    let finish!: (result: CartonCustomerResponsibilities) => void
    api.get.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    api.get.mockResolvedValueOnce({ ...scope, can_manage: false, unrestricted: false, customers: [], users: [], own_customer_codes: [] })
    const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } })
    await wrapper.setProps({ factoryId: 'huakang-b' }); await flushPromises()
    finish(scope); await flushPromises()
    expect(wrapper.text()).not.toContain('迪奇'); expect(wrapper.text()).toContain('尚未分配客户')
    expect(wrapper.find('form').exists()).toBe(false); wrapper.unmount()
  })
  it('clears management controls on a rejected authorization refresh', async () => {
    const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(wrapper.find('[aria-label="分配客户 迪奇"]').exists()).toBe(true)
    api.get.mockRejectedValueOnce(new Error('权限已撤销')); actor.authorizationVersion++
    await flushPromises()
    expect(wrapper.find('[aria-label="分配客户 迪奇"]').exists()).toBe(false)
    expect(wrapper.find('[role=alert]').exists()).toBe(true); wrapper.unmount()
  })
})

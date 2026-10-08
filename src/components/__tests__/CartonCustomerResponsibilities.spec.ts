import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Responsibilities from '../CartonCustomerResponsibilities.vue'
import type { CartonCustomerResponsibilities } from '@/api/cartonCustomerResponsibilities'
import type { AuthMeResponse } from '@/api/auth'

const api = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), claim: vi.fn() }))
type Actor = {
  currentUser: { id: string; identity?: Pick<NonNullable<AuthMeResponse['identity']>, 'effective_context_key' | 'employment_epoch' | 'server_now'> }
  authorizationVersion: number
  authzMode: string
}
const currentUser = (): Actor['currentUser'] => ({ id: 'manager', identity: { effective_context_key: 'primary', employment_epoch: 1, server_now: '2026-10-08T09:00:00Z' } })
const actor = reactive<Actor>({ currentUser: currentUser(), authorizationVersion: 1, authzMode: 'enforce' })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => actor }))
vi.mock('@/api/cartonCustomerResponsibilities', () => ({ cartonCustomerResponsibilitiesApi: api,
  emptyResponsibilities: () => ({ can_manage: false, unrestricted: false, own_customer_codes: [], users: [], customers: [] }) }))
const scope: CartonCustomerResponsibilities = { can_manage: true, unrestricted: true, own_customer_codes: [],
  users: [{ id: 'one', name: '甲' }, { id: 'two', name: '乙' }],
  customers: [{ id: 'customer', code: 'DICKIE', name: '迪奇', revision: 4, status: 'ACTIVE', users: [{ id: 'one', name: '甲' }] }] }
beforeEach(() => { vi.resetAllMocks(); api.get.mockResolvedValue(scope); api.save.mockResolvedValue(scope); actor.currentUser = currentUser(); actor.authorizationVersion = 1; actor.authzMode = 'enforce' })

describe('carton customer responsibilities', () => {
  it('saves multiple responsible users with the displayed revision and an explicit reason', async () => {
    const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.get('[aria-label="分配客户 迪奇"]').trigger('click')
    await wrapper.findAll('input[type=checkbox]')[1]!.setValue(true)
    await wrapper.get('[aria-label="客户责任分配原因"]').setValue('客户订单交接安排')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', 'customer', ['one', 'two'], 4, '客户订单交接安排', expect.any(AbortSignal), undefined)
    expect(wrapper.emitted('changed')).toHaveLength(1); wrapper.unmount()
  })
  it('claims only an open customer and uses the displayed version', async () => {
    api.get.mockResolvedValue({ ...scope, unrestricted: false, customers: [{ ...scope.customers[0], users: [], owner: null, can_claim: true, can_manage: false }] })
    api.claim.mockResolvedValue(scope)
    const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } }); await flushPromises()
    expect(wrapper.find('[aria-label="分配客户 迪奇"]').exists()).toBe(false)
    await wrapper.get('[aria-label="认领客户 迪奇"]').trigger('click'); await flushPromises()
    expect(api.claim).toHaveBeenCalledWith('huaxing', 'customer', 4, expect.any(AbortSignal))
    expect(wrapper.emitted('changed')).toHaveLength(1); wrapper.unmount()
  })
  it('allows a claimant to authorize colleagues but keeps the owner selected', async () => {
    api.get.mockResolvedValue({ ...scope, unrestricted: false, customers: [{ ...scope.customers[0], owner: scope.users[0], can_manage: true, can_claim: false }] })
    const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } }); await flushPromises()
    await wrapper.get('[aria-label="分配客户 迪奇"]').trigger('click')
    expect(wrapper.findAll('input[type=checkbox]')[0]!.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[aria-label="客户负责人"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('clears the previous factory and rejects a late response', async () => {
    let finish!: (result: CartonCustomerResponsibilities) => void
    api.get.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    api.get.mockResolvedValueOnce({ ...scope, can_manage: false, unrestricted: false, customers: [], users: [], own_customer_codes: [] })
    const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } })
    await wrapper.setProps({ factoryId: 'huakang-b' }); await flushPromises()
    finish(scope); await flushPromises()
    expect(wrapper.text()).not.toContain('迪奇'); expect(wrapper.text()).toContain('未设置责任范围')
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
  it('preserves the visible list and unsaved delegation during unchanged session heartbeats', async () => {
    const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } })
    try {
      await flushPromises()
      await wrapper.get('[aria-label="分配客户 迪奇"]').trigger('click')
      await wrapper.findAll('input[type=checkbox]')[1]!.setValue(true)
      const reason = wrapper.get('[aria-label="客户责任分配原因"]')
      await reason.setValue('客户订单交接安排')
      for (const serverNow of ['2026-10-08T09:00:45Z', '2026-10-08T09:01:30Z']) {
        actor.currentUser = { ...currentUser(), identity: { ...currentUser().identity!, server_now: serverNow } }
        await flushPromises()
        expect(wrapper.get('[aria-label="客户责任分配原因"]').element).toBe(reason.element)
        expect((reason.element as HTMLTextAreaElement).value).toBe('客户订单交接安排')
        expect((wrapper.findAll('input[type=checkbox]')[1]!.element as HTMLInputElement).checked).toBe(true)
        expect(wrapper.text()).not.toContain('正在读取责任范围')
      }
      expect(api.get).toHaveBeenCalledTimes(1)
      expect(api.save).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })
  it('does not cancel the initial load when the same account receives a new session object', async () => {
    let finish!: (result: CartonCustomerResponsibilities) => void
    api.get.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } })
    try {
      const signal = api.get.mock.calls[0]![1] as AbortSignal
      actor.currentUser = { ...currentUser() }
      await flushPromises()
      expect(signal.aborted).toBe(false)
      expect(api.get).toHaveBeenCalledTimes(1)
      finish(scope); await flushPromises()
      expect(wrapper.find('[aria-label="分配客户 迪奇"]').exists()).toBe(true)
    } finally { wrapper.unmount() }
  })
  it.each(['account', 'authorization version', 'identity context', 'employment epoch', 'authorization mode'])(
    'clears stale delegation controls while revalidating a changed %s', async change => {
      const wrapper = mount(Responsibilities, { props: { factoryId: 'huaxing' } })
      try {
        await flushPromises()
        await wrapper.get('[aria-label="分配客户 迪奇"]').trigger('click')
        let finish!: (result: CartonCustomerResponsibilities) => void
        api.get.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
        if (change === 'account') actor.currentUser = { ...currentUser(), id: 'other' }
        if (change === 'authorization version') actor.authorizationVersion++
        if (change === 'identity context') actor.currentUser.identity!.effective_context_key = 'temporary'
        if (change === 'employment epoch') actor.currentUser.identity!.employment_epoch++
        if (change === 'authorization mode') actor.authzMode = 'legacy'
        await flushPromises()
        expect(api.get).toHaveBeenCalledTimes(2)
        expect(wrapper.find('form').exists()).toBe(false)
        expect(wrapper.find('[aria-label="分配客户 迪奇"]').exists()).toBe(false)
        expect(wrapper.text()).toContain('正在读取责任范围')
        finish({ ...scope, can_manage: false, unrestricted: false, customers: [], users: [] })
        await flushPromises()
        expect(wrapper.find('[aria-label="分配客户 迪奇"]').exists()).toBe(false)
      } finally { wrapper.unmount() }
    },
  )
})

import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CustomerOrderCenterView from '@/views/CustomerOrderCenterView.vue'
import CartonQuickAssetLibrary from '@/components/CartonQuickAssetLibrary.vue'
const route = vi.hoisted(() => ({ query: {} }))
vi.mock('vue-router', async original => ({ ...await original<typeof import('vue-router')>(), useRoute: () => route, useRouter: () => ({ replace: vi.fn() }) }))
describe('sales materials native entry', () => {
  afterEach(() => vi.restoreAllMocks())
  it('opens materials from the customer order center using sales scope and the current factory', async () => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    const wrapper = mount(CustomerOrderCenterView, { global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot /></a>' }, AccountMenu: true, UsageGuideDialog: true, ModuleFeedbackHub: true, CustomerOrderCenterWorkspace: true, HuakangBJPIntake: true } } })
    await wrapper.findAll('button').find(button => button.text() === '箱唛资料')!.trigger('click'); await flushPromises()
    expect(wrapper.findAllComponents(CartonQuickAssetLibrary)).toHaveLength(1)
    expect(wrapper.getComponent(CartonQuickAssetLibrary).props().audience).toBe('sales')
    expect(wrapper.getComponent(CartonQuickAssetLibrary).props().factoryId).toBeTruthy()
    expect(wrapper.getComponent(CartonQuickAssetLibrary).props().search).toBe('')
    await wrapper.get('input[aria-label="搜索箱唛资料"]').setValue('4500222793')
    expect(wrapper.getComponent(CartonQuickAssetLibrary).props().search).toBe('4500222793')
    expect(wrapper.find('input[aria-label="搜索资料"]').exists()).toBe(false)
    await wrapper.get('input[aria-label="搜索箱唛资料"]').setValue('')
    expect(wrapper.getComponent(CartonQuickAssetLibrary).props().search).toBe('')
    wrapper.unmount()
  })
})

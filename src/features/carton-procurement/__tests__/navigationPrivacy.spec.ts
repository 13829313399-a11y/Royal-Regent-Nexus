import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { reactive } from 'vue'
import Route from '@/views/CartonProcurementRoute.vue'
import { guardCartonNavigation, registerCartonNavigationGuard } from '../navigationGuard'

const mocks = vi.hoisted(() => ({ auth: {} as any, route: {} as any, replace: vi.fn(), mount: vi.fn(), unmount: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeProductionFactory: { id: 'huakang-a' } }) }))
vi.mock('vue-router', () => ({ useRoute: () => mocks.route, useRouter: () => ({ replace: mocks.replace }) }))
vi.mock('@/views/CartonProcurementView.vue', async () => {
  const { defineComponent, onBeforeUnmount } = await import('vue')
  return { default: defineComponent({ setup() { mocks.mount(); onBeforeUnmount(mocks.unmount) }, template: '<main>当前用户的工作区</main>' }) }
})
let wrapper: VueWrapper | undefined
beforeEach(() => {
  vi.clearAllMocks()
  mocks.auth = reactive({ currentUser: { id: 'alice', identity: { employment_epoch: 1 } }, authorizationVersion: 1, authzMode: 'legacy', can: () => true })
  mocks.route = reactive({ query: { factory: 'huakang-a', carton_record: 'PURCHASE:P1', carton_from: '2026-10-20' } })
  mocks.replace.mockImplementation(async ({ query }) => { mocks.route.query = query })
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined })

it('clears the old record and unmounts the old workspace during account boundary changes', async () => {
  let finish!: () => void
  mocks.replace.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve }))
  wrapper = mount(Route)
  mocks.auth.currentUser = { id: 'bob', identity: { employment_epoch: 1 } }
  await flushPromises()
  expect(wrapper.text()).not.toContain('当前用户的工作区')
  expect(mocks.unmount).toHaveBeenCalledTimes(1)
  expect(mocks.replace.mock.calls[0]![0].query).toMatchObject({ carton_record: undefined, carton_from: undefined, carton_to: undefined })
  finish(); await flushPromises()
  expect(mocks.mount).toHaveBeenCalledTimes(2)
})

it('removes private workspace data on permission loss and recreates it on a session boundary', async () => {
  wrapper = mount(Route)
  window.dispatchEvent(new Event('auth-session-boundary-changed')); await flushPromises()
  expect(mocks.mount).toHaveBeenCalledTimes(2)
  mocks.auth.can = () => false
  await flushPromises()
  expect(wrapper.text()).toContain('无此厂区的纸箱读取权限')
  expect(wrapper.find('main').exists()).toBe(false)
})

it('blocks route changes while native drafts are open, permits session exit, and releases only its own guard', () => {
  const from = { fullPath: '/carton?factory=a' }
  const releaseOld = registerCartonNavigationGuard(() => true)
  let dirty = true
  const releaseCurrent = registerCartonNavigationGuard(() => !dirty)
  releaseOld()
  expect(guardCartonNavigation({ fullPath: '/carton?factory=b' }, from)).toBe(false)
  expect(guardCartonNavigation(from, from)).toBe(true)
  expect(guardCartonNavigation({ fullPath: '/login', name: 'login' }, from)).toBe(true)
  dirty = false
  expect(guardCartonNavigation({ fullPath: '/other' }, from)).toBe(true)
  releaseCurrent()
})

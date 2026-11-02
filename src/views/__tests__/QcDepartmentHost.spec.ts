// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  route: { path: '/modules/qc/inspection-operations', hash: '', query: {} as Record<string, string> },
  app: { activeFactoryId: 'group' },
  auth: { currentUser: { id: 'one' }, authorizationVersion: 1 },
  get: vi.fn(), replace: vi.fn(), can: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRoute: () => state.route, useRouter: () => ({ replace: state.replace }), RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('@/stores/app', () => ({ useAppStore: () => state.app }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => new Proxy(state.auth, { get: (target, key) => key === 'can' ? state.can : Reflect.get(target, key) }) }))
vi.mock('@/lib/http', () => ({ http: { get: state.get }, getApiErrorMessage: (error: Error) => error.message }))
import Host from '@/views/QcOperationsCenterView.vue'
import { canChangeFactory } from '@/lib/factoryChangeGuard'

beforeEach(() => {
  state.route = reactive({ path: '/modules/qc/inspection-operations', hash: '', query: {} })
  state.app = reactive({ activeFactoryId: 'group' })
  state.auth = reactive({ currentUser: { id: 'one' }, authorizationVersion: 1 })
  state.get.mockReset()
  state.can.mockReset().mockReturnValue(true)
  state.replace.mockReset().mockImplementation(async (destination) => {
    if (!canChangeFactory()) return
    state.app.activeFactoryId = destination.query.factory
    state.route.query = destination.query
  })
})

describe('QC_department host', () => {
  it('does not default a group context to another factory', async () => {
    const wrapper = mount(Host)
    await flushPromises()
    expect(state.get).not.toHaveBeenCalled()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.text()).toContain('选择具体厂区')
    wrapper.unmount()
  })
  it('embeds the authorized URL and reloads on same-factory account changes', async () => {
    state.route.query.factory = 'huaxing'
    state.get.mockResolvedValueOnce({ data: { frame_url: '/api/qc-department/huaxing/u-one/' } })
    const wrapper = mount(Host)
    await flushPromises()
    expect(wrapper.find('iframe').attributes('src')).toBe('/api/qc-department/huaxing/u-one/')
    state.get.mockResolvedValueOnce({ data: { frame_url: '/api/qc-department/huaxing/u-two/' } })
    state.auth.currentUser.id = 'two'
    await flushPromises()
    expect(wrapper.find('iframe').attributes('src')).toBe('/api/qc-department/huaxing/u-two/')
    expect(state.get).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
  it('removes the old frame while rechecking a changed authorization version', async () => {
    state.route.query.factory = 'huaxing'
    state.get.mockResolvedValueOnce({ data: { frame_url: '/api/qc-department/huaxing/u-one/' } })
    const wrapper = mount(Host)
    await flushPromises()
    state.get.mockRejectedValueOnce(new Error('当前账号没有权限'))
    state.auth.authorizationVersion++
    await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('没有权限')
    wrapper.unmount()
  })
  it('does not apply a late response from the previous factory', async () => {
    state.route.query.factory = 'huaxing'
    let resolveFirst!: (value: unknown) => void
    state.get.mockReturnValueOnce(new Promise(resolve => { resolveFirst = resolve }))
    const wrapper = mount(Host)
    state.get.mockResolvedValueOnce({ data: { frame_url: '/api/qc-department/huakang-a/u-one/' } })
    state.route.query.factory = 'huakang-a'
    await nextTick()
    await flushPromises()
    resolveFirst({ data: { frame_url: '/api/qc-department/huaxing/u-one/' } })
    await flushPromises()
    expect(wrapper.find('iframe').attributes('src')).toContain('/huakang-a/')
    wrapper.unmount()
  })
})

function bridgeFor(wrapper: ReturnType<typeof mount>) {
  const iframe = wrapper.get('iframe').element as HTMLIFrameElement
  // Detached jsdom iframes do not create a browsing context.
  Object.defineProperty(iframe, 'contentWindow', { configurable: true, value: {} })
  const bridge = { factory: '', page: '', options: [] as {id: string; label: string}[], select: async (_: string) => {} }
  Object.assign(iframe.contentWindow!, {
    __QC_SET_FACTORY_BRIDGE: (value: typeof bridge) => Object.assign(bridge, value),
    __QC_CONFIRM_FACTORY_LEAVE: vi.fn().mockReturnValue(true),
    __QC_CURRENT_PAGE: () => 'sales-schedule',
  })
  return { iframe, bridge }
}
function health() {
  state.get.mockImplementation(async (url: string) => ({data:{frame_url:url.replace('/api/health','/u-one/')}}))
}
it('QC selection updates the Nexus context and URL, replacing the old factory frame', async () => {
  state.route.query.factory = 'huaxing'; health()
  const wrapper = mount(Host)
  await flushPromises()
  const { iframe, bridge } = bridgeFor(wrapper)
  await wrapper.get('iframe').trigger('load')
  expect(bridge.factory).toBe('huaxing')
  await bridge.select('huakang-a'); await flushPromises()
  expect(state.app.activeFactoryId).toBe('huakang-a')
  expect(state.route.query.factory).toBe('huakang-a')
  expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('huakang-a')
  expect(wrapper.get('iframe').element).not.toBe(iframe)
  expect(wrapper.get('iframe').attributes('src')).toContain('/huakang-a/')
  const next = bridgeFor(wrapper)
  await wrapper.get('iframe').trigger('load')
  expect(next.bridge.page).toBe('sales-schedule')
  await bridge.select('huadeng') // A detached frame cannot switch the current factory.
  expect(state.route.query.factory).toBe('huakang-a')
  wrapper.unmount()
})
it('Nexus selection and group clear the previous frame without fetching group data', async () => {
  state.route.query.factory = 'huaxing'; health()
  const wrapper = mount(Host)
  await flushPromises()
  await wrapper.get('select').setValue('huakang-b'); await flushPromises()
  expect(state.app.activeFactoryId).toBe('huakang-b')
  expect(wrapper.get('iframe').attributes('src')).toContain('/huakang-b/')
  state.get.mockClear()
  await wrapper.get('select').setValue('group'); await flushPromises()
  expect(state.app.activeFactoryId).toBe('group')
  expect(wrapper.find('iframe').exists()).toBe(false)
  expect(state.get).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('请选择具体厂区')
  wrapper.unmount()
})
it('cancelled changes preserve both selectors, URL, frame and current edits', async () => {
  state.route.query.factory = 'huaxing'; state.app.activeFactoryId = 'huaxing'; health()
  const wrapper = mount(Host)
  await flushPromises()
  const {iframe, bridge} = bridgeFor(wrapper)
  const guard = vi.fn().mockReturnValue(false)
  Object.assign(iframe.contentWindow!, {__QC_CONFIRM_FACTORY_LEAVE:guard})
  await wrapper.get('iframe').trigger('load')
  await bridge.select('huakang-a'); await flushPromises()
  await wrapper.get('select').setValue('group'); await flushPromises()
  expect(guard).toHaveBeenCalledTimes(2)
  expect(state.app.activeFactoryId).toBe('huaxing')
  expect(state.route.query.factory).toBe('huaxing')
  expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('huaxing')
  expect(wrapper.get('iframe').element).toBe(iframe)
  expect(state.get).toHaveBeenCalledTimes(1)
  wrapper.unmount()
  expect(canChangeFactory()).toBe(true)
})
it('QC options are limited to readable factories and cannot request another factory', async () => {
  state.route.query.factory = 'huaxing'; health()
  state.can.mockImplementation((_p, factory) => factory === 'huaxing')
  const wrapper = mount(Host)
  await flushPromises()
  const {bridge} = bridgeFor(wrapper)
  await wrapper.get('iframe').trigger('load')
  expect(bridge.options.map(option=>option.id)).toEqual(['group','huaxing'])
  await bridge.select('huakang-d')
  expect(state.replace).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('authorization refresh reconnects options without resetting the current QC page', async () => {
  state.route.query.factory='huaxing';health()
  state.can.mockImplementation(() => Boolean(state.auth.currentUser.id))
  const wrapper=mount(Host);await flushPromises()
  const {bridge}=bridgeFor(wrapper);await wrapper.get('iframe').trigger('load')
  expect(bridge.page).toBe('dashboard')
  state.auth.currentUser={id:'one'};await flushPromises()
  expect(bridge.page).toBe('sales-schedule')
  wrapper.unmount()
})

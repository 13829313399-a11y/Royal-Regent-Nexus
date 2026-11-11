import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IndonesiaShippingView from '@/views/IndonesiaShippingView.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { guardShippingNavigation } from '@/features/indonesia-shipping/navigationGuard'
const mocks = vi.hoisted(() => ({ get: vi.fn(), replace: vi.fn(), push: vi.fn() }))
vi.mock('@/lib/http', () => ({ http: { get: mocks.get } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push, replace: mocks.replace, currentRoute: { value: { query: {} } } }) }))

function setup(factory: 'group' | 'huaxing' | 'huadeng' = 'huaxing') {
  const pinia = createPinia(); setActivePinia(pinia)
  const app = useAppStore(); const auth = useAuthStore()
  app.activeFactoryId = factory; auth.isAuthenticated = true
  return { app, auth, wrapper: mount(IndonesiaShippingView, { attachTo: document.body, global: { plugins: [pinia] } }) }
}
beforeEach(() => { vi.clearAllMocks(); mocks.get.mockResolvedValue({ data: { ready: true } }) })

describe('印尼走货独立业务入口', () => {
  it('accepts toolbar counts only from the current frame, factory and connection', async () => {
    const { wrapper, app } = setup(); await flushPromises()
    const frame = wrapper.get('iframe').element as HTMLIFrameElement
    const post = vi.spyOn(frame.contentWindow!, 'postMessage')
    await wrapper.get('iframe').trigger('load')
    const connect = post.mock.calls[0][0] as { id: string }
    const send = (data: object, source: MessageEventSource | null = frame.contentWindow, origin = window.location.origin) => window.dispatchEvent(new MessageEvent('message', {
      origin, source, data: { type: 'nexus-shipping-toolbar-state', factory: 'huaxing', id: connect.id, alertsEnabled: true, count: 7, ...data },
    }))
    send({}, null); send({}, frame.contentWindow, 'https://untrusted.example'); send({ factory: 'huadeng' }); send({ id: 'old' })
    await flushPromises(); expect(wrapper.text()).not.toContain('物料提醒')
    send({}); await flushPromises()
    const alertButton = wrapper.findAll('button').find(button => button.text().includes('物料提醒'))!
    expect(alertButton.text()).toContain('7')
    await alertButton.trigger('click')
    expect(post).toHaveBeenLastCalledWith(expect.objectContaining({ action: 'alerts', id: connect.id, factory: 'huaxing' }), window.location.origin)
    send({ alertsEnabled: false }); await flushPromises(); expect(wrapper.text()).not.toContain('物料提醒')
    send({ active: false }); await flushPromises(); expect(wrapper.text()).not.toContain('物料提醒')
    send({}); await flushPromises(); app.activeFactoryId = 'huadeng'; await flushPromises()
    send({}); await flushPromises(); expect(wrapper.text()).not.toContain('物料提醒')
    wrapper.unmount()
  })
  it('accepts draft notices only from its own frame and checks before factory context changes', async () => {
    const { wrapper, app } = setup(); await flushPromises()
    const frame = wrapper.get('iframe').element as HTMLIFrameElement
    const send = (source: MessageEventSource | null) => window.dispatchEvent(new MessageEvent('message', { origin: window.location.origin, source, data: { type: 'nexus-shipping-navigation', dirty: true } }))
    send(null)
    expect(guardShippingNavigation({ fullPath: '/other' }, { fullPath: '/shipping' })).toBe(true)
    send(frame.contentWindow)
    const leaving = guardShippingNavigation({ fullPath: '/other' }, { fullPath: '/shipping' })
    await flushPromises()
    const stay = [...document.body.querySelectorAll('button')].find(button => button.textContent?.includes('继续留在工作区'))!
    expect(stay).toBeTruthy(); stay.click()
    expect(await leaving).toBe(false)
    expect(app.activeFactoryId).toBe('huaxing')
    expect(guardShippingNavigation({ fullPath: '/login', name: 'login' }, { fullPath: '/shipping' })).toBe(true)
    wrapper.unmount()
  })
  it('requires a real factory without falling back from group', async () => {
    const { wrapper } = setup('group'); await flushPromises()
    expect(wrapper.text()).toContain('请选择厂区')
    expect(mocks.get).not.toHaveBeenCalled(); expect(wrapper.find('iframe').exists()).toBe(false)
    wrapper.unmount()
  })
  it('shows unavailable service errors without mounting a business frame', async () => {
    mocks.get.mockRejectedValue({ response: { data: { detail: '当前厂区的印尼走货服务尚未配置' } } })
    const { wrapper } = setup(); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('尚未配置')
    expect(wrapper.find('iframe').exists()).toBe(false); wrapper.unmount()
  })
  it('drops the previous factory immediately and ignores its late response', async () => {
    let finishOld!: (value: unknown) => void
    let finishNew!: (value: unknown) => void
    mocks.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { finishNew = resolve }))
    const { app, wrapper } = setup()
    app.activeFactoryId = 'huadeng'; await flushPromises()
    finishOld({}); await flushPromises(); expect(wrapper.find('iframe').exists()).toBe(false)
    finishNew({}); await flushPromises()
    expect(wrapper.get('iframe').attributes('src')).toBe('/api/indonesia-shipping/huadeng/app/shipments')
    expect(mocks.get).toHaveBeenLastCalledWith('/indonesia-shipping/huadeng/status', { timeout: 20000 })
    wrapper.unmount()
  })
  it('rechecks changed authority and clears previous content while reconnecting', async () => {
    const { auth, wrapper } = setup(); await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(true)
    mocks.get.mockReturnValue(new Promise(() => {})); auth.authorizationVersion++
    await flushPromises(); expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('核对'); wrapper.unmount()
  })
})

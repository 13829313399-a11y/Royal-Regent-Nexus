import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { sprayProductionApi as api, type SpraySummary } from '@/api/sprayProduction'
import SprayProductionView from '@/views/SprayProductionView.vue'

vi.mock('@/api/sprayProduction', () => ({ sprayProductionApi: { summary: vi.fn(), collection: vi.fn(), balances: vi.fn(), command: vi.fn(), preferences: vi.fn() } }))
vi.mock('@/lib/http', () => ({ http: { get: vi.fn() } }))

/* 滑动胶囊指示器的几何测试。
   这里用确定性的假几何替换 getBoundingClientRect：jsdom 不做布局，真实浏览器里
   一旦测量函数写错坐标系（例如存视口坐标而不是容器内坐标），指示器会与选中项错位。
   两个必须成立的性质：
   1) 指示器位置等于选中链接相对导航容器的滚动位置；
   2) 导航上方发生布局位移（顶部条换行、状态文案切换）后重新测量，位置不变。 */
const NAV_TOP = 140, NAV_LEFT = 10
const LINK_TOP = 60, LINK_HEIGHT = 40, LINK_WIDTH = 190
const snapshot = (factory: string): SpraySummary => ({ factory_id: factory, revision: 1, as_of: '2026-09-11T00:00:00Z', data_mode: 'live', coverage: 'no_data', counts: {}, permissions: ['read'] })
const Shell = { template: '<div><RouterView /></div>' }

async function routerAt(path: string): Promise<Router> {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: Shell }, { path: '/modules/production/spray-production/:page/:id?', component: Shell }] })
  await router.push(path)
  await router.isReady()
  return router
}

/* 只桩掉两个元素：导航容器与当前选中链接，其余元素沿用 jsdom 的零矩形。
   clientWidth 必须一并桩掉：测量函数会用它夹紧指示器宽度，jsdom 默认返回 0。 */
function stubGeometry(navTop = NAV_TOP, scrollTop = 0, scrollLeft = 0) {
  const original = Element.prototype.getBoundingClientRect
  Element.prototype.getBoundingClientRect = function (this: Element) {
    if (this instanceof HTMLElement && this.classList.contains('spray-nav')) {
      const rect = { x: NAV_LEFT, y: navTop, top: navTop, left: NAV_LEFT, right: NAV_LEFT + 232, bottom: navTop + 480, width: 232, height: 480, toJSON: () => ({}) }
      Object.defineProperty(this, 'scrollTop', { value: scrollTop, configurable: true })
      Object.defineProperty(this, 'scrollLeft', { value: scrollLeft, configurable: true })
      Object.defineProperty(this, 'clientWidth', { value: 232, configurable: true })
      return rect as DOMRect
    }
    if (this instanceof HTMLElement && this.matches('a.router-link-active')) {
      const top = navTop + LINK_TOP - scrollTop, left = NAV_LEFT + 8 - scrollLeft
      return { x: left, y: top, top, left, right: left + LINK_WIDTH, bottom: top + LINK_HEIGHT, width: LINK_WIDTH, height: LINK_HEIGHT, toJSON: () => ({}) } as DOMRect
    }
    return original.call(this)
  }
  return () => { Element.prototype.getBoundingClientRect = original }
}

/* 测量写入 requestAnimationFrame，测试里同步执行更贴近“同帧完成”的语义。 */
function immediateFrames(restore: () => void) {
  const original = window.requestAnimationFrame
  const pending: FrameRequestCallback[] = []
  window.requestAnimationFrame = ((callback: FrameRequestCallback) => { pending.push(callback); return pending.length }) as typeof window.requestAnimationFrame
  return {
    flush: () => { while (pending.length) pending.shift()!(0) },
    restore: () => { window.requestAnimationFrame = original; restore() },
  }
}

const pill = (wrapper: VueWrapper) => wrapper.get<HTMLElement>('.spray-nav-pill').element as HTMLElement

beforeEach(() => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }) as unknown as typeof window.matchMedia
  vi.mocked(api.summary).mockImplementation(async factory => snapshot(factory))
  vi.mocked(api.collection).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1000 })
  vi.mocked(api.balances).mockResolvedValue({})
  vi.mocked(api.preferences).mockResolvedValue([])
})

describe('spray nav sliding pill geometry', () => {
  it('positions the pill at the selected link position measured inside the nav container', async () => {
    const frames = immediateFrames(stubGeometry())
    const router = await routerAt('/modules/production/spray-production/logistics?factory=huaxing')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    /* 挂载期的 rAF（字体就绪与首帧校准）也一并放行，避免依赖执行顺序。 */
    frames.flush()
    await flushPromises()
    frames.flush()

    const element = pill(wrapper)
    expect(element.style.getPropertyValue('--spray-nav-left')).toBe('8px')
    expect(element.style.getPropertyValue('--spray-nav-top')).toBe('60px')
    expect(element.style.getPropertyValue('--spray-nav-width')).toBe(`${LINK_WIDTH}px`)
    expect(element.style.getPropertyValue('--spray-nav-height')).toBe(`${LINK_HEIGHT}px`)
    expect(element.style.opacity).toBe('1')
    wrapper.unmount()
    frames.restore()
  })

  it('keeps the pill aligned when layout above the nav shifts and re-measurement runs', async () => {
    let navTop = NAV_TOP
    let restore = stubGeometry(navTop)
    const original = Element.prototype.getBoundingClientRect
    Element.prototype.getBoundingClientRect = function (this: Element) {
      if (this instanceof HTMLElement && this.classList.contains('spray-nav')) {
        Object.defineProperty(this, 'scrollTop', { value: 0, configurable: true })
        Object.defineProperty(this, 'scrollLeft', { value: 0, configurable: true })
        Object.defineProperty(this, 'clientWidth', { value: 232, configurable: true })
        return { x: NAV_LEFT, y: navTop, top: navTop, left: NAV_LEFT, right: NAV_LEFT + 232, bottom: navTop + 480, width: 232, height: 480, toJSON: () => ({}) } as DOMRect
      }
      if (this instanceof HTMLElement && this.matches('a.router-link-active')) {
        const top = navTop + LINK_TOP, left = NAV_LEFT + 8
        return { x: left, y: top, top, left, right: left + LINK_WIDTH, bottom: top + LINK_HEIGHT, width: LINK_WIDTH, height: LINK_HEIGHT, toJSON: () => ({}) } as DOMRect
      }
      return original.call(this)
    }

    const frames = immediateFrames(() => { Element.prototype.getBoundingClientRect = original })
    const router = await routerAt('/modules/production/spray-production/logistics?factory=huaxing')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    frames.flush()
    await flushPromises()

    const element = pill(wrapper)
    expect(element.style.getPropertyValue('--spray-nav-top')).toBe('60px')

    /* 顶部条换行使导航整体下移 40px；容器内坐标必须保持不变，指示器才不会错位。 */
    navTop = NAV_TOP + 40
    restore = stubGeometry(navTop)
    window.dispatchEvent(new Event('resize'))
    frames.flush()

    expect(element.style.getPropertyValue('--spray-nav-top')).toBe('60px')
    wrapper.unmount()
    frames.restore()
    restore()
  })

  it('accounts for the nav scroll offset on the narrow horizontal navigation', async () => {
    const frames = immediateFrames(stubGeometry(NAV_TOP, 0, 24))
    const router = await routerAt('/modules/production/spray-production/logistics?factory=huaxing')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    frames.flush()
    await flushPromises()

    /* 横向滚动 24px 后，选中项在视口里左移 24px；加回 scrollLeft 才能得到容器内坐标。 */
    const element = pill(wrapper)
    expect(element.style.getPropertyValue('--spray-nav-left')).toBe('8px')
    wrapper.unmount()
    frames.restore()
  })

  it('accounts for the nav vertical scroll offset so the pill cannot drift by one row', async () => {
    /* 桌面纵向导航滚动 24px：选中链接的视口位置随之上升 24px，
       必须加回 scrollTop 才能得到与滚动无关的容器内坐标。
       少了这一项，指示器会随滚动越飘越高，正是实际观察到的“错一格”现象。 */
    const frames = immediateFrames(stubGeometry(NAV_TOP, 24))
    const router = await routerAt('/modules/production/spray-production/logistics?factory=huaxing')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    frames.flush()
    await flushPromises()

    const element = pill(wrapper)
    expect(element.style.getPropertyValue('--spray-nav-top')).toBe('60px')
    expect(element.style.getPropertyValue('--spray-nav-left')).toBe('8px')
    wrapper.unmount()
    frames.restore()
  })
})

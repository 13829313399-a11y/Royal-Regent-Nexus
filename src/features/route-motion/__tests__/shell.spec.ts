import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, nextTick, onMounted, onUnmounted } from 'vue'
import { createMemoryHistory, createRouter, createWebHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Boxes } from '@lucide/vue'
import AppShell from '@/components/layout/AppShell.vue'
import ModuleCard from '@/components/modules/ModuleCard.vue'
import { useHomeAppearance, type HomeAppearance } from '@/composables/useHomeAppearance'
import { installRouteMotionNavigation } from '../navigation'
import type { EnterpriseModule } from '@/data/enterpriseMock'

vi.mock('@/composables/usePresenceHeartbeat', () => ({ usePresenceHeartbeat: vi.fn() }))
vi.mock('@/components/layout/TopBar.vue', () => ({ default: defineComponent({ template: '<header>Topbar</header>' }) }))
vi.mock('@/components/layout/SidebarNav.vue', () => ({ default: defineComponent({ template: '<aside>Sidebar</aside>' }) }))
vi.mock('@/components/auth/AuthExperienceShell.vue', () => ({ default: defineComponent({ template: '<div><slot /></div>' }) }))

const entry: EnterpriseModule = { id: 'full', title: 'Full workspace', route: '/full?factory=huakang-a', icon: Boxes, owner: 'QA', summary: 'Test', status: 'ready', statusTone: 'teal', stats: '', statusMetrics: [], children: [], todos: [] }
let appearance: HomeAppearance
const mediaListeners = new Set<(event: MediaQueryListEvent) => void>()
let reduced = false
const animations: { target: HTMLElement; frames: Keyframe[]; options: KeyframeAnimationOptions }[] = []
const cleanup: (() => void)[] = []

beforeEach(() => {
  reduced = false; mediaListeners.clear(); animations.length = 0
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    get matches() { return query.includes('prefers-reduced-motion') ? reduced : false },
    addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => { if (query.includes('prefers-reduced-motion')) mediaListeners.add(listener) },
    removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => mediaListeners.delete(listener),
  })))
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 40, y: 100, width: 40, height: 40, left: 40, top: 100, right: 80, bottom: 140, toJSON: () => ({}) })
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList)
  Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, value: vi.fn(function (this: HTMLElement, frames: Keyframe[], options: KeyframeAnimationOptions) {
    animations.push({ target: this, frames, options })
    return { finished: Promise.resolve(), cancel: vi.fn() }
  }) })
})
afterEach(() => {
  for (const stop of cleanup.splice(0)) stop()
  Reflect.deleteProperty(HTMLElement.prototype, 'animate')
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); document.body.innerHTML = ''
})

async function setup(options: { anchors?: boolean; native?: boolean } = {}) {
  const counts = { plainMount: 0, plainUnmount: 0, fullMount: 0, fullUnmount: 0 }
  const Home = defineComponent({ setup() { appearance = useHomeAppearance(); return () => h('section', { 'data-page': 'home' }, [
    h('h1', 'Home'), h(ModuleCard, { module: entry, 'data-rr-motion-source': options.anchors ? 'surface' : undefined }),
  ]) } })
  const Plain = defineComponent({ setup() {
    onMounted(() => counts.plainMount++); onUnmounted(() => counts.plainUnmount++)
    return () => h('section', { 'data-page': 'plain' }, [h('h1', 'Plain'), h('input', { 'aria-label': 'Plain draft' })])
  } })
  const Full = defineComponent({ setup() {
    onMounted(() => counts.fullMount++); onUnmounted(() => counts.fullUnmount++)
    return () => h('main', { 'data-page': 'full' }, [
      h('header', { 'data-rr-motion-target': options.anchors ? 'surface' : undefined }, [
        h('span', { 'data-rr-motion-target': options.anchors ? 'icon' : undefined }, [h('svg', { 'aria-hidden': 'true' })]),
        h('h1', { 'data-route-motion-anchor': '' }, 'Full'),
      ]),
      h('input', { 'aria-label': 'Full draft' }), h('button', 'Action'),
    ])
  } })
  if (options.native) window.history.replaceState(null, '', '/modules/production?factory=huakang-a')
  const history = options.native ? createWebHistory() : createMemoryHistory()
  const router = createRouter({ history, routes: [
    { path: '/modules/:department', name: 'modules-department', component: Home },
    { path: '/plain', name: 'plain', component: Plain },
    { path: '/full', name: 'full', component: Full, meta: { fullPage: true } },
  ] })
  const nav = installRouteMotionNavigation(router)
  await router.push('/modules/production?factory=huakang-a')
  const wrapper = mount(AppShell, { attachTo: document.body, global: { plugins: [createPinia(), router] } })
  cleanup.push(() => { wrapper.unmount(); nav.dispose(); history.destroy() })
  await flushPromises()
  return { router, wrapper, counts, nav }
}

describe('real AppShell single-business-tree integration', () => {
  it('immediately replaces standard/fullPage content; query/hash preserve input and instances', async () => {
    const { router, counts } = await setup()
    await router.push('/plain?factory=huakang-a'); await flushPromises()
    const plainInput = document.querySelector<HTMLInputElement>('input')!; plainInput.value = 'unsaved plain'
    await router.push('/plain?factory=huakang-a&page=2#rows'); await flushPromises()
    expect(document.querySelector('input')).toBe(plainInput)
    expect(plainInput.value).toBe('unsaved plain')
    await router.push('/full?factory=huakang-a'); await flushPromises()
    expect(document.querySelectorAll('[data-page]')).toHaveLength(1)
    expect(document.querySelector('[data-page="plain"]')).toBeNull()
    expect(document.querySelector('.app-shell')).toBeNull()
    const fullInput = document.querySelector<HTMLInputElement>('input')!; fullInput.value = 'unsaved full'
    const count = animations.length
    await router.push('/full?factory=huakang-a&page=2'); await flushPromises()
    expect(document.querySelector('input')).toBe(fullInput)
    expect(fullInput.value).toBe('unsaved full')
    expect(animations).toHaveLength(count)
    expect(counts).toEqual({ plainMount: 1, plainUnmount: 1, fullMount: 1, fullUnmount: 0 })
    expect(animations.every(animation => animation.frames.every(frame => !('filter' in frame)))).toBe(true)
    const rootAnimation = animations.find(animation => animation.target.dataset.page === 'full')!
    expect(rootAnimation.frames.every(frame => !('transform' in frame))).toBe(true)
  })
  it('records one card navigation, renders only decoration, and restores the source focus', async () => {
    const { router, wrapper } = await setup()
    const push = vi.spyOn(router, 'push')
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(push).toHaveBeenCalledOnce()
    expect(document.querySelectorAll('[data-page]')).toHaveLength(1)
    expect(document.querySelector('.rr-route-motion')?.getAttribute('aria-hidden')).toBe('true')
    expect(document.querySelector('.rr-route-motion input')).toBeNull()
    await router.push('/modules/production?factory=huakang-a'); await flushPromises()
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve())); await flushPromises()
    expect((document.activeElement as HTMLElement).dataset.routeEntryId).toBe('full')
    expect(window.scrollTo).toHaveBeenCalled()
  })
  it('keeps a rejected navigation on the same draft with no success animation', async () => {
    const { router } = await setup()
    await router.push('/plain?factory=huakang-a'); await flushPromises()
    const input = document.querySelector<HTMLInputElement>('input')!; input.value = 'retain me'; input.focus()
    const count = animations.length
    router.beforeEach(to => to.name === 'full' ? false : true)
    await router.push('/full?factory=huakang-a'); await flushPromises()
    expect(document.querySelector('input')).toBe(input)
    expect(input.value).toBe('retain me')
    expect(document.activeElement).toBe(input)
    expect(animations).toHaveLength(count)
    expect(document.querySelector('.rr-route-motion')).toBeNull()
  })
  it('falls back to the home heading when filtering moved the original card outside the restored viewport', async () => {
    const { router, wrapper } = await setup()
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const y = this.matches('article,[data-route-entry-icon]') ? 3000 : 100
      return { x: 40, y, width: 40, height: 40, left: 40, top: y, right: 80, bottom: y + 40, toJSON: () => ({}) }
    })
    await router.push('/modules/production?factory=huakang-a'); await flushPromises()
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve())); await flushPromises()
    expect(document.activeElement?.tagName).toBe('H1')
    expect(document.querySelector('.rr-route-motion')).toBeNull()
    expect(window.scrollTo).toHaveBeenLastCalledWith({ left: 0, top: 0, behavior: 'instant' })
  })
  it('cancels a pending home restoration frame when a newer route wins', async () => {
    const { router } = await setup()
    await router.push('/full?factory=huakang-a'); await flushPromises()
    await router.push('/modules/production?factory=huakang-a')
    await router.push('/plain?factory=huakang-a'); await flushPromises()
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve())); await flushPromises()
    expect(document.querySelector('h1')?.textContent).toBe('Plain')
    expect(document.activeElement?.textContent).toBe('Plain')
    expect(document.querySelector('.rr-route-motion')).toBeNull()
  })
  it('observes system preference on fullPage, cancels immediately, and never replays on visibility return', async () => {
    const { router } = await setup()
    await router.push('/full?factory=huakang-a'); await flushPromises()
    expect(mediaListeners.size).toBe(1)
    reduced = true; for (const listener of mediaListeners) listener({ matches: true } as MediaQueryListEvent)
    await nextTick()
    expect(appearance.effectiveMotion.value).toBe('off')
    const count = animations.length
    await router.push('/plain?factory=huakang-a'); await flushPromises()
    expect(animations).toHaveLength(count)
    reduced = false; for (const listener of mediaListeners) listener({ matches: false } as MediaQueryListEvent)
    document.dispatchEvent(new Event('visibilitychange')); await nextTick()
    expect(animations).toHaveLength(count)
  })
  it.each(['preference', 'feature-switch'])('keeps immediate navigation usable with %s off', async mode => {
    if (mode === 'feature-switch') vi.stubEnv('VITE_ROUTE_MOTION_ENABLED', 'false')
    const { router, counts, nav } = await setup()
    if (mode === 'preference') appearance.motion.value = 'off'
    await router.push('/full?factory=huakang-a'); await flushPromises()
    expect(counts.fullMount).toBe(1)
    expect(animations).toHaveLength(0)
    expect(Boolean(nav.entry.value)).toBe(mode === 'preference')
    expect(document.querySelector('button')?.disabled).toBe(false)
    expect(document.querySelector('main')?.style.opacity).toBe('')
  })
  it('keeps a pending allowed navigation silent when the preference changes before its guard resolves', async () => {
    const { router, nav } = await setup()
    let release!: () => void
    router.beforeEach(() => new Promise<void>(resolve => { release = resolve }))
    const pending = router.push('/full?factory=huakang-a')
    await flushPromises()
    appearance.motion.value = 'off'
    await nextTick()
    release(); await pending; await flushPromises()
    expect(router.currentRoute.value.name).toBe('full')
    expect(nav.entry.value?.to.name).toBe('full')
    expect(animations).toHaveLength(0)
  })
  it('skips late decoration if mounting the real target consumes the whole entry budget', async () => {
    const { router } = await setup()
    let now = 0
    vi.spyOn(performance, 'now').mockImplementation(() => now)
    router.addRoute({ path: '/slow', name: 'slow', component: defineComponent({
      setup() { onMounted(() => { now = 500 }); return () => h('section', [h('h1', 'Ready'), h('button', 'Use now')]) },
    }) })
    await router.push('/slow?factory=huakang-a'); await flushPromises()
    expect(document.querySelector('h1')?.textContent).toBe('Ready')
    expect(document.querySelector('button')?.disabled).toBe(false)
    expect(animations).toHaveLength(0)
  })
})

const homePath = '/modules/production?factory=huakang-a'
async function back(router: Awaited<ReturnType<typeof setup>>['router']) {
  await new Promise<void>(resolve => {
    const stop = router.afterEach(() => { stop(); resolve() })
    router.back()
  })
  await flushPromises()
}
function holdAnimations() {
  const cancel = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, value: function (this: HTMLElement, frames: Keyframe[], options: KeyframeAnimationOptions) {
    animations.push({ target: this, frames, options })
    return { finished: new Promise<void>(() => {}), cancel }
  } })
  return cancel
}
const nextPaint = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()))

describe('V2 alongside the existing route host', () => {
  it('keeps a real source press alive through a pending guard without previewing success', async () => {
    vi.stubEnv('VITE_ROUTE_MOTION_V2_ENABLED', 'true')
    const cancel = holdAnimations(), { router, wrapper } = await setup({ anchors: true })
    let release!: (allowed: boolean) => void
    router.beforeResolve(() => new Promise<boolean>(resolve => { release = resolve }))
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(animations.map(a => a.target.tagName)).toEqual(['ARTICLE'])
    expect(cancel).not.toHaveBeenCalled()
    expect(document.querySelector('[data-page="home"]')).toBeTruthy()
    expect(document.querySelector('.rr-route-motion')).toBeNull()
    release(false); await flushPromises()
    expect(cancel).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.fullPath).toBe(homePath)
  })
  it.each(['/plain?factory=huakang-a', homePath])('keeps the winning native return when an older guard for %s finishes late', async earlierPath => {
    vi.stubEnv('VITE_ROUTE_MOTION_V2_ENABLED', 'true')
    vi.spyOn(performance, 'now').mockReturnValue(10)
    const { router, wrapper } = await setup({ native: true, anchors: true })
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    const gates: (() => void)[] = []
    router.beforeResolve(() => new Promise<void>(resolve => { gates.push(resolve) }))
    const earlier = router.push(earlierPath)
    await vi.waitFor(() => expect(gates).toHaveLength(1))
    const arrived = new Promise<void>(resolve => {
      const stop = router.afterEach((to, _from, failure) => { if (!failure && to.fullPath === homePath) { stop(); resolve() } })
    })
    router.back()
    await vi.waitFor(() => expect(gates).toHaveLength(2))
    gates[0]!(); await earlier; gates[1]!(); await arrived; await flushPromises(); await nextPaint(); await flushPromises()
    expect((document.activeElement as HTMLElement).dataset.routeEntryId).toBe('full')
    expect(animations.filter(a => a.target.matches('.rr-spatial-plane'))).toHaveLength(2)
  })
  it('never restores focus to a newly inert home card', async () => {
    vi.stubEnv('VITE_ROUTE_MOTION_V2_ENABLED', 'true')
    const { router, wrapper } = await setup({ native: true })
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    let restore!: FrameRequestCallback
    vi.stubGlobal('requestAnimationFrame', (fn: FrameRequestCallback) => { restore = fn; return 81 })
    await back(router)
    document.querySelector('article')!.setAttribute('inert', '')
    restore(0); await flushPromises()
    expect(document.activeElement?.tagName).toBe('H1')
    expect(document.querySelector('.rr-route-motion')).toBeNull()
  })
  it('ignores unrelated row styling and releases a replaced target and every owned effect', async () => {
    vi.stubEnv('VITE_ROUTE_MOTION_V2_ENABLED', 'true')
    vi.spyOn(performance, 'now').mockReturnValue(10)
    const cancel = holdAnimations(), { wrapper } = await setup({ anchors: true, native: true })
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(document.querySelector('.rr-spatial-plane')).toBeTruthy()
    const layout = vi.mocked(HTMLElement.prototype.getBoundingClientRect); layout.mockClear()
    const input = document.querySelector('input')!
    input.style.color = 'red'; await flushPromises(); input.className = 'active'; await flushPromises()
    expect(layout).not.toHaveBeenCalled(); expect(document.querySelector('.rr-spatial-plane')).toBeTruthy()
    const header = document.querySelector('[data-rr-motion-target="surface"]')!
    header.replaceWith(header.cloneNode(true)); await flushPromises()
    expect(document.querySelector('.rr-route-motion')).toBeNull()
    expect(cancel).toHaveBeenCalled()
  })
  it('drops a flight when browser intersection tracking reports a purely positional shift', async () => {
    vi.stubEnv('VITE_ROUTE_MOTION_V2_ENABLED', 'true')
    vi.spyOn(performance, 'now').mockReturnValue(10)
    let changed!: () => void
    const disconnect = vi.fn()
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: () => void) { changed = callback }
      observe() {} disconnect = disconnect
    })
    holdAnimations(); const { wrapper } = await setup({ anchors: true, native: true })
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(document.querySelector('.rr-spatial-plane')).toBeTruthy()
    const header = document.querySelector<HTMLElement>('[data-rr-motion-target="surface"]')!
    const rect = header.getBoundingClientRect()
    vi.spyOn(header, 'getBoundingClientRect').mockReturnValue({ ...rect, x: rect.x + 20, left: rect.left + 20, right: rect.right + 20 })
    changed(); await nextTick()
    expect(document.querySelector('.rr-route-motion')).toBeNull()
    expect(disconnect).toHaveBeenCalledOnce()
  })
  it('retains default V1 restoration when a user visits a query, then backs through the original module', async () => {
    const { router, wrapper } = await setup({ native: true, anchors: true })
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(document.querySelector('[data-route-motion-ghost]')).toBeTruthy()
    expect(document.querySelector('[data-rr-spatial-layer]')).toBeNull()
    await router.push('/full?factory=huakang-a&page=2'); await back(router); await back(router); await nextPaint()
    expect((document.activeElement as HTMLElement).dataset.routeEntryId).toBe('full')
  })
  it('owns one surface and icon on confirmed native entry and return and never animates a business root', async () => {
    vi.stubEnv('VITE_ROUTE_MOTION_V2_ENABLED', 'true')
    vi.spyOn(performance, 'now').mockReturnValue(100)
    const cancel = holdAnimations(), { router, wrapper, counts } = await setup({ anchors: true, native: true })
    const push = vi.spyOn(router, 'push')
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(push).toHaveBeenCalledOnce()
    expect(counts.fullMount).toBe(1)
    const layer = document.querySelector<HTMLElement>('[data-rr-spatial-layer]')!
    expect(layer?.matches('[aria-hidden="true"][inert]')).toBe(true)
    expect(layer.querySelectorAll('.rr-spatial-plane,.rr-spatial-icon')).toHaveLength(2)
    expect(layer.querySelector('input, button, table, iframe, [tabindex]')).toBeNull()
    expect(document.querySelector('[data-route-motion-ghost]')).toBeNull()
    const input = document.querySelector('input')!; input.focus(); input.value = 'my draft'
    input.dispatchEvent(new Event('beforeinput', { bubbles: true })); await nextTick()
    expect(document.querySelector('.rr-route-motion')).toBeNull()
    expect(document.activeElement).toBe(input); expect(input.value).toBe('my draft'); expect(cancel).toHaveBeenCalled()
    await router.push('/full?factory=huakang-a&page=2'); await back(router); await back(router); await nextPaint(); await flushPromises()
    expect((document.activeElement as HTMLElement).dataset.routeEntryId).toBe('full')
    expect(document.querySelectorAll('[data-rr-spatial-layer]')).toHaveLength(1)
    const dockingCard = document.querySelector<HTMLElement>('[data-rr-motion-docking]')!
    expect(dockingCard).toBe(document.activeElement)
    expect(animations.filter(effect => effect.target.matches('.rr-spatial-plane'))).toHaveLength(2)
    expect(animations.some(effect => effect.target.matches('[data-page], #app-content, .app-shell, .rr-route-fullpage'))).toBe(false)
    expect(animations.every(effect => effect.options.fill === 'none')).toBe(true)
    window.dispatchEvent(new Event('resize')); await nextTick()
    expect(document.querySelector('.rr-route-motion')).toBeNull()
    expect(dockingCard.hasAttribute('data-rr-motion-docking')).toBe(false)
  })
  it('lets deliberate input win while native scroll restoration is waiting for the next frame', async () => {
    vi.stubEnv('VITE_ROUTE_MOTION_V2_ENABLED', 'true')
    const { router, wrapper } = await setup({ native: true })
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    vi.mocked(window.scrollTo).mockClear()
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 812))
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    await back(router)
    document.dispatchEvent(new WheelEvent('wheel', { bubbles: true })); await flushPromises()
    expect(window.scrollTo).not.toHaveBeenCalled()
    expect((document.activeElement as HTMLElement).dataset.routeEntryId).toBeUndefined()
    expect(document.querySelector('.rr-route-motion')).toBeNull()
  })
  it.each(['missing anchors', 'missing WAAPI', 'global off', 'calm', 'reduced', 'hidden'])('keeps the destination usable with %s', async situation => {
    vi.stubEnv('VITE_ROUTE_MOTION_V2_ENABLED', 'true')
    if (situation === 'global off') vi.stubEnv('VITE_ROUTE_MOTION_ENABLED', 'false')
    const { wrapper, counts } = await setup({ anchors: situation !== 'missing anchors' })
    if (situation === 'missing WAAPI') Reflect.deleteProperty(HTMLElement.prototype, 'animate')
    if (situation === 'calm') appearance.motion.value = 'calm'
    if (situation === 'reduced') { reduced = true; for (const listener of mediaListeners) listener({ matches: true } as MediaQueryListEvent) }
    if (situation === 'hidden') { vi.spyOn(document, 'hidden', 'get').mockReturnValue(true); document.dispatchEvent(new Event('visibilitychange')) }
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(counts.fullMount).toBe(1); expect(document.querySelector('button')!.disabled).toBe(false)
    expect(document.querySelector('.rr-route-motion')).toBeNull()
    const targetEffects = animations.filter(a => !a.target.matches('article'))
    if (situation === 'missing anchors' || situation === 'calm') expect(targetEffects.map(a => a.target.tagName)).toEqual(['H1'])
    else expect(targetEffects).toHaveLength(0)
  })
  it('discards an aged capture after a slow guard and rejects a push pretending to return', async () => {
    vi.stubEnv('VITE_ROUTE_MOTION_V2_ENABLED', 'true')
    const { router, wrapper } = await setup({ anchors: true, native: true })
    let now = 100; vi.spyOn(performance, 'now').mockImplementation(() => now)
    router.beforeResolve(() => { now += 1500 })
    await wrapper.get('article').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(document.querySelector('[data-page="full"]')).toBeTruthy()
    expect(animations.some(a => a.target.matches('.rr-spatial-plane'))).toBe(false)
    await router.push(homePath); await flushPromises(); await nextPaint()
    expect(document.activeElement?.tagName).toBe('H1')
    expect(document.querySelector('.rr-route-motion')).toBeNull()
  })
})

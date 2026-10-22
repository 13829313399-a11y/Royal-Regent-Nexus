import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { defineComponent } from 'vue'
import { classifyNavigation, routeVisualIdentity } from '../classifyNavigation'
import { createRouteMotionNavigation, type EntryOrigin, type MotionCommit } from '../navigation'
import { createRouteMotionCoordinator } from '../createRouteMotionCoordinator'
import { acceptsEntryActivation, resolveMotionDestination } from '../useModuleEntryMotion'

const Page = defineComponent({ template: '<main><h1>Page</h1></main>' })
const makeRouter = () => createRouter({ history: createMemoryHistory(), routes: [
  { path: '/', name: 'dashboard', component: Page },
  { path: '/modules/:department', name: 'modules-department', component: Page },
  { path: '/plain/:id?', name: 'plain', component: Page },
  { path: '/full', component: Page, meta: { fullPage: true }, children: [
    { path: '', redirect: '/full/a' }, { path: 'a', name: 'full-a', component: Page }, { path: 'b', name: 'full-b', component: Page },
  ] },
  { path: '/modules/:department/:module', name: 'module-detail', component: Page },
  { path: '/login', name: 'login', component: Page, meta: { fullPage: true, requiresAuth: false } },
  { path: '/forbidden', name: 'forbidden', component: Page, meta: { fullPage: true } },
  { path: '/alias', redirect: '/full/a' },
] })
const origin = (router: Router, path: string): EntryOrigin => ({
  icon: Page, accent: '#0f766e', soft: '#e5f5f2', rect: null, viewport: [1440, 900], triggerId: 'full',
  homeId: 'home:production', homePath: '/modules/production', historyPosition: 1, scroll: [0, 500, 0, 0],
  expectedId: routeVisualIdentity(resolveMotionDestination(router, path)).id, expectedPath: path, context: 'account:factory',
})
const deferred = () => { let resolve!: () => void; const promise = new Promise<void>(done => { resolve = done }); return { promise, resolve } }
afterEach(() => vi.restoreAllMocks())

describe('final route semantics', () => {
  const router = makeRouter(), resolve = (url: string) => router.resolve(url)
  it.each([
    ['/', '/modules/production', 'home-to-department'],
    ['/modules/production', '/plain', 'home-to-module'],
    ['/modules/production', '/full/a', 'home-to-module'],
    ['/full/a', '/modules/production', 'module-to-home'],
    ['/plain', '/full/a', 'module-to-module'],
    ['/full/a', '/full/b', 'none'],
    ['/plain/1', '/plain/2?page=3#rows', 'none'],
    ['/plain?factory=a', '/plain?factory=b', 'none'],
    ['/modules/production?factory=a', '/full/a?factory=b', 'none'],
    ['/modules/production', '/login', 'none'],
    ['/full/a', '/forbidden', 'none'],
    ['/login', '/full/a', 'none'],
    ['/modules/engineering/bom', '/modules/engineering/ecn', 'module-to-module'],
  ])('%s → %s is %s', (from, to, expected) => expect(classifyNavigation(resolve(to), resolve(from))).toBe(expected))
  it('follows registered redirects without navigating', () => {
    expect(resolveMotionDestination(router, '/alias').name).toBe('full-a')
    expect(resolveMotionDestination(router, '/full').name).toBe('full-a')
    expect(router.currentRoute.value.matched).toHaveLength(0)
  })
})

describe('navigation ownership', () => {
  async function setup() {
    const router = makeRouter(), nav = createRouteMotionNavigation(router), commits: MotionCommit[] = []
    nav.attach(() => 'account:factory', () => true, value => { if (value) commits.push(value) })
    await router.push('/modules/production')
    commits.length = 0
    return { router, nav, commits }
  }
  it('lets the last allowed A → B → C intent win, including a late cancelled guard', async () => {
    const { router, nav, commits } = await setup(), wait = deferred(), entered = deferred()
    router.beforeEach(async to => { if (to.path === '/full/a') { entered.resolve(); await wait.promise } })
    nav.recordIntent(origin(router, '/full/a'))
    const old = router.push('/full/a'); await entered.promise
    nav.recordIntent(origin(router, '/plain'))
    await router.push('/plain')
    const winner = commits.at(-1)!
    wait.resolve(); await old
    expect(router.currentRoute.value.path).toBe('/plain')
    expect(nav.isCurrent(winner.token)).toBe(true)
    expect(commits.map(item => item.to.path)).toEqual(['/plain'])
    nav.dispose()
  })
  it('does not revive an older target when the latest intent is denied', async () => {
    const { router, nav, commits } = await setup(), wait = deferred(), entered = deferred()
    router.beforeEach(async to => {
      if (to.path === '/full/a') { entered.resolve(); await wait.promise }
      if (to.path === '/plain') return false
    })
    nav.recordIntent(origin(router, '/full/a')); const old = router.push('/full/a'); await entered.promise
    nav.recordIntent(origin(router, '/plain')); await router.push('/plain')
    wait.resolve(); await old
    expect(router.currentRoute.value.path).toBe('/modules/production')
    expect(commits).toHaveLength(0)
    nav.dispose()
  })
  it('uses only final destinations and excludes login redirects', async () => {
    const { router, nav, commits } = await setup()
    router.beforeEach(to => to.path === '/plain' ? '/login' : true)
    nav.recordIntent(origin(router, '/plain')); await router.push('/plain')
    expect(commits.at(-1)).toMatchObject({ kind: 'none', origin: null })
    expect(nav.entry.value).toBeNull()
    nav.dispose()
  })
  it('retains presentation for a canonical redirect, but does not replay duplicates/query', async () => {
    const { router, nav, commits } = await setup()
    nav.recordIntent(origin(router, '/alias')); await router.push('/alias')
    expect(commits.at(-1)).toMatchObject({ kind: 'home-to-module', origin: { expectedPath: '/alias' } })
    const count = commits.length
    await router.push('/full/a')
    expect(commits).toHaveLength(count)
    await router.push('/full/a?q=2')
    expect(commits.at(-1)?.kind).toBe('none')
    nav.dispose()
  })
  it('cleans thrown errors and allows a subsequent navigation', async () => {
    const { router, nav, commits } = await setup()
    router.beforeEach(to => { if (to.path === '/plain') throw Error('controlled import/guard failure') })
    nav.recordIntent(origin(router, '/plain'))
    await expect(router.push('/plain')).rejects.toThrow('controlled')
    nav.recordIntent(origin(router, '/full/a')); await router.push('/full/a')
    expect(commits.map(item => item.to.path)).toEqual(['/full/a'])
    nav.dispose()
  })
  it('invalidates a pending visual intent at an identity boundary', async () => {
    const { router, nav, commits } = await setup(), wait = deferred(), entered = deferred()
    router.beforeEach(async () => { entered.resolve(); await wait.promise })
    nav.recordIntent(origin(router, '/full/a')); const pending = router.push('/full/a'); await entered.promise
    nav.invalidate(); wait.resolve(); await pending
    expect(commits).toHaveLength(0)
    expect(nav.entry.value).toBeNull()
    nav.dispose()
  })
})

describe('animation resources', () => {
  it('handles cancel rejection and late finished callbacks without releasing a newer resource', async () => {
    const coordinator = createRouteMotionCoordinator(), element = document.createElement('div')
    let reject!: (reason: unknown) => void
    const cancel = vi.fn(() => reject(new DOMException('cancelled', 'AbortError')))
    const animation = { finished: new Promise((_resolve, fail) => { reject = fail }), cancel } as unknown as Animation
    element.animate = vi.fn(() => animation)
    const old = coordinator.begin()
    coordinator.animate(old, element, [{ opacity: 0 }, { opacity: 1 }], { duration: 180 })
    const next = coordinator.begin(), release = vi.fn()
    coordinator.own(next, release)
    await Promise.resolve()
    expect(cancel).toHaveBeenCalled()
    expect(coordinator.current(old)).toBe(false)
    expect(release).not.toHaveBeenCalled()
    coordinator.dispose()
    expect(release).toHaveBeenCalledOnce()
    expect(element.style.opacity).toBe('')
  })
  it('is immediately usable for missing APIs, zero duration and synchronous failure', () => {
    const coordinator = createRouteMotionCoordinator(), token = coordinator.begin(), element = document.createElement('main')
    expect(coordinator.animate(token, element, [{ opacity: 0 }], { duration: 100 })).toBeUndefined()
    element.animate = vi.fn(() => { throw Error('unsupported') })
    expect(coordinator.animate(token, element, [{ opacity: 0 }], { duration: 0 })).toBeUndefined()
    expect(coordinator.animate(token, element, [{ opacity: 0 }], { duration: 100 })).toBeUndefined()
    expect(element.style.cssText).toBe('')
    coordinator.dispose()
  })
  it('leaves modified clicks, downloads and prevented activations native', () => {
    expect(acceptsEntryActivation(new MouseEvent('click'))).toBe(true)
    for (const options of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
      expect(acceptsEntryActivation(new MouseEvent('click', options))).toBe(false)
    }
    const prevented = new MouseEvent('click', { cancelable: true }); prevented.preventDefault()
    expect(acceptsEntryActivation(prevented)).toBe(false)
    const anchor = document.createElement('a'); anchor.download = 'export.xlsx'
    anchor.addEventListener('click', event => expect(acceptsEntryActivation(event)).toBe(false))
    anchor.dispatchEvent(new MouseEvent('click'))
  })
})

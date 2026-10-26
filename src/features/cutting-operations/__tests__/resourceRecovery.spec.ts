import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { installCuttingResourceRecovery } from '../resourceRecovery'

let recovery: ReturnType<typeof installCuttingResourceRecovery> | undefined
afterEach(() => { recovery?.dispose(); vi.restoreAllMocks() })
const target = '/modules/production/cutting/dashboard?factory=huakang-c&day=2026-10-21'
async function setup(message: string, factory = 'huakang-c') {
  const component = { template: '<div />' }, navigate = vi.fn()
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component }, { path: '/other', component },
    { path: '/modules/production/cutting/:page', component: () => Promise.reject(new Error(message)) },
  ] })
  recovery = installCuttingResourceRecovery(router, navigate)
  await router.push('/')
  await expect(router.push(target.replace('huakang-c', factory))).rejects.toThrow(message)
  return { router, navigate, recovery }
}

describe('cutting lazy resource recovery', () => {
  it.each(['Failed to fetch dynamically imported module: /assets/cutting.js', 'Unable to preload CSS for /assets/cutting.css'])('keeps the current page and requires a clean document after %s', async message => {
    const { router, navigate, recovery } = await setup(message)
    expect(router.currentRoute.value.path).toBe('/')
    expect(recovery.failure.value).toEqual({ target, title: '生产看板' })
    const failure = await router.push(target)
    expect(failure).toBeTruthy()
    expect(router.currentRoute.value.path).toBe('/')
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
    recovery.reload(); recovery.reload()
    expect(navigate).toHaveBeenCalledExactlyOnceWith(target)
  })
  it.each(['business validation failed', 'forbidden'])('does not mislabel a non-resource error: %s', async message => {
    expect((await setup(message)).recovery.failure.value).toBeUndefined()
  })
  it('does not provide a recovery target for a foreign factory', async () => {
    expect((await setup('Unable to preload CSS for /assets/cutting.css', 'huaxing')).recovery.failure.value).toBeUndefined()
  })
  it('retains the page and explains an offline reload attempt', async () => {
    const { recovery, navigate } = await setup('Failed to fetch dynamically imported module')
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    recovery.reload()
    expect(navigate).not.toHaveBeenCalled()
    expect(recovery.feedback.value).toContain('页面未重新加载')
    expect(recovery.failure.value?.target).toBe(target)
  })
  it('honors existing unsaved and unknown-operation unload guards', async () => {
    const { recovery, navigate } = await setup('Unable to preload CSS for /assets/cutting.css')
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
    const guard = (e: Event) => e.preventDefault()
    window.addEventListener('beforeunload', guard)
    try {
      recovery.reload()
      expect(navigate).not.toHaveBeenCalled()
      expect(recovery.feedback.value).toContain('未保存内容或待核实操作')
      expect(recovery.failure.value?.target).toBe(target)
    } finally { window.removeEventListener('beforeunload', guard) }
    recovery.reload()
    expect(navigate).toHaveBeenCalledExactlyOnceWith(target)
  })
  it.each(['auth-session-boundary-changed', 'authorization-context-changed'])('clears private targets on %s while still requiring healthy resources for future entry', async event => {
    const { router, recovery, navigate } = await setup('Failed to fetch dynamically imported module')
    window.dispatchEvent(new Event(event))
    recovery.reload()
    expect(recovery.failure.value).toBeUndefined()
    expect(navigate).not.toHaveBeenCalled()
    await router.push(target)
    expect(recovery.failure.value?.target).toBe(target)
    expect(router.currentRoute.value.path).toBe('/')
  })
  it('does not let an older error overwrite a later destination', async () => {
    let reject!: (error: Error) => void
    const component = { template: '<div />' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', component }, { path: '/other', component },
      { path: '/modules/production/cutting/:page', component: () => new Promise((_resolve, no) => { reject = no }) },
    ] })
    recovery = installCuttingResourceRecovery(router, vi.fn())
    await router.push('/')
    const old = router.push(target).catch(() => undefined)
    await vi.waitFor(() => expect(reject).toBeTypeOf('function'))
    await router.push('/other')
    reject(new Error('Failed to fetch dynamically imported module')); await old
    expect(router.currentRoute.value.path).toBe('/other')
    expect(recovery.failure.value).toBeUndefined()
  })
  it('keeps a cancelled component leave guard in control', async () => {
    const { router, recovery } = await setup('Unable to preload CSS for /assets/cutting.css')
    await router.push('/other')
    const remove = router.beforeEach(() => false)
    await router.push('/other?keep=1'); remove()
    expect(router.currentRoute.value.fullPath).toBe('/other')
    expect(recovery.failure.value).toBeUndefined()
  })
})

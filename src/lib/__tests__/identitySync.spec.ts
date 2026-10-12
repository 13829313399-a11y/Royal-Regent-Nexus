import { createPinia, setActivePinia } from 'pinia'
import type { Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
const api = vi.hoisted(() => ({ getMe: vi.fn() }))
const revalidate = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
vi.mock('@/api/auth', () => ({ authApi: api }))
vi.mock('@/router', () => ({ refreshAndRevalidateAuthorization: revalidate }))
vi.mock('@/lib/postLoginRedirect', () => ({ resolvePostLoginRedirect: () => '/modules?tab=mine#work' }))
import { installIdentitySync } from '../identitySync'
import { useAuthStore } from '@/stores/auth'
import { announceSessionBoundary } from '../authenticationGeneration'
const user = { id: 'a', username: 'a', display_name: '测试', roles: [], permissions: [], grants: [], factory_scopes: [], department_scopes: [], force_password_change: false }
let dispose: (() => void) | undefined
let channel: FakeChannel
class FakeChannel {
  onmessage: ((event: { data: string }) => void) | null = null
  postMessage = vi.fn()
  close = vi.fn()
  constructor(public name: string) { channel = this }
}
function setup(name = 'login') {
  const pinia = createPinia(); setActivePinia(pinia)
  const auth = useAuthStore(pinia)
  const router = { currentRoute: { value: { name, query: {}, fullPath: '/modules', meta: { requiresAuth: name !== 'login' } } }, replace: vi.fn().mockResolvedValue(undefined) }
  dispose = installIdentitySync(router as unknown as Router, pinia)
  return { auth, router }
}
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks()
  vi.stubGlobal('BroadcastChannel', FakeChannel)
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})
afterEach(() => { dispose?.(); dispose = undefined; vi.useRealTimers(); vi.unstubAllGlobals() })
describe('cross-tab session boundary confirmation', () => {
  it('clears private state immediately, confirms the cookie identity, and never echoes', async () => {
    const { auth, router } = setup()
    auth.applySession(user)
    let resolve!: (value: typeof user) => void
    api.getMe.mockImplementationOnce(() => new Promise(r => { resolve = r }))
    channel.onmessage?.({ data: 'session-boundary-changed' })
    expect(auth.currentUser).toBeNull(); expect(auth.isConfirmingSession).toBe(true)
    resolve({ ...user, id: 'b', username: 'b' }); await flushPromises()
    expect(auth.currentUser?.id).toBe('b'); expect(auth.isConfirmingSession).toBe(false)
    expect(router.replace).toHaveBeenCalledWith('/modules?tab=mine#work')
    expect(channel.postMessage).not.toHaveBeenCalled()
    announceSessionBoundary()
    expect(channel.postMessage).toHaveBeenCalledExactlyOnceWith('session-boundary-changed')
    expect(channel.name).toBe('rr-identity-refresh')
  })
  it('confirms a hidden tab on visibility and sends expired sessions to login', async () => {
    const { auth, router } = setup('home'); auth.applySession(user)
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    channel.onmessage?.({ data: 'session-boundary-changed' })
    expect(api.getMe).not.toHaveBeenCalled(); expect(auth.currentUser).toBeNull()
    api.getMe.mockRejectedValueOnce({ response: { status: 401 } })
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange')); await flushPromises()
    expect(router.replace).toHaveBeenCalledWith({ name: 'login', query: { redirect: '/modules' } })
    expect(auth.isConfirmingSession).toBe(false)
  })
  it('discards an old boundary response and always removes the overlay after navigation failure', async () => {
    const { auth, router } = setup()
    let old!: (value: typeof user) => void
    api.getMe.mockImplementationOnce(() => new Promise(r => { old = r }))
    channel.onmessage?.({ data: 'session-boundary-changed' })
    api.getMe.mockResolvedValueOnce({ ...user, id: 'new' })
    router.replace.mockRejectedValueOnce(new Error('chunk unavailable'))
    channel.onmessage?.({ data: 'session-boundary-changed' }); await flushPromises()
    old(user); await flushPromises()
    expect(auth.currentUser?.id).toBe('new'); expect(auth.isConfirmingSession).toBe(false)
    expect(channel.postMessage).not.toHaveBeenCalled()
  })
  it('removes all listeners and timers on disposal', async () => {
    setup(); dispose?.(); dispose = undefined
    announceSessionBoundary(); document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(100_000)
    expect(channel.close).toHaveBeenCalledOnce(); expect(channel.postMessage).not.toHaveBeenCalled()
    expect(api.getMe).not.toHaveBeenCalled()
  })
})

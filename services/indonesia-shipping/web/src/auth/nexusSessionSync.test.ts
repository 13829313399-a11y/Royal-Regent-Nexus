import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { AuthSession } from './permissions'
let getStoredSession: typeof import('./permissions').getStoredSession
let saveSession: typeof import('./permissions').saveSession
let getSessionGeneration: typeof import('./permissions').getSessionGeneration
let installNexusSessionSync: typeof import('./nexusSessionSync').installNexusSessionSync
let validateExportSession: typeof import('./validateExportSession').validateExportSession
const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api/client', () => ({ api: { get: mocks.get } }))
let channel: { onmessage?: (event: { data: string }) => void }
let stop: (() => void) | undefined
const session = (identity = 'first'): AuthSession => ({ nexus: true, identity, factoryId: 'huaxing', token: '', displayName: '验收', userbqrpower: '111111111', usereditpower: '000000000' })
beforeEach(async () => {
  vi.resetModules()
  vi.useFakeTimers()
  const document = Object.assign(new EventTarget(), { visibilityState: 'visible', querySelector: () => ({ content: '/api/indonesia-shipping/huaxing/app/' }) })
  vi.stubGlobal('document', document)
  vi.stubGlobal('window', new EventTarget())
  vi.stubGlobal('BroadcastChannel', class { onmessage = undefined; close() {} constructor() { channel = this } })
  ;({ getStoredSession, saveSession, getSessionGeneration } = await import('./permissions'))
  ;({ installNexusSessionSync } = await import('./nexusSessionSync'))
  ;({ validateExportSession } = await import('./validateExportSession'))
  saveSession(null); mocks.get.mockReset()
})
afterEach(() => { stop?.(); stop = undefined; saveSession(null); vi.useRealTimers(); vi.unstubAllGlobals() })
const flush = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() }

it('keeps unchanged identity and drafts during ordinary refresh, clears revoked access on focus', async () => {
  const load = vi.fn().mockResolvedValue(session())
  stop = installNexusSessionSync(load, () => {})
  await flush()
  const generation = getSessionGeneration()
  await vi.advanceTimersByTimeAsync(45000)
  expect(getSessionGeneration()).toBe(generation)
  load.mockRejectedValueOnce(new Error('revoked'))
  window.dispatchEvent(new Event('focus')); await flush()
  expect(getStoredSession()).toBeNull()
})
it('immediately clears a logout broadcast and ignores an older in-flight response', async () => {
  saveSession(session())
  let finish!: (value: AuthSession) => void
  const load = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockRejectedValue(new Error('logged out'))
  stop = installNexusSessionSync(load, () => {})
  channel.onmessage?.({ data: 'session-boundary-changed' })
  expect(getStoredSession()).toBeNull()
  finish(session()); await flush()
  expect(getStoredSession()).toBeNull()
})
it('rechecks time-limited authorization at the server-supplied transition', async () => {
  const load = vi.fn().mockResolvedValueOnce({ ...session(), serverNow: '2026-11-09T00:00:00Z', nextTransitionAt: '2026-11-09T00:00:01Z' }).mockResolvedValue(session('changed'))
  stop = installNexusSessionSync(load, () => {}); await flush()
  await vi.advanceTimersByTimeAsync(1100)
  expect(getStoredSession()).toBeNull()
  saveSession(session('another-login'))
  expect(getStoredSession()).toBeNull()
})
it('blocks cached-row export after revoked or changed permissions', async () => {
  saveSession(session()); mocks.get.mockResolvedValue({ data: session('changed') })
  expect(await validateExportSession()).toBe(false)
  expect(getStoredSession()).toBeNull()
  mocks.get.mockRejectedValue(new Error('403'))
  expect(await validateExportSession()).toBe(false)
  expect(getStoredSession()).toBeNull()
})
it('allows original export only for the current unchanged owner', async () => {
  saveSession(session()); mocks.get.mockResolvedValue({ data: session() })
  expect(await validateExportSession()).toBe(true)
  let finish!: (value: unknown) => void
  mocks.get.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const result = validateExportSession(); saveSession(session('another-login'))
  finish({ data: session() })
  expect(await result).toBe(false)
  expect(getStoredSession()?.identity).toBe('another-login')
})

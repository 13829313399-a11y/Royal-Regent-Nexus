import { afterEach, expect, it, vi } from 'vitest'
vi.mock('antd', () => ({ message: { error: vi.fn() } }))
afterEach(() => { vi.unstubAllGlobals(); vi.resetModules() })
it('cannot resume an old batch under a new login after invalidation', async () => {
  vi.stubGlobal('document', { querySelector: () => ({ content: '/api/indonesia-shipping/huaxing/app/' }) })
  const window = Object.assign(new EventTarget(), { location: { origin: 'http://localhost' }, parent: null })
  window.parent = window as any
  vi.stubGlobal('window', window)
  const { api } = await import('./client')
  const { saveSession, invalidateNexusSession, getStoredSession } = await import('../auth/permissions')
  const owner = { nexus: true, identity: 'A', token: '', displayName: 'A', userbqrpower: '111111111', usereditpower: '111111111' }
  saveSession(owner)
  let complete!: () => void
  const transport = vi.fn(config => new Promise<any>(resolve => { complete = () => resolve({ status: 200, statusText: 'OK', headers: {}, data: {}, config }) }))
  api.defaults.adapter = transport
  const first = api.patch('/purchase/1', {})
  await Promise.resolve(); await Promise.resolve()
  invalidateNexusSession(); saveSession({ ...owner, identity: 'B' })
  complete()
  await expect(first).rejects.toMatchObject({ code: 'ERR_CANCELED' })
  await expect(api.patch('/purchase/2', {})).rejects.toMatchObject({ code: 'ERR_CANCELED' })
  expect(transport).toHaveBeenCalledTimes(1)
  expect(getStoredSession()).toBeNull()
})

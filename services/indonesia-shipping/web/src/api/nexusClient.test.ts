import { afterEach, expect, it, vi } from 'vitest'
vi.mock('antd', () => ({ message: { error: vi.fn() } }))
afterEach(() => { vi.unstubAllGlobals(); vi.resetModules() })
it('cannot resume an old batch under a new login after invalidation', async () => {
  vi.stubGlobal('document', { querySelector: () => ({ content: '/api/indonesia-shipping/huaxing/app/' }) })
  const window = Object.assign(new EventTarget(), { location: { origin: 'http://localhost' }, parent: null })
  window.parent = window as any
  vi.stubGlobal('window', window)
  const { api } = await import('./client')
  const refreshed = vi.fn()
  window.addEventListener('material-alerts-refresh', refreshed)
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
  expect(refreshed).not.toHaveBeenCalled()
})

it('refreshes alert statistics only after successful business writes', async () => {
  vi.stubGlobal('document', { querySelector: () => null })
  vi.stubGlobal('localStorage', { getItem: () => null })
  const target = new EventTarget()
  vi.stubGlobal('window', target)
  const refreshed = vi.fn()
  target.addEventListener('material-alerts-refresh', refreshed)
  const { api } = await import('./client')
  api.defaults.adapter = async config => ({ status: 200, statusText: 'OK', headers: {}, data: {}, config })
  await api.get('/material-alerts/stats')
  expect(refreshed).not.toHaveBeenCalled()
  await api.put('/material-alerts/adjustment', { status: '已送完' })
  expect(refreshed).toHaveBeenCalledTimes(1)
  api.defaults.adapter = async () => { throw new Error('save failed') }
  await expect(api.put('/material-alerts/adjustment', {})).rejects.toThrow('save failed')
  expect(refreshed).toHaveBeenCalledTimes(1)
})

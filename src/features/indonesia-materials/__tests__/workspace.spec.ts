import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, reactive } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import { createMaterialsWorkspace, type MaterialsWorkspace } from '../workspace'
import { useVisibleModules } from '@/composables/useVisibleModules'
import { savedBuckets } from './draftMemory'
vi.mock('../draftPersistence', async importOriginal => {
  const original = await importOriginal<typeof import('../draftPersistence')>()
  const { memoryDatabase } = await import('./draftMemory')
  return { ...original, createDraftPersistence: () => original.createDraftPersistence(memoryDatabase) }
})

const mocks = vi.hoisted(() => ({
  app: {} as Data, auth: {} as Data, generation: 0,
  api: { workspace: vi.fn(), command: vi.fn(), preview: vi.fn(), download: vi.fn() },
}))
vi.mock('@/stores/app', () => ({ useAppStore: () => mocks.app }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('@/api/indonesiaMaterials', () => ({ indonesiaMaterialsApi: mocks.api }))
vi.mock('@/lib/authenticationGeneration', () => ({ getAuthenticationGeneration: () => mocks.generation }))
vi.mock('@/lib/http', () => ({ getApiErrorMessage: (cause: Error) => cause.message }))

const material: MaterialRecord = { id: 'material-private', kind: 'material', version: 2, data: { code: 'SCREW', name: '螺丝' } }
function response(permissions = ['read', 'write', 'receipt_confirm', 'export']) {
  return { records: [structuredClone(material)], board: [], permissions }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function failure(status?: number) { return Object.assign(new Error('请求失败'), status ? { response: { status } } : {}) }
const cleanup: (() => void)[] = []
function setup() {
  let ws!: MaterialsWorkspace
  const wrapper = mount(defineComponent({ setup() { ws = createMaterialsWorkspace(); return () => h('div') } }))
  cleanup.push(() => wrapper.unmount())
  return ws
}
beforeEach(() => {
  savedBuckets.clear()
  vi.resetAllMocks()
  mocks.app = reactive({ activeFactoryId: 'huaxing', activeProductionFactory: { id: 'huadeng' } })
  mocks.auth = reactive({ currentUser: { id: 'user-a', identity: { employment_epoch: 1 } }, authorizationVersion: 1, permissions: [], grants: [], effectiveAccess: [] })
  mocks.generation = 0
  mocks.api.workspace.mockResolvedValue(response())
  mocks.api.command.mockResolvedValue({ record: material })
})
afterEach(() => { cleanup.splice(0).forEach(close => close()) })

describe('materials factory and identity boundaries', () => {
  it.each(['group', 'huaxing', 'huakang-c'])('keeps the selected %s scope in the existing business card link', (factory) => {
    mocks.app.activeFactoryId = factory
    mocks.auth.can = () => true
    mocks.auth.canAny = () => true
    const module = useVisibleModules('sales-business').value.find(item => item.id === 'indonesia-material-shipment')
    expect(module?.route).toBe(`/modules/sales-business/indonesia-material-shipment?factory=${factory}`)
  })

  it('requires an explicit factory and never uses the production fallback', async () => {
    mocks.app.activeFactoryId = 'group'
    const ws = setup()
    await flushPromises()
    expect(ws.factory).toBe('')
    expect(mocks.api.workspace).not.toHaveBeenCalled()
    expect(await ws.run('material_save', {})).toBe(false)
    mocks.app.activeFactoryId = 'huakang-a'
    await flushPromises()
    expect(mocks.api.workspace).toHaveBeenCalledExactlyOnceWith('huakang-a')
  })

  it('clears private records immediately and ignores the previous factory response', async () => {
    const old = deferred<ReturnType<typeof response>>()
    mocks.api.workspace.mockReturnValueOnce(old.promise)
    const ws = setup()
    mocks.app.activeFactoryId = 'huadeng'
    expect(ws.records).toEqual([])
    await flushPromises()
    old.resolve({ ...response(), records: [{ ...material, id: 'old-factory' }] })
    await flushPromises()
    expect(ws.records[0]?.id).toBe('material-private')
    expect(ws.factory).toBe('huadeng')
    expect(ws.loading).toBe(false)
  })

  it('preserves same-identity refresh but clears pending work on identity or session change', async () => {
    const ws = setup(); await flushPromises()
    const initial = ws.scopeEpoch
    mocks.auth.currentUser = { id: 'user-a', identity: { employment_epoch: 1 } }
    await flushPromises()
    expect(ws.scopeEpoch).toBe(initial)
    mocks.api.command.mockRejectedValueOnce(failure())
    await ws.run('material_save', { code: 'private draft' })
    mocks.auth.currentUser = { id: 'user-b', identity: { employment_epoch: 2 } }
    expect(ws.records).toEqual([])
    expect(ws.pending).toBeNull()
    expect(ws.scopeEpoch).toBeGreaterThan(initial)
    await flushPromises()
    mocks.generation++
    window.dispatchEvent(new Event('auth-session-boundary-changed'))
    expect(ws.records).toEqual([])
  })

  it('keeps records and unresolved work when a session refresh only advances the server clock', async () => {
    mocks.auth.currentUser.identity.server_now = '2026-10-21T01:00:00Z'
    const ws = setup(); await flushPromises()
    const epoch = ws.scopeEpoch
    mocks.api.command.mockRejectedValueOnce(failure())
    await ws.run('product_save', { code: 'unsaved-product' })
    const operation = ws.pending?.operation_id
    mocks.auth.currentUser = { ...mocks.auth.currentUser, identity: { ...mocks.auth.currentUser.identity, server_now: '2026-10-21T01:00:45Z' } }
    await flushPromises()
    expect(ws.scopeEpoch).toBe(epoch)
    expect(ws.records[0]?.id).toBe('material-private')
    expect(ws.pending?.operation_id).toBe(operation)
    expect(mocks.api.workspace).toHaveBeenCalledTimes(1)
  })

  it.each(['employment_epoch', 'identity_version', 'effective_context_key'])('still invalidates private work when stable identity field %s changes', async field => {
    mocks.auth.currentUser.identity = { employment_epoch: 1, identity_version: 1, effective_context_key: 'context-a' }
    const ws = setup(); await flushPromises()
    const epoch = ws.scopeEpoch
    mocks.api.command.mockRejectedValueOnce(failure())
    await ws.run('product_save', { code: 'private-product' })
    mocks.auth.currentUser.identity[field] = field === 'effective_context_key' ? 'context-b' : 2
    expect(ws.records).toEqual([])
    expect(ws.pending).toBeNull()
    expect(ws.scopeEpoch).toBeGreaterThan(epoch)
    await flushPromises()
    expect(mocks.api.workspace).toHaveBeenCalledTimes(2)
  })

  it('does not reload or publish an old command result into a new factory', async () => {
    const ws = setup(); await flushPromises()
    const old = deferred<{ record: MaterialRecord }>()
    mocks.api.command.mockReturnValueOnce(old.promise)
    const saving = ws.run('material_save', { code: 'old' })
    mocks.app.activeFactoryId = 'huadeng'
    await flushPromises()
    old.resolve({ record: material })
    expect(await saving).toBe(false)
    expect(mocks.api.workspace.mock.calls).toEqual([['huaxing'], ['huadeng']])
    expect(ws.notice).toBe('')
  })
})

describe('materials permissions and command receipts', () => {
  it('persists the original operation before the first HTTP request and recovers it on a new workspace', async () => {
    const ws = setup(); await flushPromises()
    mocks.api.command.mockImplementationOnce(async command => {
      expect([...savedBuckets.values()].find(bucket => bucket.pending)?.pending?.command).toEqual(command)
      throw failure()
    })
    await ws.run('material_save', { code: 'recover' })
    const original = JSON.parse(JSON.stringify(ws.pending))
    const reopened = setup(); await flushPromises()
    expect(reopened.pending).toEqual(original); expect(reopened.locked).toBe(true)
    await reopened.run('material_save', { code: 'duplicate' })
    expect(mocks.api.command).toHaveBeenCalledTimes(1)
    await reopened.retry()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(original)
  })

  it('locks ordinary submissions when a saved operation cannot be recognized', async () => {
    savedBuckets.set(JSON.stringify(['v1', 'user-a', 1, 'huaxing']), { format: 1, drafts: {}, pending: { command: { action: 'unexpected' } as never, writer: 'old' } })
    const ws = setup(); await flushPromises()
    expect(ws.locked).toBe(true)
    expect(ws.localDrafts.error).toContain('无法识别')
    expect(await ws.run('material_save', {})).toBe(false)
    expect(mocks.api.command).not.toHaveBeenCalled()
  })

  it('does not run an old owner callback after another page supplies a different pending operation', async () => {
    const ws = setup(); await flushPromises()
    const oldCompletion = vi.fn()
    mocks.api.command.mockRejectedValueOnce(failure())
    await ws.run('material_save', { code: 'old' }, undefined, oldCompletion)
    const bucket = [...savedBuckets.values()][0]!
    bucket.pending = { writer: 'other-page', command: { ...bucket.pending!.command, operation_id: '00000000-0000-4000-8000-000000000009', action: 'supply_save', data: { purchase_no: 'new' } } }
    window.dispatchEvent(new StorageEvent('storage', { key: 'rrn-indonesia-draft-signal' })); await flushPromises()
    await ws.retry()
    expect(mocks.api.command.mock.calls[1]![0].action).toBe('supply_save')
    expect(oldCompletion).not.toHaveBeenCalled()
  })

  it('allows shipping receipt permission independently from business write permission', async () => {
    mocks.api.workspace.mockResolvedValue(response(['indonesia_material:read', 'indonesia_material:receipt_confirm']))
    const ws = setup(); await flushPromises()
    expect(ws.canWrite).toBe(false)
    expect(await ws.run('material_save', {})).toBe(false)
    expect(await ws.run('receipt_confirm', { actual_date: '2026-10-13' }, material)).toBe(true)
    expect(mocks.api.command).toHaveBeenCalledTimes(1)
    await ws.download('shipment', 'private.xlsx')
    expect(mocks.api.download).not.toHaveBeenCalled()
  })

  it.each([undefined, 408, 503])('retries the exact operation and original nested payload after status %s', async code => {
    const ws = setup(); await flushPromises()
    const data = { lines: [{ allocation_id: 'A', normal_quantity: '9', spare_quantity: '1' }] }
    const committed = vi.fn()
    const scope = ws.scopeEpoch
    mocks.api.command.mockRejectedValueOnce(failure(code))
    expect(await ws.run('shipment_save', data, material, committed)).toBe(false)
    expect(committed).not.toHaveBeenCalled()
    const first = structuredClone(mocks.api.command.mock.calls[0]![0])
    data.lines[0]!.normal_quantity = '999'
    expect(ws.locked).toBe(true)
    expect(await ws.run('material_save', { code: 'other' })).toBe(false)
    await ws.retry()
    expect(mocks.api.command.mock.calls[1]![0]).toEqual(first)
    expect(first).toMatchObject({ factory_id: 'huaxing', entity_id: material.id, expected_version: 2, data: { lines: [{ normal_quantity: '9' }] } })
    expect(first.operation_id).toHaveLength(36)
    expect(ws.pending).toBeNull()
    expect(committed).toHaveBeenCalledTimes(1)
    expect(ws.scopeEpoch).toBe(scope)
  })

  it('leaves version conflicts for explicit review without automatic overwrite or retry', async () => {
    const ws = setup(); await flushPromises()
    mocks.api.command.mockRejectedValueOnce(failure(409))
    expect(await ws.run('material_save', {}, material)).toBe(false)
    await ws.retry()
    expect(ws.pending).toBeNull()
    expect(ws.error).toContain('重新打开记录核对')
    expect(mocks.api.command).toHaveBeenCalledTimes(1)
  })

  it('drops an unresolved command when switching factory', async () => {
    const ws = setup(); await flushPromises()
    mocks.api.command.mockRejectedValueOnce(failure())
    await ws.run('material_save', {})
    mocks.app.activeFactoryId = 'huadeng'
    await flushPromises(); await ws.retry()
    expect(mocks.api.command).toHaveBeenCalledTimes(1)
    expect(ws.pending).toBeNull()
  })

  it('warns before leaving dirty work but never lets an old draft block an identity boundary', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const ws = setup(); await flushPromises()
    const unregister = ws.registerDraft(() => true)
    expect(ws.permitLeave()).toBe(false)
    const unload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)
    mocks.auth.currentUser = { id: 'another-user' }
    expect(ws.permitLeave()).toBe(true)
    const afterBoundary = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(afterBoundary)
    expect(afterBoundary.defaultPrevented).toBe(false)
    unregister(); confirm.mockRestore()
  })

  it.each(['workspace', 'command', 'preview', 'download'] as const)('clears protected data and form scope after a %s denial', async endpoint => {
    const ws = setup(); await flushPromises()
    const epoch = ws.scopeEpoch
    mocks.api[endpoint].mockRejectedValueOnce(failure(403))
    if (endpoint === 'workspace') await ws.reload()
    if (endpoint === 'command') await ws.run('material_save', {})
    if (endpoint === 'preview') await ws.preview('C', 'RRI', new File(['xlsx'], 'schedule.xlsx'))
    if (endpoint === 'download') await ws.download('S', 'shipment.xlsx')
    expect(ws.records).toEqual([])
    expect(ws.permissions).toEqual([])
    expect(ws.pending).toBeNull()
    expect(ws.scopeEpoch).toBeGreaterThan(epoch)
    expect(ws.busy).toBe(false)
    expect(ws.loading).toBe(false)
  })
})

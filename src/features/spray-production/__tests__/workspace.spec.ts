import { effectScope, reactive } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosError } from 'axios'
const mocks = vi.hoisted(() => ({ route: vi.fn(), app: vi.fn(), auth: vi.fn(), get: vi.fn(), post: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: mocks.route }))
vi.mock('@/stores/app', () => ({ useAppStore: mocks.app }))
vi.mock('@/stores/auth', () => ({ useAuthStore: mocks.auth }))
vi.mock('@/lib/http', () => ({ http: { get: mocks.get, post: mocks.post } }))
import { createSprayWorkspace } from '../workspace'

const envelope = (data: unknown, factory = 'huaxing', total?: number) => ({ data: {
  meta: { factory_id: factory, data_mode: 'live', factory_revision: 1, as_of: '2026-09-22' }, data,
  ...(total === undefined ? {} : { pagination: { total } }),
} })
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }

describe('spray workspace authorization refresh', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_SPRAY_OPS_ENABLED', 'true')
    mocks.route.mockReturnValue(reactive({ query: { factory: 'huaxing' } }))
    mocks.app.mockReturnValue(reactive({ activeFactoryId: 'huaxing' }))
    mocks.get.mockResolvedValue({ data: { meta: { factory_id: 'huaxing', data_mode: 'live', factory_revision: 1, as_of: '2026-09-22' }, data: { permissions: ['read', 'plan'] } } })
  })
  afterEach(() => { vi.unstubAllEnvs(); vi.clearAllMocks() })
  it('retains a draft across an identical refreshed auth snapshot', async () => {
    const auth = reactive({ currentUser: { id: 'same-user' }, sessionVersion: 1, isAuthenticated: true, authorizationVersion: 1, effectiveAccess: [{ allowed: true }] })
    mocks.auth.mockReturnValue(auth)
    const scope = effectScope()
    const workspace = scope.run(createSprayWorkspace)!
    await flushPromises()
    workspace.dirty.value = true
    workspace.passportId.value = workspace.verifiedDemandId.value = 'same-demand'
    const revision = workspace.contextVersion.value
    auth.currentUser = { id: 'same-user' }
    auth.effectiveAccess = [{ allowed: true }]
    auth.sessionVersion++
    await flushPromises()
    expect(workspace.contextVersion.value).toBe(revision)
    expect(workspace.dirty.value).toBe(true)
    expect(workspace.passportId.value).toBe('same-demand')
    expect(workspace.verifiedDemandId.value).toBe('same-demand')
    expect(workspace.ready.value).toBe(true)
    expect(mocks.get).toHaveBeenCalledTimes(1)
    auth.effectiveAccess = [{ allowed: false }]
    await flushPromises()
    expect(workspace.contextVersion.value).toBe(revision + 1)
    expect(mocks.get).toHaveBeenCalledTimes(2)
    scope.stop()
  })

  it('preserves native filters through refresh and pagination', async () => {
    mocks.auth.mockReturnValue(reactive({ currentUser: { id: 'same-user' }, isAuthenticated: true, authorizationVersion: 1, effectiveAccess: [] }))
    const scope = effectScope(), w = scope.run(createSprayWorkspace)!
    await flushPromises()
    mocks.get.mockResolvedValue(envelope([{ id: 'task-a' }], 'huaxing', 201))
    w.configureCollection('tasks', { task_scope: 'active', search: 'manual' })
    await w.load(['tasks'])
    expect(w.readScopes.tasks).toMatchObject({ ready: true, params: { task_scope: 'active', search: 'manual' } })
    mocks.get.mockResolvedValue(envelope([{ id: 'task-b' }], 'huaxing', 201))
    await w.loadMore('tasks')
    expect(mocks.get.mock.lastCall?.[1].params).toMatchObject({ page: 2, task_scope: 'active', search: 'manual' })
    expect(w.items('tasks').map(row => row.id)).toEqual(['task-a', 'task-b'])
    await w.refresh()
    expect(mocks.get.mock.lastCall?.[1].params).toMatchObject({ task_scope: 'active', search: 'manual' })
    expect(w.paging.tasks?.page).toBe(1)
    scope.stop()
  })

  it('rejects late A to B to A reads and invalidates verified list scope before loading', async () => {
    mocks.auth.mockReturnValue(reactive({ currentUser: { id: 'same-user' }, isAuthenticated: true, authorizationVersion: 1, effectiveAccess: [] }))
    const scope = effectScope(), w = scope.run(createSprayWorkspace)!
    await flushPromises()
    const old = deferred<ReturnType<typeof envelope>>()
    mocks.get.mockImplementation((path: string) => path.endsWith('/tasks') ? old.promise : Promise.resolve(envelope({ permissions: ['read'] }, mocks.app().activeFactoryId)))
    const pending = w.load(['tasks'])
    expect(w.readScopes.tasks?.ready).toBe(false)
    mocks.route().query.factory = 'huakang-b'; mocks.app().activeFactoryId = 'huakang-b'
    await flushPromises()
    mocks.route().query.factory = 'huaxing'; mocks.app().activeFactoryId = 'huaxing'
    await flushPromises()
    mocks.get.mockResolvedValue(envelope([{ id: 'latest' }]))
    await w.load(['tasks'])
    old.resolve(envelope([{ id: 'private-old' }]))
    await pending
    expect(w.items('tasks').map(row => row.id)).toEqual(['latest'])
    expect(w.readScopes.tasks?.ready).toBe(true)
    scope.stop()
  })

  it('clears old private selections and operation payload on authorization change', async () => {
    const auth = reactive({ currentUser: { id: 'same-user', identity: { employment_epoch: 1 } }, sessionVersion: 1, isAuthenticated: true, authorizationVersion: 1, effectiveAccess: [] })
    mocks.auth.mockReturnValue(auth)
    const scope = effectScope(), w = scope.run(createSprayWorkspace)!
    await flushPromises()
    w.passportId.value = w.verifiedDemandId.value = 'private-demand'
    w.assistantRecord.value = { id:'private-demand', kind:'demand', label:'private-label' }
    w.data.value = { demands: [{ id: 'private-demand' }] }; w.dirty.value = true
    const response = deferred<ReturnType<typeof envelope>>()
    mocks.post.mockReturnValue(response.promise)
    const saved = w.command('demands', { note: 'private-body' }).catch(error => error)
    const op = [...w.pending.values()][0]!
    expect(w.hasPending.value).toBe(true)
    auth.authorizationVersion++
    expect(w.data.value).toEqual({}); expect(w.verifiedDemandId.value).toBeNull()
    expect(w.passportId.value).toBeNull(); expect(w.dirty.value).toBe(false)
    expect(w.assistantRecord.value).toBeNull()
    expect(op.body).toEqual({}); expect(op.canRetry).toBe(false)
    response.resolve(envelope({ id: 'private-result' }))
    expect(await saved).toBeInstanceOf(Error)
    expect(op.result).toBeUndefined(); expect(w.notification.value).toBe('')
    scope.stop()
  })

  it('a new employment epoch for the same user clears old pending operations synchronously', async () => {
    const auth = reactive({ currentUser: { id: 'same-user', identity: { employment_epoch: 1 } }, sessionVersion: 1, isAuthenticated: true, authorizationVersion: 1, effectiveAccess: [] })
    mocks.auth.mockReturnValue(auth)
    const scope = effectScope(), w = scope.run(createSprayWorkspace)!
    await flushPromises()
    const response = deferred<ReturnType<typeof envelope>>()
    mocks.post.mockReturnValue(response.promise)
    const saved = w.command('demands', { note: 'private-body' }).catch(error => error)
    auth.currentUser.identity.employment_epoch++
    expect(w.pending.size).toBe(0)
    response.resolve(envelope({ id: 'private-result' }))
    expect(await saved).toBeInstanceOf(Error)
    expect(w.pending.size).toBe(0)
    scope.stop()
  })

  it('disposing a workspace prevents late export writes from starting a download', async () => {
    mocks.auth.mockReturnValue(reactive({ currentUser: { id: 'same-user' }, isAuthenticated: true, authorizationVersion: 1, effectiveAccess: [] }))
    const scope = effectScope(), w = scope.run(createSprayWorkspace)!
    await flushPromises()
    const response = deferred<ReturnType<typeof envelope>>()
    mocks.post.mockReturnValue(response.promise)
    const exported = w.download('production').catch(error => error)
    const op = [...w.pending.values()][0]!
    scope.stop()
    response.resolve(envelope({ id: 'private-export', factory_id: 'huaxing' }))
    expect(await exported).toBeInstanceOf(Error)
    expect(op.result).toBeUndefined(); expect(w.pending.size).toBe(0)
    expect(mocks.get).toHaveBeenCalledTimes(1)
  })

  it('reactively releases the navigation barrier only after confirmation and rejects duplicate in-flight writes', async () => {
    mocks.auth.mockReturnValue(reactive({currentUser:{id:'same-user'},isAuthenticated:true,authorizationVersion:1,effectiveAccess:[]}))
    const scope=effectScope(),w=scope.run(createSprayWorkspace)!
    await flushPromises()
    const response=deferred<ReturnType<typeof envelope>>()
    mocks.post.mockReturnValue(response.promise)
    const saved=w.command('demands/D1/amend',{reason:'synthetic'})
    expect(w.hasPending.value).toBe(true)
    await expect(w.command('demands/D1/amend',{reason:'synthetic'})).rejects.toThrow('仍在保存')
    expect(mocks.post).toHaveBeenCalledTimes(1)
    response.resolve(envelope({id:'D1'}));await saved
    expect(w.hasPending.value).toBe(false)
    scope.stop()
  })

  it('reconciles an uncertain write with the same operation id and frozen values', async()=>{
    mocks.auth.mockReturnValue(reactive({currentUser:{id:'same-user'},isAuthenticated:true,authorizationVersion:1,effectiveAccess:[]}))
    const scope=effectScope(),w=scope.run(createSprayWorkspace)!
    await flushPromises()
    mocks.post.mockRejectedValueOnce(new AxiosError('offline','ERR_NETWORK'))
    await expect(w.command('demands/D1/amend',{reason:'original'},3)).rejects.toThrow('offline')
    const operation=[...w.pending.values()][0]!
    expect(operation.state).toBe('uncertain');expect(w.hasPending.value).toBe(true)
    await expect(w.command('demands/D1/amend',{reason:'changed'},3)).rejects.toThrow('上一笔')
    mocks.get.mockRejectedValueOnce({isAxiosError:true,response:{status:404}})
    const response=deferred<ReturnType<typeof envelope>>()
    mocks.post.mockReturnValueOnce(response.promise)
    const retry=w.resolveOperation(operation);await flushPromises()
    expect(operation.state).toBe('sending');expect(w.hasPending.value).toBe(true)
    expect(mocks.post.mock.lastCall?.[1]).toMatchObject({reason:'original',expected_version:3,operation_id:operation.operation_id})
    response.resolve(envelope({id:'D1'}));await retry
    expect(w.hasPending.value).toBe(false)
    expect(operation.state).toBe('confirmed')
    scope.stop()
  })

  it('refreshes native rows after a found receipt and displays reconciliation failures without losing the receipt', async()=>{
    mocks.auth.mockReturnValue(reactive({currentUser:{id:'same-user'},isAuthenticated:true,authorizationVersion:1,effectiveAccess:[]}))
    const scope=effectScope(),w=scope.run(createSprayWorkspace)!
    await flushPromises()
    w.data.value={demands:[{id:'D1',version:1}]}
    mocks.post.mockRejectedValueOnce(new AxiosError('offline','ERR_NETWORK'))
    await expect(w.command('demands/D1/amend',{reason:'original'},1)).rejects.toThrow('offline')
    const operation=[...w.pending.values()][0]!
    mocks.get.mockRejectedValueOnce(new Error('still offline'))
    await w.resolveOperation(operation)
    expect(w.error.value).toBe('still offline');expect(w.hasPending.value).toBe(true)
    mocks.get.mockResolvedValueOnce(envelope({id:'D1',version:2})).mockResolvedValueOnce(envelope([{id:'D1',version:2}]))
    await w.resolveOperation(operation)
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(w.items('demands')[0]?.version).toBe(2)
    expect(w.error.value).toBe('');expect(w.hasPending.value).toBe(false)
    expect(operation.result).toMatchObject({id:'D1',version:2})
    scope.stop()
  })
})

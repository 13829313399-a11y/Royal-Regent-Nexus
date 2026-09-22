import { effectScope, reactive } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ route: vi.fn(), app: vi.fn(), auth: vi.fn(), get: vi.fn(), post: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: mocks.route }))
vi.mock('@/stores/app', () => ({ useAppStore: mocks.app }))
vi.mock('@/stores/auth', () => ({ useAuthStore: mocks.auth }))
vi.mock('@/lib/http', () => ({ http: { get: mocks.get, post: mocks.post } }))
import { createSprayWorkspace } from '../workspace'

describe('spray workspace authorization refresh', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_SPRAY_OPS_ENABLED', 'true')
    mocks.route.mockReturnValue(reactive({ query: { factory: 'huaxing' } }))
    mocks.app.mockReturnValue(reactive({ activeFactoryId: 'huaxing' }))
    mocks.get.mockResolvedValue({ data: { meta: { factory_id: 'huaxing', data_mode: 'live', factory_revision: 1, as_of: '2026-09-22' }, data: { permissions: ['read', 'plan'] } } })
  })
  afterEach(() => { vi.unstubAllEnvs(); vi.clearAllMocks() })
  it('retains a draft across an identical refreshed auth snapshot', async () => {
    const auth = reactive({ currentUser: { id: 'same-user' }, isAuthenticated: true, authorizationVersion: 1, effectiveAccess: [{ allowed: true }] })
    mocks.auth.mockReturnValue(auth)
    const scope = effectScope()
    const workspace = scope.run(createSprayWorkspace)!
    await flushPromises()
    workspace.dirty.value = true
    const revision = workspace.contextVersion.value
    auth.currentUser = { id: 'same-user' }
    auth.effectiveAccess = [{ allowed: true }]
    await flushPromises()
    expect(workspace.contextVersion.value).toBe(revision)
    expect(workspace.dirty.value).toBe(true)
    expect(workspace.ready.value).toBe(true)
    expect(mocks.get).toHaveBeenCalledTimes(1)
    auth.effectiveAccess = [{ allowed: false }]
    await flushPromises()
    expect(workspace.contextVersion.value).toBe(revision + 1)
    expect(mocks.get).toHaveBeenCalledTimes(2)
    scope.stop()
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useInjectionSchedulingV2Store } from '../stores/useInjectionSchedulingV2Store'
import { createSchedulingBaselineFixture } from './fixtures/schedulingBaselineFixture'

const apiMocks = vi.hoisted(() => ({
  fetchSchedulingWorkspace: vi.fn(),
  fetchIncrementalEvents: vi.fn(),
  fetchCurrentSchedulingPlan: vi.fn(),
}))

vi.mock('../api/injectionSchedulingV2Api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/injectionSchedulingV2Api')>(),
  ...apiMocks,
}))

function workspaceFixture(revision = 14) {
  const fixture = createSchedulingBaselineFixture(3, 9)
  const planningPlan = {
    ...fixture.plan,
    id: 'B1A-DRAFT-PLAN',
    status: 'DRAFT',
    revision,
  }
  return {
    machines: fixture.machines,
    molds: fixture.molds,
    orders: fixture.orders,
    tasks: fixture.tasks,
    backlogOrderIds: [],
    backlogOrders: [],
    plan: planningPlan,
    executionPlan: null,
    planningPlan,
    executionOrders: [],
    executionTasks: [],
    planningOrders: fixture.orders,
    planningTasks: fixture.tasks,
    pollingRevision: 98,
    events: [],
    autoScheduleRuns: [],
  }
}

function axiosFailure(status?: number, detail = 'B1a 模拟同步失败') {
  return {
    isAxiosError: true,
    message: status ? `Request failed with status code ${status}` : 'Network Error',
    response: status ? { status, data: { detail } } : undefined,
  }
}

function createStore() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const authStore = useAuthStore(pinia)
  authStore.permissions = [
    'injection_scheduling:edit',
    'injection_scheduling:import',
    'injection_scheduling:export',
  ]
  authStore.factoryScopes = ['huaxing']
  authStore.isAuthenticated = true
  authStore.hasLoadedSession = true
  return useInjectionSchedulingV2Store(pinia)
}

describe('injection scheduling workspace freshness', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('preserves the last formal snapshot, local drafts, and existing capabilities after a quiet refresh failure', async () => {
    const store = createStore()
    const initialWorkspace = workspaceFixture()
    apiMocks.fetchSchedulingWorkspace.mockResolvedValueOnce(initialWorkspace)

    await store.load()
    const task = initialWorkspace.planningTasks[0]!
    const order = initialWorkspace.planningOrders[0]!
    store.cellDrafts = {
      [`${task.id}:status`]: {
        taskId: task.id,
        orderId: order.id,
        key: 'status',
        value: 'RUNNING',
        originalValue: task.status,
      },
    }
    const snapshot = {
      machineIds: store.machines.map((item) => item.id),
      taskIds: store.tasks.map((item) => item.id),
      lastSyncedAt: store.lastSyncedAt,
      canEdit: store.canEdit,
      canImport: store.canImport,
    }
    apiMocks.fetchSchedulingWorkspace.mockRejectedValueOnce(axiosFailure())

    await store.load({ quiet: true })

    expect(store.syncHealth).toBe('stale')
    expect(store.sourceMode).toBe('live')
    expect(store.hasFormalSnapshot).toBe(true)
    expect(store.machines.map((item) => item.id)).toEqual(snapshot.machineIds)
    expect(store.tasks.map((item) => item.id)).toEqual(snapshot.taskIds)
    expect(store.cellDrafts[`${task.id}:status`]?.value).toBe('RUNNING')
    expect(store.lastSyncedAt).toBe(snapshot.lastSyncedAt)
    expect(store.canEdit).toBe(snapshot.canEdit)
    expect(store.canImport).toBe(snapshot.canImport)
    expect(store.sourceMessage).toContain('数据同步暂时中断')
    expect(store.asyncFeedback).toMatchObject({ operation: 'refresh', phase: 'failed', tone: 'warning' })
  })

  it('returns to live after a successful retry without changing the permission-derived capabilities', async () => {
    const store = createStore()
    apiMocks.fetchSchedulingWorkspace
      .mockResolvedValueOnce(workspaceFixture(14))
      .mockRejectedValueOnce(axiosFailure(503))
      .mockResolvedValueOnce(workspaceFixture(15))

    await store.load()
    const canEditBefore = store.canEdit
    await store.load({ quiet: true })
    expect(store.syncHealth).toBe('stale')

    await store.load({ quiet: true })

    expect(store.syncHealth).toBe('live')
    expect(store.sourceMode).toBe('live')
    expect(store.plan?.revision).toBe(15)
    expect(store.canEdit).toBe(canEditBefore)
    expect(store.syncFailureKind).toBeNull()
    expect(store.asyncFeedback).toMatchObject({ operation: 'refresh', phase: 'succeeded', tone: 'success' })
  })

  it.each([
    ['network', undefined],
    ['controlled 5xx', 503],
  ])('uses an explicit read-only demo only for an initial %s failure', async (_label, status) => {
    const store = createStore()
    apiMocks.fetchSchedulingWorkspace.mockRejectedValueOnce(axiosFailure(status))

    await store.load()

    expect(store.syncHealth).toBe('demo-readonly')
    expect(store.sourceMode).toBe('fallback')
    expect(store.hasFormalSnapshot).toBe(false)
    expect(store.sourceMessage).toContain('只读演示数据')
    expect(store.asyncFeedback).toMatchObject({ operation: 'initial-load', phase: 'failed', tone: 'warning' })
  })

  it.each([
    [401, 'authentication'],
    [403, 'authorization'],
    [422, 'business'],
  ])('does not hide an initial %i response behind demo data', async (status, expectedKind) => {
    const store = createStore()
    apiMocks.fetchSchedulingWorkspace.mockRejectedValueOnce(axiosFailure(status))

    await store.load()

    expect(store.syncHealth).toBe('error')
    expect(store.syncFailureKind).toBe(expectedKind)
    expect(store.sourceMode).toBe('live')
    expect(store.hasFormalSnapshot).toBe(false)
    expect(store.machines).toEqual([])
    expect(store.tasks).toEqual([])
    expect(store.sourceMessage).not.toContain('演示数据')
    expect(store.asyncFeedback).toMatchObject({ operation: 'initial-load', phase: 'failed', tone: 'error' })
  })

  it('marks polling failures stale without overwriting data and heals on the next successful poll', async () => {
    const store = createStore()
    const workspace = workspaceFixture()
    apiMocks.fetchSchedulingWorkspace.mockResolvedValueOnce(workspace)
    await store.load()
    const previousTaskIds = store.tasks.map((item) => item.id)
    const previousSyncTime = store.lastSyncedAt
    apiMocks.fetchIncrementalEvents.mockRejectedValueOnce(axiosFailure())

    await store.pollEvents()

    expect(store.syncHealth).toBe('stale')
    expect(store.tasks.map((item) => item.id)).toEqual(previousTaskIds)
    expect(store.lastSyncedAt).toBe(previousSyncTime)
    expect(store.asyncFeedback).toMatchObject({ operation: 'poll', phase: 'failed', tone: 'warning' })

    apiMocks.fetchIncrementalEvents.mockResolvedValueOnce({ events: [], latestSequence: 98 })
    await store.pollEvents()

    expect(store.syncHealth).toBe('live')
    expect(store.sourceMode).toBe('live')
    expect(store.syncFailureKind).toBeNull()
    expect(store.lastSyncedAt).toBeTruthy()
    expect(store.asyncFeedback).toMatchObject({ operation: 'poll', phase: 'succeeded', tone: 'info' })
  })
})

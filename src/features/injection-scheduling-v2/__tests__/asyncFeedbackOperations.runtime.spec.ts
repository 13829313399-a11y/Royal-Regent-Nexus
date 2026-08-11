import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useInjectionSchedulingV2Store } from '../stores/useInjectionSchedulingV2Store'
import { shouldShowFeedbackToast } from '../presentation/asyncFeedback'
import { createSchedulingBaselineFixture } from './fixtures/schedulingBaselineFixture'

const apiMocks = vi.hoisted(() => ({
  fetchSchedulingWorkspace: vi.fn(),
  fetchCurrentSchedulingPlan: vi.fn(),
  patchScheduleTask: vi.fn(),
  publishSchedulingPlan: vi.fn(),
  createAutoSchedulePreview: vi.fn(),
}))

vi.mock('../api/injectionSchedulingV2Api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/injectionSchedulingV2Api')>(),
  ...apiMocks,
}))

function workspaceFixture(status: 'DRAFT' | 'PUBLISHED' = 'DRAFT', revision = 14) {
  const fixture = createSchedulingBaselineFixture(2, 4)
  const plan = { ...fixture.plan, id: `B1C-${status}-PLAN`, status, revision }
  const tasks = fixture.tasks.map((task) => ({ ...task, planId: plan.id, activeExecution: status === 'PUBLISHED', locked: false }))
  return {
    machines: fixture.machines,
    molds: fixture.molds,
    orders: fixture.orders,
    tasks,
    backlogOrderIds: [],
    backlogOrders: [],
    plan,
    executionPlan: status === 'PUBLISHED' ? plan : null,
    planningPlan: status === 'DRAFT' ? plan : null,
    executionOrders: status === 'PUBLISHED' ? fixture.orders : [],
    executionTasks: status === 'PUBLISHED' ? tasks : [],
    planningOrders: status === 'DRAFT' ? fixture.orders : [],
    planningTasks: status === 'DRAFT' ? tasks : [],
    pollingRevision: 98,
    events: [],
    autoScheduleRuns: [],
  }
}

function createStore() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const authStore = useAuthStore(pinia)
  authStore.permissions = ['injection_scheduling:edit', 'injection_scheduling:publish']
  authStore.factoryScopes = ['huaxing']
  authStore.isAuthenticated = true
  authStore.hasLoadedSession = true
  return useInjectionSchedulingV2Store(pinia)
}

describe('injection scheduling async operation feedback', () => {
  beforeEach(() => vi.clearAllMocks())

  it('tracks save pending and success explicitly', async () => {
    const workspace = workspaceFixture()
    apiMocks.fetchSchedulingWorkspace.mockResolvedValueOnce(workspace)
    const store = createStore()
    await store.load()
    const task = workspace.planningTasks[0]!
    store.stageCellEdit(task.id, 'status', task.status === 'RUNNING' ? 'QUEUED' : 'RUNNING')

    let releaseSave!: (value: unknown) => void
    apiMocks.patchScheduleTask.mockReturnValueOnce(new Promise((resolve) => { releaseSave = resolve }))
    const saving = store.savePendingEdits()
    expect(store.asyncFeedback).toMatchObject({ operation: 'save', phase: 'pending', tone: 'info' })

    releaseSave({ plan: workspace.planningPlan, tasks: workspace.planningTasks, orders: workspace.planningOrders })
    await saving
    expect(store.asyncFeedback).toMatchObject({ operation: 'save', phase: 'succeeded', tone: 'success' })
    expect(store.pendingEditCount).toBe(0)
  })

  it('retains save conflicts as a dialog workflow instead of a toast', async () => {
    const workspace = workspaceFixture()
    apiMocks.fetchSchedulingWorkspace.mockResolvedValueOnce(workspace)
    apiMocks.fetchCurrentSchedulingPlan.mockResolvedValueOnce({
      plan: workspace.planningPlan,
      executionPlan: null,
      planningPlan: workspace.planningPlan,
      tasks: workspace.planningTasks,
      orders: workspace.planningOrders,
      pollingRevision: 99,
    })
    apiMocks.patchScheduleTask.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 409, data: { detail: { message: 'revision mismatch', diff: { status: 'QUEUED' } } } },
    })
    const store = createStore()
    await store.load()
    const task = workspace.planningTasks[0]!
    store.stageCellEdit(task.id, 'status', task.status === 'RUNNING' ? 'QUEUED' : 'RUNNING')

    await store.savePendingEdits()

    expect(store.asyncFeedback).toMatchObject({ operation: 'save', phase: 'failed', tone: 'error' })
    expect(store.revisionConflict).not.toBeNull()
    expect(store.pendingEditCount).toBe(1)
    expect(shouldShowFeedbackToast(store.asyncFeedback, Boolean(store.revisionConflict))).toBe(false)
  })

  it('keeps publish feedback typed across its internal refresh', async () => {
    const draftWorkspace = workspaceFixture('DRAFT', 14)
    const publishedWorkspace = workspaceFixture('PUBLISHED', 15)
    apiMocks.fetchSchedulingWorkspace.mockResolvedValueOnce(draftWorkspace).mockResolvedValueOnce(publishedWorkspace)
    apiMocks.publishSchedulingPlan.mockResolvedValueOnce({ plan: publishedWorkspace.executionPlan, auditSequence: 101 })
    const store = createStore()
    await store.load()

    expect(await store.publishPlanningPlan()).toBe(true)
    expect(store.asyncFeedback).toMatchObject({ operation: 'publish', phase: 'succeeded', tone: 'success' })
    expect(store.saveMessage).toContain('当前执行 · 版本 15')
  })

  it('keeps publish failures in the publish dialog layer', async () => {
    const workspace = workspaceFixture()
    apiMocks.fetchSchedulingWorkspace.mockResolvedValueOnce(workspace)
    apiMocks.publishSchedulingPlan.mockRejectedValueOnce(new Error('B1c 去敏发布失败'))
    const store = createStore()
    await store.load()

    expect(await store.publishPlanningPlan()).toBe(false)
    expect(store.asyncFeedback).toMatchObject({ operation: 'publish', phase: 'failed', tone: 'error' })
    expect(store.publishPlanError).toContain('B1c 去敏发布失败')
    expect(shouldShowFeedbackToast(store.asyncFeedback, false)).toBe(false)
  })

  it('reports auto-generation success without routing dialog errors through toast heuristics', async () => {
    const workspace = workspaceFixture()
    apiMocks.fetchSchedulingWorkspace.mockResolvedValueOnce(workspace)
    apiMocks.createAutoSchedulePreview.mockResolvedValueOnce({
      id: 'b1c-run', scenarioGroupId: 'b1c-group', scenarioName: 'B1c 去敏方案', alternativeNo: 1,
      status: 'SUCCEEDED', assignments: [], summary: {},
    })
    const store = createStore()
    await store.load()

    await store.generateAutoSchedulePreview()

    expect(store.asyncFeedback).toMatchObject({ operation: 'auto-generate', phase: 'succeeded', tone: 'success' })
    expect(store.autoScheduleRun?.id).toBe('b1c-run')
    expect(shouldShowFeedbackToast(store.asyncFeedback, false)).toBe(false)
  })

  it('keeps auto-generation failures in the automatic-scheduling dialog layer', async () => {
    const workspace = workspaceFixture()
    apiMocks.fetchSchedulingWorkspace.mockResolvedValueOnce(workspace)
    apiMocks.createAutoSchedulePreview.mockRejectedValueOnce(new Error('B1c 去敏求解失败'))
    const store = createStore()
    await store.load()

    await store.generateAutoSchedulePreview()

    expect(store.asyncFeedback).toMatchObject({ operation: 'auto-generate', phase: 'failed', tone: 'error' })
    expect(store.autoScheduleError).toContain('B1c 去敏求解失败')
    expect(shouldShowFeedbackToast(store.asyncFeedback, false)).toBe(false)
  })
})

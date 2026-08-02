import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  FactoryDatasetNotFoundError,
  MockInjectionSchedulingRepository,
  OptimisticConflictError,
} from '@/repositories/injectionSchedulingRepository'
import { useInjectionSchedulingStore } from '@/stores/injectionScheduling'

describe('injection scheduling frontend mock contract', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('keeps Huaxing data isolated and large enough for the 257-row acceptance case', async () => {
    const repository = new MockInjectionSchedulingRepository()
    const snapshot = await repository.getSnapshot('huaxing')

    expect(snapshot.factoryId).toBe('huaxing')
    expect(snapshot.sourceMode).toBe('mock')
    expect(snapshot.machines).toHaveLength(69)
    expect(snapshot.tasks).toHaveLength(257)
    expect(snapshot.backlogOrders).toHaveLength(23)
    expect(snapshot.summary.overdueTasks).toBe(158)
    expect(snapshot.summary.dueSoonTasks).toBe(19)
    expect(snapshot.summary.moldDimensionCompleteness).toBe(41.7)

    await expect(repository.getSnapshot('huakang-b')).rejects.toBeInstanceOf(FactoryDatasetNotFoundError)
  })

  it('isolates GT1214 search results and enforces one running task per machine', async () => {
    const store = useInjectionSchedulingStore()
    await store.load('huaxing')
    store.search = 'GT1214'

    expect(store.filteredTaskCount).toBe(3)
    expect(store.filteredGroups.flatMap((group) => group.tasks).every((task) => task.moldCode === 'GT1214')).toBe(true)

    store.search = ''
    store.statusFilter = 'running'
    expect(store.filteredGroups.every((group) => group.tasks.length <= 1)).toBe(true)
    expect(store.filteredGroups.flatMap((group) => group.tasks).every((task) => task.status === 'RUNNING')).toBe(true)
  })

  it('defines overdue strictly as slackDays below zero', async () => {
    const store = useInjectionSchedulingStore()
    await store.load('huaxing')
    store.statusFilter = 'overdue'

    const tasks = store.filteredGroups.flatMap((group) => group.tasks)
    expect(tasks.length).toBeGreaterThan(0)
    expect(tasks.every((task) => task.slackDays < 0)).toBe(true)
  })

  it('filters mold-dimension completeness without treating missing data as a pass', async () => {
    const store = useInjectionSchedulingStore()
    await store.load('huaxing')
    store.dataQuality = 'missing'

    const missingTasks = store.filteredGroups.flatMap((group) => group.tasks)
    expect(missingTasks.length).toBeGreaterThan(0)
    expect(missingTasks.every((task) => task.moldDimensions === null)).toBe(true)
    expect(missingTasks.every((task) => task.fitDecision === 'REVIEW_REQUIRED')).toBe(true)
  })

  it('keeps missing dimensions under review and blocks injection-capacity failures', async () => {
    const repository = new MockInjectionSchedulingRepository()
    const snapshot = await repository.getSnapshot('huaxing')
    const missingDimensions = snapshot.tasks.find((task) => task.id === 't-inner-278')
    const gtBacklog = snapshot.backlogOrders.find((order) => order.id === 'backlog-gt')
    const capacityFailure = gtBacklog?.candidates.find((candidate) => candidate.decision === 'FAIL')

    expect(missingDimensions?.moldDimensions).toBeNull()
    expect(missingDimensions?.fitDecision).toBe('REVIEW_REQUIRED')
    expect(capacityFailure?.constraints.some((check) => check.key === 'shot-capacity' && check.decision === 'FAIL')).toBe(true)

    await expect(repository.assignBacklogOrder(
      'huaxing',
      gtBacklog!.id,
      capacityFailure!.machineId,
      gtBacklog!.revision,
    )).rejects.toThrow('硬约束失败')
  })

  it('previews and saves shift production while detecting stale revisions', async () => {
    const repository = new MockInjectionSchedulingRepository()
    const snapshot = await repository.getSnapshot('huaxing')
    const task = snapshot.tasks.find((entry) => entry.id === 't-gt-145')!

    const saved = await repository.saveShiftReport('huaxing', task.id, task.revision, {
      shiftCompleted: 40,
      cumulativeCompleted: 3450,
      shiftTarget: 1400,
      downtimeHours: 0.5,
      exceptionType: '换模',
      status: 'RUNNING',
      remark: '本班回报测试',
    })
    expect(saved.task.completedQuantity).toBe(3450)
    expect(saved.task.orderQuantity - saved.task.completedQuantity).toBe(78)
    expect(saved.task.downtimeHours).toBe(0.5)
    expect(saved.task.exceptionType).toBe('换模')

    await expect(repository.saveShiftReport('huaxing', task.id, task.revision, {
      shiftCompleted: 50,
      cumulativeCompleted: 3460,
      shiftTarget: 1400,
      downtimeHours: 0,
      exceptionType: '',
      status: 'RUNNING',
      remark: '旧版本',
    })).rejects.toBeInstanceOf(OptimisticConflictError)
  })
})

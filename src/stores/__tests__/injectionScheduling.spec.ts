import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { InjectionSchedulingRepository } from '@/api/injectionScheduling'
import { cloneSchedulingSnapshot } from '@/data/injectionSchedulingMock'
import { useInjectionSchedulingStore } from '@/stores/injectionScheduling'

describe('injection scheduling front-end draft store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function load(store: ReturnType<typeof useInjectionSchedulingStore>, factoryId: 'huaxing' | 'huakang-b' | 'huakang-a') {
    const promise = store.load(factoryId)
    await vi.runAllTimersAsync()
    await promise
  }

  it('loads independent Huaxing and Huakang B mocks and leaves other factories empty', async () => {
    const store = useInjectionSchedulingStore()
    await load(store, 'huaxing')
    expect(store.hasPreviewData).toBe(true)
    expect(store.machines).toHaveLength(71)
    expect(store.machines.every((machine) => machine.id.startsWith('hx-'))).toBe(true)

    await load(store, 'huakang-b')
    expect(store.machines).toHaveLength(96)
    expect(store.machines.every((machine) => machine.id.startsWith('hkb-'))).toBe(true)

    await load(store, 'huakang-a')
    expect(store.hasPreviewData).toBe(false)
    expect(store.machines).toEqual([])
    expect(store.tasks).toEqual([])
    expect(store.backlog).toEqual([])
  })

  it('keeps the current task locked and requires confirmation for a future task reorder', async () => {
    const store = useInjectionSchedulingStore()
    await load(store, 'huaxing')
    const machine = store.machines.find((item) => item.taskIds.length >= 3)!
    const [currentId, futureId] = machine.taskIds

    store.requestMove({ taskId: currentId, sourceMachineId: machine.id, targetMachineId: machine.id, targetIndex: 2 })
    expect(store.pendingMove).toBeNull()
    expect(store.toast?.title).toBe('当前任务已锁定')

    store.requestMove({ taskId: futureId, sourceMachineId: machine.id, targetMachineId: machine.id, targetIndex: 2 })
    expect(store.pendingMoveValidation?.allowed).toBe(true)
    const revision = store.plan.revision
    store.confirmMove()
    expect(store.plan.revision).toBe(revision + 1)
    expect(machine.taskIds[2]).toBe(futureId)
  })

  it('turns a backlog order into a draft task only after eligible candidate confirmation', async () => {
    const store = useInjectionSchedulingStore()
    await load(store, 'huaxing')
    const order = store.backlog.find((item) => item.candidates.length)!
    const candidate = order.candidates[0]!
    const backlogCount = store.backlog.length

    store.requestMove({ backlogId: order.id, targetMachineId: candidate.machineId })
    expect(store.backlog).toHaveLength(backlogCount)
    expect(store.pendingMoveValidation?.allowed).toBe(true)

    store.confirmMove()
    expect(store.backlog).toHaveLength(backlogCount - 1)
    expect(store.tasks).toContainEqual(expect.objectContaining({
      machineId: candidate.machineId,
      requirement: expect.objectContaining({ orderNo: order.requirement.orderNo }),
    }))
  })

  it('preserves per-factory drafts without reusing them across factories', async () => {
    const store = useInjectionSchedulingStore()
    await load(store, 'huaxing')
    const huaxingPlanId = store.plan.id
    store.plan.label = '华兴本地草案'

    await load(store, 'huakang-b')
    expect(store.plan.id).not.toBe(huaxingPlanId)
    expect(store.plan.label).not.toBe('华兴本地草案')

    await load(store, 'huaxing')
    expect(store.plan.label).toBe('华兴本地草案')
  })

  it('uses the backend snapshot, validates a move, saves a new revision and publishes', async () => {
    const remoteSnapshot = cloneSchedulingSnapshot('huaxing')!
    const repository = {
      loadSnapshot: vi.fn().mockResolvedValue(remoteSnapshot),
      validateMove: vi.fn().mockResolvedValue({
        allowed: true,
        reasons: ['后端校验通过'],
        affectedTaskCount: 2,
      }),
      saveDraft: vi.fn().mockResolvedValue({
        revision: remoteSnapshot.plan.revision + 1,
        savedAt: '2026-07-28T11:00:00+08:00',
      }),
      publishVersion: vi.fn().mockResolvedValue({
        version: '20260728.1',
        publishedAt: '2026-07-28T11:05:00+08:00',
      }),
      loadPublishedSnapshot: vi.fn(),
      previewImport: vi.fn(),
      confirmImport: vi.fn(),
      rollbackVersion: vi.fn(),
    } as InjectionSchedulingRepository
    const store = useInjectionSchedulingStore()
    store.setRepository(repository)
    await load(store, 'huaxing')

    expect(store.sourceMode).toBe('backend')
    const machine = store.machines.find((item) => item.taskIds.length >= 3)!
    const taskId = machine.taskIds[1]!
    const baseRevision = store.plan.revision
    await store.requestMove({
      taskId,
      sourceMachineId: machine.id,
      targetMachineId: machine.id,
      targetIndex: 2,
    })
    expect(repository.validateMove).toHaveBeenCalledWith(expect.objectContaining({
      factoryId: 'huaxing',
      revision: baseRevision,
      taskId,
    }))

    await store.confirmMove()
    expect(repository.saveDraft).toHaveBeenCalledWith(expect.objectContaining({
      factoryId: 'huaxing',
      revision: baseRevision,
      reason: '人工调整后续任务队列',
    }))
    expect(store.plan.revision).toBe(baseRevision + 1)
    expect(store.snapshotAt).toBe('2026-07-28T11:00:00+08:00')

    await store.publishPreview()
    expect(repository.publishVersion).toHaveBeenCalledWith({
      factoryId: 'huaxing',
      revision: baseRevision + 1,
      reason: '发布当前注塑排程到生产大屏',
    })
    expect(store.plan.status).toBe('published')
  })
})

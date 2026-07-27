import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useInjectionSchedulingStore } from '@/stores/injectionScheduling'

describe('injection scheduling front-end preview store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  it('loads Huaxing mock data without leaking it into another factory', async () => {
    const store = useInjectionSchedulingStore()

    const huaxingLoad = store.load('huaxing')
    await vi.runAllTimersAsync()
    await huaxingLoad

    expect(store.isHuaxingPreview).toBe(true)
    expect(store.machines).toHaveLength(6)
    expect(store.tasks.length).toBeGreaterThan(10)

    const huakangLoad = store.load('huakang-a')
    await vi.runAllTimersAsync()
    await huakangLoad

    expect(store.isHuaxingPreview).toBe(false)
    expect(store.machines).toEqual([])
    expect(store.tasks).toEqual([])
    expect(store.backlog).toEqual([])
  })

  it('keeps the current task locked and requires confirmation for a future task move', async () => {
    const store = useInjectionSchedulingStore()
    const load = store.load('huaxing')
    await vi.runAllTimersAsync()
    await load

    store.requestMove({ taskId: 't-201', sourceMachineId: 'old-2', targetMachineId: 'old-1' })
    expect(store.pendingMove).toBeNull()
    expect(store.toast?.title).toBe('当前任务已锁定')

    store.requestMove({ taskId: 't-202', sourceMachineId: 'old-2', targetMachineId: 'old-1' })
    expect(store.pendingMove).toMatchObject({ taskId: 't-202', targetMachineId: 'old-1' })
    expect(store.tasks.find((task) => task.id === 't-202')?.machineId).toBe('old-2')

    store.confirmMove()
    expect(store.tasks.find((task) => task.id === 't-202')?.machineId).toBe('old-1')
    expect(store.machines.find((machine) => machine.id === 'old-1')?.taskIds).toContain('t-202')
  })

  it('turns a backlog order into a draft task only after confirmation', async () => {
    const store = useInjectionSchedulingStore()
    const load = store.load('huaxing')
    await vi.runAllTimersAsync()
    await load

    store.requestMove({ backlogId: 'b-351', targetMachineId: 'new-37' })
    expect(store.backlog.some((order) => order.id === 'b-351')).toBe(true)

    store.confirmMove()
    expect(store.backlog.some((order) => order.id === 'b-351')).toBe(false)
    expect(store.tasks).toContainEqual(expect.objectContaining({
      id: 'draft-b-351',
      machineId: 'new-37',
      dueLabel: '待后端校验',
    }))
  })
})

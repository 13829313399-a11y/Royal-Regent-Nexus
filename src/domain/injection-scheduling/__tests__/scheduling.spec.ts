import { describe, expect, it, vi } from 'vitest'
import {
  calculateProductionProgress,
  calculateScheduleTiming,
  sortFutureTasks,
} from '@/domain/injection-scheduling'
import { cloneSchedulingSnapshot } from '@/data/injectionSchedulingMock'
import type { ScheduleTask } from '@/types/injectionScheduling'

describe('injection scheduling deterministic planning', () => {
  it('calculates remaining quantity and duration from production reports', () => {
    expect(calculateProductionProgress(10_000, [1_200, 800], 4_000)).toEqual({
      orderQuantity: 10_000,
      completedQuantity: 2_000,
      remainingQuantity: 8_000,
      effectiveDailyTarget: 4_000,
      productionDurationHours: 48,
    })
  })

  it('orders urgent and due-risk tasks before lower-priority work', () => {
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    const future = snapshot.tasks.filter((task) => !task.current).slice(0, 3)
    const urgent = structuredClone(future[2]!)
    urgent.requirement.priorityCode = 'P0'
    urgent.timing.slackHours = -12
    const low = structuredClone(future[0]!)
    low.requirement.priorityCode = 'P3'
    low.timing.slackHours = 240
    expect(sortFutureTasks([low, urgent])[0]?.id).toBe(urgent.id)
  })

  it('never moves the current locked task during optimization ordering', () => {
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    const machine = snapshot.machines.find((item) => item.taskIds.length >= 3)!
    const tasks = machine.taskIds.map((id) => snapshot.tasks.find((task) => task.id === id)!)
    const current = tasks.find((task) => task.current)!
    const reversed = [current, ...tasks.filter((task) => !task.current).reverse()] as ScheduleTask[]
    expect(sortFutureTasks(reversed)[0]?.id).toBe(current.id)
  })

  it('uses an explicit anchor and production calendar instead of system current time', () => {
    vi.setSystemTime('2042-01-01T00:00:00Z')
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    const timing = calculateScheduleTiming({
      anchorAt: '2026-07-28T08:00:00+08:00',
      changeoverHours: 2,
      productionDurationHours: 24,
      deliveryDueAt: '2026-08-03T08:00:00+08:00',
      calendar: snapshot.calendar,
      downstreamBufferHours: 72,
    })
    expect(timing.plannedStart).toContain('2026-07-28')
    expect(timing.plannedEnd).toContain('2026-07-29')
    expect(timing.plannedStart).not.toContain('2042')
    vi.useRealTimers()
  })

  it('keeps Huaxing and Huakang B snapshots structurally independent', () => {
    const huaxing = cloneSchedulingSnapshot('huaxing')!
    const huakangB = cloneSchedulingSnapshot('huakang-b')!
    huaxing.machines[0]!.name = 'mutated'
    expect(huakangB.factoryId).toBe('huakang-b')
    expect(huakangB.machines[0]!.id).toMatch(/^hkb-/)
    expect(huakangB.machines[0]!.name).not.toBe('mutated')
  })
})

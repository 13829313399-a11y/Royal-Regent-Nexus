import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { indexTasksByMachine } from '../selectors/schedulingTaskIndex'
import type { MachineScheduleSummary, ScheduleGridRow, ScheduleTaskRecord } from '../types'
import { createBusinessSchedulingBaselineFixture } from './fixtures/schedulingBaselineFixture'
import { seedSchedulingBaselineStore } from './helpers/seedSchedulingBaselineStore'

const emptySummary: MachineScheduleSummary = { taskCount: 0, currentLabel: '', releaseAt: '' }

function legacySummary(rows: ScheduleGridRow[], machineId: string): MachineScheduleSummary {
  const machineRows = rows.filter((row) => row.rowType === 'task' && row.machine.id === machineId)
  const running = rows.find((row) => row.rowType === 'task' && row.machine.id === machineId && row.status === 'RUNNING')
  const releaseValue = machineRows.at(-1)?.plannedFinish
  const formattedRelease = formatBusinessDateTime(releaseValue, { fallback: '' })
  return {
    taskCount: machineRows.length,
    currentLabel: running ? `${running.moldNo} · ${running.productName}` : '',
    releaseAt: formattedRelease ? formattedRelease.slice(5) : '',
  }
}

describe('B2a task indexes and machine summaries', () => {
  it('indexes each task once while preserving per-machine task order', () => {
    const fixture = createBusinessSchedulingBaselineFixture()
    let machineIdReads = 0
    const observedTasks = fixture.tasks.map((task) => new Proxy(task, {
      get(target, property, receiver) {
        if (property === 'machineId') machineIdReads += 1
        return Reflect.get(target, property, receiver)
      },
    })) as ScheduleTaskRecord[]

    const tasksByMachine = indexTasksByMachine(observedTasks)

    expect(machineIdReads).toBe(fixture.tasks.length)
    expect(tasksByMachine.size).toBe(fixture.machines.length)
    for (const machine of fixture.machines) {
      expect(tasksByMachine.get(machine.id)?.map((task) => task.id)).toEqual(
        fixture.tasks.filter((task) => task.machineId === machine.id).map((task) => task.id),
      )
    }
  })

  it('matches the previous Grid-derived summaries across filtering, sorting and collapse states', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())

    const assertCurrentRows = () => {
      const rows = store.gridRows as ScheduleGridRow[]
      for (const row of rows.filter((item) => item.rowType === 'machine')) {
        expect(store.machineSummaryById.get(row.machine.id) ?? emptySummary).toEqual(legacySummary(rows, row.machine.id))
      }
    }

    assertCurrentRows()
    store.search = 'QA-ORDER-00001'
    assertCurrentRows()
    store.search = ''
    store.sort = { key: 'orderNo', desc: true }
    assertCurrentRows()
    store.collapsedMachineIds = [store.machines[0]!.id]
    assertCurrentRows()
  })

  it('keeps cached indexes stable for selection and staged cell edits', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const fixture = createBusinessSchedulingBaselineFixture()
    const store = seedSchedulingBaselineStore(pinia, fixture)
    store.sourceMode = 'live'

    const tasksByMachine = store.tasksByMachine
    const machineSummaryById = store.machineSummaryById
    const firstTask = fixture.tasks[0]!

    store.selectedTaskId = firstTask.id
    store.stageCellEdit(firstTask.id, 'shiftCompleted', firstTask.reportedQuantity + 1)

    expect(store.tasksByMachine).toBe(tasksByMachine)
    expect(store.machineSummaryById).toBe(machineSummaryById)
    expect(store.pendingEditCount).toBe(1)
  })
})

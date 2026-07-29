import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import InjectionScheduleSpreadsheet from '@/components/injection-scheduling/spreadsheet/InjectionScheduleSpreadsheet.vue'
import { scheduleColumnsForScheme } from '@/components/injection-scheduling/spreadsheet/scheduleSpreadsheetColumns'
import { cloneSchedulingSnapshot } from '@/data/injectionSchedulingMock'
import type { InjectionMachine, ScheduleTask, SchedulingFilters } from '@/types/injectionScheduling'

const filters: SchedulingFilters = {
  search: '',
  machineClass: 'all',
  state: 'all',
  exceptionsOnly: false,
  incompleteOnly: false,
  idleOnly: false,
  taskScope: 'all',
  deliveryFrom: '',
  deliveryTo: '',
}

function fixture() {
  const snapshot = cloneSchedulingSnapshot('huaxing')!
  const machines = snapshot.machines.filter((machine) => machine.taskIds.length >= 3).slice(0, 2)
  const machineIds = new Set(machines.map((machine) => machine.id))
  const tasks = snapshot.tasks.filter((task) => machineIds.has(task.machineId))
  const tasksByMachine = new Map<string, ScheduleTask[]>()
  for (const machine of machines) {
    tasksByMachine.set(
      machine.id,
      tasks.filter((task) => task.machineId === machine.id).sort((left, right) => left.sequence - right.sequence),
    )
  }
  return { machines, tasksByMachine }
}

function mountSpreadsheet(overrides: {
  machines?: InjectionMachine[]
  tasksByMachine?: Map<string, ScheduleTask[]>
  fieldScheme?: 'core' | 'full' | 'screen'
  bigScreen?: boolean
  filters?: SchedulingFilters
} = {}) {
  const data = fixture()
  return mount(InjectionScheduleSpreadsheet, {
    attachTo: document.body,
    props: {
      factoryId: 'huaxing',
      machines: overrides.machines ?? data.machines,
      tasksByMachine: overrides.tasksByMachine ?? data.tasksByMachine,
      selectedTaskId: '',
      viewMode: 'spreadsheet',
      density: 'compact',
      fieldScheme: overrides.fieldScheme ?? 'full',
      filters: overrides.filters ?? filters,
      backlogCount: 3,
      bigScreen: overrides.bigScreen ?? false,
    },
  })
}

afterEach(() => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  document.body.innerHTML = ''
})

describe('InjectionScheduleSpreadsheet', () => {
  it('renders the two sticky header rows, machine groups and locked/current versus draggable future rows', () => {
    const wrapper = mountSpreadsheet()
    const data = fixture()
    const firstMachineTasks = data.tasksByMachine.get(data.machines[0]!.id)!

    expect(wrapper.findAll('thead tr')).toHaveLength(2)
    expect(wrapper.findAll('[data-machine-id]')).toHaveLength(2)
    expect(wrapper.text()).toContain(firstMachineTasks[0]!.requirement.orderNo)
    expect(wrapper.get(`[data-task-id="${firstMachineTasks[0]!.id}"]`).attributes('data-current')).toBe('true')
    expect(wrapper.get(`[data-task-id="${firstMachineTasks[0]!.id}"]`).find('[draggable="true"]').exists()).toBe(false)
    expect(wrapper.get(`[data-task-id="${firstMachineTasks[1]!.id}"]`).get('[draggable="true"]').attributes('draggable')).toBe('true')
    expect(wrapper.get('[data-column-key="machine"]').classes()).toContain('sticky')
  })

  it('uses explicit field schemes and never exposes commercial columns', async () => {
    const wrapper = mountSpreadsheet({ fieldScheme: 'core' })
    const data = fixture()
    const futureTask = data.tasksByMachine.get(data.machines[0]!.id)![1]!
    const coreKeys = scheduleColumnsForScheme('core').map((column) => column.key)
    const screenKeys = scheduleColumnsForScheme('screen').map((column) => column.key)

    expect(coreKeys).toContain('status')
    expect(wrapper.find('[data-column-key="unitPrice"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('单价/啤')

    await wrapper.setProps({ bigScreen: true })
    expect(wrapper.find('[data-testid="schedule-spreadsheet-toolbar"]').exists()).toBe(false)
    for (const key of screenKeys) {
      expect(wrapper.find(`[data-column-key="${key}"]`).exists()).toBe(true)
    }
    expect(wrapper.find('[data-column-key="deliveryDue"]').exists()).toBe(false)
    expect(wrapper.find('[data-column-key="inboundAt"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('外发单价')
    await wrapper.get(`[data-task-id="${futureTask.id}"]`).trigger('keydown', {
      key: 'ArrowDown',
      altKey: true,
    })
    expect(wrapper.emitted('nudgeTask')).toBeUndefined()
  })

  it('collapses machine groups, auto-expands for search and supports keyboard nudge for future rows', async () => {
    const wrapper = mountSpreadsheet()
    const data = fixture()
    const firstMachine = data.machines[0]!
    const firstBody = wrapper.findAll('tbody')[0]!
    const futureTask = data.tasksByMachine.get(firstMachine.id)![1]!

    await firstBody.get('button[aria-label^="收起"]').trigger('click')
    expect(firstBody.findAll('[data-task-id]')).toHaveLength(0)

    await wrapper.setProps({ filters: { ...filters, search: futureTask.requirement.orderNo } })
    expect(wrapper.findAll('tbody')[0]!.findAll('[data-task-id]').length).toBeGreaterThan(0)

    await wrapper.get(`[data-task-id="${futureTask.id}"]`).trigger('keydown', {
      key: 'ArrowDown',
      altKey: true,
    })
    expect(wrapper.emitted('nudgeTask')).toContainEqual([futureTask.id, 'down'])
  })
})

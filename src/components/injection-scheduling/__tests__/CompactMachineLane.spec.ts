import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CompactMachineLane from '@/components/injection-scheduling/CompactMachineLane.vue'
import { cloneSchedulingSnapshot } from '@/data/injectionSchedulingMock'

describe('CompactMachineLane', () => {
  it('keeps the compact lane at 96px and exposes current plus next-task fields', () => {
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    const machine = snapshot.machines.find((item) => item.taskIds.length >= 3)!
    const tasks = machine.taskIds.map((id) => snapshot.tasks.find((task) => task.id === id)!)
    const wrapper = mount(CompactMachineLane, {
      props: { machine, tasks, density: 'compact', bigScreen: false },
    })

    expect(wrapper.classes()).toContain('h-24')
    expect(wrapper.text()).toContain(machine.name)
    expect(wrapper.text()).toContain(tasks[0]!.requirement.mold.moldNo)
    expect(wrapper.text()).toContain(tasks[1]!.requirement.mold.moldNo)
    expect(wrapper.get('.current-task-card').attributes('draggable')).toBeUndefined()
    expect(wrapper.get('.queue-task-chip').attributes('draggable')).toBe('true')
  })

  it('provides keyboard reordering for future tasks', async () => {
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    const machine = snapshot.machines.find((item) => item.taskIds.length >= 3)!
    const tasks = machine.taskIds.map((id) => snapshot.tasks.find((task) => task.id === id)!)
    const wrapper = mount(CompactMachineLane, {
      props: { machine, tasks, density: 'compact', bigScreen: false },
    })

    await wrapper.get('.queue-task-chip').trigger('keydown', { key: 'ArrowDown', altKey: true })
    expect(wrapper.emitted('nudgeTask')?.[0]).toEqual([tasks[1]!.id, 'down'])
  })
})

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SchedulingOverlays from '@/components/injection-scheduling/SchedulingOverlays.vue'
import { cloneSchedulingSnapshot } from '@/data/injectionSchedulingMock'

describe('SchedulingOverlays', () => {
  it('requires a validated confirmation before changing a future task', async () => {
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    const machine = snapshot.machines.find((item) => item.taskIds.length >= 3)!
    const task = snapshot.tasks.find((item) => item.id === machine.taskIds[1])!
    const wrapper = mount(SchedulingOverlays, {
      global: { stubs: { teleport: true } },
      props: {
        selectedTask: null,
        selectedMachine: null,
        selectedBacklog: null,
        machines: snapshot.machines,
        tasks: snapshot.tasks,
        pendingMove: {
          factoryId: 'huaxing',
          revision: 1,
          taskId: task.id,
          sourceMachineId: machine.id,
          targetMachineId: machine.id,
          targetIndex: 2,
        },
        pendingMoveValidation: {
          allowed: true,
          reasons: ['硬约束校验通过'],
          affectedTaskCount: 2,
        },
        backlog: snapshot.backlog,
        alertsOpen: false,
        rulesOpen: false,
        publishOpen: false,
        backlogOpen: false,
        optimizerOpen: false,
        optimizationResult: null,
        plan: snapshot.plan,
        factoryName: '华兴',
        backendConnected: false,
      },
    })

    expect(wrapper.text()).toContain('确认调整后续任务')
    expect(wrapper.text()).toContain('硬约束校验通过')
    await wrapper.get('button:last-of-type').trigger('click')
    expect(wrapper.emitted('confirmMove')).toHaveLength(1)
  })
})

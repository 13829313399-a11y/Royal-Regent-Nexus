import type { ScheduleTaskRecord } from '../types'

export function indexTasksByMachine(tasks: readonly ScheduleTaskRecord[]) {
  const tasksByMachine = new Map<string, ScheduleTaskRecord[]>()
  for (const task of tasks) {
    const machineId = task.machineId
    const machineTasks = tasksByMachine.get(machineId)
    if (machineTasks) machineTasks.push(task)
    else tasksByMachine.set(machineId, [task])
  }
  return tasksByMachine
}

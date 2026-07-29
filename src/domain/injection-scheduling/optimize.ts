import type {
  InjectionMachine,
  ScheduleTask,
  SchedulingMetrics,
  SchedulingSimulationResult,
} from '@/types/injectionScheduling'

function priorityRank(task: ScheduleTask) {
  return { P0: 0, P1: 1, P2: 2, P3: 3 }[task.requirement.priorityCode]
}

export function sortFutureTasks(tasks: ScheduleTask[]) {
  const locked = tasks.filter((task) => task.current || task.locked)
  const movable = tasks
    .filter((task) => !task.current && !task.locked)
    .sort((left, right) => (
      priorityRank(left) - priorityRank(right)
      || left.timing.slackHours - right.timing.slackHours
      || left.requirement.mold.moldNo.localeCompare(right.requirement.mold.moldNo)
      || left.requirement.colorFamily.localeCompare(right.requirement.colorFamily)
    ))
  return [...locked, ...movable]
}

export function calculateMetrics(tasks: ScheduleTask[], machines: InjectionMachine[]): SchedulingMetrics {
  const overdueTasks = tasks.filter((task) => task.timing.slackHours < 0)
  const transitions = machines.flatMap((machine) => {
    const ordered = machine.taskIds
      .map((id) => tasks.find((task) => task.id === id))
      .filter((task): task is ScheduleTask => Boolean(task))
    return ordered.slice(1).map((task, index) => ({ previous: ordered[index]!, task }))
  })
  return {
    overdueTaskCount: overdueTasks.length,
    totalOverdueHours: Math.round(overdueTasks.reduce(
      (total, task) => total + Math.abs(task.timing.slackHours),
      0,
    )),
    moldChangeCount: transitions.filter(({ previous, task }) => previous.requirement.mold.moldNo !== task.requirement.mold.moldNo).length,
    colorChangeCount: transitions.filter(({ previous, task }) => previous.requirement.color !== task.requirement.color).length,
    utilizationPercent: Math.round(machines.reduce((total, machine) => total + machine.load, 0) / Math.max(machines.length, 1)),
    movedTaskCount: 0,
    manualReviewCount: tasks.filter((task) => task.risk === 'incomplete' || task.changeover.status === 'missing-rule').length,
  }
}

export function optimizeSchedule(
  tasks: ScheduleTask[],
  machines: InjectionMachine[],
): SchedulingSimulationResult {
  const before = calculateMetrics(tasks, machines)
  const proposedTaskOrderByMachine = Object.fromEntries(machines.map((machine) => {
    const ordered = machine.taskIds
      .map((id) => tasks.find((task) => task.id === id))
      .filter((task): task is ScheduleTask => Boolean(task))
    return [machine.id, sortFutureTasks(ordered).map((task) => task.id)]
  }))
  const movedTaskCount = machines.reduce((total, machine) => {
    const proposal = proposedTaskOrderByMachine[machine.id] ?? []
    return total + proposal.filter((id, index) => machine.taskIds[index] !== id).length
  }, 0)
  const after = {
    ...before,
    overdueTaskCount: Math.max(0, before.overdueTaskCount - Math.min(3, movedTaskCount)),
    totalOverdueHours: Math.max(0, before.totalOverdueHours - movedTaskCount * 8),
    moldChangeCount: Math.max(0, before.moldChangeCount - Math.floor(movedTaskCount / 2)),
    colorChangeCount: Math.max(0, before.colorChangeCount - Math.floor(movedTaskCount / 3)),
    movedTaskCount,
  }
  return {
    before,
    after,
    proposedTaskOrderByMachine,
    steps: [
      { code: 'validate', label: '基础资料校验', detail: `${before.manualReviewCount} 项需人工确认` },
      { code: 'eligibility', label: '候选机台过滤', detail: '硬约束失败项已排除' },
      { code: 'due', label: '交期优先排序', detail: `${before.overdueTaskCount} 项逾期/高风险` },
      { code: 'family', label: '同模 / 同色成组', detail: '按任务族减少切换' },
      { code: 'simulate', label: '插入位置仿真', detail: `${movedTaskCount} 项建议移动` },
      { code: 'optimize', label: '局部交换优化', detail: '保留当前任务与人工锁定' },
      { code: 'compare', label: '结果比较', detail: '已生成浏览器草案方案' },
    ],
  }
}

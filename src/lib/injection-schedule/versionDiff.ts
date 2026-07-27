import type {
  InjectionOrder,
  InjectionScheduleTask,
} from '@/types/injectionSchedule'

export interface InjectionMovedTaskDiff {
  taskId: string
  orderId: string
  fromMachineId: string
  toMachineId: string
}

export interface InjectionReorderedTaskDiff {
  taskId: string
  orderId: string
  machineId: string
  fromIndex: number
  toIndex: number
}

export interface InjectionSplitOrderDiff {
  orderId: string
  beforeTaskCount: number
  afterTaskCount: number
  beforePlannedShots: number
  afterPlannedShots: number
  addedTaskIds: string[]
  quantityConserved: boolean
}

export interface InjectionLockTaskDiff {
  taskId: string
  orderId: string
  beforeLocked: boolean
  afterLocked: boolean
}

export type InjectionDeliveryRisk = 'unknown' | 'on_time' | 'late'

export interface InjectionDeliveryImpactDiff {
  orderId: string
  beforeCompletionAt: string | null
  afterCompletionAt: string | null
  dueAt: string | null
  beforeSlackHours: number | null
  afterSlackHours: number | null
  slackDeltaHours: number | null
  beforeRisk: InjectionDeliveryRisk
  afterRisk: InjectionDeliveryRisk
}

export interface InjectionChangeoverDiff {
  beforeCount: number
  afterCount: number
  deltaCount: number
  beforeSetupMinutes: number
  afterSetupMinutes: number
  deltaSetupMinutes: number
}

export interface InjectionVersionDiff {
  addedTaskIds: string[]
  removedTaskIds: string[]
  movedTasks: InjectionMovedTaskDiff[]
  reorderedTasks: InjectionReorderedTaskDiff[]
  splitOrders: InjectionSplitOrderDiff[]
  lockChanges: InjectionLockTaskDiff[]
  deliveryImpacts: InjectionDeliveryImpactDiff[]
  changeovers: InjectionChangeoverDiff
  affectedOrderIds: string[]
  counts: {
    added: number
    removed: number
    moved: number
    reordered: number
    splitOrders: number
    lockChanges: number
    deliveryImpacts: number
  }
}

export interface CalculateInjectionVersionDiffInput {
  beforeTasks: readonly InjectionScheduleTask[]
  afterTasks: readonly InjectionScheduleTask[]
  orders: readonly InjectionOrder[]
}

function activeTasks(tasks: readonly InjectionScheduleTask[]) {
  return tasks.filter((task) => task.status !== 'cancelled')
}

function parseTimestamp(value: string | null) {
  if (!value) return null
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : null
}

function taskOrder(tasks: readonly InjectionScheduleTask[]) {
  return [...activeTasks(tasks)].sort((left, right) => {
    const leftStart = parseTimestamp(left.startAt) ?? Number.POSITIVE_INFINITY
    const rightStart = parseTimestamp(right.startAt) ?? Number.POSITIVE_INFINITY
    return left.machineId.localeCompare(right.machineId)
      || leftStart - rightStart
      || left.id.localeCompare(right.id)
  })
}

function machineIndexes(tasks: readonly InjectionScheduleTask[]) {
  const indexes = new Map<string, number>()
  const counts = new Map<string, number>()
  for (const task of taskOrder(tasks)) {
    const index = counts.get(task.machineId) ?? 0
    indexes.set(task.id, index)
    counts.set(task.machineId, index + 1)
  }
  return indexes
}

function groupByOrder(tasks: readonly InjectionScheduleTask[]) {
  const grouped = new Map<string, InjectionScheduleTask[]>()
  for (const task of activeTasks(tasks)) {
    const orderTasks = grouped.get(task.orderId) ?? []
    orderTasks.push(task)
    grouped.set(task.orderId, orderTasks)
  }
  return grouped
}

function completionByOrder(tasks: readonly InjectionScheduleTask[]) {
  const completions = new Map<string, number>()
  for (const task of activeTasks(tasks)) {
    const endTimestamp = parseTimestamp(task.endAt)
    if (endTimestamp == null) continue
    completions.set(
      task.orderId,
      Math.max(completions.get(task.orderId) ?? Number.NEGATIVE_INFINITY, endTimestamp),
    )
  }
  return completions
}

function slackHours(dueTimestamp: number | null, completionTimestamp: number | null) {
  if (dueTimestamp == null || completionTimestamp == null) return null
  return (dueTimestamp - completionTimestamp) / 3_600_000
}

function deliveryRisk(slack: number | null): InjectionDeliveryRisk {
  if (slack == null) return 'unknown'
  return slack < 0 ? 'late' : 'on_time'
}

function calculateChangeovers(
  tasks: readonly InjectionScheduleTask[],
  orderById: ReadonlyMap<string, InjectionOrder>,
) {
  const byMachine = new Map<string, InjectionScheduleTask[]>()
  for (const task of taskOrder(tasks)) {
    const machineTasks = byMachine.get(task.machineId) ?? []
    machineTasks.push(task)
    byMachine.set(task.machineId, machineTasks)
  }

  let count = 0
  for (const machineTasks of byMachine.values()) {
    for (let index = 1; index < machineTasks.length; index += 1) {
      const previousMoldId = orderById.get(machineTasks[index - 1]!.orderId)?.moldId
      const currentMoldId = orderById.get(machineTasks[index]!.orderId)?.moldId
      if (previousMoldId && currentMoldId && previousMoldId !== currentMoldId) {
        count += 1
      }
    }
  }

  const setupMinutes = activeTasks(tasks).reduce((sum, task) =>
    sum + (Number.isFinite(task.setupMinutesBefore) ? task.setupMinutesBefore : 0), 0)
  return { count, setupMinutes }
}

export function calculateInjectionVersionDiff(
  input: CalculateInjectionVersionDiffInput,
): InjectionVersionDiff {
  const beforeTasks = activeTasks(input.beforeTasks)
  const afterTasks = activeTasks(input.afterTasks)
  const beforeById = new Map(beforeTasks.map((task) => [task.id, task]))
  const afterById = new Map(afterTasks.map((task) => [task.id, task]))
  const orderById = new Map(input.orders.map((order) => [order.id, order]))
  const addedTaskIds = [...afterById.keys()]
    .filter((taskId) => !beforeById.has(taskId))
    .sort()
  const removedTaskIds = [...beforeById.keys()]
    .filter((taskId) => !afterById.has(taskId))
    .sort()

  const stableTaskIds = [...beforeById.keys()]
    .filter((taskId) => afterById.has(taskId))
    .sort()
  const movedTasks: InjectionMovedTaskDiff[] = []
  const reorderedTasks: InjectionReorderedTaskDiff[] = []
  const lockChanges: InjectionLockTaskDiff[] = []
  const beforeIndexes = machineIndexes(beforeTasks)
  const afterIndexes = machineIndexes(afterTasks)

  for (const taskId of stableTaskIds) {
    const before = beforeById.get(taskId)!
    const after = afterById.get(taskId)!
    if (before.machineId !== after.machineId) {
      movedTasks.push({
        taskId,
        orderId: before.orderId,
        fromMachineId: before.machineId,
        toMachineId: after.machineId,
      })
    } else {
      const fromIndex = beforeIndexes.get(taskId)!
      const toIndex = afterIndexes.get(taskId)!
      if (fromIndex !== toIndex) {
        reorderedTasks.push({
          taskId,
          orderId: before.orderId,
          machineId: before.machineId,
          fromIndex,
          toIndex,
        })
      }
    }
    if (before.locked !== after.locked) {
      lockChanges.push({
        taskId,
        orderId: before.orderId,
        beforeLocked: before.locked,
        afterLocked: after.locked,
      })
    }
  }

  const beforeByOrder = groupByOrder(beforeTasks)
  const afterByOrder = groupByOrder(afterTasks)
  const splitOrders: InjectionSplitOrderDiff[] = []
  for (const [orderId, afterOrderTasks] of afterByOrder) {
    const beforeOrderTasks = beforeByOrder.get(orderId) ?? []
    if (beforeOrderTasks.length === 0 || afterOrderTasks.length <= beforeOrderTasks.length) continue
    const beforePlannedShots = beforeOrderTasks.reduce((sum, task) => sum + task.plannedShots, 0)
    const afterPlannedShots = afterOrderTasks.reduce((sum, task) => sum + task.plannedShots, 0)
    splitOrders.push({
      orderId,
      beforeTaskCount: beforeOrderTasks.length,
      afterTaskCount: afterOrderTasks.length,
      beforePlannedShots,
      afterPlannedShots,
      addedTaskIds: afterOrderTasks
        .filter((task) => !beforeById.has(task.id))
        .map((task) => task.id)
        .sort(),
      quantityConserved: beforePlannedShots === afterPlannedShots,
    })
  }
  splitOrders.sort((left, right) => left.orderId.localeCompare(right.orderId))

  const beforeCompletions = completionByOrder(beforeTasks)
  const afterCompletions = completionByOrder(afterTasks)
  const completionOrderIds = new Set([
    ...beforeCompletions.keys(),
    ...afterCompletions.keys(),
  ])
  const deliveryImpacts: InjectionDeliveryImpactDiff[] = []
  for (const orderId of [...completionOrderIds].sort()) {
    const beforeCompletion = beforeCompletions.get(orderId) ?? null
    const afterCompletion = afterCompletions.get(orderId) ?? null
    if (beforeCompletion === afterCompletion) continue
    const dueTimestamp = parseTimestamp(orderById.get(orderId)?.deliveryDueAt ?? null)
    const beforeSlack = slackHours(dueTimestamp, beforeCompletion)
    const afterSlack = slackHours(dueTimestamp, afterCompletion)
    deliveryImpacts.push({
      orderId,
      beforeCompletionAt: beforeCompletion == null ? null : new Date(beforeCompletion).toISOString(),
      afterCompletionAt: afterCompletion == null ? null : new Date(afterCompletion).toISOString(),
      dueAt: dueTimestamp == null ? null : new Date(dueTimestamp).toISOString(),
      beforeSlackHours: beforeSlack,
      afterSlackHours: afterSlack,
      slackDeltaHours: beforeSlack == null || afterSlack == null
        ? null
        : afterSlack - beforeSlack,
      beforeRisk: deliveryRisk(beforeSlack),
      afterRisk: deliveryRisk(afterSlack),
    })
  }

  const beforeChangeovers = calculateChangeovers(beforeTasks, orderById)
  const afterChangeovers = calculateChangeovers(afterTasks, orderById)
  const affectedOrderIds = uniqueOrderIds([
    ...addedTaskIds.map((taskId) => afterById.get(taskId)?.orderId),
    ...removedTaskIds.map((taskId) => beforeById.get(taskId)?.orderId),
    ...movedTasks.map((entry) => entry.orderId),
    ...reorderedTasks.map((entry) => entry.orderId),
    ...splitOrders.map((entry) => entry.orderId),
    ...lockChanges.map((entry) => entry.orderId),
    ...deliveryImpacts.map((entry) => entry.orderId),
  ])

  return {
    addedTaskIds,
    removedTaskIds,
    movedTasks,
    reorderedTasks,
    splitOrders,
    lockChanges,
    deliveryImpacts,
    changeovers: {
      beforeCount: beforeChangeovers.count,
      afterCount: afterChangeovers.count,
      deltaCount: afterChangeovers.count - beforeChangeovers.count,
      beforeSetupMinutes: beforeChangeovers.setupMinutes,
      afterSetupMinutes: afterChangeovers.setupMinutes,
      deltaSetupMinutes: afterChangeovers.setupMinutes - beforeChangeovers.setupMinutes,
    },
    affectedOrderIds,
    counts: {
      added: addedTaskIds.length,
      removed: removedTaskIds.length,
      moved: movedTasks.length,
      reordered: reorderedTasks.length,
      splitOrders: splitOrders.length,
      lockChanges: lockChanges.length,
      deliveryImpacts: deliveryImpacts.length,
    },
  }
}

function uniqueOrderIds(values: Array<string | undefined>) {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].sort()
}

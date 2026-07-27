import { calculateInjectionSetupCost } from '@/lib/injection-schedule/setupCost'
import type {
  InjectionMachine,
  InjectionMold,
  InjectionOrder,
  InjectionScheduleTask,
  InjectionSetupProfile,
  InjectionSetupRuleConfig,
} from '@/types/injectionSchedule'

export type InjectionScheduleMutation =
  | {
      type: 'assign'
      task: InjectionScheduleTask
      machineId: string
      index?: number
    }
  | {
      type: 'reorder'
      taskId: string
      index: number
    }
  | {
      type: 'move'
      taskId: string
      machineId: string
      index?: number
    }
  | {
      type: 'set_lock'
      taskId: string
      locked: boolean
    }
  | {
      type: 'split'
      taskId: string
      newTaskId: string
      splitPlannedShots: number
      machineId?: string
      index?: number
    }

export interface InjectionScheduleMutationResult {
  tasks: InjectionScheduleTask[]
  affectedMachineIds: string[]
  changedTaskIds: string[]
}

export interface ProjectInjectionScheduleInput {
  tasks: readonly InjectionScheduleTask[]
  affectedMachineIds: readonly string[]
  machines: readonly InjectionMachine[]
  orders: readonly InjectionOrder[]
  molds: readonly InjectionMold[]
  setupConfig: InjectionSetupRuleConfig
  planBaseAt: string
  /**
   * Explicit task durations are useful when the server already calculated
   * effective production rates. Missing entries fall back to targetShotsPerDay.
   */
  productionMinutesByTaskId?: Readonly<Record<string, number>>
  productionDayHours?: number
  preserveProtectedTaskTimes?: boolean
}

export interface ProjectInjectionScheduleResult {
  tasks: InjectionScheduleTask[]
  affectedMachineIds: string[]
  projectedTaskIds: string[]
}

export interface MutateAndProjectInjectionScheduleInput
  extends Omit<ProjectInjectionScheduleInput, 'tasks' | 'affectedMachineIds'> {
  tasks: readonly InjectionScheduleTask[]
  mutation: InjectionScheduleMutation
}

export interface MutateAndProjectInjectionScheduleResult
  extends ProjectInjectionScheduleResult {
  changedTaskIds: string[]
}

const protectedStatuses = new Set<InjectionScheduleTask['status']>([
  'published',
  'running',
  'completed',
  'cancelled',
])

function uniqueSorted(values: readonly string[]) {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right))
}

function assertFinitePositive(value: number, label: string) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new RangeError(`${label}必须是大于 0 的有限数值`)
  }
}

function assertTaskMutable(task: InjectionScheduleTask, action: string) {
  if (task.locked) {
    throw new Error(`任务 ${task.id} 已锁定，不能${action}`)
  }
  if (protectedStatuses.has(task.status)) {
    throw new Error(`任务 ${task.id} 状态为 ${task.status}，不能${action}`)
  }
}

function findTaskIndex(tasks: readonly InjectionScheduleTask[], taskId: string) {
  const index = tasks.findIndex((task) => task.id === taskId)
  if (index < 0) {
    throw new Error(`找不到排程任务 ${taskId}`)
  }
  return index
}

function normalizedMachineIndex(index: number | undefined, taskCount: number) {
  if (index == null) return taskCount
  if (!Number.isInteger(index) || index < 0 || index > taskCount) {
    throw new RangeError(`机台任务位置必须在 0–${taskCount} 之间`)
  }
  return index
}

function insertAtMachineIndex(
  tasks: readonly InjectionScheduleTask[],
  task: InjectionScheduleTask,
  machineId: string,
  index?: number,
) {
  const result = [...tasks]
  const machineIndexes = result
    .map((entry, taskIndex) => entry.machineId === machineId ? taskIndex : -1)
    .filter((taskIndex) => taskIndex >= 0)
  const targetIndex = normalizedMachineIndex(index, machineIndexes.length)

  if (machineIndexes.length === 0) {
    result.push(task)
    return result
  }

  const insertionIndex = targetIndex === machineIndexes.length
    ? machineIndexes.at(-1)! + 1
    : machineIndexes[targetIndex]!
  result.splice(insertionIndex, 0, task)
  return result
}

function applyAssign(
  tasks: readonly InjectionScheduleTask[],
  mutation: Extract<InjectionScheduleMutation, { type: 'assign' }>,
): InjectionScheduleMutationResult {
  if (tasks.some((task) => task.id === mutation.task.id)) {
    throw new Error(`排程任务 ${mutation.task.id} 已存在`)
  }
  assertFinitePositive(mutation.task.plannedShots, '计划啤数')
  const assignedTask = {
    ...mutation.task,
    machineId: mutation.machineId,
  }

  return {
    tasks: insertAtMachineIndex(tasks, assignedTask, mutation.machineId, mutation.index),
    affectedMachineIds: [mutation.machineId],
    changedTaskIds: [assignedTask.id],
  }
}

function applyMove(
  tasks: readonly InjectionScheduleTask[],
  taskId: string,
  machineId: string,
  index: number | undefined,
  action: string,
): InjectionScheduleMutationResult {
  const taskIndex = findTaskIndex(tasks, taskId)
  const task = tasks[taskIndex]!
  assertTaskMutable(task, action)

  const withoutTask = [...tasks]
  withoutTask.splice(taskIndex, 1)
  const movedTask = {
    ...task,
    machineId,
  }

  return {
    tasks: insertAtMachineIndex(withoutTask, movedTask, machineId, index),
    affectedMachineIds: uniqueSorted([task.machineId, machineId]),
    changedTaskIds: [task.id],
  }
}

function applySetLock(
  tasks: readonly InjectionScheduleTask[],
  mutation: Extract<InjectionScheduleMutation, { type: 'set_lock' }>,
): InjectionScheduleMutationResult {
  const taskIndex = findTaskIndex(tasks, mutation.taskId)
  const task = tasks[taskIndex]!
  if (protectedStatuses.has(task.status)) {
    throw new Error(`任务 ${task.id} 状态为 ${task.status}，不能修改锁定状态`)
  }
  const result = [...tasks]
  result[taskIndex] = {
    ...task,
    locked: mutation.locked,
  }

  return {
    tasks: result,
    affectedMachineIds: [task.machineId],
    changedTaskIds: [task.id],
  }
}

function applySplit(
  tasks: readonly InjectionScheduleTask[],
  mutation: Extract<InjectionScheduleMutation, { type: 'split' }>,
): InjectionScheduleMutationResult {
  const taskIndex = findTaskIndex(tasks, mutation.taskId)
  const task = tasks[taskIndex]!
  assertTaskMutable(task, '拆单')
  assertFinitePositive(mutation.splitPlannedShots, '拆出啤数')
  if (mutation.splitPlannedShots >= task.plannedShots) {
    throw new RangeError('拆出啤数必须小于原任务计划啤数')
  }
  if (tasks.some((entry) => entry.id === mutation.newTaskId)) {
    throw new Error(`排程任务 ${mutation.newTaskId} 已存在`)
  }

  const sourceMachineTasks = tasks.filter((entry) => entry.machineId === task.machineId)
  const sourceMachineIndex = sourceMachineTasks.findIndex((entry) => entry.id === task.id)
  const destinationMachineId = mutation.machineId ?? task.machineId
  const destinationIndex = mutation.index ?? (
    destinationMachineId === task.machineId ? sourceMachineIndex + 1 : undefined
  )
  const reducedTask = {
    ...task,
    plannedShots: task.plannedShots - mutation.splitPlannedShots,
  }
  const splitTask: InjectionScheduleTask = {
    ...task,
    id: mutation.newTaskId,
    machineId: destinationMachineId,
    plannedShots: mutation.splitPlannedShots,
    locked: false,
    status: 'draft',
    source: 'manual',
  }
  const withReducedTask = [...tasks]
  withReducedTask[taskIndex] = reducedTask

  return {
    tasks: insertAtMachineIndex(
      withReducedTask,
      splitTask,
      destinationMachineId,
      destinationIndex,
    ),
    affectedMachineIds: uniqueSorted([task.machineId, destinationMachineId]),
    changedTaskIds: [task.id, splitTask.id],
  }
}

export function applyInjectionScheduleMutation(
  tasks: readonly InjectionScheduleTask[],
  mutation: InjectionScheduleMutation,
): InjectionScheduleMutationResult {
  switch (mutation.type) {
    case 'assign':
      return applyAssign(tasks, mutation)
    case 'reorder': {
      const taskIndex = findTaskIndex(tasks, mutation.taskId)
      return applyMove(
        tasks,
        mutation.taskId,
        tasks[taskIndex]!.machineId,
        mutation.index,
        '调整顺序',
      )
    }
    case 'move':
      return applyMove(
        tasks,
        mutation.taskId,
        mutation.machineId,
        mutation.index,
        '跨机移动',
      )
    case 'set_lock':
      return applySetLock(tasks, mutation)
    case 'split':
      return applySplit(tasks, mutation)
  }
}

function parseTimestamp(value: string, label: string) {
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) {
    throw new Error(`${label}不是有效时间：${value}`)
  }
  return timestamp
}

function laterTimestamp(left: number, rightValue: string | null, label: string) {
  if (!rightValue) return left
  return Math.max(left, parseTimestamp(rightValue, label))
}

function setupProfile(
  order: InjectionOrder,
  mold: InjectionMold | undefined,
): InjectionSetupProfile {
  return {
    moldId: order.moldId || mold?.id || null,
    productName: order.productName,
    materialCode: order.materialCode ?? mold?.materialCode ?? null,
    colorCode: order.colorCode,
    colorRank: order.colorRank ?? mold?.defaultColorRank ?? null,
  }
}

function taskProductionMinutes(
  task: InjectionScheduleTask,
  order: InjectionOrder,
  input: ProjectInjectionScheduleInput,
) {
  const explicitMinutes = input.productionMinutesByTaskId?.[task.id]
  if (explicitMinutes != null) {
    assertFinitePositive(explicitMinutes, `任务 ${task.id} 的生产分钟数`)
    return explicitMinutes
  }

  const productionDayHours = input.productionDayHours ?? 24
  assertFinitePositive(productionDayHours, '生产日小时数')
  const targetShotsPerDay = order.targetShotsPerDay
  if (targetShotsPerDay == null) {
    throw new Error(`订单 ${order.id} 缺少 targetShotsPerDay，无法投影生产时长`)
  }
  assertFinitePositive(targetShotsPerDay, `订单 ${order.id} 的日产目标`)
  assertFinitePositive(task.plannedShots, `任务 ${task.id} 的计划啤数`)
  return task.plannedShots / targetShotsPerDay * productionDayHours * 60
}

function isProtectedTask(task: InjectionScheduleTask) {
  return task.locked || protectedStatuses.has(task.status)
}

export function projectInjectionSchedule(
  input: ProjectInjectionScheduleInput,
): ProjectInjectionScheduleResult {
  const affectedMachineIds = uniqueSorted(input.affectedMachineIds)
  const affectedMachineIdSet = new Set(affectedMachineIds)
  const machineById = new Map(input.machines.map((machine) => [machine.id, machine]))
  const orderById = new Map(input.orders.map((order) => [order.id, order]))
  const moldById = new Map(input.molds.map((mold) => [mold.id, mold]))
  const planBaseTimestamp = parseTimestamp(input.planBaseAt, '计划版本基准时间')
  const preserveProtectedTaskTimes = input.preserveProtectedTaskTimes ?? true
  const projectedById = new Map<string, InjectionScheduleTask>()

  for (const machineId of affectedMachineIds) {
    const machine = machineById.get(machineId)
    if (!machine) {
      throw new Error(`找不到机台 ${machineId}`)
    }
    let cursor = laterTimestamp(
      planBaseTimestamp,
      machine.availableFrom,
      `机台 ${machineId} 可用时间`,
    )
    let previousProfile: InjectionSetupProfile | null = null
    const machineTasks = input.tasks.filter((task) =>
      task.machineId === machineId && task.status !== 'cancelled')

    for (const task of machineTasks) {
      const order = orderById.get(task.orderId)
      if (!order) {
        throw new Error(`任务 ${task.id} 找不到订单 ${task.orderId}`)
      }
      const mold = moldById.get(order.moldId)
      const nextProfile = setupProfile(order, mold)
      const setupCost = calculateInjectionSetupCost({
        previous: previousProfile,
        next: nextProfile,
        config: input.setupConfig,
      })
      const startTimestamp = cursor + setupCost.totalMinutes * 60_000
      const endTimestamp = startTimestamp
        + taskProductionMinutes(task, order, input) * 60_000
      const projectedTask: InjectionScheduleTask = {
        ...task,
        startAt: new Date(startTimestamp).toISOString(),
        endAt: new Date(endTimestamp).toISOString(),
        setupMinutesBefore: setupCost.totalMinutes,
        setupReason: [...setupCost.reasons],
      }

      if (
        preserveProtectedTaskTimes
        && isProtectedTask(task)
        && (
          parseTimestamp(task.startAt, `受保护任务 ${task.id} 开始时间`) !== startTimestamp
          || parseTimestamp(task.endAt, `受保护任务 ${task.id} 完成时间`) !== endTimestamp
        )
      ) {
        throw new Error(`排程调整会移动受保护任务 ${task.id}`)
      }

      projectedById.set(task.id, projectedTask)
      cursor = endTimestamp
      previousProfile = nextProfile
    }
  }

  const tasks = input.tasks.map((task) =>
    affectedMachineIdSet.has(task.machineId)
      ? projectedById.get(task.id) ?? task
      : task)

  return {
    tasks,
    affectedMachineIds,
    projectedTaskIds: [...projectedById.keys()],
  }
}

export function mutateAndProjectInjectionSchedule(
  input: MutateAndProjectInjectionScheduleInput,
): MutateAndProjectInjectionScheduleResult {
  const mutationResult = applyInjectionScheduleMutation(input.tasks, input.mutation)
  const projectionResult = projectInjectionSchedule({
    ...input,
    tasks: mutationResult.tasks,
    affectedMachineIds: mutationResult.affectedMachineIds,
  })

  return {
    ...projectionResult,
    changedTaskIds: mutationResult.changedTaskIds,
  }
}

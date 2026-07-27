import type {
  ConstraintResult,
  InjectionMachine,
  InjectionOrder,
  InjectionScheduleTask,
} from '@/types/injectionSchedule'

export type InjectionScheduleConflictCode =
  | 'duplicate_task'
  | 'missing_machine'
  | 'missing_order'
  | 'factory_mismatch'
  | 'invalid_quantity'
  | 'invalid_time'
  | 'machine_locked'
  | 'task_overlap'
  | 'unavailable_window'
  | 'constraint_failure'
  | 'constraint_unknown'
  | 'constraint_override'
  | 'constraint_snapshot_missing'
  | 'order_overallocated'

export interface InjectionScheduleConflict {
  id: string
  code: InjectionScheduleConflictCode
  severity: 'error' | 'warning'
  blocking: boolean
  autoPublishBlocked: boolean
  message: string
  taskIds: string[]
  machineId: string | null
  orderId: string | null
  constraintCode: string | null
  windowId: string | null
}

export interface ValidateInjectionScheduleInput {
  factoryId: string
  tasks: readonly InjectionScheduleTask[]
  machines: readonly InjectionMachine[]
  orders: readonly InjectionOrder[]
}

export interface ValidateInjectionScheduleResult {
  conflicts: InjectionScheduleConflict[]
  valid: boolean
  autoPublishAllowed: boolean
}

function parseTimestamp(value: string) {
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : null
}

function taskBusyStart(task: InjectionScheduleTask, startTimestamp: number) {
  const setupMinutes = Number.isFinite(task.setupMinutesBefore) && task.setupMinutesBefore > 0
    ? task.setupMinutesBefore
    : 0
  return startTimestamp - setupMinutes * 60_000
}

function intervalsOverlap(
  leftStart: number,
  leftEnd: number,
  rightStart: number,
  rightEnd: number,
) {
  return leftStart < rightEnd && rightStart < leftEnd
}

function makeConflict(
  input: Omit<InjectionScheduleConflict, 'id'>,
): InjectionScheduleConflict {
  const identity = [
    input.code,
    input.machineId ?? '-',
    input.orderId ?? '-',
    input.taskIds.join(','),
    input.constraintCode ?? '-',
    input.windowId ?? '-',
  ].join(':')
  return {
    id: identity,
    ...input,
  }
}

function constraintConflict(
  task: InjectionScheduleTask,
  result: ConstraintResult,
): InjectionScheduleConflict | null {
  if (result.status === 'pass') return null
  const statusConfig = result.status === 'override'
    ? {
        code: 'constraint_override' as const,
        severity: 'warning' as const,
        message: `${result.label}使用人工例外：${result.reason}`,
      }
    : result.status === 'unknown'
      ? {
          code: 'constraint_unknown' as const,
          severity: 'error' as const,
          message: `${result.label}资料未知：${result.reason}`,
        }
      : {
          code: 'constraint_failure' as const,
          severity: 'error' as const,
          message: `${result.label}不通过：${result.reason}`,
        }

  return makeConflict({
    ...statusConfig,
    blocking: result.blocking,
    autoPublishBlocked: result.autoPublishBlocked,
    taskIds: [task.id],
    machineId: task.machineId,
    orderId: task.orderId,
    constraintCode: result.code,
    windowId: null,
  })
}

function sortConflicts(conflicts: InjectionScheduleConflict[]) {
  return conflicts.sort((left, right) =>
    left.id.localeCompare(right.id) || left.message.localeCompare(right.message))
}

export function validateInjectionSchedule(
  input: ValidateInjectionScheduleInput,
): ValidateInjectionScheduleResult {
  const conflicts: InjectionScheduleConflict[] = []
  const machineById = new Map(input.machines.map((machine) => [machine.id, machine]))
  const orderById = new Map(input.orders.map((order) => [order.id, order]))
  const seenTaskIds = new Set<string>()
  const activeTasks = input.tasks.filter((task) => task.status !== 'cancelled')
  const validIntervals = new Map<string, {
    task: InjectionScheduleTask
    busyStart: number
    end: number
  }>()

  for (const task of activeTasks) {
    if (seenTaskIds.has(task.id)) {
      conflicts.push(makeConflict({
        code: 'duplicate_task',
        severity: 'error',
        blocking: true,
        autoPublishBlocked: true,
        message: `任务 ID ${task.id} 重复`,
        taskIds: [task.id],
        machineId: task.machineId,
        orderId: task.orderId,
        constraintCode: null,
        windowId: null,
      }))
    }
    seenTaskIds.add(task.id)

    const machine = machineById.get(task.machineId)
    const order = orderById.get(task.orderId)
    if (!machine) {
      conflicts.push(makeConflict({
        code: 'missing_machine',
        severity: 'error',
        blocking: true,
        autoPublishBlocked: true,
        message: `任务 ${task.id} 找不到机台 ${task.machineId}`,
        taskIds: [task.id],
        machineId: task.machineId,
        orderId: task.orderId,
        constraintCode: null,
        windowId: null,
      }))
    }
    if (!order) {
      conflicts.push(makeConflict({
        code: 'missing_order',
        severity: 'error',
        blocking: true,
        autoPublishBlocked: true,
        message: `任务 ${task.id} 找不到订单 ${task.orderId}`,
        taskIds: [task.id],
        machineId: task.machineId,
        orderId: task.orderId,
        constraintCode: null,
        windowId: null,
      }))
    }
    if (
      task.factoryId !== input.factoryId
      || (machine && machine.factoryId !== input.factoryId)
      || (order && order.factoryId !== input.factoryId)
    ) {
      conflicts.push(makeConflict({
        code: 'factory_mismatch',
        severity: 'error',
        blocking: true,
        autoPublishBlocked: true,
        message: `任务 ${task.id} 的任务、机台或订单厂区与 ${input.factoryId} 不一致`,
        taskIds: [task.id],
        machineId: task.machineId,
        orderId: task.orderId,
        constraintCode: null,
        windowId: null,
      }))
    }
    if (!Number.isFinite(task.plannedShots) || task.plannedShots <= 0) {
      conflicts.push(makeConflict({
        code: 'invalid_quantity',
        severity: 'error',
        blocking: true,
        autoPublishBlocked: true,
        message: `任务 ${task.id} 的计划啤数必须大于 0`,
        taskIds: [task.id],
        machineId: task.machineId,
        orderId: task.orderId,
        constraintCode: null,
        windowId: null,
      }))
    }
    if (machine?.schedulingLocked) {
      conflicts.push(makeConflict({
        code: 'machine_locked',
        severity: 'error',
        blocking: true,
        autoPublishBlocked: true,
        message: `机台 ${machine.machineNo} 已锁定，任务 ${task.id} 不可排入`,
        taskIds: [task.id],
        machineId: task.machineId,
        orderId: task.orderId,
        constraintCode: null,
        windowId: null,
      }))
    }

    const startTimestamp = parseTimestamp(task.startAt)
    const endTimestamp = parseTimestamp(task.endAt)
    if (startTimestamp == null || endTimestamp == null || endTimestamp <= startTimestamp) {
      conflicts.push(makeConflict({
        code: 'invalid_time',
        severity: 'error',
        blocking: true,
        autoPublishBlocked: true,
        message: `任务 ${task.id} 的开始或完成时间无效`,
        taskIds: [task.id],
        machineId: task.machineId,
        orderId: task.orderId,
        constraintCode: null,
        windowId: null,
      }))
    } else {
      validIntervals.set(task.id, {
        task,
        busyStart: taskBusyStart(task, startTimestamp),
        end: endTimestamp,
      })
    }

    if (task.constraintSnapshot.length === 0) {
      conflicts.push(makeConflict({
        code: 'constraint_snapshot_missing',
        severity: 'error',
        blocking: true,
        autoPublishBlocked: true,
        message: `任务 ${task.id} 缺少约束校验快照`,
        taskIds: [task.id],
        machineId: task.machineId,
        orderId: task.orderId,
        constraintCode: null,
        windowId: null,
      }))
    } else {
      for (const result of task.constraintSnapshot) {
        const conflict = constraintConflict(task, result)
        if (conflict) conflicts.push(conflict)
      }
    }
  }

  for (const machine of input.machines) {
    const intervals = [...validIntervals.values()]
      .filter((entry) => entry.task.machineId === machine.id)
      .sort((left, right) =>
        left.busyStart - right.busyStart || left.task.id.localeCompare(right.task.id))

    for (let index = 0; index < intervals.length; index += 1) {
      const current = intervals[index]!
      for (let nextIndex = index + 1; nextIndex < intervals.length; nextIndex += 1) {
        const next = intervals[nextIndex]!
        if (next.busyStart >= current.end) break
        conflicts.push(makeConflict({
          code: 'task_overlap',
          severity: 'error',
          blocking: true,
          autoPublishBlocked: true,
          message: `机台 ${machine.machineNo} 的任务 ${current.task.id} 与 ${next.task.id} 时间重叠`,
          taskIds: [current.task.id, next.task.id],
          machineId: machine.id,
          orderId: null,
          constraintCode: null,
          windowId: null,
        }))
      }

      for (const window of machine.unavailableWindows) {
        const windowStart = parseTimestamp(window.startAt)
        const windowEnd = parseTimestamp(window.endAt)
        if (
          windowStart != null
          && windowEnd != null
          && windowEnd > windowStart
          && intervalsOverlap(current.busyStart, current.end, windowStart, windowEnd)
        ) {
          conflicts.push(makeConflict({
            code: 'unavailable_window',
            severity: 'error',
            blocking: true,
            autoPublishBlocked: true,
            message: `任务 ${current.task.id} 占用机台 ${machine.machineNo} 的${window.kind}窗口：${window.reason}`,
            taskIds: [current.task.id],
            machineId: machine.id,
            orderId: current.task.orderId,
            constraintCode: null,
            windowId: window.id,
          }))
        }
      }
    }
  }

  const tasksByOrder = new Map<string, InjectionScheduleTask[]>()
  for (const task of activeTasks) {
    const grouped = tasksByOrder.get(task.orderId) ?? []
    grouped.push(task)
    tasksByOrder.set(task.orderId, grouped)
  }
  for (const [orderId, orderTasks] of tasksByOrder) {
    const order = orderById.get(orderId)
    if (!order) continue
    const totalPlannedShots = orderTasks.reduce((sum, task) => sum + task.plannedShots, 0)
    if (totalPlannedShots > order.outstandingShots) {
      conflicts.push(makeConflict({
        code: 'order_overallocated',
        severity: 'error',
        blocking: true,
        autoPublishBlocked: true,
        message: `订单 ${order.orderNo} 计划 ${totalPlannedShots} 啤，超过欠数 ${order.outstandingShots}`,
        taskIds: orderTasks.map((task) => task.id).sort(),
        machineId: null,
        orderId,
        constraintCode: null,
        windowId: null,
      }))
    }
  }

  const sortedConflicts = sortConflicts(conflicts)
  return {
    conflicts: sortedConflicts,
    valid: sortedConflicts.every((conflict) => !conflict.blocking),
    autoPublishAllowed: sortedConflicts.every((conflict) => !conflict.autoPublishBlocked),
  }
}

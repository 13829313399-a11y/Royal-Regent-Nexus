import { defineStore } from 'pinia'
import { injectionScheduleApi } from '@/api/injectionSchedule'
import { getInjectionPreviewDataset } from '@/data/injectionScheduleMock'
import { getApiErrorMessage } from '@/lib/http'
import type {
  InjectionActualProjection,
  InjectionAutomationResult,
  InjectionAutomationRun,
  InjectionAutoDraftInput,
  InjectionDraftCreateInput,
  InjectionFormalScheduleTask,
  InjectionImportBatch,
  InjectionImportConfirmInput,
  InjectionMachineCreateInput,
  InjectionMachineRecord,
  InjectionMachineUpdateInput,
  InjectionMoldCreateInput,
  InjectionMoldRecord,
  InjectionMoldUpdateInput,
  InjectionOrderCreateInput,
  InjectionOrderRecommendationResponse,
  InjectionOrderRecord,
  InjectionOrderUpdateInput,
  InjectionPlanVersion,
  InjectionPlanVersionDetail,
  InjectionPreviewDataset,
  InjectionReplanInput,
  InjectionRevisionConflict,
  InjectionScheduleOperation,
  InjectionScheduleOperationRequest,
  InjectionScheduleOperationResult,
  InjectionScheduleRuleConfigUpdateInput,
  InjectionScheduleRuleConfigV3,
  InjectionScheduleWorkspace,
  InjectionShiftActual,
  InjectionShiftActualCorrectionInput,
  InjectionShiftActualCreateInput,
  InjectionShiftActualListOptions,
  InjectionShiftActualResult,
  InjectionValidationResult,
  InjectionVersionCloneInput,
  InjectionVersionDiff,
  InjectionVersionPublishInput,
} from '@/types/injectionSchedule'

export type InjectionWorkspaceMode = 'empty' | 'formal' | 'preview'

export interface LoadInjectionWorkspaceOptions {
  versionId?: string
  /**
   * Preview fallback is deliberately opt-in. It is only used for unavailable
   * endpoints and never for authorization, validation, or revision failures.
   */
  allowPreviewFallback?: boolean
}

export interface InjectionManualConfirmationRequirement {
  code: 'manual_confirmation_required'
  message: string
  reasons: string[]
}

type MasterCollectionKey = 'machines' | 'molds' | 'orders'

function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function responseStatus(error: unknown) {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined
  const response = (error as { response?: { status?: unknown } }).response
  return typeof response?.status === 'number' ? response.status : undefined
}

function responseDetail(error: unknown) {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined
  return (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
}

export function isInjectionScheduleApiUnavailable(error: unknown) {
  const status = responseStatus(error)
  if (status != null) return [404, 501, 502, 503, 504].includes(status)
  return error instanceof TypeError
    || (error instanceof Error && /network|timeout|failed to fetch/i.test(error.message))
}

export function getInjectionRevisionConflict(
  error: unknown,
): InjectionRevisionConflict | null {
  const detail = responseDetail(error)
  if (!detail || typeof detail !== 'object') return null
  const record = detail as Record<string, unknown>
  if (record.code !== 'revision_conflict') return null
  const currentRevision = Number(record.current_revision)
  const expectedRevision = Number(record.expected_revision)
  if (!Number.isFinite(currentRevision) || !Number.isFinite(expectedRevision)) return null

  return {
    code: 'revision_conflict',
    message: typeof record.message === 'string'
      ? record.message
      : '计划版本已被其他计划员更新',
    currentRevision,
    expectedRevision,
    entityId: typeof record.entity_id === 'string' ? record.entity_id : '',
  }
}

export function getInjectionManualConfirmationRequirement(
  error: unknown,
): InjectionManualConfirmationRequirement | null {
  const detail = responseDetail(error)
  if (!detail || typeof detail !== 'object') return null
  const record = detail as Record<string, unknown>
  if (record.code !== 'manual_confirmation_required') return null
  return {
    code: 'manual_confirmation_required',
    message: typeof record.message === 'string' && record.message.trim()
      ? record.message.trim()
      : '资料不足，需要计划员人工确认后才能保存到草稿',
    reasons: Array.isArray(record.reasons)
      ? record.reasons.filter((reason): reason is string =>
          typeof reason === 'string' && Boolean(reason.trim()))
      : [],
  }
}

function errorMessage(error: unknown) {
  const conflict = getInjectionRevisionConflict(error)
  if (conflict) {
    return `${conflict.message}（提交 revision ${conflict.expectedRevision}，服务端当前 revision ${conflict.currentRevision}）`
  }
  const detail = responseDetail(error)
  if (detail && typeof detail === 'object') {
    const record = detail as Record<string, unknown>
    const message = typeof record.message === 'string'
      ? record.message.trim()
      : getApiErrorMessage(error)
    const reasons = Array.isArray(record.reasons)
      ? record.reasons.filter((reason): reason is string =>
          typeof reason === 'string' && Boolean(reason.trim()))
      : []
    if (reasons.length) {
      return `${message || '硬约束冲突'}：${reasons.join('；')}`
    }
  }
  return getApiErrorMessage(error)
}

function assertFormalWorkspace(
  workspace: InjectionScheduleWorkspace,
  factoryId: string,
) {
  if (workspace.mode !== 'formal') {
    throw new Error('正式排产接口返回了非正式工作区')
  }
  if (workspace.factoryId !== factoryId) {
    throw new Error(`排产工作区厂区不一致：请求 ${factoryId}，返回 ${workspace.factoryId}`)
  }
  for (const record of [
    ...workspace.machines,
    ...workspace.molds,
    ...workspace.orders,
    ...workspace.tasks,
  ]) {
    if (record.factoryId !== factoryId) {
      throw new Error(`正式排产工作区包含跨厂记录 ${record.id}`)
    }
  }
}

function assertRecordFactory(record: { id: string; factoryId: string }, factoryId: string) {
  if (record.factoryId !== factoryId) {
    throw new Error(`接口返回跨厂记录 ${record.id}`)
  }
}

function assertRuleConfigFactory(
  record: InjectionScheduleRuleConfigV3,
  factoryId: string,
) {
  if (record.factoryId !== factoryId) {
    throw new Error(`规则配置厂区不一致：请求 ${factoryId}，返回 ${record.factoryId}`)
  }
}

function insertTask(
  tasks: InjectionFormalScheduleTask[],
  task: InjectionFormalScheduleTask,
  targetIndex?: number,
) {
  const sameMachine = tasks
    .filter((entry) => entry.machineId === task.machineId && entry.id !== task.id)
    .sort((left, right) => left.sequenceNo - right.sequenceNo)
  const insertionIndex = targetIndex == null
    ? sameMachine.length
    : Math.min(Math.max(Math.trunc(targetIndex), 0), sameMachine.length)
  sameMachine.splice(insertionIndex, 0, task)
  const otherMachines = tasks.filter((entry) =>
    entry.machineId !== task.machineId && entry.id !== task.id)
  return [...otherMachines, ...sameMachine]
}

function resequenceTasks(tasks: InjectionFormalScheduleTask[]) {
  const grouped = new Map<string, InjectionFormalScheduleTask[]>()
  for (const task of tasks) {
    const rows = grouped.get(task.machineId) ?? []
    rows.push(task)
    grouped.set(task.machineId, rows)
  }
  return [...grouped.values()].flatMap((rows) =>
    rows
      .sort((left, right) => left.sequenceNo - right.sequenceNo)
      .map((task, sequenceNo) => ({ ...task, sequenceNo })))
}

function assertTaskIsMutable(task: InjectionFormalScheduleTask) {
  if (task.locked) throw new Error(`任务 ${task.id} 已锁定，不能移动或拆分`)
}

function optimisticTaskForAssignment(
  workspace: InjectionScheduleWorkspace,
  operation: Extract<InjectionScheduleOperation, { type: 'assign' }>,
  requestId: string,
) {
  const version = workspace.activeVersion
  if (!version) throw new Error('当前没有可编辑的草稿版本')
  const order = workspace.orders.find((entry) => entry.id === operation.orderId)
  if (!order) throw new Error(`待排订单 ${operation.orderId} 不存在`)
  const machine = workspace.machines.find((entry) => entry.id === operation.machineId)
  if (!machine) throw new Error(`目标机台 ${operation.machineId} 不存在`)
  const machineTasks = workspace.tasks
    .filter((entry) => entry.machineId === machine.id)
    .sort((left, right) => left.sequenceNo - right.sequenceNo)
  const previous = machineTasks.at(-1)
  const startAt = previous?.plannedFinishAt
    || machine.availableAt
    || version.planBaseAt
  const startAtTimestamp = Date.parse(startAt)
  const plannedQty = operation.plannedQty ?? order.outstandingQty
  const targetPerDay = Math.max(order.dailyTargetQty ?? plannedQty, 1)
  const durationHours = Math.max(1, plannedQty / targetPerDay * 24)
  const mold = workspace.molds.find((entry) => entry.moldCode === order.moldCode)

  return {
    id: `optimistic-${requestId}-${order.id}`,
    factoryId: workspace.factoryId,
    versionId: version.id,
    orderId: order.id,
    orderNo: order.orderNo,
    productCode: order.productCode,
    productName: order.productName,
    moldId: mold?.id ?? null,
    moldCode: order.moldCode,
    machineId: machine.id,
    machineCode: machine.machineCode,
    sequenceNo: machineTasks.length,
    plannedQty,
    plannedStartAt: startAt,
    plannedFinishAt: Number.isFinite(startAtTimestamp)
      ? new Date(startAtTimestamp + durationHours * 3_600_000).toISOString()
      : startAt,
    setupHours: 0,
    durationHours,
    locked: false,
    splitGroupId: '',
    parentTaskId: '',
    riskLevel: 'pending_validation',
    riskReasons: ['等待服务端增量校验'],
    revision: version.revision,
    changeReason: operation.reason ?? '',
  } satisfies InjectionFormalScheduleTask
}

export function applyOptimisticScheduleOperations(
  workspaceSource: InjectionScheduleWorkspace,
  request: InjectionScheduleOperationRequest,
) {
  const workspace = cloneValue(workspaceSource)
  if (!request.reason.trim()) throw new Error('草稿保存原因不能为空')
  if (request.commands.length < 1 || request.commands.length > 100) {
    throw new Error('每次排程变更必须包含 1 至 100 条命令')
  }
  const version = workspace.activeVersion
  if (!version || version.status !== 'draft') {
    throw new Error('当前没有可编辑的草稿版本')
  }
  if (version.revision !== request.expectedRevision) {
    throw new Error(
      `本地草稿 revision ${version.revision} 与提交 revision ${request.expectedRevision} 不一致`,
    )
  }

  let tasks = workspace.tasks.slice()
  const requestId = request.requestId ?? `revision-${request.expectedRevision}`

  for (const command of request.commands) {
    if (
      command.manualConfirmation
      && (
        !command.manualConfirmation.confirmed
        || command.manualConfirmation.reason.trim().length < 4
      )
    ) {
      throw new Error('人工确认必须勾选确认，且原因至少填写 4 个字符')
    }

    if (command.type === 'assign') {
      if (
        command.plannedQty != null
        && (command.plannedQty <= 0 || !Number.isFinite(command.plannedQty))
      ) {
        throw new Error('预排数量必须是正数')
      }
      const task = optimisticTaskForAssignment(workspace, command, requestId)
      tasks = insertTask(tasks, task, command.targetIndex)
      continue
    }

    if (command.type === 'refresh_masters') {
      if (
        command.taskId
        && !tasks.some((entry) => entry.id === command.taskId)
      ) {
        throw new Error(`排程任务 ${command.taskId} 不存在`)
      }
      continue
    }

    const task = tasks.find((entry) => entry.id === command.taskId)
    if (!task) throw new Error(`排程任务 ${command.taskId} 不存在`)

    if (command.type === 'lock' || command.type === 'unlock') {
      tasks = tasks.map((entry) => entry.id === task.id
        ? {
            ...entry,
            locked: command.type === 'lock',
            changeReason: command.reason ?? request.reason,
          }
        : entry)
      continue
    }

    assertTaskIsMutable(task)

    if (command.type === 'move') {
      const machine = workspace.machines.find((entry) => entry.id === command.machineId)
      if (!machine) throw new Error(`目标机台 ${command.machineId} 不存在`)
      tasks = insertTask(
        tasks,
        {
          ...task,
          machineId: command.machineId,
          machineCode: machine.machineCode,
          changeReason: command.reason ?? request.reason,
        },
        command.targetIndex,
      )
      continue
    }

    if (command.type === 'reorder') {
      tasks = insertTask(
        tasks,
        { ...task, changeReason: command.reason ?? request.reason },
        command.targetIndex,
      )
      continue
    }

    if (command.type !== 'split') {
      throw new Error(`不支持的排程操作 ${(command as InjectionScheduleOperation).type}`)
    }
    if (
      !Number.isFinite(command.splitQty)
      || command.splitQty <= 0
      || command.splitQty >= task.plannedQty
    ) {
      throw new Error('拆出数量必须大于 0 且小于原任务计划数量')
    }

    tasks = tasks.filter((entry) => entry.id !== task.id)
    const splitGroupId = task.splitGroupId || `split-${task.id}`
    const destinationMachineId = command.machineId || task.machineId
    const destinationMachine = workspace.machines.find(
      (entry) => entry.id === destinationMachineId,
    )
    if (!destinationMachine) throw new Error(`目标机台 ${destinationMachineId} 不存在`)
    const remainingTask = {
      ...task,
      plannedQty: task.plannedQty - command.splitQty,
      splitGroupId,
      changeReason: command.reason ?? request.reason,
    }
    const splitTask = {
      ...task,
      id: `optimistic-${requestId}-${task.id}-split`,
      machineId: destinationMachine.id,
      machineCode: destinationMachine.machineCode,
      plannedQty: command.splitQty,
      splitGroupId,
      parentTaskId: task.id,
      sequenceNo: task.sequenceNo + 1,
      changeReason: command.reason ?? request.reason,
    }
    tasks = insertTask(tasks, remainingTask, task.sequenceNo)
    tasks = insertTask(
      tasks,
      splitTask,
      command.targetIndex ?? (destinationMachineId === task.machineId ? task.sequenceNo + 1 : undefined),
    )
  }

  workspace.tasks = resequenceTasks(tasks)
  return workspace
}

function replaceVersion(
  versions: InjectionPlanVersion[],
  version: InjectionPlanVersion,
) {
  const next = versions.filter((entry) => entry.id !== version.id)
  next.push(version)
  return next.sort((left, right) => right.versionNo - left.versionNo)
}

function applyOperationResult(
  workspaceSource: InjectionScheduleWorkspace,
  result: InjectionScheduleOperationResult,
) {
  const workspace = cloneValue(workspaceSource)
  assertRecordFactory(result.version, workspace.factoryId)
  for (const task of result.tasks) assertRecordFactory(task, workspace.factoryId)
  workspace.activeVersion = result.version
  workspace.versions = replaceVersion(workspace.versions, result.version)
  workspace.tasks = result.tasks
  workspace.conflicts = result.conflicts
  return workspace
}

function applyAutomationResult(
  workspaceSource: InjectionScheduleWorkspace,
  result: InjectionAutomationResult,
) {
  const workspace = cloneValue(workspaceSource)
  assertRecordFactory(result.version, workspace.factoryId)
  assertRecordFactory(result.run, workspace.factoryId)
  for (const task of result.tasks) assertRecordFactory(task, workspace.factoryId)
  if (
    result.run.sourceVersionId !== workspace.activeVersion?.id
    || result.run.resultVersionId !== result.version.id
  ) {
    throw new Error('自动排程结果与当前计划版本不一致')
  }
  workspace.activeVersion = result.version
  workspace.versions = replaceVersion(workspace.versions, result.version)
  workspace.tasks = result.tasks
  workspace.conflicts = result.conflicts
  return workspace
}

function automationTaskProjections(
  beforeTasks: InjectionFormalScheduleTask[],
  result: InjectionAutomationResult,
) {
  const serverRows = result.run.impact.rows
  if (serverRows.length > 0) {
    const afterById = new Map(result.tasks.map((task) => [task.id, task]))
    const beforeById = new Map(beforeTasks.map((task) => [task.id, task]))
    return serverRows.map((row): InjectionActualProjection => {
      const after = afterById.get(row.taskId)
      const before = beforeById.get(row.sourceTaskId)
      return {
        taskId: row.taskId,
        orderId: row.orderId,
        machineId: row.machineIdAfter,
        machineCode: after?.machineCode ?? before?.machineCode ?? row.machineIdAfter,
        plannedQtyBefore: row.plannedQtyBefore,
        plannedQtyAfter: row.plannedQtyAfter,
        plannedFinishAtBefore: row.plannedFinishAtBefore,
        plannedFinishAtAfter: row.plannedFinishAtAfter,
        etaShiftMinutes: row.etaShiftMinutes,
        shortageQty: 0,
      }
    })
  }
  const affectedTaskIds = new Set(result.affectedTaskIds)
  const beforeById = new Map(beforeTasks.map((task) => [task.id, task]))
  return result.tasks.flatMap((task): InjectionActualProjection[] => {
    const before = beforeById.get(task.parentTaskId || task.id)
    if (!before) return []
    if (
      affectedTaskIds.size > 0
      && !affectedTaskIds.has(task.id)
      && !affectedTaskIds.has(before.id)
    ) return []
    if (
      before.machineId === task.machineId
      && before.plannedQty === task.plannedQty
      && before.plannedFinishAt === task.plannedFinishAt
    ) return []
    const beforeFinish = Date.parse(before.plannedFinishAt)
    const afterFinish = Date.parse(task.plannedFinishAt)
    return [{
      taskId: task.id,
      orderId: task.orderId,
      machineId: task.machineId,
      machineCode: task.machineCode,
      plannedQtyBefore: before.plannedQty,
      plannedQtyAfter: task.plannedQty,
      plannedFinishAtBefore: before.plannedFinishAt,
      plannedFinishAtAfter: task.plannedFinishAt,
      etaShiftMinutes: Number.isFinite(beforeFinish) && Number.isFinite(afterFinish)
        ? Math.round((afterFinish - beforeFinish) / 60_000)
        : 0,
      shortageQty: 0,
    }]
  })
}

function applyActualResult(
  workspaceSource: InjectionScheduleWorkspace,
  result: InjectionShiftActualResult,
) {
  const workspace = cloneValue(workspaceSource)
  const sourceVersion = workspace.activeVersion
  if (!sourceVersion) throw new Error('实绩回写前没有打开正式计划版本')
  assertRecordFactory(result.actual, workspace.factoryId)
  assertRecordFactory(result.updatedOrder, workspace.factoryId)
  assertRecordFactory(result.version, workspace.factoryId)
  for (const task of result.tasks) assertRecordFactory(task, workspace.factoryId)
  if (
    result.actual.versionId !== result.version.id
    || result.actual.orderId !== result.updatedOrder.id
  ) {
    throw new Error('实绩回写结果与当前版本或订单不一致')
  }
  if (sourceVersion.status === 'published') {
    const rollingTask = result.tasks.find((task) => task.id === result.actual.taskId)
    if (
      result.version.id === sourceVersion.id
      || result.version.status !== 'draft'
      || result.version.baseVersionId !== sourceVersion.id
      || result.actual.sourceVersionId !== sourceVersion.id
      || result.actual.sourceTaskId === result.actual.taskId
      || rollingTask?.parentTaskId !== result.actual.sourceTaskId
    ) {
      throw new Error('已发布计划的实绩没有返回可追溯的滚动草稿')
    }
  } else if (
    sourceVersion.status !== 'draft'
    || result.version.id !== sourceVersion.id
    || (
      result.actual.sourceVersionId !== sourceVersion.id
      && result.actual.sourceVersionId !== sourceVersion.baseVersionId
    )
  ) {
    throw new Error('实绩回写只能更新当前草稿，或从已发布计划创建滚动草稿')
  }
  workspace.activeVersion = result.version
  workspace.versions = replaceVersion(workspace.versions, result.version)
  workspace.tasks = result.tasks
  const orderIndex = workspace.orders.findIndex(
    (entry) => entry.id === result.updatedOrder.id,
  )
  if (orderIndex < 0) throw new Error(`实绩回写订单 ${result.updatedOrder.id} 不存在`)
  workspace.orders[orderIndex] = result.updatedOrder
  return workspace
}

function applyVersionDetail(
  workspaceSource: InjectionScheduleWorkspace,
  detail: InjectionPlanVersionDetail,
) {
  const workspace = cloneValue(workspaceSource)
  assertRecordFactory(detail.version, workspace.factoryId)
  for (const task of detail.tasks) assertRecordFactory(task, workspace.factoryId)
  workspace.activeVersion = detail.version
  workspace.versions = replaceVersion(workspace.versions, detail.version)
  workspace.tasks = detail.tasks
  workspace.conflicts = detail.conflicts
  return workspace
}

export const useInjectionScheduleStore = defineStore('injection-schedule', {
  state: () => ({
    factoryId: null as string | null,
    mode: 'empty' as InjectionWorkspaceMode,
    formalWorkspace: null as InjectionScheduleWorkspace | null,
    previewWorkspace: null as InjectionPreviewDataset | null,
    importBatch: null as InjectionImportBatch | null,
    importHistory: [] as InjectionImportBatch[],
    validation: null as InjectionValidationResult | null,
    versionDiff: null as InjectionVersionDiff | null,
    recommendation: null as InjectionOrderRecommendationResponse | null,
    phase3RuleConfig: null as InjectionScheduleRuleConfigV3 | null,
    phase4Run: null as InjectionAutomationRun | null,
    phase4Result: null as InjectionAutomationResult | null,
    automationProjections: [] as InjectionActualProjection[],
    shiftActuals: [] as InjectionShiftActual[],
    actualProjections: [] as InjectionActualProjection[],
    lastActualResult: null as InjectionShiftActualResult | null,
    revisionConflict: null as InjectionRevisionConflict | null,
    manualConfirmationRequirement: null as InjectionManualConfirmationRequirement | null,
    loading: false,
    importLoading: false,
    masterLoading: false,
    versionLoading: false,
    recommendationLoading: false,
    ruleConfigLoading: false,
    ruleConfigSaving: false,
    phase4Loading: false,
    actualsLoading: false,
    mutationPending: false,
    errorMessage: '',
    loadRequestId: 0,
    mutationRequestId: 0,
    recommendationRequestId: 0,
    ruleConfigRequestId: 0,
    phase4RequestId: 0,
    actualsRequestId: 0,
  }),

  getters: {
    activeWorkspace(state): InjectionScheduleWorkspace | InjectionPreviewDataset | null {
      return state.mode === 'formal'
        ? state.formalWorkspace
        : state.mode === 'preview'
          ? state.previewWorkspace
          : null
    },
    activeVersion(state) {
      return state.formalWorkspace?.activeVersion ?? null
    },
    canMutate(state) {
      return state.mode === 'formal'
        && state.formalWorkspace?.activeVersion?.status === 'draft'
        && !state.mutationPending
    },
    canPublish(state) {
      return state.mode === 'formal'
        && state.formalWorkspace?.activeVersion?.status === 'draft'
        && state.validation?.status === 'passed'
        && state.validation.blockingCount === 0
        && state.validation.versionRevision === state.formalWorkspace.activeVersion.revision
        && state.validation.versionId === state.formalWorkspace.activeVersion.id
        && state.validation.dataHash === state.formalWorkspace.activeVersion.dataHash
        && !state.mutationPending
    },
  },

  actions: {
    clearTransientState() {
      this.importBatch = null
      this.importHistory = []
      this.validation = null
      this.versionDiff = null
      this.recommendation = null
      this.phase3RuleConfig = null
      this.phase4Run = null
      this.phase4Result = null
      this.automationProjections = []
      this.shiftActuals = []
      this.actualProjections = []
      this.lastActualResult = null
      this.revisionConflict = null
      this.manualConfirmationRequirement = null
      this.errorMessage = ''
    },

    setFormalWorkspace(workspace: InjectionScheduleWorkspace) {
      assertFormalWorkspace(workspace, workspace.factoryId)
      this.factoryId = workspace.factoryId
      this.mode = 'formal'
      this.formalWorkspace = workspace
      this.previewWorkspace = null
    },

    setPreviewWorkspace(workspace: InjectionPreviewDataset) {
      this.factoryId = workspace.factoryId
      this.mode = 'preview'
      this.previewWorkspace = workspace
      this.formalWorkspace = null
    },

    async loadWorkspace(
      factoryId: string,
      options: LoadInjectionWorkspaceOptions = {},
    ) {
      const requestId = ++this.loadRequestId
      ++this.mutationRequestId
      this.mutationPending = false
      this.importLoading = false
      this.masterLoading = false
      this.versionLoading = false
      this.recommendationLoading = false
      this.ruleConfigLoading = false
      this.ruleConfigSaving = false
      this.phase4Loading = false
      this.actualsLoading = false
      ++this.recommendationRequestId
      ++this.ruleConfigRequestId
      ++this.phase4RequestId
      ++this.actualsRequestId
      this.factoryId = factoryId
      this.mode = 'empty'
      this.formalWorkspace = null
      this.previewWorkspace = null
      this.clearTransientState()
      this.loading = true

      try {
        const workspace = await injectionScheduleApi.getWorkspace(
          factoryId,
          options.versionId,
        )
        if (requestId !== this.loadRequestId || this.factoryId !== factoryId) return undefined
        assertFormalWorkspace(workspace, factoryId)
        this.setFormalWorkspace(workspace)
        return workspace
      } catch (error) {
        if (requestId !== this.loadRequestId || this.factoryId !== factoryId) return undefined
        if (options.allowPreviewFallback && isInjectionScheduleApiUnavailable(error)) {
          const preview = getInjectionPreviewDataset(factoryId)
          this.setPreviewWorkspace(preview)
          this.errorMessage = `正式排产接口不可用，当前仅显示明确的 mock 快照预览：${errorMessage(error)}`
          return preview
        }
        this.errorMessage = errorMessage(error)
        return undefined
      } finally {
        if (requestId === this.loadRequestId) this.loading = false
      }
    },

    requireFormalWorkspace() {
      if (this.mode !== 'formal' || !this.formalWorkspace || !this.factoryId) {
        throw new Error('当前不是正式排产工作区，禁止写入')
      }
      return {
        factoryId: this.factoryId,
        workspace: this.formalWorkspace,
      }
    },

    setMutationError(error: unknown) {
      this.revisionConflict = getInjectionRevisionConflict(error)
      this.manualConfirmationRequirement = getInjectionManualConfirmationRequirement(error)
      this.errorMessage = errorMessage(error)
    },

    async loadRecommendations(
      orderId: string,
      options: { limit?: number; plannedQty?: number } = {},
    ) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const version = workspace.activeVersion
      if (!version) throw new Error('当前没有可用于推荐的计划版本')
      const order = workspace.orders.find((entry) => entry.id === orderId)
      if (!order) throw new Error(`待排订单 ${orderId} 不存在`)

      const requestId = ++this.recommendationRequestId
      this.recommendationLoading = true
      this.recommendation = null
      this.errorMessage = ''
      try {
        const response = await injectionScheduleApi.getRecommendations(
          factoryId,
          version.id,
          orderId,
          options,
        )
        if (
          requestId !== this.recommendationRequestId
          || this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
        ) return undefined
        if (response.factoryId !== factoryId) {
          throw new Error(`推荐结果厂区不一致：请求 ${factoryId}，返回 ${response.factoryId}`)
        }
        if (
          response.versionId !== version.id
          || response.versionRevision !== version.revision
        ) {
          throw new Error('推荐结果与当前计划版本 revision 不一致，请重新计算')
        }
        if (
          response.orderId !== order.id
          || response.orderRevision !== order.revision
        ) {
          throw new Error('推荐结果与当前订单 revision 不一致，请重新计算')
        }
        this.recommendation = response
        return response
      } catch (error) {
        if (
          requestId !== this.recommendationRequestId
          || this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
        ) return undefined
        this.errorMessage = errorMessage(error)
        throw error
      } finally {
        if (requestId === this.recommendationRequestId) {
          this.recommendationLoading = false
        }
      }
    },

    async loadRuleConfig() {
      const { factoryId } = this.requireFormalWorkspace()
      const requestId = ++this.ruleConfigRequestId
      this.ruleConfigLoading = true
      this.errorMessage = ''
      try {
        const config = await injectionScheduleApi.getRuleConfig(factoryId)
        assertRuleConfigFactory(config, factoryId)
        if (
          requestId !== this.ruleConfigRequestId
          || this.factoryId !== factoryId
          || this.mode !== 'formal'
        ) return undefined
        this.phase3RuleConfig = config
        return config
      } catch (error) {
        if (requestId === this.ruleConfigRequestId && this.factoryId === factoryId) {
          this.errorMessage = errorMessage(error)
        }
        throw error
      } finally {
        if (requestId === this.ruleConfigRequestId) this.ruleConfigLoading = false
      }
    },

    async updateRuleConfig(input: InjectionScheduleRuleConfigUpdateInput) {
      const { factoryId } = this.requireFormalWorkspace()
      const current = this.phase3RuleConfig
      if (!current) throw new Error('请先读取当前厂区规则配置')
      if (input.expectedRevision !== current.revision) {
        throw new Error(
          `本地规则 revision ${current.revision} 与提交 revision ${input.expectedRevision} 不一致`,
        )
      }
      this.ruleConfigSaving = true
      this.revisionConflict = null
      this.errorMessage = ''
      try {
        const config = await injectionScheduleApi.updateRuleConfig(factoryId, input)
        assertRuleConfigFactory(config, factoryId)
        if (this.factoryId !== factoryId || this.mode !== 'formal') return undefined
        this.phase3RuleConfig = config
        this.recommendation = null
        ++this.recommendationRequestId
        return config
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.ruleConfigSaving = false
      }
    },

    async previewImport(file: File) {
      const { factoryId } = this.requireFormalWorkspace()
      this.importLoading = true
      this.errorMessage = ''
      try {
        const batch = await injectionScheduleApi.previewImport(factoryId, file)
        assertRecordFactory(batch, factoryId)
        if (this.factoryId !== factoryId || this.mode !== 'formal') return undefined
        this.importBatch = batch
        return batch
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.importLoading = false
      }
    },

    async loadImports() {
      const { factoryId } = this.requireFormalWorkspace()
      this.importLoading = true
      try {
        const batches = await injectionScheduleApi.listImports(factoryId)
        for (const batch of batches) assertRecordFactory(batch, factoryId)
        if (this.factoryId !== factoryId || this.mode !== 'formal') return []
        this.importHistory = batches
        return batches
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.importLoading = false
      }
    },

    async confirmImport(
      batchId: string,
      input: InjectionImportConfirmInput,
    ): Promise<InjectionImportBatch | undefined> {
      const { factoryId } = this.requireFormalWorkspace()
      this.importLoading = true
      this.errorMessage = ''
      try {
        const batch = await injectionScheduleApi.confirmImport(factoryId, batchId, input)
        assertRecordFactory(batch, factoryId)
        if (this.factoryId !== factoryId || this.mode !== 'formal') return undefined
        const workspace = await this.loadWorkspace(factoryId, {
          versionId: batch.draftVersionId || undefined,
        })
        if (!workspace || workspace.mode !== 'formal') {
          throw new Error('导入已确认，但正式工作区刷新失败，请重新读取')
        }
        this.importBatch = batch
        return batch
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.importLoading = false
      }
    },

    async loadMasters(kind: MasterCollectionKey) {
      const { factoryId } = this.requireFormalWorkspace()
      this.masterLoading = true
      try {
        const records = kind === 'machines'
          ? await injectionScheduleApi.listMachines(factoryId)
          : kind === 'molds'
            ? await injectionScheduleApi.listMolds(factoryId)
            : await injectionScheduleApi.listOrders(factoryId)
        for (const record of records) assertRecordFactory(record, factoryId)
        if (this.factoryId !== factoryId || this.mode !== 'formal' || !this.formalWorkspace) {
          return []
        }
        if (kind === 'machines') this.formalWorkspace.machines = records as InjectionMachineRecord[]
        else if (kind === 'molds') this.formalWorkspace.molds = records as InjectionMoldRecord[]
        else this.formalWorkspace.orders = records as InjectionOrderRecord[]
        this.validation = null
        this.versionDiff = null
        this.recommendation = null
        ++this.recommendationRequestId
        return records
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.masterLoading = false
      }
    },

    async createMachine(input: InjectionMachineCreateInput) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      this.masterLoading = true
      this.revisionConflict = null
      this.errorMessage = ''
      try {
        const record = await injectionScheduleApi.createMachine(factoryId, input)
        assertRecordFactory(record, factoryId)
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          workspace.machines.push(record)
          this.validation = null
          this.versionDiff = null
          this.recommendation = null
          ++this.recommendationRequestId
        }
        return record
      } catch (error) {
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (this.factoryId === factoryId) this.masterLoading = false
      }
    },

    async createMold(input: InjectionMoldCreateInput) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      this.masterLoading = true
      this.revisionConflict = null
      this.errorMessage = ''
      try {
        const record = await injectionScheduleApi.createMold(factoryId, input)
        assertRecordFactory(record, factoryId)
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          workspace.molds.push(record)
          this.validation = null
          this.versionDiff = null
          this.recommendation = null
          ++this.recommendationRequestId
        }
        return record
      } catch (error) {
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (this.factoryId === factoryId) this.masterLoading = false
      }
    },

    async createOrder(input: InjectionOrderCreateInput) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      this.masterLoading = true
      this.revisionConflict = null
      this.errorMessage = ''
      try {
        const record = await injectionScheduleApi.createOrder(factoryId, input)
        assertRecordFactory(record, factoryId)
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          workspace.orders.push(record)
          this.validation = null
          this.versionDiff = null
          this.recommendation = null
          ++this.recommendationRequestId
        }
        return record
      } catch (error) {
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (this.factoryId === factoryId) this.masterLoading = false
      }
    },

    async updateMachine(
      machineId: string,
      expectedRevision: number,
      input: InjectionMachineUpdateInput,
    ) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const index = workspace.machines.findIndex((entry) => entry.id === machineId)
      if (index < 0) throw new Error(`机台 ${machineId} 不存在`)
      const before = cloneValue(workspace.machines[index])
      this.masterLoading = true
      this.revisionConflict = null
      this.errorMessage = ''
      workspace.machines[index] = { ...workspace.machines[index], ...input }
      try {
        const record = await injectionScheduleApi.updateMachine(
          factoryId,
          machineId,
          expectedRevision,
          input,
        )
        assertRecordFactory(record, factoryId)
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          workspace.machines[index] = record
          this.validation = null
          this.versionDiff = null
          this.recommendation = null
          ++this.recommendationRequestId
        }
        return record
      } catch (error) {
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          workspace.machines[index] = before
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (this.factoryId === factoryId) this.masterLoading = false
      }
    },

    async updateMold(
      moldId: string,
      expectedRevision: number,
      input: InjectionMoldUpdateInput,
    ) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const index = workspace.molds.findIndex((entry) => entry.id === moldId)
      if (index < 0) throw new Error(`模具 ${moldId} 不存在`)
      const before = cloneValue(workspace.molds[index])
      this.masterLoading = true
      this.revisionConflict = null
      this.errorMessage = ''
      workspace.molds[index] = { ...workspace.molds[index], ...input }
      try {
        const record = await injectionScheduleApi.updateMold(
          factoryId,
          moldId,
          expectedRevision,
          input,
        )
        assertRecordFactory(record, factoryId)
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          workspace.molds[index] = record
          this.validation = null
          this.versionDiff = null
          this.recommendation = null
          ++this.recommendationRequestId
        }
        return record
      } catch (error) {
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          workspace.molds[index] = before
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (this.factoryId === factoryId) this.masterLoading = false
      }
    },

    async updateOrder(
      orderId: string,
      expectedRevision: number,
      input: InjectionOrderUpdateInput,
    ) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const index = workspace.orders.findIndex((entry) => entry.id === orderId)
      if (index < 0) throw new Error(`订单 ${orderId} 不存在`)
      const before = cloneValue(workspace.orders[index])
      this.masterLoading = true
      this.revisionConflict = null
      this.errorMessage = ''
      workspace.orders[index] = { ...workspace.orders[index], ...input }
      try {
        const record = await injectionScheduleApi.updateOrder(
          factoryId,
          orderId,
          expectedRevision,
          input,
        )
        assertRecordFactory(record, factoryId)
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          workspace.orders[index] = record
          this.validation = null
          this.versionDiff = null
          this.recommendation = null
          ++this.recommendationRequestId
        }
        return record
      } catch (error) {
        if (this.factoryId === factoryId && this.formalWorkspace === workspace) {
          workspace.orders[index] = before
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (this.factoryId === factoryId) this.masterLoading = false
      }
    },

    async createDraft(input: InjectionDraftCreateInput) {
      const { factoryId } = this.requireFormalWorkspace()
      this.versionLoading = true
      try {
        const version = await injectionScheduleApi.createDraftVersion(factoryId, input)
        assertRecordFactory(version, factoryId)
        if (this.factoryId !== factoryId || this.mode !== 'formal') return undefined
        await this.loadWorkspace(factoryId, { versionId: version.id })
        return version
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.versionLoading = false
      }
    },

    async loadVersion(versionId: string) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      this.versionLoading = true
      try {
        const detail = await injectionScheduleApi.getVersion(factoryId, versionId)
        if (this.factoryId !== factoryId || this.formalWorkspace !== workspace) return undefined
        this.formalWorkspace = applyVersionDetail(workspace, detail)
        this.validation = null
        this.versionDiff = null
        this.recommendation = null
        ++this.recommendationRequestId
        return detail
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.versionLoading = false
      }
    },

    async executeOperations(input: InjectionScheduleOperationRequest) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const version = workspace.activeVersion
      if (!version) throw new Error('当前没有可编辑的草稿版本')
      if (this.mutationPending) throw new Error('已有排程变更正在保存，请稍后再试')

      const mutationId = ++this.mutationRequestId
      const before = cloneValue(workspace)
      const optimistic = applyOptimisticScheduleOperations(workspace, input)
      this.formalWorkspace = optimistic
      this.mutationPending = true
      this.revisionConflict = null
      this.manualConfirmationRequirement = null
      this.errorMessage = ''
      this.validation = null
      this.versionDiff = null
      this.recommendation = null
      ++this.recommendationRequestId

      try {
        const result = await injectionScheduleApi.executeOperations(
          factoryId,
          version.id,
          input,
        )
        if (
          mutationId !== this.mutationRequestId
          || this.factoryId !== factoryId
          || this.mode !== 'formal'
        ) return undefined
        this.formalWorkspace = applyOperationResult(optimistic, result)
        return result
      } catch (error) {
        if (
          mutationId === this.mutationRequestId
          && this.factoryId === factoryId
          && this.mode === 'formal'
        ) {
          this.formalWorkspace = before
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (mutationId === this.mutationRequestId) this.mutationPending = false
      }
    },

    saveDraft(input: InjectionScheduleOperationRequest) {
      return this.executeOperations(input)
    },

    async generateAutoDraft(input: InjectionAutoDraftInput) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const version = workspace.activeVersion
      if (!version || version.status !== 'draft') {
        throw new Error('当前没有可生成自动排程的草稿版本')
      }
      if (input.expectedRevision !== version.revision) {
        throw new Error(
          `本地草稿 revision ${version.revision} 与自动排程 revision ${input.expectedRevision} 不一致`,
        )
      }
      if (this.mutationPending || this.phase4Loading) {
        throw new Error('已有排程计算正在执行，请稍后再试')
      }

      const requestId = ++this.phase4RequestId
      this.phase4Loading = true
      this.mutationPending = true
      this.revisionConflict = null
      this.manualConfirmationRequirement = null
      this.errorMessage = ''
      try {
        const result = await injectionScheduleApi.generateAutoDraft(
          factoryId,
          version.id,
          input,
        )
        if (
          requestId !== this.phase4RequestId
          || this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
        ) return undefined
        this.phase4Run = result.run
        this.phase4Result = result
        this.automationProjections = automationTaskProjections(
          workspace.tasks,
          result,
        )
        if (!input.dryRun && result.run.status === 'applied') {
          this.formalWorkspace = applyAutomationResult(workspace, result)
          this.validation = null
          this.versionDiff = null
          this.recommendation = null
          ++this.recommendationRequestId
        }
        return result
      } catch (error) {
        if (
          requestId === this.phase4RequestId
          && this.factoryId === factoryId
          && this.formalWorkspace === workspace
        ) {
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (requestId === this.phase4RequestId) {
          this.phase4Loading = false
          this.mutationPending = false
        }
      }
    },

    async replanActiveVersion(input: InjectionReplanInput) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const version = workspace.activeVersion
      if (!version || version.status !== 'draft') {
        throw new Error('当前没有可执行局部重排的草稿版本')
      }
      if (input.expectedRevision !== version.revision) {
        throw new Error(
          `本地草稿 revision ${version.revision} 与局部重排 revision ${input.expectedRevision} 不一致`,
        )
      }
      if (this.mutationPending || this.phase4Loading) {
        throw new Error('已有排程计算正在执行，请稍后再试')
      }

      const requestId = ++this.phase4RequestId
      this.phase4Loading = true
      this.mutationPending = true
      this.revisionConflict = null
      this.manualConfirmationRequirement = null
      this.errorMessage = ''
      try {
        const result = await injectionScheduleApi.replanVersion(
          factoryId,
          version.id,
          input,
        )
        if (
          requestId !== this.phase4RequestId
          || this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
        ) return undefined
        this.phase4Run = result.run
        this.phase4Result = result
        this.automationProjections = automationTaskProjections(
          workspace.tasks,
          result,
        )
        if (!input.dryRun && result.run.status === 'applied') {
          this.formalWorkspace = applyAutomationResult(workspace, result)
          this.validation = null
          this.versionDiff = null
          this.recommendation = null
          ++this.recommendationRequestId
        }
        return result
      } catch (error) {
        if (
          requestId === this.phase4RequestId
          && this.factoryId === factoryId
          && this.formalWorkspace === workspace
        ) {
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (requestId === this.phase4RequestId) {
          this.phase4Loading = false
          this.mutationPending = false
        }
      }
    },

    async loadActuals(options: InjectionShiftActualListOptions = {}) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const requestId = ++this.actualsRequestId
      this.actualsLoading = true
      this.errorMessage = ''
      try {
        const actuals = await injectionScheduleApi.listActuals(factoryId, options)
        for (const actual of actuals) assertRecordFactory(actual, factoryId)
        if (
          requestId !== this.actualsRequestId
          || this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
        ) return []
        this.shiftActuals = actuals
        return actuals
      } catch (error) {
        if (
          requestId === this.actualsRequestId
          && this.factoryId === factoryId
          && this.formalWorkspace === workspace
        ) {
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (requestId === this.actualsRequestId) this.actualsLoading = false
      }
    },

    async writeActual(input: InjectionShiftActualCreateInput) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const version = workspace.activeVersion
      if (!version || version.id !== input.versionId) {
        throw new Error('实绩回写版本不是当前打开版本')
      }
      if (version.status !== 'draft' && version.status !== 'published') {
        throw new Error('实绩回写只能基于当前草稿或已发布计划执行')
      }
      if (version.revision !== input.expectedVersionRevision) {
        throw new Error(
          `本地草稿 revision ${version.revision} 与实绩回写 revision ${input.expectedVersionRevision} 不一致`,
        )
      }
      const task = workspace.tasks.find((entry) => entry.id === input.taskId)
      const order = workspace.orders.find((entry) => entry.id === input.orderId)
      if (
        !task
        || !order
        || task.orderId !== order.id
        || task.machineId !== input.machineId
      ) {
        throw new Error('实绩任务、订单和机台不属于同一当前厂区排程')
      }
      if (order.revision !== input.expectedOrderRevision) {
        throw new Error(
          `本地订单 revision ${order.revision} 与实绩回写 revision ${input.expectedOrderRevision} 不一致`,
        )
      }
      if (this.mutationPending) throw new Error('已有排程写入正在执行，请稍后再试')

      const mutationId = ++this.mutationRequestId
      this.mutationPending = true
      this.revisionConflict = null
      this.errorMessage = ''
      try {
        const result = await injectionScheduleApi.writeActual(factoryId, input)
        if (
          mutationId !== this.mutationRequestId
          || this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
        ) return undefined
        this.formalWorkspace = applyActualResult(workspace, result)
        this.lastActualResult = result
        this.actualProjections = result.projections
        this.shiftActuals = [
          result.actual,
          ...this.shiftActuals.filter((entry) => entry.id !== result.actual.id),
        ]
        this.validation = null
        this.versionDiff = null
        this.recommendation = null
        ++this.recommendationRequestId
        return result
      } catch (error) {
        if (
          mutationId === this.mutationRequestId
          && this.factoryId === factoryId
          && this.formalWorkspace === workspace
        ) {
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (mutationId === this.mutationRequestId) this.mutationPending = false
      }
    },

    async correctActual(
      actualId: string,
      input: InjectionShiftActualCorrectionInput,
    ) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const actual = this.shiftActuals.find((entry) => entry.id === actualId)
      const version = workspace.activeVersion
      if (!actual) throw new Error(`实绩记录 ${actualId} 不存在`)
      if (!version || version.id !== actual.versionId) {
        throw new Error('实绩更正版本不是当前打开版本')
      }
      if (actual.revision !== input.expectedRevision) {
        throw new Error(
          `本地实绩 revision ${actual.revision} 与更正 revision ${input.expectedRevision} 不一致`,
        )
      }
      const order = workspace.orders.find((entry) => entry.id === actual.orderId)
      if (!order || order.revision !== input.expectedOrderRevision) {
        throw new Error('实绩更正引用的订单 revision 已失效')
      }
      if (version.revision !== input.expectedVersionRevision) {
        throw new Error('实绩更正引用的计划 revision 已失效')
      }
      if (this.mutationPending) throw new Error('已有排程写入正在执行，请稍后再试')

      const mutationId = ++this.mutationRequestId
      this.mutationPending = true
      this.revisionConflict = null
      this.errorMessage = ''
      try {
        const result = await injectionScheduleApi.correctActual(
          factoryId,
          actualId,
          input,
        )
        if (
          mutationId !== this.mutationRequestId
          || this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
        ) return undefined
        this.formalWorkspace = applyActualResult(workspace, result)
        this.lastActualResult = result
        this.actualProjections = result.projections
        this.shiftActuals = [
          result.actual,
          ...this.shiftActuals.filter((entry) => entry.id !== result.actual.id),
        ]
        this.validation = null
        this.versionDiff = null
        this.recommendation = null
        ++this.recommendationRequestId
        return result
      } catch (error) {
        if (
          mutationId === this.mutationRequestId
          && this.factoryId === factoryId
          && this.formalWorkspace === workspace
        ) {
          this.setMutationError(error)
        }
        throw error
      } finally {
        if (mutationId === this.mutationRequestId) this.mutationPending = false
      }
    },

    async validateActiveVersion(expectedRevision: number) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const version = workspace.activeVersion
      if (!version) throw new Error('当前没有可校验的计划版本')
      if (version.revision !== expectedRevision) {
        throw new Error(
          `本地草稿 revision ${version.revision} 与校验 revision ${expectedRevision} 不一致`,
        )
      }
      this.versionLoading = true
      try {
        const validation = await injectionScheduleApi.validateVersion(
          factoryId,
          version.id,
          expectedRevision,
        )
        assertRecordFactory(validation, factoryId)
        if (
          validation.versionId !== version.id
          || validation.versionRevision !== expectedRevision
        ) {
          throw new Error('校验结果与当前计划版本不一致，请重新读取工作区')
        }
        if (
          this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
          || workspace.activeVersion?.id !== version.id
        ) return undefined
        this.validation = validation
        workspace.conflicts = validation.items
        const validatedVersion = {
          ...version,
          dataHash: validation.dataHash,
          validationHash: validation.resultHash,
        }
        workspace.activeVersion = validatedVersion
        workspace.versions = replaceVersion(workspace.versions, validatedVersion)
        return validation
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.versionLoading = false
      }
    },

    async loadVersionDiff(againstVersionId?: string | null) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const version = workspace.activeVersion
      if (!version) throw new Error('当前没有可比较的计划版本')
      this.versionLoading = true
      try {
        const diff = await injectionScheduleApi.getVersionDiff(
          factoryId,
          version.id,
          againstVersionId,
        )
        if (
          this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
          || workspace.activeVersion?.id !== version.id
        ) return undefined
        this.versionDiff = diff
        return diff
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.versionLoading = false
      }
    },

    async publishActiveVersion(input: InjectionVersionPublishInput) {
      const { factoryId, workspace } = this.requireFormalWorkspace()
      const version = workspace.activeVersion
      if (!version || version.status !== 'draft') {
        throw new Error('当前没有可发布的草稿版本')
      }
      if (
        this.validation?.status !== 'passed'
        || this.validation.blockingCount > 0
        || this.validation.versionRevision !== version.revision
        || this.validation.versionId !== version.id
        || this.validation.dataHash !== version.dataHash
      ) {
        throw new Error('当前草稿尚未通过与本 revision 一致的发布校验')
      }
      if (input.expectedRevision !== version.revision) {
        throw new Error(
          `本地草稿 revision ${version.revision} 与发布 revision ${input.expectedRevision} 不一致`,
        )
      }
      if (
        input.validationRunId != null
        && input.validationRunId !== this.validation.id
      ) {
        throw new Error('发布请求引用的校验记录不是当前草稿的最新校验')
      }
      this.versionLoading = true
      try {
        const published = await injectionScheduleApi.publishVersion(
          factoryId,
          version.id,
          input,
        )
        assertRecordFactory(published, factoryId)
        if (
          this.factoryId !== factoryId
          || this.formalWorkspace !== workspace
          || workspace.activeVersion?.id !== version.id
        ) return undefined
        const refreshed = await this.loadWorkspace(factoryId, {
          versionId: published.id,
        })
        if (!refreshed || refreshed.mode !== 'formal') {
          throw new Error('计划已发布，但正式工作区刷新失败，请重新读取')
        }
        return published
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.versionLoading = false
      }
    },

    async cloneHistoricalAsDraft(
      versionId: string,
      input: InjectionVersionCloneInput,
    ) {
      const { factoryId } = this.requireFormalWorkspace()
      this.versionLoading = true
      try {
        const draft = await injectionScheduleApi.cloneVersionAsDraft(
          factoryId,
          versionId,
          input,
        )
        assertRecordFactory(draft, factoryId)
        if (this.factoryId !== factoryId || this.mode !== 'formal') return undefined
        await this.loadWorkspace(factoryId, { versionId: draft.id })
        return draft
      } catch (error) {
        if (this.factoryId === factoryId) this.setMutationError(error)
        throw error
      } finally {
        if (this.factoryId === factoryId) this.versionLoading = false
      }
    },
  },
})

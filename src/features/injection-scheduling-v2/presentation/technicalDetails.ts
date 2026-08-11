import type { AuditEvent, AutoScheduleRunRecord, PlanSliceKey, RevisionConflict, ScheduleTaskRecord, SchedulingPlanRecord } from '../types'

export interface TechnicalDetailItem {
  label: string
  rawValue: string
  copyable?: boolean
}

function raw(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function item(label: string, value: unknown, copyable = false): TechnicalDetailItem {
  return { label, rawValue: raw(value), copyable }
}

export function planTechnicalDetails(input: {
  plan: SchedulingPlanRecord | null
  activeSlice?: PlanSliceKey
  eventSequence?: number
}) {
  const plan = input.plan
  return [
    item('计划 ID', plan?.id, true),
    item('当前切片原始值', input.activeSlice),
    item('计划原始状态', plan?.status),
    item('计划 revision', plan?.revision),
    item('规则 revision', plan?.ruleRevision),
    item('事件序列', input.eventSequence),
    item('Profile ID', plan?.exportProfileId, true),
    item('Profile revision', plan?.exportProfileRevision),
    item('导出绑定来源', plan?.exportBindingSource),
    item('计算版本', plan?.calculationVersion),
  ]
}

export function autoScheduleTechnicalDetails(run: AutoScheduleRunRecord) {
  return [
    item('运行 ID', run.id, true),
    item('运行原始状态', run.status),
    item('请求求解器', run.requestedSolver),
    item('实际求解器', run.solverType),
    item('求解器原始状态', run.solverStatus),
    item('求解器版本', run.solverVersion),
    item('计划 revision', run.expectedPlanRevision),
    item('规则 revision', run.ruleRevision),
    item('目标值', run.summary.objectiveValue),
    item('目标下界', run.summary.bestObjectiveBound),
    item('目标权重', run.objectiveWeights),
    item('冻结任务数', run.summary.frozenTaskCount),
    item('深浅色切换', run.summary.darkToLightChanges),
    item('机台接续点', run.summary.continuationAnchors),
    item('回退原因', run.fallbackReason),
    item('方案组 ID', run.scenarioGroupId, true),
    item('求解耗时（毫秒）', run.summary.solverElapsedMs),
  ]
}

export function taskTechnicalDetails(task: ScheduleTaskRecord) {
  const calculation = task.autoExplanation?.calculation
  const calculated = calculation && typeof calculation === 'object' && !Array.isArray(calculation)
    ? calculation as Record<string, unknown>
    : {}
  return [
    item('任务 ID', task.id, true),
    item('计划 ID', task.planId, true),
    item('任务原始状态', task.status),
    item('任务 revision', task.revision),
    item('Profile ID', task.profileId, true),
    item('Profile revision', task.profileRevision),
    item('来源工作表', task.sourceSheetName),
    item('来源行', task.sourceRow),
    item('来源原始类型', task.origin),
    item('continuation anchor', calculated.continuation_anchor),
    item('setup minutes', task.setupMinutes),
    item('production minutes', task.productionMinutes),
    item('downtime minutes', task.plannedDowntimeMinutes),
    item('transition raw value', task.changeoverType),
    item('calculation version', calculated.calculation_version),
    item('speed source', calculated.speed_source),
    item('自动排期运行 ID', task.autoScheduleRunId, true),
    item('自动排期原始说明', task.autoExplanation),
  ]
}

export function auditEventTechnicalDetails(event: AuditEvent) {
  return [
    item('事件 ID', event.id, true),
    item('event type', event.eventType),
    item('event sequence', event.sequence),
    item('request ID', event.requestId, true),
    item('entity type', event.entityType),
    item('entity ID', event.entityId, true),
    item('entity revision', event.entityRevision),
    item('原始详情', event.detail),
  ]
}

export function conflictTechnicalDetails(conflict: RevisionConflict) {
  return [
    item('原始标题', conflict.title),
    item('原始消息', conflict.message),
    ...Object.entries(conflict.localValues).map(([key, value]) => item(`本地字段 · ${key}`, value)),
    ...Object.entries(conflict.serverValues).map(([key, value]) => item(`服务器字段 · ${key}`, value)),
  ]
}

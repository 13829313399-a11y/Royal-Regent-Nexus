import { http } from '@/lib/http'
import { createRandomUuidHex } from '@/lib/randomUuid'
import {
  confirmImportBatch,
  mapImportBatch,
  uploadImportPreview,
} from '../api/injectionSchedulingV2Api'
import type { ImportBatchRecord, ImportDocumentKindChoice } from '../types'
import type {
  SchedulePreview,
  ShiftReportInput,
  WorkbenchCellChange,
  WorkbenchJob,
  WorkbenchMachine,
  WorkbenchSnapshot,
} from './types'

type UnknownRecord = Record<string, unknown>

const textValue = (value: unknown) => value == null ? '' : String(value)
const numberValue = (value: unknown) => Number.isFinite(Number(value)) ? Number(value) : 0
const nullableNumber = (value: unknown) => value == null || value === '' ? null : numberValue(value)
const nullableBoolean = (value: unknown) => {
  if (value == null || value === '') return null
  if (typeof value === 'string') return !['0', 'false', 'no', 'n', '否'].includes(value.trim().toLocaleLowerCase())
  return Boolean(value)
}
const stringList = (value: unknown) => Array.isArray(value) ? value.map(textValue) : []
const objectValue = (value: unknown): UnknownRecord => value && typeof value === 'object' ? value as UnknownRecord : {}
const requestId = (prefix: string) => `${prefix}-${createRandomUuidHex()}`.slice(0, 128)

function mapMachine(source: UnknownRecord): WorkbenchMachine {
  return {
    id: textValue(source.id), factoryId: textValue(source.factory_id), code: textValue(source.code),
    position: textValue(source.position), area: textValue(source.area), aClass: nullableNumber(source.a_class),
    tonnage: nullableNumber(source.tonnage), armCapabilities: stringList(source.arm_capabilities),
    fixtureCapabilities: stringList(source.fixture_capabilities), processRestrictions: stringList(source.process_restrictions),
    status: textValue(source.status), availableForAutoSchedule: Boolean(source.available_for_auto_schedule),
    remark: textValue(source.remark), parsedConstraintSummary: textValue(source.parsed_constraint_summary),
    revision: numberValue(source.revision),
  }
}

function mapJob(source: UnknownRecord): WorkbenchJob {
  return {
    id: textValue(source.id), factoryId: textValue(source.factory_id), planId: source.plan_id ? textValue(source.plan_id) : null,
    taskId: source.task_id ? textValue(source.task_id) : null, orderId: textValue(source.order_id),
    machineId: source.machine_id ? textValue(source.machine_id) : null, machineCode: textValue(source.machine_code),
    sequenceNo: nullableNumber(source.sequence_no), status: textValue(source.status) as WorkbenchJob['status'],
    orderNo: textValue(source.order_no), itemNo: textValue(source.item_no), productName: textValue(source.product_name),
    warehouseText: textValue(source.warehouse_text), setQuantity: nullableNumber(source.set_quantity),
    orderQuantity: numberValue(source.order_quantity), openingCompletedQuantity: numberValue(source.opening_completed_quantity),
    reportedQuantity: numberValue(source.reported_quantity), completedQuantity: numberValue(source.completed_quantity),
    outstandingQuantity: numberValue(source.outstanding_quantity), completionRate: numberValue(source.completion_rate),
    moldId: source.mold_id ? textValue(source.mold_id) : null, moldNo: textValue(source.mold_no), moldName: textValue(source.mold_name),
    requiredMachineA: nullableNumber(source.required_machine_a), materialName: textValue(source.material_name),
    sprueRatio: nullableNumber(source.sprue_ratio), colorName: textValue(source.color_name),
    colorPowderCode: textValue(source.color_powder_code), netWeightG: nullableNumber(source.net_weight_g),
    grossWeightG: nullableNumber(source.gross_weight_g), materialWeightKg: nullableNumber(source.material_weight_kg),
    unitPrice: nullableNumber(source.unit_price), sprayRequired: nullableBoolean(source.spray_required),
    armRequirement: textValue(source.arm_requirement), fixtureRequirement: textValue(source.fixture_requirement),
    orderDate: textValue(source.order_date), deliveryStartDate: textValue(source.delivery_start_date),
    deliveryDueDate: textValue(source.delivery_due_date), priority: textValue(source.priority),
    plannedStart: textValue(source.planned_start), plannedFinish: textValue(source.planned_finish),
    estimatedFinish: textValue(source.estimated_finish), deliverySlackDays: nullableNumber(source.delivery_slack_days),
    shiftTargetQuantity: numberValue(source.shift_target_quantity), todayDayQuantity: numberValue(source.today_day_quantity),
    todayNightQuantity: numberValue(source.today_night_quantity), downtimeMinutes: numberValue(source.downtime_minutes),
    locked: Boolean(source.locked), manualOverrideReason: textValue(source.manual_override_reason),
    orderRemark: textValue(source.order_remark), machineRemark: textValue(source.machine_remark),
    parsedConstraintSummary: textValue(source.parsed_constraint_summary), suggestionReason: textValue(source.suggestion_reason),
    materialReadinessStatus: textValue(source.material_readiness_status), moldEnrichmentStatus: textValue(source.mold_enrichment_status),
    sourceBatchId: source.source_batch_id ? textValue(source.source_batch_id) : null,
    sourceSheetName: textValue(source.source_sheet_name), sourceRowNumber: nullableNumber(source.source_row_number),
    sourceLineKey: textValue(source.source_line_key), taskRevision: nullableNumber(source.task_revision),
    orderRevision: numberValue(source.order_revision), planRevision: nullableNumber(source.plan_revision),
    updatedByName: textValue(source.updated_by_name), updatedAt: textValue(source.updated_at), lineage: objectValue(source.lineage),
  }
}

function mapSnapshot(source: UnknownRecord): WorkbenchSnapshot {
  const summary = objectValue(source.summary)
  return {
    factoryId: textValue(source.factory_id), businessDate: textValue(source.business_date),
    planId: source.plan_id ? textValue(source.plan_id) : null, planRevision: nullableNumber(source.plan_revision),
    ruleRevision: nullableNumber(source.rule_revision), planMode: textValue(source.plan_mode) as WorkbenchSnapshot['planMode'],
    pollingRevision: numberValue(source.polling_revision),
    machines: (Array.isArray(source.machines) ? source.machines : []).map((item) => mapMachine(objectValue(item))),
    jobs: (Array.isArray(source.jobs) ? source.jobs : []).map((item) => mapJob(objectValue(item))),
    summary: {
      unplannedCount: numberValue(summary.unplanned_count), overdueCount: numberValue(summary.overdue_count),
      conflictCount: numberValue(summary.conflict_count), runningCount: numberValue(summary.running_count),
      todayDayQuantity: numberValue(summary.today_day_quantity), todayNightQuantity: numberValue(summary.today_night_quantity),
    },
  }
}

export async function fetchWorkbench(factoryId: string) {
  const { data } = await http.get('/injection-scheduling/workbench', { params: { factory_id: factoryId } })
  return mapSnapshot(data as UnknownRecord)
}

const bulkFieldMap: Record<WorkbenchCellChange['field'], string> = {
  status: 'status', shiftTargetQuantity: 'shift_target_quantity', plannedStart: 'planned_start',
  plannedFinish: 'planned_finish', locked: 'locked', manualOverrideReason: 'manual_override_reason',
  warehouseText: 'warehouse_text', orderRemark: 'order_remark',
}

export async function saveWorkbenchChanges(factoryId: string, expectedPlanRevision: number | null, changes: WorkbenchCellChange[]) {
  const { data } = await http.post('/injection-scheduling/workbench/jobs/bulk-update', {
    factory_id: factoryId,
    expected_plan_revision: expectedPlanRevision,
    request_id: requestId('workbench-paste'),
    changes: changes.map((change) => ({
      job_id: change.jobId,
      expected_task_revision: change.expectedTaskRevision,
      expected_order_revision: change.expectedOrderRevision,
      field: bulkFieldMap[change.field],
      value: change.value,
    })),
  })
  return mapSnapshot(data as UnknownRecord)
}

export async function reportWorkbenchShift(factoryId: string, businessDate: string, job: WorkbenchJob, input: ShiftReportInput) {
  if (!job.taskId || !job.taskRevision) throw new Error('待排任务不能回报班次')
  await http.post('/injection-scheduling/tasks/shift-reports/bulk', {
    factory_id: factoryId,
    reports: [{
      task_id: job.taskId, expected_revision: job.taskRevision, request_id: requestId(`shift-${job.taskId}`),
      business_date: businessDate, shift_code: input.shiftCode, quantity_mode: 'INCREMENTAL',
      reported_quantity: input.quantity, shift_target_quantity: input.targetQuantity,
      downtime_minutes: input.downtimeMinutes, exception_code: input.exceptionCode,
      exception_detail: input.exceptionDetail, reported_status: input.reportedStatus,
    }],
  })
}

export async function evaluateWorkbenchMove(factoryId: string, job: WorkbenchJob, targetMachineId: string) {
  const { data } = await http.post('/injection-scheduling/matches/evaluate', {
    factory_id: factoryId, order_id: job.orderId, machine_ids: [targetMachineId], allow_scheduled: true,
  })
  return objectValue(data)
}

export async function moveWorkbenchJob(snapshot: WorkbenchSnapshot, job: WorkbenchJob, targetMachineId: string, sequenceNo: number, overrideReason = '') {
  if (!snapshot.planId || !snapshot.planRevision || !snapshot.ruleRevision || !job.taskId || !job.taskRevision) {
    throw new Error('当前任务没有可移动的规划版本')
  }
  await http.post(`/injection-scheduling/plans/${snapshot.planId}/tasks/bulk-move`, {
    factory_id: snapshot.factoryId, expected_plan_revision: snapshot.planRevision,
    expected_rule_revision: snapshot.ruleRevision, request_id: requestId('workbench-move'),
    moves: [{ task_id: job.taskId, expected_revision: job.taskRevision, machine_id: targetMachineId,
      sequence_no: sequenceNo, planned_start: job.plannedStart, planned_finish: job.plannedFinish,
      override_reason: overrideReason }],
  })
}

export async function withdrawWorkbenchJob(snapshot: WorkbenchSnapshot, job: WorkbenchJob, reason: string) {
  if (!snapshot.planRevision || !job.taskId || !job.taskRevision) throw new Error('当前任务无法撤回待排池')
  await http.post(`/injection-scheduling/tasks/${job.taskId}/withdraw-to-backlog`, {
    factory_id: snapshot.factoryId, expected_plan_revision: snapshot.planRevision,
    expected_task_revision: job.taskRevision, expected_planning_revision: null,
    request_id: requestId('workbench-withdraw'), reason,
  })
}

export async function createHeuristicPreview(snapshot: WorkbenchSnapshot) {
  if (!snapshot.planId || !snapshot.planRevision || !snapshot.ruleRevision) throw new Error('请先建立可编辑的规划')
  const day = snapshot.businessDate || new Date().toISOString().slice(0, 10)
  const start = `${day}T08:00:00`
  const endDate = new Date(`${day}T00:00:00`)
  endDate.setDate(endDate.getDate() + 7)
  const end = `${endDate.toISOString().slice(0, 10)}T20:00:00`
  const { data } = await http.post('/injection-scheduling/auto-schedule/runs', {
    factory_id: snapshot.factoryId, plan_id: snapshot.planId, expected_plan_revision: snapshot.planRevision,
    rule_revision: snapshot.ruleRevision, mode: 'PREVIEW', horizon_start: start, horizon_end: end,
    order_ids: [], respect_locked_tasks: true, solver: 'HEURISTIC', time_limit_seconds: 10,
    objective_weights: { tardiness_weight: 100, transition_weight: 2, class_gap_weight: 1.5,
      load_balance_weight: 25, existing_task_move_cost: 40 }, scenario_group_id: '',
    scenario_name: '简化建议', alternative_no: 1, replay_of_run_id: null,
  }, { headers: { 'X-Request-ID': requestId('heuristic-preview') } })
  const raw = objectValue(data)
  const summary = objectValue(raw.summary)
  return {
    id: textValue(raw.id), solverType: textValue(raw.solver_type),
    assignmentCount: numberValue(summary.assignment_count ?? raw.assignment_count),
    unscheduledCount: numberValue(summary.unscheduled_count ?? raw.unscheduled_count),
    warningCount: numberValue(summary.warning_count ?? raw.warning_count),
    objectiveScore: numberValue(raw.objective_score), raw,
  } satisfies SchedulePreview
}

export async function applyHeuristicPreview(snapshot: WorkbenchSnapshot, preview: SchedulePreview) {
  if (!snapshot.planRevision || !snapshot.ruleRevision) throw new Error('规划版本已失效')
  await http.post(`/injection-scheduling/auto-schedule/runs/${preview.id}/apply`, {
    factory_id: snapshot.factoryId, expected_plan_revision: snapshot.planRevision,
    expected_rule_revision: snapshot.ruleRevision, request_id: requestId('heuristic-apply'),
    review_override_reason: '',
  })
}

export async function previewWorkbenchImport(factoryId: string, file: File, kind: ImportDocumentKindChoice, businessDate: string) {
  return uploadImportPreview(factoryId, file, kind, 'AUTO', businessDate)
}

export async function applyWorkbenchImportMapping(
  factoryId: string,
  batch: ImportBatchRecord,
  mappings: Record<string, string>,
) {
  const { data } = await http.post(`/injection-scheduling/workbench/imports/${batch.id}/apply-mapping`, {
    factory_id: factoryId,
    expected_revision: batch.revision,
    request_id: requestId('workbench-import-map'),
    mappings,
  })
  return mapImportBatch(data as UnknownRecord)
}

export async function confirmWorkbenchImport(factoryId: string, batch: ImportBatchRecord, businessDate: string) {
  const selectedRows = batch.documentKind === 'DEMAND_ORDER' ? batch.demandRows.map((row) => row.rowId) : []
  return confirmImportBatch(factoryId, batch, businessDate, selectedRows)
}

import { http } from '@/lib/http'
import type {
  AutoScheduleAssignmentRecord,
  AutoScheduleGenerationOptions,
  AutoScheduleRunRecord,
  AuditEvent,
  MachineRecord,
  MoldRecord,
  OrderRecord,
  Phase5AnalyticsRecord,
  ScheduleTaskRecord,
  SchedulingPlanRecord,
  ShiftReportDraft,
} from '../types'

type UnknownRecord = Record<string, unknown>

const text = (value: unknown) => typeof value === 'string' ? value : ''
const numberOrNull = (value: unknown) => typeof value === 'number' ? value : null
const numberValue = (value: unknown) => typeof value === 'number' ? value : 0
const strings = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []

function mapMachine(source: UnknownRecord): MachineRecord {
  return {
    id: text(source.id),
    code: text(source.machine_code),
    position: text(source.position),
    area: text(source.area),
    aClass: numberOrNull(source.machine_a_class),
    aClassRaw: text(source.machine_class_raw) || text(source.machine_class),
    injectionCapacityG: numberOrNull(source.injection_capacity_g),
    armCapabilities: strings(source.robot_capabilities),
    fixtureCapabilities: strings(source.fixture_capabilities),
    processRestrictions: strings(source.process_restrictions),
    machineType: text(source.machine_type),
    specialMachineType: text(source.special_machine_type),
    status: (text(source.status) || 'available') as MachineRecord['status'],
    normalizationStatus: (text(source.normalization_status) || 'REVIEW_REQUIRED') as MachineRecord['normalizationStatus'],
  }
}

function mapMold(source: UnknownRecord): MoldRecord {
  return {
    id: text(source.id),
    moldNo: text(source.mold_no),
    name: text(source.name),
    aClass: numberOrNull(source.mold_a_class),
    aClassRaw: text(source.mold_class_raw) || text(source.recommended_machine_class),
    netWeightG: numberOrNull(source.whole_shot_net_weight_g),
    grossWeightG: numberOrNull(source.whole_shot_gross_weight_g),
    requiredArmType: text(source.required_arm_type),
    requiredFixtureType: text(source.required_fixture_type),
    materialCode: text(source.material_code),
    materialName: text(source.material_name),
    colorProfile: text(source.color_profile),
    processRequirements: strings(source.process_requirements),
    specialMachineType: text(source.special_machine_type),
    normalizationStatus: (text(source.normalization_status) || 'REVIEW_REQUIRED') as MoldRecord['normalizationStatus'],
  }
}

export function mapOrder(source: UnknownRecord): OrderRecord {
  return {
    id: text(source.id), orderNo: text(source.order_no), itemNo: text(source.item_no), productName: text(source.product_name),
    moldId: text(source.mold_id) || null, orderQuantity: numberValue(source.order_quantity),
    sourceCompletedQuantity: numberValue(source.source_completed_quantity),
    completedQuantity: numberValue(source.completed_quantity), outstandingQuantity: numberValue(source.outstanding_quantity),
    completionRate: numberValue(source.completion_rate), deliveryStartDate: text(source.delivery_start_date),
    deliveryDueDate: text(source.delivery_due_date), deliverySlackDays: numberOrNull(source.delivery_slack_days),
    priorityCode: (text(source.priority_code) || 'NORMAL') as OrderRecord['priorityCode'],
    materialReadinessStatus: (text(source.material_readiness_status) || 'unknown') as OrderRecord['materialReadinessStatus'],
    warehouseText: text(source.warehouse_text), remark: text(source.remark),
    status: (text(source.status) || 'BACKLOG') as OrderRecord['status'],
    lineage: source.lineage && typeof source.lineage === 'object' ? source.lineage as UnknownRecord : {},
    revision: numberValue(source.revision),
  }
}

export function mapTask(source: UnknownRecord): ScheduleTaskRecord {
  return {
    id: text(source.id), planId: text(source.plan_id), machineId: text(source.machine_id), orderId: text(source.order_id), moldId: text(source.mold_id) || null,
    sequence: numberValue(source.sequence_no), status: (text(source.execution_status) || 'QUEUED') as ScheduleTaskRecord['status'],
    plannedStart: text(source.planned_start), plannedFinish: text(source.planned_finish),
    targetQuantity: numberValue(source.shift_target_quantity), reportedQuantity: numberValue(source.reported_quantity),
    sourceSheetName: text(source.source_sheet_name), sourceRow: numberOrNull(source.source_row), locked: Boolean(source.locked),
    manualOverrideReason: text(source.manual_override_reason), activeExecution: Boolean(source.active_execution),
    estimatedStart: text(source.estimated_start), estimatedFinish: text(source.estimated_finish),
    estimatedRemainingShifts: numberValue(source.estimated_remaining_shifts), deliverySlackDays: numberOrNull(source.delivery_slack_days),
    revision: numberValue(source.revision), setupMinutes: numberValue(source.setup_minutes),
    productionMinutes: numberValue(source.production_minutes), plannedDowntimeMinutes: numberValue(source.planned_downtime_minutes),
    changeoverType: text(source.changeover_type), autoScheduleRunId: text(source.auto_schedule_run_id) || null,
    autoScore: numberOrNull(source.auto_score), autoExplanation: source.auto_explanation && typeof source.auto_explanation === 'object' ? source.auto_explanation as UnknownRecord : {},
    manualAdjusted: Boolean(source.manual_adjusted),
    allocatedQuantity: numberValue(source.allocated_quantity), takeoverSourceCompletedQuantity: numberValue(source.takeover_source_completed_quantity),
    origin: text(source.origin), stableOrderKey: text(source.stable_order_key), stableRowKey: text(source.stable_row_key),
    sourceTaskId: text(source.source_task_id) || null, inheritedReportCounter: numberValue(source.inherited_report_counter),
    completedAtClone: numberValue(source.completed_at_clone), reportEventWatermark: numberValue(source.report_event_watermark),
    profileId: text(source.profile_id) || null, profileRevision: numberOrNull(source.profile_revision),
  }
}

function mapEvent(source: UnknownRecord): AuditEvent {
  return {
    id: text(source.id), sequence: numberValue(source.sequence), eventType: text(source.event_type), entityType: text(source.entity_type),
    entityId: text(source.entity_id), entityRevision: numberValue(source.entity_revision), requestId: text(source.request_id),
    actorName: text(source.actor_name), createdAt: text(source.created_at),
    detail: source.detail && typeof source.detail === 'object' ? source.detail as UnknownRecord : {},
  }
}

export function mapPlan(source: UnknownRecord | null): { plan: SchedulingPlanRecord | null; orders: OrderRecord[]; tasks: ScheduleTaskRecord[] } {
  if (!source) return { plan: null, orders: [], tasks: [] }
  return {
    plan: {
      id: text(source.id), status: text(source.status), revision: numberValue(source.revision),
      ruleRevision: numberValue(source.rule_revision), businessDate: text(source.business_date),
      basedOnPlanId: text(source.based_on_plan_id), basedOnEventSequence: numberValue(source.based_on_event_sequence),
      basedOnReportWatermark: numberValue(source.based_on_report_watermark),
    },
    orders: (Array.isArray(source.orders) ? source.orders as UnknownRecord[] : []).map(mapOrder),
    tasks: (Array.isArray(source.tasks) ? source.tasks as UnknownRecord[] : []).map(mapTask),
  }
}

function mapAssignment(source: UnknownRecord): AutoScheduleAssignmentRecord {
  return {
    id: text(source.id), orderId: text(source.order_id), existingTaskId: text(source.existing_task_id) || null,
    moldId: text(source.mold_id) || null, moldCopyNo: numberValue(source.mold_copy_no), machineId: text(source.machine_id) || null,
    sequence: numberOrNull(source.sequence_no), plannedStart: text(source.planned_start), plannedFinish: text(source.planned_finish),
    setupMinutes: numberValue(source.setup_minutes), productionMinutes: numberValue(source.production_minutes),
    plannedDowntimeMinutes: numberValue(source.planned_downtime_minutes), changeoverType: text(source.changeover_type),
    decision: (text(source.decision) || 'UNASSIGNED') as AutoScheduleAssignmentRecord['decision'], score: numberOrNull(source.score),
    explanation: source.explanation && typeof source.explanation === 'object' ? source.explanation as UnknownRecord : {},
    unassignedReasonCode: text(source.unassigned_reason_code),
  }
}

export function mapAutoScheduleRun(source: UnknownRecord): AutoScheduleRunRecord {
  const summary = source.summary && typeof source.summary === 'object' ? source.summary as UnknownRecord : {}
  const objective = source.objective_config && typeof source.objective_config === 'object' ? source.objective_config as UnknownRecord : {}
  const metric = (value: unknown) => {
    const item = value && typeof value === 'object' ? value as UnknownRecord : {}
    return { before: numberValue(item.before), after: numberValue(item.after), change: numberValue(item.change) }
  }
  const loads = Array.isArray(summary.machine_loads) ? summary.machine_loads as UnknownRecord[] : []
  const anchors = Array.isArray(summary.continuation_anchors) ? summary.continuation_anchors as UnknownRecord[] : []
  return {
    id: text(source.id), factoryId: text(source.factory_id), planId: text(source.plan_id), expectedPlanRevision: numberValue(source.expected_plan_revision),
    ruleRevision: numberValue(source.rule_revision), solverType: (text(source.solver_type) || 'HEURISTIC') as AutoScheduleRunRecord['solverType'],
    requestedSolver: (text(source.requested_solver) || 'HEURISTIC') as AutoScheduleRunRecord['requestedSolver'], solverVersion: text(source.solver_version),
    solverStatus: (text(source.solver_status) || text(summary.solver_status) || 'NOT_RUN') as AutoScheduleRunRecord['solverStatus'],
    fallbackUsed: Boolean(source.fallback_used), fallbackReason: text(source.fallback_reason),
    scenarioGroupId: text(source.scenario_group_id), scenarioName: text(source.scenario_name) || '方案 A', alternativeNo: numberValue(source.alternative_no) || 1,
    replayOfRunId: text(source.replay_of_run_id) || null, status: (text(source.status) || 'FAILED') as AutoScheduleRunRecord['status'],
    horizonStart: text(source.horizon_start), horizonEnd: text(source.horizon_end), errorDetail: text(source.error_detail),
    createdByName: text(source.created_by_name), createdAt: text(source.created_at), appliedByName: text(source.applied_by_name), appliedAt: text(source.applied_at),
    objectiveWeights: {
      tardinessWeight: numberValue(objective.tardiness_weight), transitionWeight: numberValue(objective.transition_weight),
      classGapWeight: numberValue(objective.class_gap_weight), loadBalanceWeight: numberValue(objective.load_balance_weight),
      existingTaskMoveCost: numberValue(objective.existing_task_move_cost),
    },
    summary: {
      inputOrderCount: numberValue(summary.input_order_count), scheduledCount: numberValue(summary.scheduled_count), reviewCount: numberValue(summary.review_count),
      unassignedCount: numberValue(summary.unassigned_count), movedTaskCount: numberValue(summary.moved_task_count), localImprovementMoveCount: numberValue(summary.local_improvement_move_count), frozenTaskCount: numberValue(summary.frozen_task_count),
      overdue: metric(summary.overdue), moldChanges: metric(summary.mold_changes), darkToLightChanges: metric(summary.dark_to_light_changes),
      machineLoads: loads.map((item) => ({ machineId: text(item.machine_id), machineCode: text(item.machine_code), scheduledMinutes: numberValue(item.scheduled_minutes), loadRatio: numberValue(item.load_ratio) })),
      solverElapsedMs: numberValue(summary.solver_elapsed_ms), solverStatus: (text(summary.solver_status) || text(source.solver_status) || 'NOT_RUN') as AutoScheduleRunRecord['solverStatus'],
      objectiveValue: numberOrNull(summary.objective_value), bestObjectiveBound: numberOrNull(summary.best_objective_bound),
      fallbackUsed: Boolean(summary.fallback_used ?? source.fallback_used), fallbackReason: text(summary.fallback_reason) || text(source.fallback_reason),
      continuationAnchors: anchors.map((item) => ({
        machineId: text(item.machine_id), startsAt: text(item.starts_at),
        sources: Array.isArray(item.sources) ? item.sources.filter((source): source is UnknownRecord => Boolean(source) && typeof source === 'object') : [],
      })),
    },
    assignments: (Array.isArray(source.assignments) ? source.assignments as UnknownRecord[] : []).map(mapAssignment),
  }
}

function mapPhase5Metric(source: unknown): Phase5AnalyticsRecord['planAccuracy'] {
  const item = source && typeof source === 'object' ? source as UnknownRecord : {}
  return {
    value: numberValue(item.value),
    numerator: numberValue(item.numerator),
    denominator: numberValue(item.denominator),
    unit: text(item.unit),
    sampleCount: numberValue(item.sample_count),
    formula: text(item.formula),
  }
}

export function mapPhase5Analytics(source: UnknownRecord): Phase5AnalyticsRecord {
  const integrations = Array.isArray(source.integration_statuses) ? source.integration_statuses as UnknownRecord[] : []
  const speedModels = Array.isArray(source.speed_models) ? source.speed_models as UnknownRecord[] : []
  return {
    factoryId: text(source.factory_id),
    dateFrom: text(source.date_from),
    dateTo: text(source.date_to),
    generatedAt: text(source.generated_at),
    planAccuracy: mapPhase5Metric(source.plan_accuracy),
    moldChangeCount: mapPhase5Metric(source.mold_change_count),
    overdueRate: mapPhase5Metric(source.overdue_rate),
    machineUtilization: mapPhase5Metric(source.machine_utilization),
    integrationStatuses: integrations.map((item) => ({
      sourceType: (text(item.source_type) || 'ERP') as 'ERP' | 'DEVICE',
      sourceKey: text(item.source_key),
      cursor: text(item.cursor),
      status: (text(item.status) || 'NOT_CONFIGURED') as 'ACTIVE' | 'ERROR' | 'NOT_CONFIGURED',
      lastReceivedAt: text(item.last_received_at),
      lastSuccessAt: text(item.last_success_at),
      lastError: text(item.last_error),
      eventCount: numberValue(item.event_count),
      revision: numberValue(item.revision),
    })),
    speedModels: speedModels.map((item) => ({
      id: text(item.id),
      factoryId: text(item.factory_id),
      moldId: text(item.mold_id),
      moldNo: text(item.mold_no),
      sampleCount: numberValue(item.sample_count),
      calibratedCycleSeconds: numberValue(item.calibrated_cycle_seconds),
      unitsPerCycle: numberValue(item.units_per_cycle),
      calibratedUnitsPerHour: numberValue(item.calibrated_units_per_hour),
      confidence: numberValue(item.confidence),
      status: (text(item.status) || 'INSUFFICIENT_DATA') as 'ACTIVE' | 'INSUFFICIENT_DATA',
      sourceWindowStart: text(item.source_window_start),
      sourceWindowEnd: text(item.source_window_end),
      lastObservedAt: text(item.last_observed_at),
      revision: numberValue(item.revision),
      updatedAt: text(item.updated_at),
    })),
    deviceInterfaceConfigured: Boolean(source.device_interface_configured),
    notes: strings(source.notes),
  }
}

export async function fetchPhase5Analytics(factoryId: string) {
  const response = await http.get('/injection-scheduling/analytics/overview', { params: { factory_id: factoryId } })
  return mapPhase5Analytics(response.data as UnknownRecord)
}

export async function rebuildPhase5SpeedModels(factoryId: string) {
  await http.post('/injection-scheduling/calibration/speed-models/rebuild', {
    factory_id: factoryId,
    mold_ids: [],
    minimum_sample_count: 3,
  }, { headers: { 'X-Request-ID': `phase5-calibration-${crypto.randomUUID()}` } })
  return fetchPhase5Analytics(factoryId)
}

export async function fetchSchedulingWorkspace(factoryId: string) {
  const [machinesResponse, moldsResponse, planResponse, backlogResponse, eventsResponse, runsResponse] = await Promise.all([
    http.get('/injection-scheduling/machines', { params: { factory_id: factoryId } }),
    http.get('/injection-scheduling/molds', { params: { factory_id: factoryId } }),
    http.get('/injection-scheduling/plans/context', { params: { factory_id: factoryId } }),
    http.get('/injection-scheduling/backlog', { params: { factory_id: factoryId } }),
    http.get('/injection-scheduling/events', { params: { factory_id: factoryId, after_sequence: 0, limit: 100 } }),
    http.get('/injection-scheduling/auto-schedule/runs', { params: { factory_id: factoryId, limit: 30 } }),
  ])
  const planPayload = planResponse.data as { execution_published_plan?: UnknownRecord | null; planning_draft_plan?: UnknownRecord | null; polling_revision?: number }
  const publishedPlan = mapPlan(planPayload.execution_published_plan ?? null)
  const draftPlan = mapPlan(planPayload.planning_draft_plan ?? null)
  const mappedPlan = draftPlan.plan ? draftPlan : publishedPlan
  const planOrders = mappedPlan.orders
  const backlogItems = Array.isArray((backlogResponse.data as UnknownRecord).items) ? (backlogResponse.data as { items: UnknownRecord[] }).items : []
  const orderMap = new Map<string, OrderRecord>()
  for (const source of [...planOrders, ...backlogItems.map(mapOrder)]) {
    const order = source
    orderMap.set(order.id, order)
  }
  return {
    machines: ((machinesResponse.data as UnknownRecord).items as UnknownRecord[] ?? []).map(mapMachine),
    molds: ((moldsResponse.data as UnknownRecord).items as UnknownRecord[] ?? []).map(mapMold),
    orders: [...orderMap.values()],
    tasks: mappedPlan.tasks,
    backlogOrderIds: backlogItems.map((source) => text(source.id)),
    plan: mappedPlan.plan,
    executionPlan: publishedPlan.plan,
    planningPlan: draftPlan.plan,
    pollingRevision: numberValue(planPayload.polling_revision),
    events: (((eventsResponse.data as UnknownRecord).events as UnknownRecord[]) ?? []).map(mapEvent),
    autoScheduleRuns: (((runsResponse.data as UnknownRecord).items as UnknownRecord[]) ?? []).map(mapAutoScheduleRun),
  }
}

export async function createAutoSchedulePreview(
  factoryId: string,
  plan: SchedulingPlanRecord,
  horizonStart: string,
  horizonEnd: string,
  options: AutoScheduleGenerationOptions,
) {
  const requestId = newRequestId('auto-preview')
  const { data } = await http.post('/injection-scheduling/auto-schedule/runs', {
    factory_id: factoryId, plan_id: plan.id, expected_plan_revision: plan.revision,
    rule_revision: plan.ruleRevision, mode: 'PREVIEW', horizon_start: horizonStart,
    horizon_end: horizonEnd, order_ids: [], respect_locked_tasks: true,
    solver: options.solver, time_limit_seconds: 10,
    objective_weights: {
      tardiness_weight: options.objectiveWeights.tardinessWeight,
      transition_weight: options.objectiveWeights.transitionWeight,
      class_gap_weight: options.objectiveWeights.classGapWeight,
      load_balance_weight: options.objectiveWeights.loadBalanceWeight,
      existing_task_move_cost: options.objectiveWeights.existingTaskMoveCost,
    },
    scenario_group_id: options.scenarioGroupId ?? '', scenario_name: options.scenarioName,
    alternative_no: options.alternativeNo ?? 1, replay_of_run_id: options.replayOfRunId ?? null,
  }, { headers: { 'X-Request-ID': requestId } })
  return mapAutoScheduleRun(data as UnknownRecord)
}

export async function applyAutoSchedulePreview(
  factoryId: string,
  plan: SchedulingPlanRecord,
  run: AutoScheduleRunRecord,
  reviewOverrideReason: string,
) {
  const requestId = newRequestId('auto-apply')
  const { data } = await http.post(`/injection-scheduling/auto-schedule/runs/${run.id}/apply`, {
    factory_id: factoryId, expected_plan_revision: plan.revision,
    expected_rule_revision: plan.ruleRevision, request_id: requestId,
    review_override_reason: reviewOverrideReason,
  })
  const payload = data as { run: UnknownRecord; plan: UnknownRecord; audit_sequence?: number }
  return { run: mapAutoScheduleRun(payload.run), ...mapPlan(payload.plan), auditSequence: numberValue(payload.audit_sequence) }
}

export async function fetchEligibility(factoryId: string, orderId: string, machineIds: string[] = [], allowScheduled = false) {
  const { data } = await http.post('/injection-scheduling/matches/evaluate', {
    factory_id: factoryId,
    order_id: orderId,
    machine_ids: machineIds,
    allow_scheduled: allowScheduled,
  })
  return data as UnknownRecord
}

export async function patchScheduleTask(
  factoryId: string,
  plan: SchedulingPlanRecord,
  task: ScheduleTaskRecord,
  changes: UnknownRecord,
) {
  const { data } = await http.patch(`/injection-scheduling/plans/${plan.id}/tasks/${task.id}`, {
    factory_id: factoryId,
    expected_revision: task.revision,
    expected_plan_revision: plan.revision,
    ...changes,
  }, { headers: { 'X-Request-ID': newRequestId('task-edit') } })
  return mapPlan(data as UnknownRecord)
}

export async function patchScheduleOrder(
  factoryId: string,
  order: OrderRecord,
  changes: { warehouse_text?: string; remark?: string },
) {
  const { data } = await http.patch(`/injection-scheduling/orders/${order.id}`, {
    factory_id: factoryId,
    expected_revision: order.revision,
    ...changes,
  }, { headers: { 'X-Request-ID': newRequestId('order-edit') } })
  return mapOrder(data as UnknownRecord)
}

export async function saveShiftReportsBulk(
  factoryId: string,
  businessDate: string,
  reports: ShiftReportDraft[],
) {
  const requestId = newRequestId('shift-bulk')
  const { data } = await http.post('/injection-scheduling/tasks/shift-reports/bulk', {
    factory_id: factoryId,
    reports: reports.map((report) => ({
      task_id: report.taskId,
      expected_revision: report.expectedRevision,
      request_id: newRequestId(`shift-${report.taskId}`),
      business_date: businessDate,
      shift_code: new Date().getHours() < 20 && new Date().getHours() >= 8 ? 'DAY' : 'NIGHT',
      quantity_mode: 'CUMULATIVE',
      reported_quantity: report.reportedQuantity,
      shift_target_quantity: report.shiftTargetQuantity,
      downtime_minutes: report.downtimeMinutes,
      exception_code: report.exceptionCode,
      exception_detail: report.exceptionDetail,
      reported_status: report.reportedStatus,
    })),
  }, { headers: { 'X-Request-ID': requestId } })
  const payload = data as { results?: UnknownRecord[]; latest_sequence?: number }
  return {
    latestSequence: numberValue(payload.latest_sequence),
    results: (payload.results ?? []).map((item) => ({
      task: mapTask(item.task as UnknownRecord),
      order: mapOrder(item.order as UnknownRecord),
      auditSequence: numberValue(item.audit_sequence),
    })),
  }
}

export async function moveScheduleTask(
  factoryId: string,
  plan: SchedulingPlanRecord,
  task: ScheduleTaskRecord,
  target: { machineId: string; sequence: number; plannedStart: string; plannedFinish: string; overrideReason: string },
) {
  const requestId = newRequestId('manual-move')
  const { data } = await http.post(`/injection-scheduling/plans/${plan.id}/tasks/bulk-move`, {
    factory_id: factoryId,
    expected_plan_revision: plan.revision,
    expected_rule_revision: plan.ruleRevision,
    request_id: requestId,
    moves: [{
      task_id: task.id,
      expected_revision: task.revision,
      machine_id: target.machineId,
      sequence_no: target.sequence,
      planned_start: target.plannedStart,
      planned_finish: target.plannedFinish,
      override_reason: target.overrideReason,
    }],
  }, { headers: { 'X-Request-ID': requestId } })
  const payload = data as { plan: UnknownRecord; moves?: UnknownRecord[]; audit_sequence?: number }
  return {
    ...mapPlan(payload.plan),
    moves: payload.moves ?? [],
    auditSequence: numberValue(payload.audit_sequence),
  }
}

export async function fetchIncrementalEvents(factoryId: string, afterSequence: number) {
  const { data } = await http.get('/injection-scheduling/events', {
    params: { factory_id: factoryId, after_sequence: afterSequence, limit: 200 },
  })
  const payload = data as { latest_sequence?: number; retry_after_seconds?: number; events?: UnknownRecord[] }
  return {
    latestSequence: numberValue(payload.latest_sequence),
    retryAfterSeconds: numberValue(payload.retry_after_seconds) || 12,
    events: (payload.events ?? []).map(mapEvent),
  }
}

export async function fetchCurrentSchedulingPlan(factoryId: string) {
  const { data } = await http.get('/injection-scheduling/plans/context', { params: { factory_id: factoryId } })
  const payload = data as { execution_published_plan?: UnknownRecord | null; planning_draft_plan?: UnknownRecord | null; polling_revision?: number }
  const publishedPlan = mapPlan(payload.execution_published_plan ?? null)
  const draftPlan = mapPlan(payload.planning_draft_plan ?? null)
  return {
    ...(draftPlan.plan ? draftPlan : publishedPlan),
    executionPlan: publishedPlan.plan,
    planningPlan: draftPlan.plan,
    pollingRevision: numberValue(payload.polling_revision),
  }
}

function newRequestId(prefix: string) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replaceAll('-', '')
    : Math.random().toString(36).slice(2)
  return `${prefix}-${Date.now()}-${random}`.slice(0, 128)
}

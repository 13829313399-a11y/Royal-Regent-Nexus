import { http } from '@/lib/http'
import type {
  AutoScheduleAssignmentRecord,
  AutoScheduleGenerationOptions,
  AutoScheduleRunRecord,
  AuditEvent,
  ImportBatchRecord,
  ImportDocumentKindChoice,
  ImportIssueRecord,
  MachineRecord,
  ManualAppendPreviewRecord,
  MoldRecord,
  OrderRecord,
  Phase5AnalyticsRecord,
  PlanExportMode,
  PlanExportResult,
  ScheduleTaskRecord,
  SchedulingPlanRecord,
  ShiftReportDraft,
} from '../types'

type UnknownRecord = Record<string, unknown>

export interface SharedMoldCatalogOutput {
  id: string
  itemNo: string
  productName: string
  cavityCount: number | null
}

export interface SharedMoldCatalogItem {
  id: string
  canonicalMoldNo: string
  displayMoldNo: string
  standardName: string
  moldAClass: number | null
  recommendedMachineClassRaw: string
  defaultArmType: string
  defaultFixtureType: string
  status: string
  dataQuality: string
  revision: number
  outputCount: number
  outputs: SharedMoldCatalogOutput[]
  nominalDailyCapacity: number | null
  factoryCapability: { machineClass: number | null; requiredArmType: string; requiredFixtureType: string } | null
  price: { amount: number; currency: string; pricingBasis: string; taxMode: string } | null
  factoryReadiness: { status: string; availableAssetCount: number; activeCapabilityCount: number }
}

export interface SharedMoldCatalogPage {
  items: SharedMoldCatalogItem[]
  page: number
  pageSize: number
  total: number
  summary: {
    totalDefinitions: number
    factoryReady: number
    notFactoryReady: number
    pendingProposals: number
    canReadPrices: boolean
  }
}

export interface SharedMoldDetail extends SharedMoldCatalogItem {
  aliases: Array<{ id: string; rawAlias: string; sourceNamespaceId: string }>
  outputs: Array<SharedMoldCatalogOutput & {
    variantCode: string
    wholeShotNetWeightG: number | null
    wholeShotGrossWeightG: number | null
    defaultMaterial: string
    defaultColor: string
    nominalDailyCapacity: number | null
    revision: number
  }>
  assets: Array<{ id: string; assetCode: string; serialNo: string; currentLocation: string; status: string; actualCavityCount: number | null; revision: number }>
  capabilities: Array<{ id: string; machineClass: number | null; requiredArmType: string; requiredFixtureType: string; nominalDailyCapacity: number | null; priority: number; revision: number }>
  prices: Array<{ id: string; moldOutputSpecId: string; amount: number; currency: string; pricingBasis: string; taxMode: string; revision: number }>
  priceAccess: 'GRANTED' | 'RESTRICTED'
}

export interface SharedMoldProposalInput {
  canonicalMoldNo: string
  displayMoldNo: string
  standardName: string
  rawAliases: string[]
  recommendedMachineClassRaw: string
  moldAClass: number | null
  defaultArmType: string
  defaultFixtureType: string
  outputs: Array<{
    itemNo: string
    variantCode: string
    productName: string
    cavityCount: number | null
    wholeShotNetWeightG: number | null
    wholeShotGrossWeightG: number | null
    defaultMaterial: string
    defaultColor: string
    nominalDailyCapacity: number | null
    unitPriceCny: number | null
  }>
  capability: { machineClass: number | null; machineClassRaw: string; requiredArmType: string; requiredFixtureType: string } | null
  reason: string
}

const text = (value: unknown) => typeof value === 'string' ? value : ''
const numberOrNull = (value: unknown) => typeof value === 'number' ? value : null
const numberValue = (value: unknown) => typeof value === 'number' ? value : 0
const numberLikeOrNull = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return null
}
const strings = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
const objectValue = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}

function mapMachine(source: UnknownRecord): MachineRecord {
  return {
    id: text(source.id),
    factoryId: text(source.factory_id),
    code: text(source.machine_code),
    position: text(source.position),
    area: text(source.area),
    aClass: numberOrNull(source.machine_a_class),
    aClassRaw: text(source.machine_class_raw) || text(source.machine_class),
    clampingForceTons: numberOrNull(source.clamping_force_tons),
    injectionCapacityG: numberOrNull(source.injection_capacity_g),
    tieBarXmm: numberOrNull(source.tie_bar_x_mm),
    tieBarYmm: numberOrNull(source.tie_bar_y_mm),
    processTags: strings(source.process_tags),
    armCapabilities: strings(source.robot_capabilities),
    fixtureCapabilities: strings(source.fixture_capabilities),
    processRestrictions: strings(source.process_restrictions),
    equipmentDetails: objectValue(source.equipment_details),
    remarks: text(source.remarks),
    machineType: text(source.machine_type),
    specialMachineType: text(source.special_machine_type),
    status: (text(source.status) || 'available') as MachineRecord['status'],
    normalizationStatus: (text(source.normalization_status) || 'REVIEW_REQUIRED') as MachineRecord['normalizationStatus'],
    revision: numberValue(source.revision),
  }
}

export interface MachineMasterInput {
  machineCode: string
  area: string
  position: string
  machineClassRaw: string
  clampingForceTons: number | null
  injectionCapacityG: number | null
  tieBarXmm: number | null
  tieBarYmm: number | null
  machineType: string
  processTags: string[]
  robotCapabilities: string[]
  fixtureCapabilities: string[]
  processRestrictions: string[]
  specialMachineType: string
  equipmentDetails: Record<string, unknown>
  remarks: string
  status: MachineRecord['status']
}

function machineMasterPayload(factoryId: string, input: MachineMasterInput, expectedRevision: number) {
  return {
    factory_id: factoryId,
    expected_revision: expectedRevision,
    machine_code: input.machineCode,
    area: input.area,
    position: input.position,
    machine_class: input.machineClassRaw,
    machine_class_raw: input.machineClassRaw,
    process_tags: input.processTags,
    special_machine_type: input.specialMachineType,
    clamping_force_tons: input.clampingForceTons,
    injection_capacity_g: input.injectionCapacityG,
    tie_bar_x_mm: input.tieBarXmm,
    tie_bar_y_mm: input.tieBarYmm,
    platen_x_mm: null,
    platen_y_mm: null,
    min_mold_thickness_mm: null,
    max_mold_thickness_mm: null,
    opening_stroke_mm: null,
    machine_type: input.machineType,
    robot_capabilities: input.robotCapabilities,
    fixture_capabilities: input.fixtureCapabilities,
    process_restrictions: input.processRestrictions,
    equipment_details: input.equipmentDetails,
    remarks: input.remarks,
    status: input.status,
  }
}

export async function listMachineMasters(factoryId: string, filters: { search?: string; status?: string } = {}) {
  const { data } = await http.get('/injection-scheduling/machines', {
    params: { factory_id: factoryId, search: filters.search || '', status: filters.status || '' },
  })
  const source = data as UnknownRecord
  return (Array.isArray(source.items) ? source.items : []).map((item) => mapMachine(item as UnknownRecord))
}

export async function createMachineMaster(factoryId: string, input: MachineMasterInput) {
  const { data } = await http.post('/injection-scheduling/machines', machineMasterPayload(factoryId, input, 0))
  return mapMachine(data as UnknownRecord)
}

export async function updateMachineMaster(factoryId: string, machine: MachineRecord, input: MachineMasterInput) {
  const { data } = await http.put(`/injection-scheduling/machines/${machine.id}`, machineMasterPayload(factoryId, input, machine.revision))
  return mapMachine(data as UnknownRecord)
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
    moldId: text(source.mold_id) || null,
    moldDefinitionId: text(source.mold_definition_id) || null,
    moldOutputSpecId: text(source.mold_output_spec_id) || null,
    orderQuantity: numberValue(source.order_quantity),
    sourceCompletedQuantity: numberValue(source.source_completed_quantity),
    completedQuantity: numberValue(source.completed_quantity), outstandingQuantity: numberValue(source.outstanding_quantity),
    completionRate: numberValue(source.completion_rate), deliveryStartDate: text(source.delivery_start_date),
    deliveryDueDate: text(source.delivery_due_date), deliverySlackDays: numberOrNull(source.delivery_slack_days),
    priorityCode: (text(source.priority_code) || 'NORMAL') as OrderRecord['priorityCode'],
    materialReadinessStatus: (text(source.material_readiness_status) || 'unknown') as OrderRecord['materialReadinessStatus'],
    warehouseText: text(source.warehouse_text), remark: text(source.remark), sourceType: text(source.source_type),
    status: (text(source.status) || 'BACKLOG') as OrderRecord['status'],
    lineage: source.lineage && typeof source.lineage === 'object' ? source.lineage as UnknownRecord : {},
    revision: numberValue(source.revision),
  }
}

export interface ManualDemandInput {
  businessDate: string
  moldDefinitionId: string
  moldOutputSpecId: string | null
  plannedQuantity: number
  quantityBasis: 'UNITS' | 'SHOTS'
  itemNo: string
  productName: string
  deliveryDueDate: string
  priorityCode: OrderRecord['priorityCode']
  materialReadinessStatus: OrderRecord['materialReadinessStatus']
  warehouseText: string
  materialName: string
  colorName: string
  remark: string
}

function manualDemandPayload(factoryId: string, input: ManualDemandInput) {
  return {
    factory_id: factoryId,
    mold_definition_id: input.moldDefinitionId,
    mold_output_spec_id: input.moldOutputSpecId,
    planned_quantity: input.plannedQuantity,
    quantity_basis: input.quantityBasis,
    item_no: input.itemNo,
    product_name: input.productName,
    delivery_due_date: input.deliveryDueDate || null,
    priority_code: input.priorityCode,
    material_readiness_status: input.materialReadinessStatus,
    warehouse_text: input.warehouseText,
    material_name: input.materialName,
    color_name: input.colorName,
    remark: input.remark,
  }
}

export async function createManualDemand(factoryId: string, input: ManualDemandInput) {
  const { data } = await http.post('/injection-scheduling/manual-demands', {
    ...manualDemandPayload(factoryId, input),
    expected_revision: 0,
    business_date: input.businessDate,
  }, { headers: { 'X-Request-ID': newRequestId('manual-demand-create') } })
  return mapOrder(data as UnknownRecord)
}

export async function updateManualDemand(factoryId: string, order: OrderRecord, input: ManualDemandInput) {
  const { data } = await http.patch(`/injection-scheduling/manual-demands/${order.id}`, {
    ...manualDemandPayload(factoryId, input),
    expected_revision: order.revision,
    clear_delivery_due_date: !input.deliveryDueDate,
  }, { headers: { 'X-Request-ID': newRequestId('manual-demand-update') } })
  return mapOrder(data as UnknownRecord)
}

export async function cancelManualDemand(factoryId: string, order: OrderRecord, reason: string) {
  const { data } = await http.post(`/injection-scheduling/manual-demands/${order.id}/cancel`, {
    factory_id: factoryId,
    expected_revision: order.revision,
    reason,
  }, { headers: { 'X-Request-ID': newRequestId('manual-demand-cancel') } })
  return mapOrder(data as UnknownRecord)
}

export async function cancelBacklogOrder(
  factoryId: string,
  order: OrderRecord,
  planningPlan: SchedulingPlanRecord | null,
  reason: string,
) {
  const { data } = await http.post(`/injection-scheduling/backlog/${order.id}/cancel`, {
    factory_id: factoryId,
    expected_revision: order.revision,
    expected_plan_id: planningPlan?.id ?? null,
    expected_plan_revision: planningPlan?.revision ?? null,
    reason,
  }, { headers: { 'X-Request-ID': newRequestId('backlog-order-cancel') } })
  return mapOrder(data as UnknownRecord)
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
      exportProfileId: text(source.export_profile_id) || null, exportProfileRevision: numberOrNull(source.export_profile_revision),
      exportProfileFamily: text(source.export_profile_family), exportRendererCode: text(source.export_renderer_code),
      exportBindingSource: text(source.export_binding_source), calculationVersion: text(source.calculation_version),
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
  const mappedBacklogOrders = backlogItems.map(mapOrder)
  const orderMap = new Map<string, OrderRecord>()
  for (const source of [...planOrders, ...mappedBacklogOrders]) {
    const order = source
    orderMap.set(order.id, order)
  }
  return {
    machines: ((machinesResponse.data as UnknownRecord).items as UnknownRecord[] ?? []).map(mapMachine),
    molds: ((moldsResponse.data as UnknownRecord).items as UnknownRecord[] ?? []).map(mapMold),
    orders: [...orderMap.values()],
    tasks: mappedPlan.tasks,
    backlogOrderIds: backlogItems.map((source) => text(source.id)),
    backlogOrders: mappedBacklogOrders,
    plan: mappedPlan.plan,
    executionPlan: publishedPlan.plan,
    planningPlan: draftPlan.plan,
    executionOrders: publishedPlan.orders,
    executionTasks: publishedPlan.tasks,
    planningOrders: draftPlan.orders,
    planningTasks: draftPlan.tasks,
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

export async function publishSchedulingPlan(factoryId: string, plan: SchedulingPlanRecord) {
  const requestId = newRequestId('plan-publish')
  const { data } = await http.post(`/injection-scheduling/plans/${plan.id}/publish`, {
    factory_id: factoryId,
    expected_revision: plan.revision,
    request_id: requestId,
  }, { headers: { 'X-Request-ID': requestId } })
  const payload = data as {
    plan: UnknownRecord
    snapshot_id?: string
    audit_sequence?: number
    idempotent_replay?: boolean
  }
  return {
    ...mapPlan(payload.plan),
    snapshotId: text(payload.snapshot_id),
    auditSequence: numberValue(payload.audit_sequence),
    idempotentReplay: Boolean(payload.idempotent_replay),
  }
}

// Published plans are immutable; the server applies this operation to a successor DRAFT.
export async function withdrawScheduleTask(
  factoryId: string,
  sourcePlan: SchedulingPlanRecord,
  task: ScheduleTaskRecord,
  planningPlan: SchedulingPlanRecord | null,
  reason: string,
) {
  const requestId = newRequestId('task-withdraw')
  const { data } = await http.post(`/injection-scheduling/tasks/${task.id}/withdraw-to-backlog`, {
    factory_id: factoryId,
    expected_plan_revision: sourcePlan.revision,
    expected_task_revision: task.revision,
    expected_planning_revision: sourcePlan.status === 'PUBLISHED' ? planningPlan?.revision ?? null : null,
    request_id: requestId,
    reason,
  }, { headers: { 'X-Request-ID': requestId } })
  const payload = data as {
    plan: UnknownRecord
    source_plan_id?: string
    source_task_id?: string
    order_id?: string
    withdrawn_task_ids?: string[]
    successor_created?: boolean
    audit_sequence?: number
    idempotent_replay?: boolean
  }
  return {
    ...mapPlan(payload.plan),
    sourcePlanId: text(payload.source_plan_id),
    sourceTaskId: text(payload.source_task_id),
    orderId: text(payload.order_id),
    withdrawnTaskIds: strings(payload.withdrawn_task_ids),
    successorCreated: Boolean(payload.successor_created),
    auditSequence: numberValue(payload.audit_sequence),
    idempotentReplay: Boolean(payload.idempotent_replay),
  }
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
    executionOrders: publishedPlan.orders,
    executionTasks: publishedPlan.tasks,
    planningOrders: draftPlan.orders,
    planningTasks: draftPlan.tasks,
    pollingRevision: numberValue(payload.polling_revision),
  }
}

function newRequestId(prefix: string) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replaceAll('-', '')
    : Math.random().toString(36).slice(2)
  return `${prefix}-${Date.now()}-${random}`.slice(0, 128)
}

function mapImportIssue(source: UnknownRecord): ImportIssueRecord {
  return {
    id: text(source.id), severity: (text(source.severity) || 'WARNING') as ImportIssueRecord['severity'],
    code: text(source.code), message: text(source.message), sheetName: text(source.sheet_name),
    sourceRow: numberOrNull(source.source_row), fieldName: text(source.field_name), cellRef: text(source.cell_ref),
    rawValue: text(source.raw_value), blocking: Boolean(source.blocking),
  }
}

function mapDemandImportRow(source: UnknownRecord) {
  const strings = (value: unknown) => Array.isArray(value) ? value.map((item) => text(item)).filter(Boolean) : []
  const record = (value: unknown) => value && typeof value === 'object' ? value as UnknownRecord : {}
  return {
    rowId: text(source.row_id),
    source: record(source.source),
    canonical: record(source.canonical),
    resolutionStatus: text(source.resolution_status),
    resolutionReasons: strings(source.resolution_reasons),
    resolvedValues: record(source.resolved_values),
    confirmationState: text(source.confirmation_state) || 'PENDING',
    resolutionDigest: text(source.resolution_digest),
  }
}

export function mapImportBatch(source: UnknownRecord): ImportBatchRecord {
  const record = (value: unknown) => value && typeof value === 'object' ? value as UnknownRecord : {}
  const records = (value: unknown) => Array.isArray(value)
    ? value.filter((item): item is UnknownRecord => Boolean(item) && typeof item === 'object')
    : []
  return {
    id: text(source.id), factoryId: text(source.factory_id), sourceFileName: text(source.source_file_name),
    sourceFileHash: text(source.source_file_hash), batchState: text(source.batch_state),
    previewGeneration: numberValue(source.preview_generation),
    documentKind: (text(source.document_kind) || 'PLANNED_SCHEDULE') as ImportBatchRecord['documentKind'],
    sourceNamespaceId: text(source.source_namespace_id),
    profile: source.profile && typeof source.profile === 'object' ? source.profile as UnknownRecord : null,
    sheetRoles: records(source.sheet_roles), mapping: records(source.mapping),
    scheduledBaselineTasks: records(source.scheduled_baseline_tasks), backlogOrders: records(source.backlog_orders),
    invalidRows: records(source.invalid_rows), masterDifferences: records(source.master_differences),
    calculationComparisons: records(source.calculation_comparisons), reconciliationActions: records(source.reconciliation_actions),
    demandRows: records(source.demand_rows).map(mapDemandImportRow),
    masterDataRows: records(source.master_data_rows).map((row) => ({
      rowId: text(row.row_id), entityType: text(row.entity_type),
      source: record(row.source), canonical: record(row.canonical),
      resolutionStatus: text(row.resolution_status), confirmationState: text(row.confirmation_state) || 'PENDING',
      activationBlockers: strings(row.activation_blockers), rowDigest: text(row.row_digest),
    })),
    resolutionDigest: text(source.resolution_digest),
    mappingDraft: source.mapping_draft && typeof source.mapping_draft === 'object' ? source.mapping_draft as UnknownRecord : {},
    partialConfirmation: source.partial_confirmation && typeof source.partial_confirmation === 'object' ? source.partial_confirmation as UnknownRecord : {},
    planContext: source.plan_context && typeof source.plan_context === 'object' ? source.plan_context as UnknownRecord : {},
    actionFingerprint: text(source.action_fingerprint),
    summary: source.summary && typeof source.summary === 'object' ? source.summary as UnknownRecord : {},
    status: (text(source.status) || 'PREVIEW') as ImportBatchRecord['status'], revision: numberValue(source.revision),
    confirmedPlanId: text(source.confirmed_plan_id), confirmedPlanRevision: numberValue(source.confirmed_plan_revision),
    result: source.result && typeof source.result === 'object' ? source.result as UnknownRecord : {},
    artifactAvailable: Boolean(source.artifact_available), artifactExpiresAt: text(source.artifact_expires_at),
    issues: records(source.issues).map(mapImportIssue), idempotentReplay: Boolean(source.idempotent_replay),
  }
}

export async function listImportBatches(factoryId: string) {
  const { data } = await http.get('/injection-scheduling/imports', { params: { factory_id: factoryId, limit: 20 } })
  return (Array.isArray(data) ? data as UnknownRecord[] : []).map(mapImportBatch)
}

export async function recoverImportBatch(factoryId: string, batchId: string) {
  const { data } = await http.get(`/injection-scheduling/imports/${batchId}`, { params: { factory_id: factoryId } })
  return mapImportBatch(data as UnknownRecord)
}

export async function uploadImportPreview(factoryId: string, file: File, documentKind: ImportDocumentKindChoice = 'AUTO') {
  const body = new FormData()
  body.set('factory_id', factoryId)
  body.set('expected_revision', '0')
  body.set('document_kind', documentKind)
  body.set('file', file)
  const { data } = await http.post('/injection-scheduling/imports/preview', body, {
    headers: {
      'Content-Type': 'multipart/form-data',
      'X-Request-ID': newRequestId('import-preview'),
    },
  })
  return mapImportBatch(data as UnknownRecord)
}

export async function retryImportPreview(factoryId: string, batch: ImportBatchRecord) {
  const { data } = await http.post(`/injection-scheduling/imports/${batch.id}/retry`, {
    factory_id: factoryId, expected_revision: batch.revision, request_id: newRequestId('import-retry'),
  })
  return mapImportBatch(data as UnknownRecord)
}

export async function updateImportMappingDraft(factoryId: string, batch: ImportBatchRecord, mappings: Record<string, string>) {
  const { data } = await http.patch(`/injection-scheduling/imports/${batch.id}/mapping-draft`, {
    factory_id: factoryId,
    expected_revision: batch.revision,
    request_id: newRequestId('import-mapping'),
    mappings,
  })
  return mapImportBatch(data as UnknownRecord)
}

export async function proposeImportProfile(factoryId: string, batch: ImportBatchRecord, name: string, reason: string) {
  const { data } = await http.post(`/injection-scheduling/imports/${batch.id}/profile-proposal`, {
    factory_id: factoryId,
    expected_revision: batch.revision,
    request_id: newRequestId('import-profile-proposal'),
    name,
    reason,
  })
  return mapImportBatch(data as UnknownRecord)
}

export async function listImportProfiles(factoryId: string) {
  const { data } = await http.get('/injection-scheduling/import-profiles', { params: { factory_id: factoryId } })
  const source = data as UnknownRecord
  return Array.isArray(source.items)
    ? source.items.filter((item): item is UnknownRecord => Boolean(item) && typeof item === 'object')
    : []
}

export async function transitionImportProfile(factoryId: string, profile: UnknownRecord, target: 'activate' | 'retire', reason: string) {
  const { data } = await http.post(`/injection-scheduling/import-profiles/${text(profile.id)}/${target}`, {
    factory_id: factoryId,
    expected_lifecycle_revision: numberValue(profile.lifecycle_revision),
    request_id: newRequestId(`import-profile-${target}`),
    reason,
  })
  return data as UnknownRecord
}

export async function listMasterDataProposals(factoryId: string) {
  const { data } = await http.get('/injection-scheduling/master-data-proposals', { params: { factory_id: factoryId } })
  return Array.isArray(data)
    ? data.filter((item): item is UnknownRecord => Boolean(item) && typeof item === 'object')
    : []
}

function mapSharedMoldCatalogItem(source: UnknownRecord): SharedMoldCatalogItem {
  const capability = source.factory_capability && typeof source.factory_capability === 'object'
    ? source.factory_capability as UnknownRecord
    : null
  const price = source.price && typeof source.price === 'object' ? source.price as UnknownRecord : null
  const readiness = source.factory_readiness && typeof source.factory_readiness === 'object'
    ? source.factory_readiness as UnknownRecord
    : {}
  const outputs = Array.isArray(source.outputs)
    ? source.outputs.filter((item): item is UnknownRecord => Boolean(item) && typeof item === 'object')
    : []
  return {
    id: text(source.id),
    canonicalMoldNo: text(source.canonical_mold_no),
    displayMoldNo: text(source.display_mold_no),
    standardName: text(source.standard_name),
    moldAClass: numberLikeOrNull(source.mold_a_class),
    recommendedMachineClassRaw: text(source.recommended_machine_class_raw),
    defaultArmType: text(source.default_arm_type),
    defaultFixtureType: text(source.default_fixture_type),
    status: text(source.status),
    dataQuality: text(source.data_quality),
    revision: numberValue(source.revision),
    outputCount: numberValue(source.output_count),
    outputs: outputs.map((item) => ({
      id: text(item.id),
      itemNo: text(item.item_no),
      productName: text(item.product_name),
      cavityCount: numberLikeOrNull(item.cavity_count),
    })),
    nominalDailyCapacity: numberLikeOrNull(source.nominal_daily_capacity),
    factoryCapability: capability ? {
      machineClass: numberLikeOrNull(capability.machine_class),
      requiredArmType: text(capability.required_arm_type),
      requiredFixtureType: text(capability.required_fixture_type),
    } : null,
    price: price && numberLikeOrNull(price.amount) !== null ? {
      amount: numberLikeOrNull(price.amount) as number,
      currency: text(price.currency),
      pricingBasis: text(price.pricing_basis),
      taxMode: text(price.tax_mode),
    } : null,
    factoryReadiness: {
      status: text(readiness.status),
      availableAssetCount: numberValue(readiness.available_asset_count),
      activeCapabilityCount: numberValue(readiness.active_capability_count),
    },
  }
}

export async function listSharedMoldCatalog(factoryId: string, options: { q?: string; readiness?: string; page?: number; pageSize?: number } = {}): Promise<SharedMoldCatalogPage> {
  const { data } = await http.get('/injection-scheduling/shared-molds/catalog', {
    params: {
      factory_id: factoryId,
      q: options.q ?? '',
      readiness: options.readiness ?? 'ALL',
      page: options.page ?? 1,
      page_size: options.pageSize ?? 30,
    },
  })
  const source = data as UnknownRecord
  const summary = source.summary && typeof source.summary === 'object' ? source.summary as UnknownRecord : {}
  const items = Array.isArray(source.items)
    ? source.items.filter((item): item is UnknownRecord => Boolean(item) && typeof item === 'object')
    : []
  return {
    items: items.map(mapSharedMoldCatalogItem),
    page: numberValue(source.page),
    pageSize: numberValue(source.page_size),
    total: numberValue(source.total),
    summary: {
      totalDefinitions: numberValue(summary.total_definitions),
      factoryReady: numberValue(summary.factory_ready),
      notFactoryReady: numberValue(summary.not_factory_ready),
      pendingProposals: numberValue(summary.pending_proposals),
      canReadPrices: Boolean(summary.can_read_prices),
    },
  }
}

export async function getSharedMoldDetail(factoryId: string, definitionId: string): Promise<SharedMoldDetail> {
  const { data } = await http.get(`/injection-scheduling/shared-molds/catalog/${definitionId}`, { params: { factory_id: factoryId } })
  const source = data as UnknownRecord
  const base = mapSharedMoldCatalogItem(source)
  const records = (value: unknown) => Array.isArray(value)
    ? value.filter((item): item is UnknownRecord => Boolean(item) && typeof item === 'object')
    : []
  return {
    ...base,
    aliases: records(source.aliases).map((item) => ({ id: text(item.id), rawAlias: text(item.raw_alias), sourceNamespaceId: text(item.source_namespace_id) })),
    outputs: records(source.outputs).map((item) => ({
      id: text(item.id), itemNo: text(item.item_no), variantCode: text(item.variant_code), productName: text(item.product_name), cavityCount: numberLikeOrNull(item.cavity_count),
      wholeShotNetWeightG: numberLikeOrNull(item.whole_shot_net_weight_g), wholeShotGrossWeightG: numberLikeOrNull(item.whole_shot_gross_weight_g),
      defaultMaterial: text(item.default_material), defaultColor: text(item.default_color), nominalDailyCapacity: numberLikeOrNull(item.nominal_daily_capacity), revision: numberValue(item.revision),
    })),
    assets: records(source.assets).map((item) => ({ id: text(item.id), assetCode: text(item.asset_code), serialNo: text(item.serial_no), currentLocation: text(item.current_location), status: text(item.status), actualCavityCount: numberLikeOrNull(item.actual_cavity_count), revision: numberValue(item.revision) })),
    capabilities: records(source.capabilities).map((item) => ({ id: text(item.id), machineClass: numberLikeOrNull(item.machine_class), requiredArmType: text(item.required_arm_type), requiredFixtureType: text(item.required_fixture_type), nominalDailyCapacity: numberLikeOrNull(item.nominal_daily_capacity), priority: numberValue(item.priority), revision: numberValue(item.revision) })),
    prices: records(source.prices).map((item) => ({ id: text(item.id), moldOutputSpecId: text(item.mold_output_spec_id), amount: numberLikeOrNull(item.amount) ?? 0, currency: text(item.currency), pricingBasis: text(item.pricing_basis), taxMode: text(item.tax_mode), revision: numberValue(item.revision) })),
    priceAccess: text(source.price_access) === 'GRANTED' ? 'GRANTED' : 'RESTRICTED',
  }
}

export async function createSharedMoldProposal(factoryId: string, input: SharedMoldProposalInput) {
  const { data } = await http.post('/injection-scheduling/shared-molds/proposals', {
    factory_id: factoryId,
    request_id: newRequestId('shared-mold-proposal'),
    reason: input.reason,
    canonical_mold_no: input.canonicalMoldNo,
    display_mold_no: input.displayMoldNo,
    standard_name: input.standardName,
    raw_aliases: input.rawAliases,
    recommended_machine_class_raw: input.recommendedMachineClassRaw,
    mold_a_class: input.moldAClass,
    default_arm_type: input.defaultArmType,
    default_fixture_type: input.defaultFixtureType,
    outputs: input.outputs.map((item) => ({
      item_no: item.itemNo, variant_code: item.variantCode, product_name: item.productName, cavity_count: item.cavityCount,
      whole_shot_net_weight_g: item.wholeShotNetWeightG, whole_shot_gross_weight_g: item.wholeShotGrossWeightG,
      default_material: item.defaultMaterial, default_color: item.defaultColor, nominal_daily_capacity: item.nominalDailyCapacity, unit_price_cny: item.unitPriceCny,
    })),
    capability: input.capability ? {
      machine_class: input.capability.machineClass,
      machine_class_raw: input.capability.machineClassRaw,
      required_arm_type: input.capability.requiredArmType,
      required_fixture_type: input.capability.requiredFixtureType,
    } : null,
  })
  const source = data as UnknownRecord
  return Array.isArray(source.proposals)
    ? source.proposals.filter((item): item is UnknownRecord => Boolean(item) && typeof item === 'object')
    : []
}

export async function reviewMasterDataProposal(factoryId: string, proposal: UnknownRecord, action: 'approve' | 'activate', reason: string) {
  const activatesWorkbookPrice = action === 'activate' && text(proposal.entity_type) === 'COMMERCIAL_RATE_RULE'
  const { data } = await http.post(`/injection-scheduling/master-data-proposals/${text(proposal.id)}/${action}`, {
    factory_id: factoryId,
    expected_revision: numberValue(proposal.revision),
    request_id: newRequestId(`master-proposal-${action}`),
    reason,
    ...(activatesWorkbookPrice ? {
      price_confirmation: {
        pricing_basis: 'PER_SHOT',
        currency: 'CNY',
        tax_mode: 'AS_LISTED',
        owner_scope_type: 'FACTORY',
        applicable_factory_mode: 'SPECIFIC',
        applicable_customer_mode: 'ANY',
        contract_mode: 'ANY',
        confirmed_business_signoff: true,
      },
    } : {}),
  })
  return data as UnknownRecord
}

export async function enrichDemandOrderMolds(factoryId: string) {
  const { data } = await http.post('/injection-scheduling/demand-orders/enrich-molds', {
    factory_id: factoryId,
    request_id: newRequestId('demand-mold-enrich'),
    reason: '啤机文员重新匹配待排订单模具资料',
  })
  return data as UnknownRecord
}

export async function approveImportMasterDifferences(factoryId: string, batch: ImportBatchRecord, reason: string) {
  const differences = batch.masterDifferences.map((item) => `${text(item.entity_type)}:${text(item.business_key)}`)
  const { data } = await http.post(`/injection-scheduling/imports/${batch.id}/master-differences/approve`, {
    factory_id: factoryId, expected_revision: batch.revision, request_id: newRequestId('import-master'), reason, differences,
  })
  return mapImportBatch(data as UnknownRecord)
}

export async function confirmImportBatch(factoryId: string, batch: ImportBatchRecord, businessDate: string, selectedRowIds: string[] = []) {
  const targetDraftRevision = batch.status === 'PARTIALLY_CONFIRMED'
    ? batch.confirmedPlanRevision
    : numberValue(batch.planContext.target_draft_plan_revision)
  const confirmMode = targetDraftRevision > 0 ? 'merge_draft' : 'create_draft'
  const isDemandOrder = batch.documentKind === 'DEMAND_ORDER'
  const isMasterData = batch.documentKind === 'MASTER_DATA'
  const { data } = await http.post(`/injection-scheduling/imports/${batch.id}/confirm`, {
    factory_id: factoryId, expected_revision: batch.revision, expected_plan_revision: targetDraftRevision,
    request_id: newRequestId('import-confirm'), confirm_mode: isMasterData ? 'propose_master_data' : confirmMode, business_date: businessDate,
    acknowledged_blocking_issue_ids: [], expected_action_fingerprint: batch.actionFingerprint, action_reasons: {},
    document_kind: batch.documentKind,
    ...((isDemandOrder || isMasterData) ? {
      expected_preview_generation: batch.previewGeneration,
      expected_resolution_digest: batch.resolutionDigest,
      confirm_scope: 'SELECTED',
      selected_row_ids: selectedRowIds,
    } : {}),
    ...(isDemandOrder ? {
      target_draft_plan_id: batch.confirmedPlanId || text(batch.planContext.target_draft_plan_id),
      reference_published_plan_id: text(batch.planContext.reference_published_plan_id),
    } : {}),
  })
  return mapImportBatch(data as UnknownRecord)
}

export async function previewManualAppend(factoryId: string, plan: SchedulingPlanRecord, order: OrderRecord, machineId: string) {
  const { data } = await http.post(`/injection-scheduling/plans/${plan.id}/manual-append/preview`, {
    factory_id: factoryId, order_id: order.id, machine_id: machineId,
    expected_plan_revision: plan.revision, expected_order_revision: order.revision, expected_rule_revision: plan.ruleRevision,
  })
  const source = data as UnknownRecord
  return {
    factoryId: text(source.factory_id), planId: text(source.plan_id), planRevision: numberValue(source.plan_revision),
    orderId: text(source.order_id), orderRevision: numberValue(source.order_revision), machineId: text(source.machine_id),
    sequence: numberValue(source.sequence_no), decision: text(source.decision) as ManualAppendPreviewRecord['decision'],
    hardFailures: (source.hard_failures as UnknownRecord[]) ?? [], warnings: (source.warnings as UnknownRecord[]) ?? [],
    advisories: (source.advisories as UnknownRecord[]) ?? [], plannedQuantity: numberValue(source.planned_quantity),
    shiftTargetQuantity: numberValue(source.shift_target_quantity), plannedStart: text(source.planned_start), plannedFinish: text(source.planned_finish),
    continuationAnchor: source.continuation_anchor as UnknownRecord ?? {}, calculation: source.calculation as UnknownRecord ?? {},
    ruleRevision: numberValue(source.rule_revision), inputFingerprint: text(source.input_fingerprint),
  } satisfies ManualAppendPreviewRecord
}

export async function confirmManualAppend(factoryId: string, plan: SchedulingPlanRecord, order: OrderRecord, preview: ManualAppendPreviewRecord, overrideReason: string) {
  const { data } = await http.post(`/injection-scheduling/plans/${plan.id}/manual-append/confirm`, {
    factory_id: factoryId, order_id: order.id, machine_id: preview.machineId,
    expected_plan_revision: plan.revision, expected_order_revision: order.revision, expected_rule_revision: plan.ruleRevision,
    request_id: newRequestId('manual-append'), expected_input_fingerprint: preview.inputFingerprint, override_reason: overrideReason,
  })
  return data as UnknownRecord
}

function exportFileName(contentDisposition: unknown, fallback: string) {
  if (typeof contentDisposition !== 'string') return fallback
  const encoded = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) {
    try { return decodeURIComponent(encoded) } catch { return fallback }
  }
  return contentDisposition.match(/filename="?([^";]+)"?/i)?.[1] ?? fallback
}

export async function downloadPlanExport(
  factoryId: string,
  plan: SchedulingPlanRecord,
  mode: PlanExportMode,
): Promise<PlanExportResult> {
  const requestId = newRequestId('plan-export')
  const sourceCompatible = mode === 'SOURCE_COMPATIBLE'
  const response = await http.post<Blob>(`/injection-scheduling/plans/${plan.id}/exports`, {
    factory_id: factoryId,
    expected_plan_revision: plan.revision,
    request_id: requestId,
    export_mode: mode,
    ...(sourceCompatible
      ? { profile_id: plan.exportProfileId, profile_revision: plan.exportProfileRevision }
      : {}),
  }, { responseType: 'blob', timeout: 60_000 })
  const headers = response.headers
  return {
    blob: response.data,
    fileName: exportFileName(headers['content-disposition'], `injection-plan-${factoryId}-r${plan.revision}.xlsx`),
    auditId: String(headers['x-export-audit-id'] ?? ''),
    fileSha256: String(headers['x-export-sha256'] ?? ''),
    mode: String(headers['x-export-mode'] ?? mode) as PlanExportMode,
    profileId: String(headers['x-export-profile-id'] ?? ''),
    profileRevision: Number(headers['x-export-profile-revision'] ?? 0),
    rendererCode: String(headers['x-export-renderer'] ?? ''),
  }
}

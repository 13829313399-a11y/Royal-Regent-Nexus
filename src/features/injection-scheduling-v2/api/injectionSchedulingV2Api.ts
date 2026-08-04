import { http } from '@/lib/http'
import type {
  AuditEvent,
  MachineRecord,
  MoldRecord,
  OrderRecord,
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
    revision: numberValue(source.revision),
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

function mapPlan(source: UnknownRecord | null): { plan: SchedulingPlanRecord | null; orders: OrderRecord[]; tasks: ScheduleTaskRecord[] } {
  if (!source) return { plan: null, orders: [], tasks: [] }
  return {
    plan: {
      id: text(source.id), status: text(source.status), revision: numberValue(source.revision),
      ruleRevision: numberValue(source.rule_revision), businessDate: text(source.business_date),
    },
    orders: (Array.isArray(source.orders) ? source.orders as UnknownRecord[] : []).map(mapOrder),
    tasks: (Array.isArray(source.tasks) ? source.tasks as UnknownRecord[] : []).map(mapTask),
  }
}

export async function fetchSchedulingWorkspace(factoryId: string) {
  const [machinesResponse, moldsResponse, planResponse, backlogResponse, eventsResponse] = await Promise.all([
    http.get('/injection-scheduling/machines', { params: { factory_id: factoryId } }),
    http.get('/injection-scheduling/molds', { params: { factory_id: factoryId } }),
    http.get('/injection-scheduling/plans/current', { params: { factory_id: factoryId } }),
    http.get('/injection-scheduling/backlog', { params: { factory_id: factoryId } }),
    http.get('/injection-scheduling/events', { params: { factory_id: factoryId, after_sequence: 0, limit: 100 } }),
  ])
  const planPayload = planResponse.data as { plan?: UnknownRecord | null; polling_revision?: number }
  const mappedPlan = mapPlan(planPayload.plan ?? null)
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
    pollingRevision: numberValue(planPayload.polling_revision),
    events: (((eventsResponse.data as UnknownRecord).events as UnknownRecord[]) ?? []).map(mapEvent),
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
  const { data } = await http.get('/injection-scheduling/plans/current', { params: { factory_id: factoryId } })
  const payload = data as { plan?: UnknownRecord | null; polling_revision?: number }
  return { ...mapPlan(payload.plan ?? null), pollingRevision: numberValue(payload.polling_revision) }
}

function newRequestId(prefix: string) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replaceAll('-', '')
    : Math.random().toString(36).slice(2)
  return `${prefix}-${Date.now()}-${random}`.slice(0, 128)
}

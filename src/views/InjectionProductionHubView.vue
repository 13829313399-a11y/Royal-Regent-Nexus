<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CalendarClock,
  Check,
  CheckCircle2,
  CircleAlert,
  CircleX,
  Clock3,
  Database,
  Factory,
  FileSpreadsheet,
  GitCompareArrows,
  Info,
  Layers3,
  LockKeyhole,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import InjectionHubHeader from '@/components/modules/production/injection-schedule/InjectionHubHeader.vue'
import ExcelImportPanel, {
  type Phase2ImportPreviewView,
} from '@/components/modules/production/injection-schedule/ExcelImportPanel.vue'
import MachineTimelineBoard, {
  type MachineCandidateState,
} from '@/components/modules/production/injection-schedule/MachineTimelineBoard.vue'
import MachineMasterEditor from '@/components/modules/production/injection-schedule/MachineMasterEditor.vue'
import Phase4DynamicSchedulingPanel, {
  type Phase4ActualCorrectionRequestView,
  type Phase4ActualRequestView,
  type Phase4ActualView,
  type Phase4AutoDraftRequestView,
  type Phase4BarrierView,
  type Phase4ImpactView,
  type Phase4MachineOption,
  type Phase4OrderOption,
  type Phase4ReplanRequestView,
  type Phase4RunView,
  type Phase4SkippedView,
  type Phase4TaskOption,
  type Phase4VersionView,
} from '@/components/modules/production/injection-schedule/Phase4DynamicSchedulingPanel.vue'
import ScheduleMasterEditor from '@/components/modules/production/injection-schedule/ScheduleMasterEditor.vue'
import ScheduleKpiStrip from '@/components/modules/production/injection-schedule/ScheduleKpiStrip.vue'
import ScheduleTaskInspector from '@/components/modules/production/injection-schedule/ScheduleTaskInspector.vue'
import ScheduleVersionPanel, {
  type Phase2ConflictView,
  type Phase2VersionDiffView,
  type Phase2VersionView,
} from '@/components/modules/production/injection-schedule/ScheduleVersionPanel.vue'
import UnscheduledOrderPool from '@/components/modules/production/injection-schedule/UnscheduledOrderPool.vue'
import UnscheduledOrderTable from '@/components/modules/production/injection-schedule/UnscheduledOrderTable.vue'
import {
  factoryContexts,
  getFactoryScopedRoute,
  isFactoryContextId,
  productionFactoryContextIds,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'
import { getInjectionPreviewDataset } from '@/data/injectionScheduleMock'
import { evaluateInjectionConstraints } from '@/lib/injection-schedule/constraintEvaluator'
import { scoreInjectionRecommendation } from '@/lib/injection-schedule/scheduleScoring'
import { calculateInjectionSetupCost } from '@/lib/injection-schedule/setupCost'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useInjectionScheduleStore } from '@/stores/injectionSchedule'
import type {
  ConstraintResult,
  DataProvenance,
  InjectionAutomationResult,
  InjectionMachine,
  InjectionMachineCapability,
  InjectionMachineCreateInput,
  InjectionMachineRecommendation,
  InjectionMachineRecord,
  InjectionMoldCreateInput,
  InjectionMoldRecord,
  InjectionOrder,
  InjectionOrderCreateInput,
  InjectionOrderRecord,
  InjectionPlanVersion,
  InjectionPreviewDataset,
  InjectionScheduleOperation,
  InjectionScheduleRuleConfigUpdateInput,
  InjectionScheduleRuleConfigV3,
  InjectionScheduleWorkspace,
  InjectionScheduleTask,
  InjectionScoreBreakdown,
  InjectionScoringWeights,
  InjectionSetupProfile,
  InjectionTransitionMatrixEntry,
  InjectionVersionDiff,
  Recommendation,
} from '@/types/injectionSchedule'

type HubSection =
  | 'overview'
  | 'orders'
  | 'operations'
  | 'versions'
  | 'masters'
  | 'rules'
const hubSections: HubSection[] = [
  'overview',
  'orders',
  'operations',
  'versions',
  'masters',
  'rules',
]

function hubSectionFromQuery(value: unknown): HubSection {
  const candidate = Array.isArray(value) ? value[0] : value
  return typeof candidate === 'string' && hubSections.includes(candidate as HubSection)
    ? candidate as HubSection
    : 'overview'
}
type OrderWorkspaceMode = 'table' | 'match'
type MasterWorkspaceTab =
  | 'machines'
  | 'molds'
  | 'orders'
  | 'transitions'
  | 'calendar'
  | 'weights'
  | 'import'
type DialogTone = 'info' | 'warning' | 'danger' | 'success'

interface NoticeDialog {
  tone: DialogTone
  title: string
  message: string
  details: string[]
}

interface PendingManualOperation {
  commands: InjectionScheduleOperation[]
  successMessage: string
}

type PendingPhase4Preview =
  | {
      kind: 'auto_draft'
      sourceVersionId: string
      sourceRevision: number
      contextHash: string
      input: Phase4AutoDraftRequestView
    }
  | {
      kind: 'local_replan'
      sourceVersionId: string
      sourceRevision: number
      contextHash: string
      input: Phase4ReplanRequestView
    }

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()
const scheduleStore = useInjectionScheduleStore()

function formalProvenance(
  sourceBatchId: string,
  record: Record<string, unknown> = {},
): DataProvenance {
  return {
    source: 'system',
    confidence: 'verified',
    sourceId: sourceBatchId || null,
    sourceFileName: typeof record.sourceFileName === 'string' ? record.sourceFileName : null,
    sourceFileSha256: typeof record.sourceSha256 === 'string' ? record.sourceSha256 : null,
    sheetName: typeof record.sourceSheet === 'string' ? record.sourceSheet : null,
    sourceRow: typeof record.sourceRow === 'number' ? record.sourceRow : null,
    capturedAt: null,
    importedAt: null,
    importedBy: null,
  }
}

function formalArmType(value: string) {
  if (/双|double/i.test(value)) return 'double' as const
  if (/单|single/i.test(value)) return 'single' as const
  return 'none' as const
}

const formalCapabilities = new Set<InjectionMachineCapability>([
  'core_pull',
  'double_core_pull',
  'deep_nozzle',
  'high_pressure',
  'two_color',
  'automatic_pull',
  'submersible',
])

function toViewCapabilities(values: string[]) {
  const result = values.filter(
    (value): value is InjectionMachineCapability =>
      formalCapabilities.has(value as InjectionMachineCapability),
  )
  return result.length || values.length === 0 ? result : null
}

function finiteRuleNumber(value: unknown, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback
}

function normalizedMoldLookupKey(value: string) {
  return value.trim().toLocaleUpperCase('zh-CN')
}

function formalMaterialRules(
  machineId: string,
  values: string[],
): InjectionMachine['materialRules'] {
  const materialCodes = values.map((value) => value.trim()).filter(Boolean)
  if (materialCodes.length === 0) return []
  return [{
    id: `${machineId}-formal-material-rules`,
    mode: 'allow_only',
    materialCodes,
    reason: `正式主数据仅允许材料：${materialCodes.join('、')}`,
  }]
}

function formalTaskScoreBreakdown(
  rows: Array<Record<string, unknown>> | undefined,
): InjectionScoreBreakdown {
  const scoreFor = (...codes: string[]) => {
    const normalizedCodes = codes.map(normalizedRuleCode)
    const row = (rows ?? []).find((entry) => (
      typeof entry.code === 'string'
      && normalizedCodes.includes(normalizedRuleCode(entry.code))
    ))
    const value = Number(row?.weightedScore ?? row?.weighted_score ?? 0)
    return Number.isFinite(value) ? value : 0
  }
  return {
    dueUrgency: scoreFor('dueDate', 'dueUrgency'),
    sameMoldMaterial: scoreFor('sequenceAffinity', 'sameMoldMaterial'),
    setupCost: scoreFor('setupEfficiency', 'setupCost'),
    colorTransition: scoreFor('colorTransition'),
    loadBalance: scoreFor('loadBalance'),
    downstreamImpact: scoreFor('downstreamPriority', 'downstreamImpact'),
    exactMatch: scoreFor('exactMatch'),
    splitPenalty: scoreFor('splitPenalty'),
    specialHandlingPenalty: scoreFor('specialHandlingPenalty'),
  }
}

function formalTaskConstraints(
  rows: Array<Record<string, unknown>> | undefined,
): ConstraintResult[] {
  return (rows ?? []).map((row) => formalConstraintToView({
    code: typeof row.code === 'string' ? row.code : 'unknown',
    status: row.status === 'pass' || row.status === 'fail' || row.status === 'unknown'
      ? row.status
      : 'unknown',
    blocking: Boolean(row.blocking),
    message: typeof row.message === 'string' ? row.message : '缺少约束说明',
    details: row.details && typeof row.details === 'object' && !Array.isArray(row.details)
      ? row.details as Record<string, unknown>
      : {},
  }))
}

function toPreviewCompatibleWorkspace(
  workspace: InjectionScheduleWorkspace,
  fallback: InjectionPreviewDataset,
): InjectionPreviewDataset {
  const version = workspace.activeVersion
  const versionRules = version?.rulesSnapshot && Object.keys(version.rulesSnapshot).length > 0
    ? version.rulesSnapshot
    : workspace.ruleConfig.config
  const defaultSetupMinutes = finiteRuleNumber(
    versionRules.defaultSetupHours ?? versionRules.default_setup_hours,
    fallback.ruleConfig.setup.differentMoldChangeMinutes / 60,
  ) * 60
  const ruleConfig = {
    ...fallback.ruleConfig,
    factoryId: workspace.factoryId,
    shotSafetyFactor: finiteRuleNumber(
      versionRules.shotSafetyFactor ?? versionRules.shot_safety_factor,
      fallback.ruleConfig.shotSafetyFactor,
    ),
    setup: {
      ...fallback.ruleConfig.setup,
      firstTaskSetupMinutes: defaultSetupMinutes,
      differentMoldChangeMinutes: defaultSetupMinutes,
    },
    scoring: {
      ...fallback.ruleConfig.scoring,
      weights: { ...fallback.ruleConfig.scoring.weights },
    },
  }
  const planBaseAt = version?.planBaseAt
    || `${version?.businessDate || fallback.businessDate}T08:00:00+08:00`
  const moldIdByCode = new Map<string, string>()
  for (const mold of workspace.molds) {
    moldIdByCode.set(normalizedMoldLookupKey(mold.moldCode), mold.id)
    if (mold.normalizedMoldCode) {
      moldIdByCode.set(normalizedMoldLookupKey(mold.normalizedMoldCode), mold.id)
    }
  }
  const moldById = new Map(workspace.molds.map((mold) => [mold.id, mold]))
  const machines: InjectionMachine[] = workspace.machines.map((machine) => {
    const required = [
      machine.maxShotWeightG,
      machine.tieBarXMm,
      machine.tieBarYMm,
      machine.moldThicknessMinMm,
      machine.moldThicknessMaxMm,
      machine.openingStrokeMm,
    ]
    const completeness = required.filter((value) => value != null).length / required.length
    return {
      id: machine.id,
      factoryId: machine.factoryId,
      workshop: machine.workshop,
      machineNo: machine.machineCode,
      machineClass: machine.machineClass,
      tonnage: machine.tonnageT,
      speedType: machine.processType || null,
      armType: formalArmType(machine.robotType),
      supportedFixtures: machine.fixtureType ? [machine.fixtureType] : null,
      screwType: machine.screwType || null,
      capabilities: toViewCapabilities(machine.capabilities),
      materialRules: formalMaterialRules(machine.id, machine.materialRules),
      maxShotWeightG: machine.maxShotWeightG,
      tieBarWidthMm: machine.tieBarXMm,
      tieBarHeightMm: machine.tieBarYMm,
      minMoldThicknessMm: machine.moldThicknessMinMm,
      maxMoldThicknessMm: machine.moldThicknessMaxMm,
      maxOpeningStrokeMm: machine.openingStrokeMm,
      maxEjectorClearanceMm: machine.ejectorStrokeMm,
      status: machine.status === 'available'
        ? 'idle'
        : machine.status === 'maintenance'
          ? 'maintenance'
          : machine.status === 'stopped'
            ? 'stopped'
            : 'locked',
      schedulingLocked: machine.status === 'retired',
      availableFrom: machine.availableAt || null,
      unavailableWindows: [],
      dataCompleteness: completeness,
      dataQualityFlags: machine.qualityStatus && machine.qualityStatus !== 'ready'
        ? [machine.qualityStatus]
        : [],
      provenance: formalProvenance(machine.sourceBatchId, machine.provenance),
    }
  })
  const molds = workspace.molds.map((mold) => ({
    id: mold.id,
    factoryId: mold.factoryId,
    moldNo: mold.moldCode,
    name: mold.moldName,
    recommendedMachineClass: mold.machineClass || null,
    minTonnage: null,
    grossShotWeightG: mold.grossShotWeightG,
    engineeringNetWeightG: null,
    lengthMm: mold.lengthMm,
    widthMm: mold.widthMm,
    heightMm: mold.heightMm,
    moldThicknessMm: mold.moldThicknessMm ?? null,
    requiredOpeningStrokeMm: mold.requiredOpeningStrokeMm ?? null,
    requiredEjectorClearanceMm: null,
    moldWeightKg: mold.moldWeightKg,
    armRequirement: formalArmType(mold.robotType),
    fixtureRequirements: mold.fixtureType ? [mold.fixtureType] : [],
    capabilitiesRequired: toViewCapabilities(mold.requiredCapabilities) ?? [],
    materialCode: mold.materialRules[0] ?? null,
    requiredScrewTypes: mold.requiredScrewType ? [mold.requiredScrewType] : [],
    defaultColor: null,
    defaultColorRank: null,
    cavityCount: mold.cavities,
    standardCycleSeconds: mold.cycleSeconds,
    dataQualityFlags: mold.qualityStatus && mold.qualityStatus !== 'ready'
      ? [mold.qualityStatus]
      : [],
    provenance: formalProvenance(mold.sourceBatchId, mold.provenance),
  }))
  const orders: InjectionOrder[] = workspace.orders.map((order) => {
    const moldId = moldIdByCode.get(normalizedMoldLookupKey(order.moldCode)) ?? order.moldCode
    const mold = moldById.get(moldId)
    return {
      id: order.id,
      factoryId: order.factoryId,
      orderNo: order.orderNo,
      itemNo: order.productCode || null,
      moldId,
      productName: order.productName,
      orderShots: order.orderQty,
      producedShots: order.producedQty,
      outstandingShots: order.outstandingQty,
      targetShotsPerDay: order.dailyTargetQty,
      grossShotWeightG: mold?.grossShotWeightG ?? null,
      colorName: order.color || null,
      colorCode: order.pigment || order.color || null,
      colorRank: order.colorRank ?? null,
      materialCode: order.material || null,
      armRequirement: mold ? formalArmType(mold.robotType) : null,
      fixtureRequirements: mold?.fixtureType ? [mold.fixtureType] : [],
      capabilitiesRequired: mold
        ? toViewCapabilities(mold.requiredCapabilities) ?? []
        : [],
      orderedAt: null,
      deliveryStartAt: null,
      deliveryDueAt: order.deliveryDueDate || null,
      warehouseBufferHours: order.warehouseBufferHours ?? 0,
      downstreamBufferHours: order.downstreamBufferHours ?? 0,
      downstreamProcess: order.specialHandlingReason || null,
      downstreamUrgency: order.downstreamUrgency ?? 0,
      priority: order.priorityCode,
      status: order.status,
      dataQualityFlags: order.qualityStatus && order.qualityStatus !== 'ready'
        ? [order.qualityStatus]
        : [],
      sourceWorkbookRow: order.sourceRow || null,
      provenance: formalProvenance(order.sourceBatchId, {
        ...order.provenance,
        sourceSheet: order.sourceSheet,
        sourceRow: order.sourceRow,
      }),
    }
  })
  const tasks: InjectionScheduleTask[] = workspace.tasks.map((task) => ({
    id: task.id,
    planVersionId: task.versionId,
    factoryId: task.factoryId,
    machineId: task.machineId,
    orderId: task.orderId,
    orderNoSnapshot: task.orderNo,
    productNameSnapshot: task.productName,
    moldCodeSnapshot: task.moldCode,
    machineCodeSnapshot: task.machineCode,
    startAt: task.plannedStartAt,
    endAt: task.plannedFinishAt,
    plannedShots: task.plannedQty,
    setupMinutesBefore: Math.round(task.setupHours * 60),
    setupReason: task.riskReasons,
    score: task.recommendationScore ?? null,
    scoreBreakdown: formalTaskScoreBreakdown(task.scoreBreakdown),
    constraintSnapshot: formalTaskConstraints(task.constraintSnapshot),
    source: task.source === 'recommendation'
      ? 'recommended'
      : task.source === 'auto'
        ? 'auto'
        : 'manual',
    locked: task.locked,
    status: version?.status === 'draft' ? 'draft' : 'published',
    provenance: formalProvenance(version?.sourceBatchId ?? ''),
    sequence: task.sequenceNo,
    splitGroupId: task.splitGroupId || null,
    parentTaskId: task.parentTaskId || null,
    revision: task.revision,
    changeReason: task.changeReason ?? null,
    recommendationContextHash: task.recommendationContextHash || null,
  }))
  return {
    mode: 'preview',
    publishable: false,
    id: `formal-view:${workspace.factoryId}`,
    factoryId: workspace.factoryId,
    businessDate: version?.businessDate || fallback.businessDate,
    planBaseAt,
    provenance: formalProvenance(version?.sourceBatchId ?? ''),
    machines,
    molds,
    orders,
    tasks,
    recommendations: {},
    ruleConfig,
    dataQualityFlags: [],
  }
}

const activeSection = ref<HubSection>(hubSectionFromQuery(route.query.section))
const orderWorkspaceMode = ref<OrderWorkspaceMode>('table')
const fallbackDataset = ref(getInjectionPreviewDataset('huaxing'))
const dataset = computed<InjectionPreviewDataset>(() => (
  scheduleStore.mode === 'formal' && scheduleStore.formalWorkspace
    ? toPreviewCompatibleWorkspace(scheduleStore.formalWorkspace, fallbackDataset.value)
    : scheduleStore.previewWorkspace ?? fallbackDataset.value
))
const selectedOrderId = ref('')
const selectedMachineId = ref('')
const previewTasks = ref<InjectionScheduleTask[]>([])
const inspectedTaskId = ref('')
const taskInspectorOpen = ref(false)
const machineEditorOpen = ref(false)
const machineEditorMachineId = ref('')
const machineSavePending = ref(false)
const masterEditorOpen = ref(false)
const masterEditorKind = ref<'mold' | 'order'>('mold')
const masterEditorRecordId = ref('')
const masterSavePending = ref(false)
const selectedMasterMoldId = ref('')
const selectedMasterOrderId = ref('')
const dialog = ref<NoticeDialog | null>(null)
const dialogElement = ref<HTMLElement | null>(null)
const liveMessage = ref('')
const pendingManualAssignment = ref<{ orderId: string; machineId: string } | null>(null)
const pendingManualOperation = ref<PendingManualOperation | null>(null)
const pendingPhase4Preview = ref<PendingPhase4Preview | null>(null)
const manualConfirmationReason = ref('')
const manualConfirmationError = ref('')
const machineSearch = ref('')
const workshopFilter = ref<'all' | 'old' | 'new'>('all')
const masterWorkspaceTab = ref<MasterWorkspaceTab>('machines')
const visibleMachineLimit = ref(18)
const masterOrderPageSize = 120
const masterOrderPage = ref(1)
const riskOnly = ref(false)
const ruleConfigDraft = ref<InjectionScheduleRuleConfigV3 | null>(null)
const ruleChangeReason = ref('')
const ruleDraftError = ref('')
const lastActualRequestKey = ref('')
const lastActualRequestId = ref('')
let dialogReturnFocus: HTMLElement | null = null

const resolvedFactoryId = computed<ProductionFactoryContextId>(() => {
  const queryFactory = Array.isArray(route.query.factory)
    ? route.query.factory[0]
    : route.query.factory
  const candidate = String(queryFactory ?? '')
  if (
    isFactoryContextId(candidate)
    && productionFactoryContextIds.includes(candidate as ProductionFactoryContextId)
  ) {
    return candidate as ProductionFactoryContextId
  }
  return appStore.activeProductionFactory.id as ProductionFactoryContextId
})

const factory = computed(() => (
  factoryContexts.find((entry) => entry.id === resolvedFactoryId.value)
  ?? factoryContexts.find((entry) => entry.id === 'huaxing')!
))
const factoryDisplayName = computed(() => `${factory.value.shortName}厂区`)
const hasPreviewData = computed(() => dataset.value.machines.length > 0)
const isFormalWorkspace = computed(() => scheduleStore.mode === 'formal')
const activeVersion = computed(() => scheduleStore.activeVersion)
const canEditSchedule = computed(() => (
  isFormalWorkspace.value
  && scheduleStore.canMutate
  && authStore.can('injection_schedule:edit', resolvedFactoryId.value)
))
const canWriteScheduleActuals = computed(() => (
  isFormalWorkspace.value
  && Boolean(activeVersion.value)
  && (
    activeVersion.value?.status === 'draft'
    || activeVersion.value?.status === 'published'
  )
  && !scheduleStore.mutationPending
  && authStore.can('injection_schedule:edit', resolvedFactoryId.value)
))
const canPublishSchedule = computed(() => (
  isFormalWorkspace.value
  && scheduleStore.canPublish
  && authStore.can('injection_schedule:publish', resolvedFactoryId.value)
))
const canConfigureSchedule = computed(() => (
  isFormalWorkspace.value
  && authStore.can('injection_schedule:config', resolvedFactoryId.value)
))
const allTasks = computed(() => (
  isFormalWorkspace.value
    ? dataset.value.tasks
    : [...dataset.value.tasks, ...previewTasks.value]
))
const plannedQtyByOrderId = computed(() => {
  const totals = new Map<string, number>()
  for (const task of allTasks.value) {
    totals.set(task.orderId, (totals.get(task.orderId) ?? 0) + task.plannedShots)
  }
  return totals
})
const pendingOrders = computed(() => dataset.value.orders
  .map((order) => ({
    ...order,
    outstandingShots: Math.max(
      0,
      order.outstandingShots - (plannedQtyByOrderId.value.get(order.id) ?? 0),
    ),
  }))
  .filter((order) => (
    order.outstandingShots > 0
    && (!isFormalWorkspace.value || order.status === 'open')
  )))
const timelineEndAt = computed(() => new Date(
  Date.parse(dataset.value.planBaseAt) + 7 * 24 * 60 * 60 * 1000,
).toISOString())
const dateRangeLabel = computed(() => {
  const start = new Date(dataset.value.planBaseAt)
  const end = new Date(Date.parse(dataset.value.planBaseAt) + 6 * 24 * 60 * 60 * 1000)
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  return `${formatter.format(start)} 至 ${formatter.format(end)}`
})
const calendarDays = computed(() => {
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
  })
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(Date.parse(dataset.value.planBaseAt) + index * 24 * 60 * 60 * 1000)
    return index === 0 ? '今天' : formatter.format(date)
  })
})
const overviewPendingOrders = computed(() => {
  if (!riskOnly.value) return pendingOrders.value
  const baseAt = Date.parse(dataset.value.planBaseAt)
  const sevenDaysAfter = baseAt + 7 * 24 * 60 * 60 * 1000
  return pendingOrders.value.filter((order) => {
    const dueAt = order.deliveryDueAt ? Date.parse(order.deliveryDueAt) : Number.NaN
    return order.priority === 'P0'
      || order.priority === 'P1'
      || order.dataQualityFlags.length > 0
      || (!Number.isNaN(dueAt) && dueAt <= sevenDaysAfter)
  })
})
const pendingOrderSummary = computed(() => {
  const baseAt = Date.parse(dataset.value.planBaseAt)
  const sevenDaysAfter = baseAt + 7 * 24 * 60 * 60 * 1000
  return {
    outstandingShots: pendingOrders.value.reduce(
      (sum, order) => sum + order.outstandingShots,
      0,
    ),
    overdue: pendingOrders.value.filter((order) => {
      const dueAt = order.deliveryDueAt ? Date.parse(order.deliveryDueAt) : Number.NaN
      return !Number.isNaN(dueAt) && dueAt < baseAt
    }).length,
    dueWithinSevenDays: pendingOrders.value.filter((order) => {
      const dueAt = order.deliveryDueAt ? Date.parse(order.deliveryDueAt) : Number.NaN
      return !Number.isNaN(dueAt) && dueAt >= baseAt && dueAt <= sevenDaysAfter
    }).length,
  }
})
const selectedOrder = computed(() => (
  pendingOrders.value.find((order) => order.id === selectedOrderId.value)
  ?? dataset.value.orders.find((order) => order.id === selectedOrderId.value)
  ?? null
))
const selectedMold = computed(() => {
  const order = selectedOrder.value
  return order
    ? dataset.value.molds.find((mold) => mold.id === order.moldId) ?? null
    : null
})

const currentTitle = computed(() => {
  if (activeSection.value === 'orders' && orderWorkspaceMode.value === 'match') {
    return isFormalWorkspace.value ? '候选机台推荐与解释' : '注塑排产中枢'
  }
  return undefined
})
const currentDescription = computed(() => {
  if (activeSection.value === 'orders' && orderWorkspaceMode.value === 'match') {
    return isFormalWorkspace.value
      ? 'Phase 3：服务端先过滤硬约束，再按版本化规则解释候选排名'
      : '智能匹配：先过滤硬约束，再解释推荐得分与换模成本'
  }
  return undefined
})

const provenanceLabel = computed(() => (
  isFormalWorkspace.value
    ? activeVersion.value
      ? `${activeVersion.value.status === 'draft' ? '正式草稿' : '已发布'} V${activeVersion.value.versionNo} · revision ${activeVersion.value.revision}`
      : '正式工作区 · 尚无版本'
    : dataset.value.factoryId === 'huaxing'
      ? 'Excel 快照预览 · 非发布计划（正式接口回退）'
      : '当前厂区暂无快照'
))

const kpis = computed(() => {
  const runningMachines = dataset.value.machines.filter((machine) =>
    machine.status === 'running' || machine.status === 'setup').length
  const totalOutstanding = dataset.value.orders.reduce(
    (sum, order) => sum + Math.max(0, order.outstandingShots),
    0,
  )
  const overdueOrders = dataset.value.orders.filter((order) => {
    const dueAt = order.deliveryDueAt ? Date.parse(order.deliveryDueAt) : Number.NaN
    return order.outstandingShots > 0
      && !Number.isNaN(dueAt)
      && dueAt < Date.parse(dataset.value.planBaseAt)
  }).length
  const setupTasks = allTasks.value.filter((task) => task.setupMinutesBefore > 0)
  const colorChangeTasks = setupTasks.filter((task) =>
    task.setupReason.some((reason) => /色|洗机/.test(reason)))
  return [
    {
      id: 'pending',
      label: '待排订单',
      value: String(pendingOrders.value.length),
      helper: '仍有未排数量的订单',
      tone: 'red' as const,
      badge: `欠 ${pendingOrders.value.reduce((sum, order) => sum + order.outstandingShots, 0).toLocaleString('zh-CN')}`,
    },
    {
      id: 'shortage',
      label: '当前总欠数',
      value: totalOutstanding.toLocaleString('zh-CN'),
      helper: '按当前订单主数据实时汇总',
      tone: 'blue' as const,
      badge: isFormalWorkspace.value ? '正式主数据' : '快照口径',
    },
    {
      id: 'risk',
      label: '逾期订单',
      value: `${overdueOrders} 单`,
      helper: '相对当前计划基准时间',
      tone: 'red' as const,
      badge: overdueOrders > 0 ? '需处理' : '无逾期',
    },
    {
      id: 'load',
      label: '机台状态',
      value: `${runningMachines} / ${dataset.value.machines.length}`,
      helper: '运行或换模中的机台',
      tone: 'teal' as const,
      badge: '未来 7 天',
    },
    {
      id: 'changeover',
      label: '预计换模 / 转色',
      value: `${setupTasks.length} / ${colorChangeTasks.length}`,
      helper: '由当前版本相邻任务计算',
      tone: 'amber' as const,
      badge: isFormalWorkspace.value ? '版本实时值' : '预览估算',
    },
  ]
})

const phase4VersionView = computed<Phase4VersionView | null>(() => {
  const version = activeVersion.value
  if (!version || !isFormalWorkspace.value) return null
  return {
    id: version.id,
    versionNo: version.versionNo,
    revision: version.revision,
    status: version.status,
    businessDate: version.businessDate,
  }
})

const phase4OrderOptions = computed<Phase4OrderOption[]>(() => {
  const workspace = scheduleStore.formalWorkspace
  if (!workspace) return []
  return workspace.orders
    .filter((order) => order.status === 'open')
    .map((order) => {
      const projectedFinishAt = scheduleStore.actualProjections
        .filter((projection) => projection.orderId === order.id)
        .map((projection) => projection.plannedFinishAtAfter)
        .filter(Boolean)
        .sort()
        .at(-1)
      const taskFinishAt = workspace.tasks
        .filter((task) => task.orderId === order.id)
        .map((task) => task.plannedFinishAt)
        .filter(Boolean)
        .sort()
        .at(-1)
      return {
        id: order.id,
        orderNo: order.orderNo,
        productName: order.productName,
        outstandingQty: order.outstandingQty,
        producedQty: order.producedQty,
        revision: order.revision,
        priorityCode: order.priorityCode,
        priorityFlag: order.priorityFlag,
        estimatedFinishAt: projectedFinishAt ?? taskFinishAt ?? null,
      }
    })
})

const phase4MachineOptions = computed<Phase4MachineOption[]>(() => (
  (scheduleStore.formalWorkspace?.machines ?? []).map((machine) => ({
    id: machine.id,
    machineCode: machine.machineCode,
    machineName: machine.machineName,
    status: machine.status,
  }))
))

const phase4TaskOptions = computed<Phase4TaskOption[]>(() => (
  (scheduleStore.formalWorkspace?.tasks ?? []).map((task) => ({
    id: task.id,
    orderId: task.orderId,
    orderNo: task.orderNo,
    productName: task.productName,
    machineId: task.machineId,
    machineCode: task.machineCode,
    plannedQty: task.plannedQty,
    plannedFinishAt: task.plannedFinishAt,
    locked: task.locked,
    protected: Boolean(task.protected),
    executionStatus: task.executionStatus ?? 'planned',
  }))
))

const phase4BarrierViews = computed<Phase4BarrierView[]>(() => (
  phase4TaskOptions.value
    .filter((task) => (
      task.locked
      || task.protected
      || /running|completed/i.test(task.executionStatus)
    ))
    .map((task) => {
      const reasons = [
        task.locked ? '人工锁定' : '',
        task.protected ? '服务端保护' : '',
        /running/i.test(task.executionStatus) ? '生产中' : '',
        /completed/i.test(task.executionStatus) ? '已完成' : '',
      ].filter(Boolean)
      return {
        id: task.id,
        label: `${task.machineCode} · ${task.orderNo}`,
        reason: `${reasons.join('、')}，自动草稿和局部重排不会移动`,
      }
    })
))

const phase4SkippedViews = computed<Phase4SkippedView[]>(() => (
  (scheduleStore.phase4Result?.conflicts ?? [])
    .filter((conflict) => conflict.status === 'fail' || conflict.status === 'unknown')
    .map((conflict) => {
      const details = conflict.details
      const label = String(
        details.orderNo
        ?? details.orderId
        ?? conflict.taskId
        ?? conflict.constraintCode,
      )
      return {
        id: conflict.id,
        label,
        status: conflict.status as 'fail' | 'unknown',
        reason: conflict.message,
      }
    })
))

function deliverySlackHours(dueDate: string, finishAt: string) {
  const due = Date.parse(dueDate)
  const finish = Date.parse(finishAt)
  return Number.isFinite(due) && Number.isFinite(finish)
    ? Math.round(((due - finish) / 3_600_000) * 10) / 10
    : null
}

const phase4ImpactViews = computed<Phase4ImpactView[]>(() => {
  const workspace = scheduleStore.formalWorkspace
  if (!workspace) return []
  return scheduleStore.automationProjections.map((projection) => {
    const order = workspace.orders.find((entry) => entry.id === projection.orderId)
    return {
      id: projection.taskId,
      orderNo: order?.orderNo ?? projection.orderId,
      machineCode: projection.machineCode,
      beforeFinishAt: projection.plannedFinishAtBefore,
      afterFinishAt: projection.plannedFinishAtAfter,
      etaShiftMinutes: projection.etaShiftMinutes,
      deliverySlackBeforeHours: order
        ? deliverySlackHours(order.deliveryDueDate, projection.plannedFinishAtBefore)
        : null,
      deliverySlackAfterHours: order
        ? deliverySlackHours(order.deliveryDueDate, projection.plannedFinishAtAfter)
        : null,
      shortageQty: projection.shortageQty,
    }
  })
})

const phase4ActualViews = computed<Phase4ActualView[]>(() => {
  const workspace = scheduleStore.formalWorkspace
  if (!workspace) return []
  const machineById = new Map(workspace.machines.map((machine) => [machine.id, machine]))
  const orderById = new Map(workspace.orders.map((order) => [order.id, order]))
  const taskById = new Map(workspace.tasks.map((task) => [task.id, task]))
  const projectionByTaskId = new Map(
    scheduleStore.actualProjections.map((projection) => [projection.taskId, projection]),
  )
  return [...scheduleStore.shiftActuals]
    .sort((left, right) => (
      `${right.shiftDate}:${right.shift}:${right.createdAt}`
        .localeCompare(`${left.shiftDate}:${left.shift}:${left.createdAt}`)
    ))
    .map((actual) => {
      const order = orderById.get(actual.orderId)
      const task = taskById.get(actual.taskId)
      const projection = projectionByTaskId.get(actual.taskId)
      return {
        id: actual.id,
        orderId: actual.orderId,
        orderNo: order?.orderNo ?? actual.orderId,
        machineCode: machineById.get(actual.machineId)?.machineCode
          ?? task?.machineCode
          ?? actual.machineId,
        shiftDate: actual.shiftDate,
        shiftCode: actual.shift,
        source: actual.source,
        legacyShiftCode: actual.legacyShiftCode,
        actualQty: actual.actualQty,
        cumulativeProducedQty: actual.producedBaselineQty + actual.actualQty,
        outstandingQty: actual.outstandingQtyAfter,
        estimatedFinishAt: projection?.plannedFinishAtAfter
          ?? task?.plannedFinishAt
          ?? null,
        createdByName: actual.createdByName,
        createdAt: actual.createdAt,
        reason: actual.varianceReason,
        revision: actual.revision,
        correctionCount: actual.correctionCount,
        correctedByName: actual.correctedByName,
        correctedAt: actual.correctedAt,
        canCorrect: actual.versionId === workspace.activeVersion?.id,
      }
    })
})

const phase4LastRunView = computed<Phase4RunView | null>(() => {
  const run = scheduleStore.phase4Run
  if (!run) return null
  const impact = run.impact
  return {
    id: run.id,
    runType: run.triggerType === 'auto_draft' ? 'auto_draft' : 'local_replan',
    status: run.status,
    triggerType: run.triggerType,
    reason: run.reason,
    affectedMachineCount: run.affectedMachineIds.length,
    affectedTaskCount: run.affectedTaskIds.length,
    movedTaskCount: impact.movedTaskCount,
    createdAt: run.createdAt,
    createdByName: run.createdByName,
    explanations: [
      `服务端考虑 ${impact.consideredOrderCount} 单，PASS 自动排入 ${impact.scheduledOrderCount} 单`,
      `UNKNOWN 待人工 ${impact.manualReviewOrderCount} 单，FAIL 阻断 ${impact.blockedOrderCount} 单`,
      `ETA 延后 ${impact.etaDelayedTaskCount} 条，累计偏移 ${impact.totalEtaShiftMinutes} 分钟`,
      `任务数 ${impact.beforeTaskCount} → ${impact.afterTaskCount}；本动作不会自动发布`,
    ],
  }
})

const importPreviewView = computed<Phase2ImportPreviewView | null>(() => {
  const batch = scheduleStore.importBatch
  if (!batch) return null
  const summaryNumber = (...keys: string[]) => {
    const key = keys.find((candidate) => Number.isFinite(Number(batch.summary[candidate])))
    return key ? Number(batch.summary[key]) : 0
  }
  const issues = batch.issues.map((issue) => ({
    id: issue.id,
    severity: issue.severity,
    sourceRow: issue.sourceRow,
    fieldName: issue.fieldName || issue.code,
    rawValue: issue.rawValue == null
      ? ''
      : typeof issue.rawValue === 'string'
        ? issue.rawValue
        : JSON.stringify(issue.rawValue),
    message: issue.message,
  }))
  const currentMachines = scheduleStore.formalWorkspace?.machines ?? []
  const machineCount = summaryNumber('machineCount', 'machines')
  const machineCountMatches = currentMachines.length === machineCount
  return {
    batchId: batch.id,
    sourceFileName: batch.sourceFileName,
    sourceSha256: batch.sourceSha256,
    businessDate: batch.businessDate || dataset.value.businessDate,
    status: batch.status,
    revision: batch.revision,
    detectedSheets: batch.detectedSheets,
    machineCount,
    oldMachineCount: summaryNumber('oldMachineCount')
      || (machineCountMatches
        ? currentMachines.filter((machine) => machine.workshop === 'old').length
        : 0),
    newMachineCount: summaryNumber('newMachineCount')
      || (machineCountMatches
        ? currentMachines.filter((machine) => machine.workshop === 'new').length
        : 0),
    orderCount: summaryNumber('orderCount', 'orders'),
    trueUnassignedCount: summaryNumber(
      'trueUnassignedCount',
      'unassignedOrderCount',
      'unscheduledOrderCount',
      'unassigned',
    ),
    preassignedCount: summaryNumber('preassignedPendingCount', 'preassignedCount', 'preassigned'),
    scheduledCount: summaryNumber(
      'assignedOrderCount',
      'scheduledCount',
      'scheduledTaskCount',
      'tasks',
    ),
    issueCount: issues.length,
    blockingIssueCount: issues.filter((issue) =>
      batch.issues.find((source) => source.id === issue.id)?.blocking).length,
    issues,
  }
})

function versionStatusForPanel(
  status: InjectionPlanVersion['status'],
): Phase2VersionView['status'] {
  return status
}

const versionViews = computed<Phase2VersionView[]>(() => (
  (scheduleStore.formalWorkspace?.versions ?? []).map((version) => {
    const numberFromSummary = (...keys: string[]) => {
      const key = keys.find((candidate) => Number.isFinite(Number(version.summary[candidate])))
      return key ? Number(version.summary[key]) : 0
    }
    const summaryConflictKey = ['conflictCount', 'blockingCount', 'conflicts'].find(
      (candidate) => Number.isFinite(Number(version.summary[candidate])),
    )
    const currentValidation = scheduleStore.validation
    const conflictCount = currentValidation?.versionId === version.id
      && currentValidation.versionRevision === version.revision
      ? currentValidation.items.filter((item) => item.status !== 'pass').length
      : summaryConflictKey
        ? Number(version.summary[summaryConflictKey])
        : null
    return {
      id: version.id,
      versionNo: version.versionNo,
      name: version.name,
      status: versionStatusForPanel(version.status),
      revision: version.revision,
      taskCount: numberFromSummary('taskCount', 'tasks'),
      conflictCount,
      updatedAt: version.updatedAt,
      updatedByName: version.updatedBy || version.createdByName,
    }
  })
))

const versionDiffView = computed<Phase2VersionDiffView | null>(() => {
  const diff: InjectionVersionDiff | null = scheduleStore.versionDiff
  const version = activeVersion.value
  if (!diff || !version) return null
  const againstVersion = scheduleStore.formalWorkspace?.versions.find(
    (entry) => entry.id === diff.againstVersionId,
  )
  const numberFromSummary = (...keys: string[]) => {
    const key = keys.find((candidate) => Number.isFinite(Number(diff.summary[candidate])))
    return key ? Number(diff.summary[key]) : 0
  }
  const affected = new Map<string, Phase2VersionDiffView['affectedOrders'][number]>()
  for (const change of diff.items) {
    const labels = {
      added: '新增排程',
      removed: '移出版本',
      moved: '跨机移动',
      rescheduled: '时间或顺序变化',
      quantity_changed: '计划数量变化',
    } as const
    const previous = affected.get(change.orderId)
    const beforeSlack = Number(change.before?.deliverySlackHours)
    const afterSlack = Number(change.after?.deliverySlackHours)
    const deliveryDeltaHours = Number.isFinite(beforeSlack) && Number.isFinite(afterSlack)
      ? afterSlack - beforeSlack
      : null
    affected.set(change.orderId, {
      id: change.orderId,
      orderNo: change.orderNo || change.orderId,
      summary: previous
        ? `${previous.summary}、${labels[change.changeType]}`
        : labels[change.changeType],
      deliveryDeltaHours,
    })
  }
  return {
    baseVersionNo: againstVersion?.versionNo ?? null,
    targetVersionNo: version.versionNo,
    movedOrders: new Set(diff.items
      .filter((change) => change.changeType === 'moved')
      .map((change) => change.orderId)).size,
    reorderedTasks: diff.items.filter((change) => change.changeType === 'rescheduled').length,
    splitOrders: numberFromSummary('splitOrders', 'splitOrderCount'),
    lockedChanges: numberFromSummary('lockedChanges', 'lockChangeCount'),
    changedDeliveryDates: numberFromSummary('changedDeliveryDates', 'deliveryDateChangeCount'),
    addedConflicts: numberFromSummary('addedConflictCount', 'addedConflicts'),
    resolvedConflicts: numberFromSummary('resolvedConflictCount', 'resolvedConflicts'),
    changeoverDelta: numberFromSummary('changeoverMinutesDelta', 'changeoverDelta'),
    affectedOrders: [...affected.values()],
  }
})

const versionConflictViews = computed<Phase2ConflictView[]>(() => (
  (scheduleStore.formalWorkspace?.conflicts ?? [])
    .filter((conflict) => conflict.severity !== 'info')
    .map((conflict) => ({
      id: conflict.id,
      severity: conflict.severity as Phase2ConflictView['severity'],
      blocking: conflict.blocking,
      code: conflict.constraintCode,
      message: conflict.message,
    }))
))

const inspectedTask = computed(() => (
  allTasks.value.find((task) => task.id === inspectedTaskId.value) ?? null
))
const inspectedOrder = computed(() => (
  inspectedTask.value ? orderById.value.get(inspectedTask.value.orderId) ?? null : null
))
const inspectedMachine = computed(() => (
  inspectedTask.value ? machineById.value.get(inspectedTask.value.machineId) ?? null : null
))
const inspectedTaskConflictMessages = computed(() => (
  (scheduleStore.formalWorkspace?.conflicts ?? [])
    .filter((conflict) => conflict.taskId === inspectedTaskId.value)
    .map((conflict) => conflict.message)
))
const machineEditorMachine = computed<InjectionMachineRecord | null>(() => (
  scheduleStore.formalWorkspace?.machines.find(
    (machine) => machine.id === machineEditorMachineId.value,
  ) ?? null
))
const masterEditorMold = computed<InjectionMoldRecord | null>(() => (
  masterEditorKind.value === 'mold'
    ? scheduleStore.formalWorkspace?.molds.find(
        (mold) => mold.id === masterEditorRecordId.value,
      ) ?? null
    : null
))
const masterEditorOrder = computed<InjectionOrderRecord | null>(() => (
  masterEditorKind.value === 'order'
    ? scheduleStore.formalWorkspace?.orders.find(
        (order) => order.id === masterEditorRecordId.value,
      ) ?? null
    : null
))

const orderById = computed(() => new Map([
  ...dataset.value.orders.map((order) => [order.id, order] as const),
  ...pendingOrders.value.map((order) => [order.id, order] as const),
]))
const moldById = computed(() => new Map(dataset.value.molds.map((mold) => [mold.id, mold])))
const machineById = computed(() => new Map(dataset.value.machines.map((machine) => [machine.id, machine])))
const formalOrderById = computed(() => new Map(
  (scheduleStore.formalWorkspace?.orders ?? []).map((order) => [order.id, order]),
))
const masterOrderPageCount = computed(() =>
  Math.max(1, Math.ceil(dataset.value.orders.length / masterOrderPageSize)))
const visibleMasterOrders = computed(() => {
  const safePage = Math.min(masterOrderPage.value, masterOrderPageCount.value)
  const start = (safePage - 1) * masterOrderPageSize
  return dataset.value.orders.slice(start, start + masterOrderPageSize)
})

function toSetupProfile(order: InjectionOrder): InjectionSetupProfile {
  return {
    moldId: order.moldId,
    productName: order.productName,
    materialCode: order.materialCode,
    colorCode: order.colorCode,
    colorRank: order.colorRank,
  }
}

function previousProfileForMachine(machineId: string) {
  const lastTask = allTasks.value
    .filter((task) => task.machineId === machineId)
    .sort((left, right) => right.endAt.localeCompare(left.endAt))[0]
  if (!lastTask) return null
  const previousOrder = orderById.value.get(lastTask.orderId)
  return previousOrder ? toSetupProfile(previousOrder) : null
}

function estimateRecommendation(
  machine: InjectionMachine,
  order: InjectionOrder,
): Recommendation | null {
  const mold = moldById.value.get(order.moldId)
  if (!mold) return null
  const constraints = evaluateInjectionConstraints({
    machine,
    mold,
    order,
    config: dataset.value.ruleConfig,
  })
  const previous = previousProfileForMachine(machine.id)
  const setupCost = calculateInjectionSetupCost({
    previous,
    next: toSetupProfile(order),
    config: dataset.value.ruleConfig.setup,
  })
  const estimatedStartAt = machine.availableFrom ?? dataset.value.planBaseAt
  const targetPerDay = Math.max(order.targetShotsPerDay ?? 2400, 1)
  const estimatedHours = Math.max(2, (order.outstandingShots / targetPerDay) * 24)
  const estimatedEndAt = new Date(
    Date.parse(estimatedStartAt) + (setupCost.totalMinutes + estimatedHours * 60) * 60_000,
  ).toISOString()
  const machineTaskCount = allTasks.value.filter((task) => task.machineId === machine.id).length

  return scoreInjectionRecommendation({
    machine,
    mold,
    order,
    constraints,
    setupCost,
    config: dataset.value.ruleConfig,
    previous,
    referenceAt: dataset.value.planBaseAt,
    estimatedStartAt,
    estimatedEndAt,
    machineLoadRatio: Math.min(1, machineTaskCount / 6),
    exactMatch: machine.machineClass === mold.recommendedMachineClass,
  })
}

const formalRecommendationResponse = computed(() => {
  if (!isFormalWorkspace.value) return null
  const response = scheduleStore.recommendation
  const version = activeVersion.value
  const order = formalOrderById.value.get(selectedOrderId.value)
  if (
    !response
    || !version
    || !order
    || response.factoryId !== dataset.value.factoryId
    || response.versionId !== version.id
    || response.versionRevision !== version.revision
    || response.orderId !== order.id
    || response.orderRevision !== order.revision
  ) return null
  return response
})

const formalConstraintLabels: Record<string, string> = {
  factoryMatch: '厂区与主数据',
  factoryScope: '厂区范围',
  orderStatus: '订单可排状态',
  machineExists: '机台主数据',
  machineStatus: '机台状态',
  machineAvailableAt: '机台可用时间',
  unavailableWindows: '停机与锁定窗口',
  timeWindow: '可用时间窗',
  phase3TimeWindow: '计划时间窗',
  machineClass: '机型 / 锁模力',
  moldMaster: '模具主数据',
  moldDimensions: '模具长宽高',
  moldThickness: '模厚范围',
  openingStroke: '开模行程',
  shotCapacity: '整啤毛重 / 射胶量',
  robotType: '机械手',
  armType: '机械手',
  fixtureType: '夹具 / 吸盘',
  fixtures: '夹具 / 吸盘',
  capabilities: '抽芯与工艺能力',
  material: '材料 / 螺杆限制',
  materialRestrictions: '材料 / 螺杆限制',
  screwCompatibility: '螺杆兼容性',
  transitionData: '换模 / 换色 / 换料资料',
  productionRate: '日产量 / 生产时长',
  deliveryDueDate: '交货完成期',
}

function normalizedRuleCode(code: string) {
  return code.replace(/[_-]([a-z0-9])/g, (_, value: string) => value.toUpperCase())
}

function legacyConstraintCode(code: string): ConstraintResult['code'] {
  const normalized = normalizedRuleCode(code)
  if (/factory|machineExists|orderStatus/i.test(normalized)) return 'factory_match'
  if (/machineStatus|machineAvailable|unavailable|calendar|timeWindow/i.test(normalized)) return 'machine_status'
  if (/thickness/i.test(normalized)) return 'mold_thickness'
  if (/opening|ejector/i.test(normalized)) return 'opening_stroke'
  if (/dimension|machineClass/i.test(normalized)) return 'mold_dimensions'
  if (/shot|weight/i.test(normalized)) return 'shot_capacity'
  if (/robot|arm/i.test(normalized)) return 'arm_type'
  if (/fixture/i.test(normalized)) return 'fixtures'
  if (/material|screw|transition/i.test(normalized)) return 'material_restrictions'
  return 'capabilities'
}

function formalConstraintToView(
  constraint: InjectionMachineRecommendation['hardConstraints'][number],
): ConstraintResult {
  const detailMissingFields = constraint.details.missingFields
    ?? constraint.details.missing_fields
  return {
    code: legacyConstraintCode(constraint.code),
    label: formalConstraintLabels[normalizedRuleCode(constraint.code)] ?? constraint.code,
    status: constraint.status,
    blocking: constraint.blocking,
    autoPublishBlocked: constraint.status !== 'pass',
    reason: constraint.message,
    missingFields: Array.isArray(detailMissingFields)
      ? detailMissingFields.filter((value): value is string => typeof value === 'string')
      : [],
    actual: {
      sourceCode: constraint.code,
      details: constraint.details,
    },
    expected: constraint.details.expected ?? null,
    originalStatus: null,
    override: null,
  }
}

function formalScoreValue(
  candidate: InjectionMachineRecommendation,
  ...codes: string[]
) {
  const normalizedCodes = codes.map(normalizedRuleCode)
  const item = candidate.score?.breakdown.find(
    (entry) => normalizedCodes.includes(normalizedRuleCode(entry.code)),
  )
  return item?.weightedScore ?? 0
}

function formalRecommendationToView(
  candidate: InjectionMachineRecommendation,
): Recommendation {
  const order = selectedOrder.value
  const transition = candidate.score?.transition ?? null
  const previousMaterial = transition?.previousMaterial || null
  const previousColor = transition?.previousColor || null
  const currentMoldCode = selectedMold.value?.moldNo || null
  const targetColor = transition?.targetColor
    || order?.colorCode
    || order?.colorName
    || null
  const sameMoldAsPrevious = Boolean(
    transition?.previousMoldCode
    && currentMoldCode
    && transition.previousMoldCode.trim().toLocaleLowerCase()
      === currentMoldCode.trim().toLocaleLowerCase(),
  )
  const sameMaterial = Boolean(
    previousMaterial && order?.materialCode && previousMaterial === order.materialCode,
  )
  const sameColor = Boolean(
    previousColor
    && targetColor
    && previousColor === targetColor,
  )
  const transitionReasons = [
    transition?.previousMoldCode
      ? sameMoldAsPrevious
        ? `承接相同模具 ${transition.previousMoldCode}`
        : `由模具 ${transition.previousMoldCode} 转入`
      : candidate.status === 'blocked'
        ? '硬约束失败，未计算相邻换型'
        : '当前机台没有相邻前序任务',
    previousColor
      ? `${previousColor} → ${targetColor || '颜色待补'}：${transition?.colorMinutes ?? '待补'} 分钟`
      : '前序颜色缺失，按规则中的未知转换处理',
    previousMaterial
      ? `${previousMaterial} → ${order?.materialCode || '材料待补'}：${transition?.materialMinutes ?? '待补'} 分钟`
      : '前序材料缺失，按规则中的未知转换处理',
  ]
  return {
    machineId: candidate.machineId,
    factoryId: formalRecommendationResponse.value?.factoryId ?? dataset.value.factoryId,
    rank: candidate.rank,
    eligible: candidate.eligible,
    autoPublishAllowed: candidate.autoPublishAllowed,
    score: candidate.score?.total ?? null,
    hardConstraints: candidate.hardConstraints.map(formalConstraintToView),
    scoreBreakdown: {
      dueUrgency: formalScoreValue(candidate, 'dueUrgency', 'dueDate'),
      sameMoldMaterial: formalScoreValue(
        candidate,
        'sameMoldMaterial',
        'sameMoldAndMaterial',
        'sequenceAffinity',
      ),
      setupCost: formalScoreValue(
        candidate,
        'setupCost',
        'changeoverCost',
        'setupEfficiency',
      ),
      colorTransition: formalScoreValue(candidate, 'colorTransition'),
      loadBalance: formalScoreValue(candidate, 'loadBalance'),
      downstreamImpact: formalScoreValue(
        candidate,
        'downstreamImpact',
        'downstreamPriority',
      ),
      exactMatch: formalScoreValue(candidate, 'exactMatch'),
      splitPenalty: formalScoreValue(candidate, 'splitPenalty'),
      specialHandlingPenalty: formalScoreValue(candidate, 'specialHandlingPenalty'),
    },
    setupCost: {
      totalMinutes: transition?.setupMinutesBefore ?? 0,
      moldChangeMinutes: Math.max(
        0,
        (transition?.setupMinutesBefore ?? 0)
          - (transition?.colorMinutes ?? 0)
          - (transition?.materialMinutes ?? 0),
      ),
      materialChangeMinutes: transition?.materialMinutes ?? 0,
      colorChangeMinutes: transition?.colorMinutes ?? 0,
      sameMold: sameMoldAsPrevious,
      sameMaterial,
      colorDirection: sameColor ? 'same' : previousColor ? 'matrix' : 'unknown',
      reasons: transitionReasons,
      dataQualityFlags: candidate.hardConstraints
        .filter((constraint) => constraint.status === 'unknown')
        .map((constraint) => constraint.message),
      colorOverride: null,
    },
    estimatedStartAt: candidate.score?.estimated.productionStartAt
      ?? candidate.score?.estimated.slotStartAt
      ?? null,
    estimatedEndAt: candidate.score?.estimated.finishAt ?? null,
    deliverySlackHours: candidate.score?.estimated.deliverySlackHours ?? null,
    reasons: [
      ...transitionReasons,
      ...(candidate.score?.breakdown.map((entry) => entry.explanation) ?? []),
    ],
  }
}

const formalCandidateByMachineId = computed(() => new Map(
  (formalRecommendationResponse.value?.candidates ?? []).map(
    (candidate) => [candidate.machineId, candidate],
  ),
))

const selectedRecommendations = computed(() => {
  const order = selectedOrder.value
  if (!order) return []
  if (isFormalWorkspace.value) {
    return (formalRecommendationResponse.value?.candidates ?? []).map(
      formalRecommendationToView,
    )
  }
  const provided = 'recommendations' in dataset.value
    ? dataset.value.recommendations[order.id] ?? []
    : []
  const recommendations = provided.length > 0
    ? provided
    : dataset.value.machines.map((machine) => estimateRecommendation(machine, order)).filter(
      (recommendation): recommendation is Recommendation => Boolean(recommendation),
    )

  return recommendations
    .slice()
    .sort((left, right) => {
      if (left.eligible !== right.eligible) return left.eligible ? -1 : 1
      return (right.score ?? -1) - (left.score ?? -1)
    })
    .map((recommendation, index) => ({ ...recommendation, rank: index + 1 }))
})

const candidateRows = computed(() => {
  if (isFormalWorkspace.value) {
    const grouped = {
      eligible: selectedRecommendations.value.filter(
        (recommendation) => candidateDisplayState(recommendation) === 'eligible',
      ),
      manual: selectedRecommendations.value.filter(
        (recommendation) => candidateDisplayState(recommendation) === 'manual',
      ),
      blocked: selectedRecommendations.value.filter(
        (recommendation) => candidateDisplayState(recommendation) === 'blocked',
      ),
    }
    return [
      ...grouped.eligible.slice(0, 8),
      ...grouped.manual.slice(0, 6),
      ...grouped.blocked.slice(0, 6),
    ]
  }
  const eligible = selectedRecommendations.value.filter((recommendation) => recommendation.eligible)
  const blocked = selectedRecommendations.value.filter((recommendation) => !recommendation.eligible)
  const selectedEligible = eligible.slice(0, 2)
  return [
    ...selectedEligible,
    ...blocked.slice(0, Math.max(0, 4 - selectedEligible.length)),
  ]
})

const selectedCandidate = computed(() => (
  selectedRecommendations.value.find((recommendation) => recommendation.machineId === selectedMachineId.value)
  ?? selectedRecommendations.value[0]
  ?? null
))
const selectedCandidateMachine = computed(() => (
  selectedCandidate.value
    ? machineById.value.get(selectedCandidate.value.machineId) ?? null
    : null
))
const selectedCandidateAllowsManualPreview = computed(() => {
  const recommendation = selectedCandidate.value
  const formalCandidate = recommendation
    ? formalCandidateByMachineId.value.get(recommendation.machineId)
    : null
  if (formalCandidate) {
    if (!activeAllowsUnknownManualConfirmation.value) return false
    return formalCandidate.status === 'manual_review'
      && formalCandidate.requiresManualConfirmation
  }
  if (!recommendation || recommendation.eligible) return false
  if (recommendation.hardConstraints.some((constraint) => constraint.status === 'fail')) {
    return false
  }
  const blocking = recommendation.hardConstraints.filter((constraint) => constraint.blocking)
  return blocking.length > 0 && blocking.every((constraint) => constraint.status === 'unknown')
})

function candidateDisplayState(recommendation: Recommendation) {
  const formalCandidate = formalCandidateByMachineId.value.get(recommendation.machineId)
  if (formalCandidate?.status === 'blocked') return 'blocked' as const
  if (formalCandidate?.status === 'manual_review') return 'manual' as const
  if (formalCandidate?.status === 'eligible') return 'eligible' as const
  if (recommendation.hardConstraints.some((constraint) => constraint.status === 'fail')) {
    return 'blocked' as const
  }
  if (recommendation.hardConstraints.some((constraint) => constraint.status === 'unknown')) {
    return 'manual' as const
  }
  return recommendation.eligible ? 'eligible' as const : 'blocked' as const
}

function candidateStatusLabel(recommendation: Recommendation) {
  const state = candidateDisplayState(recommendation)
  if (state === 'manual') return '需确认'
  return state === 'eligible' ? '可排' : '不可排'
}

function candidateScoreLabel(recommendation: Recommendation) {
  if (recommendation.score == null) return '未评分'
  const prefix = candidateDisplayState(recommendation) === 'manual' ? '参考分' : '综合分'
  return `${prefix} ${Math.round(recommendation.score)}`
}

const selectedFormalCandidate = computed(() => (
  selectedCandidate.value
    ? formalCandidateByMachineId.value.get(selectedCandidate.value.machineId) ?? null
    : null
))

const recommendationBasisLabel = computed(() => {
  const response = formalRecommendationResponse.value
  if (!response) return ''
  const ruleRevision = response.ruleConfigRevision > 0
    ? `规则 revision ${response.ruleConfigRevision}`
    : '历史来源 revision 未知'
  return `版本 revision ${response.versionRevision} · 订单 revision ${response.orderRevision} · ${ruleRevision}`
})

const candidateStateByMachine = computed<Record<string, MachineCandidateState>>(() => {
  const states: Record<string, MachineCandidateState> = {}
  for (const recommendation of selectedRecommendations.value) {
    const firstBlocker = recommendation.hardConstraints.find((constraint) =>
      constraint.status === 'fail' || constraint.status === 'unknown')
    const state = candidateDisplayState(recommendation)
    states[recommendation.machineId] = {
      state: state === 'eligible'
        ? 'recommended'
        : state === 'manual' ? 'manual' : 'blocked',
      message: state === 'eligible'
        ? isFormalWorkspace.value
          ? `候选 ${recommendation.rank ?? '—'} · ${candidateScoreLabel(recommendation)}`
          : `可预排 · 综合 ${Math.round(recommendation.score ?? 0)} 分`
        : state === 'manual'
          ? `资料待确认 · ${firstBlocker?.reason ?? '不能自动推荐'}`
          : firstBlocker?.reason ?? '硬约束未通过',
    }
  }
  return states
})

const filteredMachines = computed(() => {
  const query = machineSearch.value.trim().toLocaleLowerCase('zh-CN')
  return dataset.value.machines.filter((machine) => {
    if (workshopFilter.value !== 'all' && machine.workshop !== workshopFilter.value) return false
    if (!query) return true
    return [
      machine.machineNo,
      machine.machineClass,
      machine.speedType ?? '',
      machine.dataQualityFlags.join(' '),
    ].some((value) => value.toLocaleLowerCase('zh-CN').includes(query))
  })
})
const visibleMasterMachines = computed(() => filteredMachines.value.slice(0, visibleMachineLimit.value))
const selectedMachine = computed(() => (
  filteredMachines.value.find((machine) => machine.id === selectedMachineId.value)
  ?? visibleMasterMachines.value[0]
  ?? null
))
const workshopCounts = computed(() => ({
  old: dataset.value.machines.filter((machine) => machine.workshop === 'old').length,
  new: dataset.value.machines.filter((machine) => machine.workshop === 'new').length,
}))
const selectedMachineCompleteness = computed(() => (
  selectedMachine.value ? Math.round(selectedMachine.value.dataCompleteness * 100) : 0
))

const missingMachineFields = computed(() => {
  const machine = selectedMachine.value
  if (!machine) return []
  const entries = [
    { field: '最大射胶量（g）', value: machine.maxShotWeightG, use: '用于整啤毛重硬约束' },
    {
      field: '拉杆内距 L×W（mm）',
      value: machine.tieBarWidthMm && machine.tieBarHeightMm
        ? `${machine.tieBarWidthMm} × ${machine.tieBarHeightMm}`
        : null,
      use: '用于模具长宽校验',
    },
    {
      field: '最小 / 最大模厚（mm）',
      value: machine.minMoldThicknessMm && machine.maxMoldThicknessMm
        ? `${machine.minMoldThicknessMm} / ${machine.maxMoldThicknessMm}`
        : null,
      use: '用于模高校验',
    },
    { field: '最大开模行程（mm）', value: machine.maxOpeningStrokeMm, use: '用于取件 / 夹具空间' },
    {
      field: '夹具 / 吸盘能力',
      value: machine.supportedFixtures?.length ? machine.supportedFixtures.join('、') : null,
      use: '用于夹具、吸盘、气剪兼容校验',
    },
    {
      field: '工艺能力',
      value: machine.capabilities?.length ? machine.capabilities.join('、') : null,
      use: '用于抽芯、双色、电热等能力校验',
    },
    {
      field: '材料 / 螺杆限制',
      value: machine.materialRules != null && machine.screwType != null
        ? `${machine.screwType} · ${machine.materialRules.length} 条规则`
        : null,
      use: '用于 PVC、材料和螺杆兼容校验',
    },
  ]
  return entries
})

const ruleWeightRows = computed(() => {
  const weights = dataset.value.ruleConfig.scoring.weights
  const formalWeights = ruleConfigDraft.value?.config.scoringWeights
    ?? scheduleStore.phase3RuleConfig?.config.scoringWeights
    ?? {}
  const rows: Array<{
    id: keyof InjectionScoringWeights
    configKey: string
    label: string
    value: number
    hint: string
  }> = [
    { id: 'dueUrgency', configKey: 'dueDate', label: '货期紧迫度', value: weights.dueUrgency, hint: '交期差越小越优先' },
    { id: 'sameMoldMaterial', configKey: 'sequenceAffinity', label: '同模 / 同料连排', value: weights.sameMoldMaterial, hint: '减少换模调机' },
    { id: 'colorTransition', configKey: 'colorTransition', label: '浅色 → 深色', value: weights.colorTransition, hint: '降低洗机损耗' },
    { id: 'setupCost', configKey: 'setupEfficiency', label: '换模 / 转色成本', value: weights.setupCost, hint: '取自厂区矩阵' },
    { id: 'loadBalance', configKey: 'loadBalance', label: '机台负载平衡', value: weights.loadBalance, hint: '避免少数机台过载' },
    { id: 'downstreamImpact', configKey: 'downstreamPriority', label: '下游交付影响', value: weights.downstreamImpact, hint: '考虑后续装配交付' },
    { id: 'exactMatch', configKey: 'exactMatch', label: '精确机型匹配', value: weights.exactMatch, hint: '优先推荐安数精确匹配' },
    { id: 'splitPenalty', configKey: 'splitPenalty', label: '拆单惩罚', value: weights.splitPenalty, hint: '同订单尽量不拆散' },
    { id: 'specialHandlingPenalty', configKey: 'specialHandlingPenalty', label: '特殊处理惩罚', value: weights.specialHandlingPenalty, hint: '人工例外进入审计' },
  ]
  return rows.map((row) => ({
    ...row,
    value: isFormalWorkspace.value
      ? Number(formalWeights[row.configKey] ?? row.value)
      : row.value,
  }))
})

const ruleMatrixEditors = computed(() => {
  const config = ruleConfigDraft.value?.config
  if (!config) return []
  return [
    {
      id: 'color' as const,
      title: '颜色转换矩阵',
      rows: config.colorTransitionMatrix,
    },
    {
      id: 'material' as const,
      title: '材料转换矩阵',
      rows: config.materialTransitionMatrix,
    },
  ]
})

const selectedDimensionUsage = computed(() => {
  const machine = selectedCandidateMachine.value
  const mold = selectedMold.value
  if (
    !machine
    || !mold
    || mold.lengthMm == null
    || mold.widthMm == null
    || machine.tieBarWidthMm == null
    || machine.tieBarHeightMm == null
  ) return null
  const normalUsage = Math.max(
    mold.lengthMm / machine.tieBarWidthMm,
    mold.widthMm / machine.tieBarHeightMm,
  )
  const rotatedUsage = Math.max(
    mold.widthMm / machine.tieBarWidthMm,
    mold.lengthMm / machine.tieBarHeightMm,
  )
  return Math.min(normalUsage, rotatedUsage)
})

const selectedShotUsage = computed(() => {
  const machine = selectedCandidateMachine.value
  const mold = selectedMold.value
  const grossShotWeightG = selectedOrder.value?.grossShotWeightG ?? mold?.grossShotWeightG
  if (!machine || grossShotWeightG == null || machine.maxShotWeightG == null) return null
  const safeCapacity = machine.maxShotWeightG * activeShotSafetyFactor.value
  return safeCapacity > 0 ? grossShotWeightG / safeCapacity : null
})

const activeShotSafetyFactor = computed(() => {
  const snapshot = activeVersion.value?.rulesSnapshot
  const snapshotValue = Number(snapshot?.shotSafetyFactor ?? snapshot?.shot_safety_factor)
  if (
    isFormalWorkspace.value
    && Number.isFinite(snapshotValue)
    && snapshotValue > 0
    && snapshotValue <= 1
  ) {
    return snapshotValue
  }
  return dataset.value.ruleConfig.shotSafetyFactor
})

const activeAllowsUnknownManualConfirmation = computed(() => {
  if (!isFormalWorkspace.value) return true
  const snapshot = activeVersion.value?.rulesSnapshot
  const snapshotValue = snapshot?.allowMissingDataInDraftWithManualConfirmation
    ?? snapshot?.allow_missing_data_in_draft_with_manual_confirmation
  if (typeof snapshotValue === 'boolean') return snapshotValue
  return true
})

const scoreRows = computed(() => {
  if (selectedFormalCandidate.value?.score) {
    return selectedFormalCandidate.value.score.breakdown.map((item, index) => ({
      code: item.code,
      label: item.label,
      value: item.weightedScore,
      rawScore: item.rawScore,
      max: Math.max(Math.abs(item.weight), Math.abs(item.weightedScore), 1),
      tone: ['red', 'teal', 'amber', 'blue', 'violet', 'green'][index % 6],
      explanation: item.explanation,
      weight: item.weight,
    }))
  }
  const breakdown = selectedCandidate.value?.scoreBreakdown
  if (!breakdown) return []
  const weights = dataset.value.ruleConfig.scoring.weights
  return [
    { code: 'dueUrgency', label: '货期紧迫度', value: breakdown.dueUrgency, rawScore: 0, max: weights.dueUrgency, tone: 'red', explanation: '', weight: weights.dueUrgency },
    { code: 'sameMoldMaterial', label: '同模 / 同料连排', value: breakdown.sameMoldMaterial, rawScore: 0, max: weights.sameMoldMaterial, tone: 'teal', explanation: '', weight: weights.sameMoldMaterial },
    { code: 'colorTransition', label: '浅色 → 深色顺序', value: breakdown.colorTransition, rawScore: 0, max: weights.colorTransition, tone: 'blue', explanation: '', weight: weights.colorTransition },
    { code: 'loadBalance', label: '机台负载平衡', value: breakdown.loadBalance, rawScore: 0, max: weights.loadBalance, tone: 'violet', explanation: '', weight: weights.loadBalance },
    { code: 'setupCost', label: '换模 / 转色成本', value: breakdown.setupCost, rawScore: 0, max: weights.setupCost, tone: 'amber', explanation: '', weight: weights.setupCost },
    { code: 'downstreamImpact', label: '下游交付影响', value: breakdown.downstreamImpact, rawScore: 0, max: weights.downstreamImpact, tone: 'green', explanation: '', weight: weights.downstreamImpact },
  ]
})

const selectedConstraintRows = computed(() => {
  const rows = selectedCandidate.value?.hardConstraints ?? []
  const statusPriority: Record<ConstraintResult['status'], number> = {
    fail: 0,
    unknown: 1,
    override: 2,
    pass: 3,
  }
  const codePriority: Record<ConstraintResult['code'], number> = {
    factory_match: 0,
    machine_status: 1,
    mold_dimensions: 2,
    shot_capacity: 3,
    arm_type: 4,
    fixtures: 5,
    capabilities: 6,
    material_restrictions: 7,
    mold_thickness: 8,
    opening_stroke: 9,
  }
  return rows
    .slice()
    .sort((left, right) => (
      statusPriority[left.status] - statusPriority[right.status]
      || codePriority[left.code] - codePriority[right.code]
    ))
    .slice(0, isFormalWorkspace.value ? rows.length : 7)
})

async function loadFactory(factoryId: ProductionFactoryContextId) {
  fallbackDataset.value = getInjectionPreviewDataset(factoryId)
  previewTasks.value = []
  ruleConfigDraft.value = null
  ruleChangeReason.value = ''
  ruleDraftError.value = ''
  pendingPhase4Preview.value = null
  lastActualRequestKey.value = ''
  lastActualRequestId.value = ''
  inspectedTaskId.value = ''
  taskInspectorOpen.value = false
  await scheduleStore.loadWorkspace(factoryId, { allowPreviewFallback: true })
  if (resolvedFactoryId.value !== factoryId) return
  selectedOrderId.value = pendingOrders.value[0]?.id
    ?? dataset.value.orders.find(
      (order) => order.outstandingShots > 0 && order.status !== 'canceled',
    )?.id
    ?? dataset.value.orders[0]?.id
    ?? ''
  selectedMachineId.value = dataset.value.machines.find((machine) => machine.machineNo === '旧2')?.id
    ?? dataset.value.machines[0]?.id
    ?? ''
  orderWorkspaceMode.value = 'table'
  visibleMachineLimit.value = 18
  masterOrderPage.value = 1
  if (isFormalWorkspace.value) {
    liveMessage.value = activeVersion.value
      ? `已载入${factory.value.shortName}正式计划 V${activeVersion.value.versionNo}`
      : `已载入${factory.value.shortName}正式排产工作区，尚无计划版本`
    if (activeSection.value === 'operations' && canWriteScheduleActuals.value) {
      void reloadPhase4Actuals()
    }
  } else {
    liveMessage.value = dataset.value.factoryId === 'huaxing'
      ? '正式接口暂不可用，已明确回退到华兴 Excel 快照预览'
      : `${factory.value.shortName}当前没有注塑排产快照`
  }
}

function selectSection(section: HubSection) {
  activeSection.value = section
  if (section !== 'orders') {
    orderWorkspaceMode.value = 'table'
  }
  if (section === 'masters') {
    masterWorkspaceTab.value = 'machines'
    selectedMachineId.value = dataset.value.machines.find((machine) => machine.machineNo === '旧2')?.id
      ?? dataset.value.machines[0]?.id
      ?? ''
  } else if (section === 'rules') {
    masterWorkspaceTab.value = 'weights'
    void loadFormalRuleConfig()
  } else if (section === 'operations') {
    if (canWriteScheduleActuals.value) {
      void reloadPhase4Actuals()
    } else {
      liveMessage.value = 'Phase 4 写入只对本厂区有编辑权限的正式草稿或已发布计划开放'
    }
  }
}

function selectMasterWorkspaceTab(tab: MasterWorkspaceTab) {
  masterWorkspaceTab.value = tab
  if (tab === 'molds' && !dataset.value.molds.some(
    (entry) => entry.id === selectedMasterMoldId.value,
  )) {
    selectedMasterMoldId.value = dataset.value.molds[0]?.id ?? ''
  }
  if (tab === 'orders' && !dataset.value.orders.some(
    (entry) => entry.id === selectedMasterOrderId.value,
  )) {
    selectedMasterOrderId.value = dataset.value.orders[0]?.id ?? ''
  }
  if (tab === 'orders') masterOrderPage.value = 1
  if (tab === 'transitions' || tab === 'calendar' || tab === 'weights') {
    void loadFormalRuleConfig()
  }
  liveMessage.value = `已切换到${masterWorkspaceEntries.find((entry) => entry.id === tab)?.label ?? tab}`
}

const masterWorkspaceEntries: Array<{ id: MasterWorkspaceTab; label: string }> = [
  { id: 'machines', label: '机台主数据' },
  { id: 'molds', label: '模具主数据' },
  { id: 'orders', label: '订单主数据' },
  { id: 'transitions', label: '颜色/材料矩阵' },
  { id: 'calendar', label: '班次与停机日历' },
  { id: 'weights', label: '评分权重' },
  { id: 'import', label: '导入映射' },
]

function explainMasterAction(action: 'import' | 'create') {
  if (isFormalWorkspace.value) {
    if (action === 'import') {
      activeSection.value = 'masters'
      masterWorkspaceTab.value = 'import'
      liveMessage.value = '已打开正式 Excel 两阶段导入'
      return
    }
    if (!canConfigureSchedule.value) {
      dialog.value = {
        tone: 'danger',
        title: '没有主数据配置权限',
        message: '当前账号不能新增或修改本厂区机台主数据。',
        details: ['需要 injection_schedule:config 权限'],
      }
      return
    }
    machineEditorMachineId.value = ''
    machineEditorOpen.value = true
    return
  }
  dialog.value = {
    tone: 'info',
    title: action === 'import' ? 'Excel 导入不可用' : '新增机台不可用',
    message: '当前是正式接口不可用时的明确回退预览，不会写入主数据。',
    details: action === 'import'
      ? [
          '当前快照来自《华兴啤机日排版表1.xlsx》',
          '接口恢复后可执行预览、错误清单和确认合并',
          '回退模式不会覆盖机台、订单或版本数据',
        ]
      : [
          '新增机台只允许写入正式厂区工作区',
          '射胶量、空间、模厚、行程、夹具和材料限制均为必填校验范围',
          '当前页面不保存任何新增记录',
        ],
  }
}

function editSelectedMachine() {
  if (!isFormalWorkspace.value || !selectedMachine.value) return
  if (!canConfigureSchedule.value) {
    explainMasterAction('create')
    return
  }
  machineEditorMachineId.value = selectedMachine.value.id
  machineEditorOpen.value = true
}

async function saveMachineMaster(payload: {
  machineId: string | null
  expectedRevision: number | null
  input: InjectionMachineCreateInput
}) {
  machineSavePending.value = true
  try {
    const { machineCode: _immutableMachineCode, ...updateInput } = payload.input
    void _immutableMachineCode
    const record = payload.machineId && payload.expectedRevision != null
      ? await scheduleStore.updateMachine(
          payload.machineId,
          payload.expectedRevision,
          updateInput,
        )
      : await scheduleStore.createMachine(payload.input)
    selectedMachineId.value = record.id
    machineEditorOpen.value = false
    liveMessage.value = `${record.machineCode}主数据已保存，revision ${record.revision}`
  } catch {
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: '机台主数据未保存',
      message: scheduleStore.errorMessage || '服务端拒绝本次主数据更新。',
      details: scheduleStore.revisionConflict
        ? ['另一位用户已更新该机台，请重新载入后再编辑']
        : ['没有修改其他机台或排产版本'],
    }
  } finally {
    machineSavePending.value = false
  }
}

function openMasterEditor(kind: 'mold' | 'order', recordId = '') {
  if (!isFormalWorkspace.value || !canConfigureSchedule.value) {
    dialog.value = {
      tone: 'danger',
      title: '没有主数据配置权限',
      message: '当前账号不能新增或修改本厂区主数据。',
      details: ['需要 injection_schedule:config 权限'],
    }
    return
  }
  masterEditorKind.value = kind
  masterEditorRecordId.value = recordId
  masterEditorOpen.value = true
}

async function saveMoldMaster(payload: {
  moldId: string | null
  expectedRevision: number | null
  input: InjectionMoldCreateInput
}) {
  masterSavePending.value = true
  try {
    const record = payload.moldId && payload.expectedRevision != null
      ? await scheduleStore.updateMold(
          payload.moldId,
          payload.expectedRevision,
          payload.input,
        )
      : await scheduleStore.createMold(payload.input)
    selectedMasterMoldId.value = record.id
    masterEditorOpen.value = false
    liveMessage.value = `${record.moldCode}模具主数据已保存，revision ${record.revision}`
  } catch {
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: '模具主数据未保存',
      message: scheduleStore.errorMessage || '服务端拒绝本次模具主数据更新。',
      details: scheduleStore.revisionConflict
        ? ['另一位用户已更新该模具，请重新载入后再编辑']
        : ['没有修改其他模具或排产版本'],
    }
  } finally {
    masterSavePending.value = false
  }
}

async function saveOrderMaster(payload: {
  orderId: string | null
  expectedRevision: number | null
  input: InjectionOrderCreateInput
}) {
  masterSavePending.value = true
  try {
    const record = payload.orderId && payload.expectedRevision != null
      ? await scheduleStore.updateOrder(
          payload.orderId,
          payload.expectedRevision,
          payload.input,
        )
      : await scheduleStore.createOrder(payload.input)
    selectedMasterOrderId.value = record.id
    const orderIndex = scheduleStore.formalWorkspace?.orders.findIndex(
      (entry) => entry.id === record.id,
    ) ?? -1
    if (orderIndex >= 0) {
      masterOrderPage.value = Math.floor(orderIndex / masterOrderPageSize) + 1
    }
    masterEditorOpen.value = false
    liveMessage.value = `${record.orderNo}订单主数据已保存，revision ${record.revision}`
  } catch {
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: '订单主数据未保存',
      message: scheduleStore.errorMessage || '服务端拒绝本次订单主数据更新。',
      details: scheduleStore.revisionConflict
        ? ['另一位用户已更新该订单，请重新载入后再编辑']
        : ['没有修改其他订单或排产版本'],
    }
  } finally {
    masterSavePending.value = false
  }
}

function cloneRuleConfig(
  config: InjectionScheduleRuleConfigV3,
): InjectionScheduleRuleConfigV3 {
  return JSON.parse(JSON.stringify(config)) as InjectionScheduleRuleConfigV3
}

async function loadFormalRuleConfig(force = false) {
  if (!isFormalWorkspace.value || scheduleStore.ruleConfigLoading) return
  if (!force && ruleConfigDraft.value) return
  if (!force && scheduleStore.phase3RuleConfig) {
    ruleConfigDraft.value = cloneRuleConfig(scheduleStore.phase3RuleConfig)
    return
  }
  try {
    const config = await scheduleStore.loadRuleConfig()
    if (!config) return
    ruleConfigDraft.value = cloneRuleConfig(config)
    ruleDraftError.value = ''
  } catch {
    ruleDraftError.value = scheduleStore.errorMessage || '规则配置读取失败'
  }
}

function matrixRows(
  kind: 'color' | 'material',
): InjectionTransitionMatrixEntry[] {
  const config = ruleConfigDraft.value?.config
  if (!config) return []
  return kind === 'color'
    ? config.colorTransitionMatrix
    : config.materialTransitionMatrix
}

function addTransitionRule(kind: 'color' | 'material') {
  matrixRows(kind).push({ fromCode: '', toCode: '', minutes: 0 })
}

function removeTransitionRule(kind: 'color' | 'material', index: number) {
  matrixRows(kind).splice(index, 1)
}

function addSetupRule() {
  ruleConfigDraft.value?.config.setupMinutes.push({
    machineClass: '',
    sameMoldMinutes: 0,
    moldChangeMinutes: 60,
  })
}

function removeSetupRule(index: number) {
  ruleConfigDraft.value?.config.setupMinutes.splice(index, 1)
}

function addUnavailableWindow() {
  ruleConfigDraft.value?.config.unavailableWindows.push({
    scope: 'factory',
    machineId: '',
    startAt: '',
    endAt: '',
    reason: '',
  })
}

function removeUnavailableWindow(index: number) {
  ruleConfigDraft.value?.config.unavailableWindows.splice(index, 1)
}

function validateRuleDraft(
  draft: InjectionScheduleRuleConfigV3,
  reason: string,
) {
  if (reason.trim().length < 4) return '变更原因至少填写 4 个字符'
  if (
    !Number.isFinite(draft.config.shotSafetyFactor)
    || draft.config.shotSafetyFactor <= 0
    || draft.config.shotSafetyFactor > 1
  ) return '射胶安全系数必须大于 0 且不超过 1'
  if (
    !draft.config.availabilityCalendarVerifiedThrough.trim()
    || Number.isNaN(Date.parse(draft.config.availabilityCalendarVerifiedThrough))
  ) {
    return '请填写有效的日历核验截止时间，避免所有候选都进入人工复核'
  }
  for (const [index, window] of draft.config.unavailableWindows.entries()) {
    const startAt = Date.parse(window.startAt)
    const endAt = Date.parse(window.endAt)
    if (Number.isNaN(startAt) || Number.isNaN(endAt) || endAt <= startAt) {
      return `停机窗口第 ${index + 1} 行的开始、结束时间无效`
    }
    if (!window.reason.trim()) return `停机窗口第 ${index + 1} 行必须填写原因`
    if (window.scope === 'machine' && !window.machineId.trim()) {
      return `停机窗口第 ${index + 1} 行必须选择机台`
    }
    if (window.scope === 'factory') window.machineId = ''
  }
  for (const [label, rows] of [
    ['颜色转换矩阵', draft.config.colorTransitionMatrix],
    ['材料转换矩阵', draft.config.materialTransitionMatrix],
  ] as const) {
    if (rows.length === 0) return `${label}至少保留一条规则`
    const keys = rows.map((row) =>
      `${row.fromCode.trim().toLocaleLowerCase()}→${row.toCode.trim().toLocaleLowerCase()}`)
    if (rows.some((row) => !row.fromCode.trim() || !row.toCode.trim())) {
      return `${label}存在空的来源或目标代码`
    }
    if (rows.some((row) => !Number.isFinite(row.minutes) || row.minutes < 0)) {
      return `${label}分钟必须是非负数`
    }
    if (new Set(keys).size !== keys.length) return `${label}不能包含重复方向`
    if (!keys.includes('*→*')) return `${label}必须保留 */* 兜底规则`
  }
  const setupKeys = draft.config.setupMinutes.map((row) =>
    row.machineClass.trim().toLocaleLowerCase())
  if (draft.config.setupMinutes.some((row) => (
    !row.machineClass.trim()
    || !Number.isFinite(row.sameMoldMinutes)
    || row.sameMoldMinutes < 0
    || !Number.isFinite(row.moldChangeMinutes)
    || row.moldChangeMinutes < 0
  ))) return '换模时间存在空机型或无效分钟'
  if (new Set(setupKeys).size !== setupKeys.length) return '换模时间不能包含重复机型'
  if (!setupKeys.includes('*')) return '换模时间必须保留 * 兜底规则'
  for (const [key, value] of Object.entries(draft.config.scoringWeights)) {
    if (!Number.isFinite(value) || value < 0 || value > 100) {
      return `${key} 权重必须在 0 到 100 之间`
    }
  }
  return ''
}

async function saveFormalRuleConfig() {
  const draft = ruleConfigDraft.value
  if (!draft || !isFormalWorkspace.value) return
  if (!canConfigureSchedule.value) {
    dialog.value = {
      tone: 'danger',
      title: '没有规则配置权限',
      message: '当前账号可以查看规则，但不能修改本厂区策略。',
      details: ['需要 injection_schedule:config 权限'],
    }
    return
  }
  const error = validateRuleDraft(draft, ruleChangeReason.value)
  if (error) {
    ruleDraftError.value = error
    return
  }
  try {
    const input: InjectionScheduleRuleConfigUpdateInput = {
      expectedRevision: draft.revision,
      reason: ruleChangeReason.value.trim(),
      config: JSON.parse(JSON.stringify(draft.config)) as InjectionScheduleRuleConfigUpdateInput['config'],
    }
    const saved = await scheduleStore.updateRuleConfig(input)
    if (!saved) return
    ruleConfigDraft.value = cloneRuleConfig(saved)
    ruleChangeReason.value = ''
    ruleDraftError.value = ''
    liveMessage.value = `规则配置已保存为 revision ${saved.revision}`
    dialog.value = {
      tone: 'success',
      title: '厂区规则已保存',
      message: `规则配置已更新为 revision ${saved.revision}。`,
      details: [
        '本次变更已记录操作人、原因和 revision',
        '已打开的推荐结果已失效，需要重新计算',
        '当前计划版本继续使用自己的规则快照；新规则用于后续草稿或新版本',
      ],
    }
  } catch {
    ruleDraftError.value = scheduleStore.errorMessage || '规则配置保存失败'
  }
}

function resetRulePreview() {
  if (isFormalWorkspace.value) {
    if (scheduleStore.phase3RuleConfig) {
      ruleConfigDraft.value = cloneRuleConfig(scheduleStore.phase3RuleConfig)
      ruleChangeReason.value = ''
      ruleDraftError.value = ''
      liveMessage.value = '已恢复为服务端当前规则，尚未保存任何更改'
    }
    return
  }
  const source = getInjectionPreviewDataset(resolvedFactoryId.value)
  Object.assign(dataset.value.ruleConfig.scoring.weights, source.ruleConfig.scoring.weights)
  liveMessage.value = '评分权重已恢复为厂区首期建议值（仅本地预览）'
}

function requirePhase4EditableDraft() {
  const version = activeVersion.value
  if (
    !isFormalWorkspace.value
    || !version
    || version.status !== 'draft'
    || !canEditSchedule.value
  ) {
    dialog.value = {
      tone: 'warning',
      title: 'Phase 4 写入未开放',
      message: '自动草稿、局部重排和实绩回写只允许在本厂区可编辑正式草稿中执行。',
      details: [
        '需要 injection_schedule:edit 权限',
        '回退预览、已发布版本和跨厂只读视图不会调用 Phase 4 写入接口',
      ],
    }
    return null
  }
  return version
}

function requirePhase4ActualVersion() {
  const version = activeVersion.value
  if (
    !isFormalWorkspace.value
    || !version
    || (version.status !== 'draft' && version.status !== 'published')
    || !canWriteScheduleActuals.value
  ) {
    dialog.value = {
      tone: 'warning',
      title: '实绩回写未开放',
      message: '白班 / 夜班实绩只允许基于本厂区正式草稿或已发布计划回写。',
      details: [
        '需要 injection_schedule:edit 权限',
        '基于已发布计划回写时，服务端会保留发布快照并创建新的滚动草稿',
        '回退预览、已废弃版本和跨厂只读视图不会调用实绩写入接口',
      ],
    }
    return null
  }
  return version
}

function phase4RequestId(prefix: string) {
  return `ui-${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

async function generatePhase4AutoDraft(input: Phase4AutoDraftRequestView) {
  const version = requirePhase4EditableDraft()
  if (!version) return
  try {
    const result = await scheduleStore.generateAutoDraft({
      expectedRevision: version.revision,
      reason: input.reason,
      name: `自动排程草稿 V${version.versionNo}`,
      planningHorizonEndAt: input.horizonEndAt || undefined,
      requestId: phase4RequestId('auto-preview'),
      dryRun: true,
    })
    if (!result) return
    if (
      result.run.status !== 'previewed'
      || result.run.sourceVersionId !== version.id
      || result.run.sourceRevision !== version.revision
      || !/^[a-f0-9]{64}$/i.test(result.run.contextHash)
    ) {
      throw new Error('自动排程预览返回了无效的版本或上下文')
    }
    const impact = result.run.impact
    pendingPhase4Preview.value = {
      kind: 'auto_draft',
      sourceVersionId: version.id,
      sourceRevision: version.revision,
      contextHash: result.run.contextHash,
      input,
    }
    liveMessage.value = `自动排程影响预览完成：PASS ${impact.scheduledOrderCount} 单，尚未写入草稿`
    dialog.value = {
      tone: 'info',
      title: '自动排程影响预览',
      message: `服务端预览 PASS ${impact.scheduledOrderCount} 单；确认前不会创建或修改草稿。`,
      details: [
        `UNKNOWN ${impact.manualReviewOrderCount} 单、FAIL ${impact.blockedOrderCount} 单保持未排`,
        `受影响机台 ${result.affectedMachineIds.length} 台；锁定、运行中、已完成和受保护任务未移动`,
        `预览绑定源版本 V${version.versionNo} revision ${version.revision}`,
        '下一步确认时必须携带本次 context hash；上下文变化会被服务端拒绝',
        '即使确认应用，也只生成草稿，不会自动校验或发布',
      ],
    }
  } catch {
    pendingPhase4Preview.value = null
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: '自动排程预览失败',
      message: scheduleStore.errorMessage || '服务端没有接受本次自动排程预览。',
      details: ['当前版本保持服务端原状态，没有生成或应用草稿'],
    }
  }
}

async function runPhase4Replan(input: Phase4ReplanRequestView) {
  const version = requirePhase4EditableDraft()
  if (!version) return
  const trigger = input.triggerType === 'urgent_order'
    ? {
        type: 'urgent_order' as const,
        orderId: input.orderId,
        reason: input.reason,
      }
    : {
        type: 'machine_downtime' as const,
        machineId: input.machineId,
        startAt: input.downtimeStartAt,
        endAt: input.downtimeEndAt,
        reason: input.reason,
      }
  try {
    const result = await scheduleStore.replanActiveVersion({
      expectedRevision: version.revision,
      trigger,
      scope: {
        freezeBeforeAt: input.freezeBeforeAt || undefined,
        maxAffectedMachines: input.maxAffectedMachines,
        maxAffectedTasks: input.maxAffectedTasks,
      },
      reason: input.reason,
      requestId: phase4RequestId('replan-preview'),
      dryRun: true,
    })
    if (!result) return
    if (
      result.run.status !== 'previewed'
      || result.run.sourceVersionId !== version.id
      || result.run.sourceRevision !== version.revision
      || !/^[a-f0-9]{64}$/i.test(result.run.contextHash)
    ) {
      throw new Error('局部重排预览返回了无效的版本或上下文')
    }
    const impact = result.run.impact
    pendingPhase4Preview.value = {
      kind: 'local_replan',
      sourceVersionId: version.id,
      sourceRevision: version.revision,
      contextHash: result.run.contextHash,
      input,
    }
    liveMessage.value = `局部重排影响预览完成：${impact.movedTaskCount} 条可能移动，尚未写入草稿`
    dialog.value = {
      tone: impact.etaDelayedTaskCount > 0 ? 'warning' : 'info',
      title: '局部重排影响预览',
      message: `服务端已预览${input.triggerType === 'urgent_order' ? '急单 / 插单' : '临时停机'}影响；确认前不会改写当前草稿。`,
      details: [
        `移动 ${impact.movedTaskCount} 条，ETA 延后 ${impact.etaDelayedTaskCount} 条`,
        `累计 ETA 偏移 ${impact.totalEtaShiftMinutes} 分钟`,
        `预览绑定源版本 V${version.versionNo} revision ${version.revision}`,
        '确认时必须携带本次 context hash；上下文变化会被拒绝并要求重新预览',
        '冻结时间、锁定任务和生产状态屏障仍由服务端执行；不会自动发布',
      ],
    }
  } catch {
    pendingPhase4Preview.value = null
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: '局部重排预览失败',
      message: scheduleStore.errorMessage || '服务端没有接受本次局部重排预览。',
      details: ['当前草稿保持服务端原状态，请核对 revision、冻结范围和保护任务'],
    }
  }
}

async function confirmPhase4Preview() {
  const pending = pendingPhase4Preview.value
  const version = activeVersion.value
  if (!pending || !version) return
  if (
    !canEditSchedule.value
    || version.status !== 'draft'
    || version.id !== pending.sourceVersionId
    || version.revision !== pending.sourceRevision
  ) {
    pendingPhase4Preview.value = null
    dialog.value = {
      tone: 'warning',
      title: '预览上下文已失效',
      message: '当前草稿或 revision 已变化，不能应用旧预览。',
      details: ['请关闭提示并重新执行影响预览'],
    }
    return
  }

  pendingPhase4Preview.value = null
  dialog.value = null
  try {
    const result = pending.kind === 'auto_draft'
      ? await scheduleStore.generateAutoDraft({
          expectedRevision: pending.sourceRevision,
          reason: pending.input.reason,
          name: `自动排程草稿 V${version.versionNo}`,
          planningHorizonEndAt: pending.input.horizonEndAt || undefined,
          requestId: phase4RequestId('auto-apply'),
          dryRun: false,
          expectedContextHash: pending.contextHash,
        })
      : await scheduleStore.replanActiveVersion({
          expectedRevision: pending.sourceRevision,
          trigger: pending.input.triggerType === 'urgent_order'
            ? {
                type: 'urgent_order',
                orderId: pending.input.orderId,
                reason: pending.input.reason,
              }
            : {
                type: 'machine_downtime',
                machineId: pending.input.machineId,
                startAt: pending.input.downtimeStartAt,
                endAt: pending.input.downtimeEndAt,
                reason: pending.input.reason,
              },
          scope: {
            freezeBeforeAt: pending.input.freezeBeforeAt || undefined,
            maxAffectedMachines: pending.input.maxAffectedMachines,
            maxAffectedTasks: pending.input.maxAffectedTasks,
          },
          reason: pending.input.reason,
          requestId: phase4RequestId('replan-apply'),
          dryRun: false,
          expectedContextHash: pending.contextHash,
        })
    if (!result || result.run.status !== 'applied') {
      throw new Error('服务端没有返回 applied 排程结果')
    }
    showPhase4AppliedResult(result, pending.kind)
  } catch {
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: pending.kind === 'auto_draft' ? '自动草稿未应用' : '局部重排未应用',
      message: scheduleStore.errorMessage || '预览上下文已变化或服务端拒绝应用。',
      details: ['当前工作区没有采用本次预览结果，请重新预览后确认'],
    }
  }
}

function showPhase4AppliedResult(
  result: InjectionAutomationResult,
  kind: PendingPhase4Preview['kind'],
) {
  const impact = result.run.impact
  if (kind === 'auto_draft') {
    liveMessage.value = `自动草稿已应用：PASS 排入 ${impact.scheduledOrderCount} 单`
    dialog.value = {
      tone: 'success',
      title: '自动排程草稿已生成',
      message: `仅硬约束 PASS 的 ${impact.scheduledOrderCount} 单以 source=auto 写入新草稿。`,
      details: [
        `源 revision ${result.run.sourceRevision}，结果 revision ${result.run.resultRevision}`,
        `UNKNOWN ${impact.manualReviewOrderCount} 单、FAIL ${impact.blockedOrderCount} 单保持未排`,
        `受影响机台 ${result.affectedMachineIds.length} 台`,
        '计划仍是草稿，没有自动校验或发布',
      ],
    }
    return
  }
  liveMessage.value = `局部重排已应用：移动 ${impact.movedTaskCount} 条任务`
  dialog.value = {
    tone: impact.etaDelayedTaskCount > 0 ? 'warning' : 'success',
    title: '局部重排已应用到草稿',
    message: '服务端已按确认过的 context hash 应用局部重排。',
    details: [
      `移动 ${impact.movedTaskCount} 条，ETA 延后 ${impact.etaDelayedTaskCount} 条`,
      `累计 ETA 偏移 ${impact.totalEtaShiftMinutes} 分钟`,
      `源 revision ${result.run.sourceRevision}，结果 revision ${result.run.resultRevision}`,
      '计划仍是草稿，不会自动发布',
    ],
  }
}

async function reloadPhase4Actuals() {
  const version = requirePhase4ActualVersion()
  if (!version) return
  try {
    await scheduleStore.loadActuals({ versionId: version.id })
    liveMessage.value = `已读取 ${scheduleStore.shiftActuals.length} 条白班 / 夜班实绩`
  } catch {
    liveMessage.value = scheduleStore.errorMessage || '实绩读取失败'
  }
}

function stableActualRequestId(
  prefix: 'actual' | 'actual-correction',
  key: string,
) {
  if (lastActualRequestKey.value === key && lastActualRequestId.value) {
    return lastActualRequestId.value
  }
  lastActualRequestKey.value = key
  lastActualRequestId.value = phase4RequestId(prefix)
  return lastActualRequestId.value
}

async function writePhase4Actual(input: Phase4ActualRequestView) {
  const version = requirePhase4ActualVersion()
  const workspace = scheduleStore.formalWorkspace
  if (!version || !workspace) return
  const sourceWasPublished = version.status === 'published'
  const task = workspace.tasks.find((entry) => entry.id === input.taskId)
  const order = task
    ? workspace.orders.find((entry) => entry.id === task.orderId)
    : null
  if (!task || !order) return
  const requestKey = JSON.stringify({
    factoryId: resolvedFactoryId.value,
    versionId: version.id,
    taskId: task.id,
    orderId: order.id,
    shiftDate: input.shiftDate,
    shift: input.shiftCode,
    actualQty: input.actualQty,
    reason: input.reason,
    versionRevision: version.revision,
    orderRevision: order.revision,
  })
  try {
    const result = await scheduleStore.writeActual({
      versionId: version.id,
      taskId: task.id,
      orderId: order.id,
      machineId: task.machineId,
      shiftDate: input.shiftDate,
      shift: input.shiftCode,
      source: 'manual',
      legacyShiftCode: input.shiftCode === 'day' ? 'A' : 'B',
      actualQty: input.actualQty,
      varianceReason: '',
      expectedVersionRevision: version.revision,
      expectedOrderRevision: order.revision,
      reason: input.reason,
      requestId: stableActualRequestId('actual', requestKey),
    })
    if (!result) return
    if (
      sourceWasPublished
      && (
        result.version.status !== 'draft'
        || result.version.id === version.id
        || result.version.baseVersionId !== version.id
      )
    ) {
      throw new Error('已发布计划的实绩回写没有返回独立滚动草稿')
    }
    liveMessage.value = result.idempotentReplay
      ? '实绩请求命中幂等回放，没有重复累计'
      : sourceWasPublished
        ? `发布快照保持不变；实绩已写入滚动草稿 V${result.version.versionNo}`
        : `已回写${input.shiftCode === 'day' ? '白班（A）' : '夜班（B）'}实绩 ${input.actualQty} 啤`
    dialog.value = {
      tone: 'success',
      title: result.idempotentReplay ? '实绩幂等回放' : '班次实绩已回写',
      message: result.idempotentReplay
        ? '服务端识别到相同 requestId 与相同载荷，返回原记录，没有重复增加已啤数。'
        : sourceWasPublished
          ? `V${version.versionNo} 发布快照没有改动；页面已安全切换到滚动草稿 V${result.version.versionNo}。`
          : `${input.shiftCode === 'day' ? '白班（A）' : '夜班（B）'}实绩已进入受控台账。`,
      details: [
        `滚动欠数 ${result.actual.outstandingQtyAfter.toLocaleString('zh-CN')}`,
        `影响机台 ${result.affectedMachineIds.length} 台，ETA 投影 ${result.projections.length} 条`,
        ...(sourceWasPublished
          ? [`滚动草稿基于发布版本 ${result.actual.sourceVersionId}，不会回写发布任务`]
          : []),
        '这是人工 / API 受控写回，不代表设备 IoT 自动采集',
      ],
    }
  } catch {
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: '班次实绩未回写',
      message: scheduleStore.errorMessage || '服务端没有接受本次实绩记录。',
      details: ['没有在前端累计产量；请核对版本、订单 revision 或 requestId'],
    }
  }
}

async function correctPhase4Actual(input: Phase4ActualCorrectionRequestView) {
  const version = requirePhase4ActualVersion()
  const workspace = scheduleStore.formalWorkspace
  if (!version || !workspace) return
  const actual = scheduleStore.shiftActuals.find(
    (entry) => entry.id === input.actualId,
  )
  const order = actual
    ? workspace.orders.find((entry) => entry.id === actual.orderId)
    : null
  if (!actual || !order) return
  if (version.status !== 'draft' || actual.versionId !== version.id) {
    dialog.value = {
      tone: 'warning',
      title: '请先打开实绩所属滚动草稿',
      message: '已发布快照本身不可更正；请切换到该实绩所属草稿后再提交审计更正。',
      details: ['发布版本保持不可变，更正只会更新滚动草稿和实绩审计链'],
    }
    return
  }
  const requestKey = JSON.stringify({
    actualId: actual.id,
    actualRevision: input.actualRevision,
    actualQty: input.actualQty,
    reason: input.reason,
    versionRevision: version.revision,
    orderRevision: order.revision,
  })
  try {
    const result = await scheduleStore.correctActual(actual.id, {
      expectedRevision: input.actualRevision,
      expectedVersionRevision: version.revision,
      expectedOrderRevision: order.revision,
      actualQty: input.actualQty,
      reason: input.reason,
      requestId: stableActualRequestId('actual-correction', requestKey),
    })
    if (!result) return
    liveMessage.value = `实绩已审计更正为 ${input.actualQty} 啤`
    dialog.value = {
      tone: 'success',
      title: '实绩更正已保存',
      message: `该记录已更新为 revision ${result.actual.revision}，原值和更正原因保留在审计中。`,
      details: [
        `累计更正 ${result.actual.correctionCount} 次`,
        `滚动欠数 ${result.actual.outstandingQtyAfter.toLocaleString('zh-CN')}`,
        `重新计算 ETA 投影 ${result.projections.length} 条`,
      ],
    }
  } catch {
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: '实绩更正未保存',
      message: scheduleStore.errorMessage || '服务端没有接受本次实绩更正。',
      details: ['原实绩记录保持不变，请重新读取最新 revision'],
    }
  }
}

function goBack() {
  void router.push(getFactoryScopedRoute('/modules/production', resolvedFactoryId.value))
}

function selectOrder(orderId: string) {
  selectedOrderId.value = orderId
  if (!isFormalWorkspace.value) {
    const firstEligible = selectedRecommendations.value.find((recommendation) => recommendation.eligible)
      ?? selectedRecommendations.value[0]
    if (firstEligible) selectedMachineId.value = firstEligible.machineId
  }
  liveMessage.value = `已选择订单 ${orderById.value.get(orderId)?.orderNo ?? orderId}`
}

async function loadFormalRecommendations(orderId: string) {
  if (!isFormalWorkspace.value || !activeVersion.value) return
  try {
    const result = await scheduleStore.loadRecommendations(orderId, {
      limit: 100,
    })
    if (
      !result
      || orderWorkspaceMode.value !== 'match'
      || selectedOrderId.value !== orderId
    ) return
    const firstCandidate = result.candidates[0]
    selectedMachineId.value = firstCandidate?.machineId ?? ''
    liveMessage.value = firstCandidate
      ? `已按版本规则生成 ${result.totalCandidates} 台候选机解释`
      : '当前版本没有可展示的候选机台'
  } catch {
    if (selectedOrderId.value === orderId) {
      liveMessage.value = scheduleStore.errorMessage || '候选机台推荐读取失败'
    }
  }
}

function openMatch(orderId: string) {
  selectOrder(orderId)
  activeSection.value = 'orders'
  orderWorkspaceMode.value = 'match'
  void loadFormalRecommendations(orderId)
}

function retryFormalRecommendations() {
  if (!selectedOrderId.value) return
  void loadFormalRecommendations(selectedOrderId.value)
}

function openOrders() {
  activeSection.value = 'orders'
  orderWorkspaceMode.value = 'table'
}

function recommendationFor(machineId: string, orderId: string) {
  if (selectedOrderId.value !== orderId) {
    selectedOrderId.value = orderId
  }
  return selectedRecommendations.value.find((recommendation) => recommendation.machineId === machineId)
    ?? null
}

async function submitScheduleCommands(
  commands: InjectionScheduleOperation[],
  successMessage: string,
  options: { allowManualRetry?: boolean } = {},
) {
  const version = activeVersion.value
  if (!isFormalWorkspace.value || !version || version.status !== 'draft') {
    activeSection.value = 'versions'
    dialog.value = {
      tone: 'warning',
      title: '请先建立可编辑草稿',
      message: '已发布版本不可原地修改，请在计划版本页建立或复制一个草稿。',
      details: ['已发布版本保持不可变', '新草稿会保留来源版本和操作审计'],
    }
    return false
  }
  if (!canEditSchedule.value) {
    dialog.value = {
      tone: 'danger',
      title: '没有排产编辑权限',
      message: '当前账号不能修改本厂区的正式排产草稿。',
      details: ['需要 injection_schedule:edit 权限', '跨厂查看权限不会授予跨厂写入能力'],
    }
    return false
  }
  try {
    await scheduleStore.executeOperations({
      expectedRevision: version.revision,
      reason: commands.map((command) => command.reason).join('；'),
      requestId: `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      commands,
    })
    liveMessage.value = successMessage
    return true
  } catch {
    const manualRequirement = scheduleStore.manualConfirmationRequirement
    if (options.allowManualRetry && manualRequirement) {
      pendingManualOperation.value = {
        commands,
        successMessage,
      }
      manualConfirmationReason.value = ''
      manualConfirmationError.value = ''
      dialog.value = {
        tone: 'warning',
        title: '主数据不完整，需要人工确认',
        message: manualRequirement.message,
        details: [
          ...manualRequirement.reasons,
          '确认后会在同一条原子命令中写入原因和审计；发布前仍需补齐主数据并重新校验',
        ],
      }
      return false
    }
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: scheduleStore.revisionConflict ? '草稿版本已更新' : '排程变更未保存',
      message: scheduleStore.errorMessage || '服务端未接受本次排程变更。',
      details: scheduleStore.revisionConflict
        ? ['页面已保留服务端原状态，请重新载入版本后再操作']
        : ['本次乐观更新已回滚，没有留下半成品任务'],
    }
    return false
  }
}

async function commitFormalAssignment(
  order: InjectionOrder,
  machine: InjectionMachine,
  recommendation: Recommendation,
  manualExceptionReason: string | null,
) {
  const formalCandidate = formalCandidateByMachineId.value.get(machine.id)
  const unknownCodes = recommendation.hardConstraints
    .filter((constraint) => constraint.status === 'unknown')
    .map((constraint) => constraint.code)
  const reason = manualExceptionReason
    ? `人工确认预排：${manualExceptionReason}`
    : `拖入${machine.machineNo}建立正式草稿任务`
  const saved = await submitScheduleCommands([
    {
      type: 'assign',
      orderId: order.id,
      machineId: machine.id,
      targetIndex: formalCandidate?.targetIndex,
      plannedQty: formalRecommendationResponse.value?.plannedQty ?? order.outstandingShots,
      recommendationContextHash: formalCandidate?.recommendationContextHash,
      reason,
      manualConfirmation: manualExceptionReason
        ? {
            confirmed: true,
            reason: manualExceptionReason,
            constraintCodes: unknownCodes,
          }
        : null,
    },
  ], `${order.orderNo}已按候选时间窗保存到${machine.machineNo}，既有任务未移动`)
  if (!saved) return
  selectedMachineId.value = machine.id
  activeSection.value = 'overview'
  orderWorkspaceMode.value = 'table'
  dialog.value = {
    tone: manualExceptionReason ? 'warning' : 'success',
    title: manualExceptionReason ? '人工确认已写入审计' : '正式草稿已保存',
    message: `${order.orderNo}已排入${machine.machineNo}。`,
    details: [
      `当前 revision ${activeVersion.value?.revision ?? '—'}`,
      `预计换型 ${recommendation.setupCost.totalMinutes} 分钟`,
      manualExceptionReason
        ? `人工例外：${manualExceptionReason}`
        : '已使用推荐上下文原子写入；既有任务未移动',
    ],
  }
}

function commitPreviewAssignment(
  order: InjectionOrder,
  machine: InjectionMachine,
  recommendation: Recommendation,
  manualExceptionReason: string | null = null,
) {
  if (isFormalWorkspace.value) {
    void commitFormalAssignment(order, machine, recommendation, manualExceptionReason)
    return
  }
  const provenance: DataProvenance = {
    ...fallbackDataset.value.provenance,
    source: 'manual',
    confidence: 'declared',
    sourceId: `local-preview:${order.id}:${machine.id}`,
    sourceRow: order.sourceWorkbookRow,
    importedAt: null,
    importedBy: null,
  }
  const constraintSnapshot = manualExceptionReason
    ? recommendation.hardConstraints.map((constraint): ConstraintResult => {
        if (constraint.status !== 'unknown') return constraint
        return {
          ...constraint,
          status: 'override',
          blocking: false,
          autoPublishBlocked: true,
          originalStatus: 'unknown',
          override: {
            reason: manualExceptionReason,
            actorId: null,
            actorName: '当前计划员（本地预览）',
            createdAt: new Date().toISOString(),
          },
        }
      })
    : recommendation.hardConstraints
  const scoreBreakdown: InjectionScoreBreakdown = recommendation.scoreBreakdown
  const task: InjectionScheduleTask = {
    id: `preview-${order.id}-${machine.id}`,
    planVersionId: 'phase1-local-preview-v18',
    factoryId: dataset.value.factoryId,
    machineId: machine.id,
    orderId: order.id,
    startAt: recommendation.estimatedStartAt ?? dataset.value.planBaseAt,
    endAt: recommendation.estimatedEndAt ?? dataset.value.planBaseAt,
    plannedShots: order.outstandingShots,
    setupMinutesBefore: recommendation.setupCost.totalMinutes,
    setupReason: [
      ...recommendation.setupCost.reasons,
      ...(manualExceptionReason ? [`人工例外：${manualExceptionReason}`] : []),
    ],
    score: recommendation.eligible ? recommendation.score : null,
    scoreBreakdown,
    constraintSnapshot,
    source: 'manual',
    locked: false,
    status: 'draft',
    provenance,
  }
  previewTasks.value = [
    ...previewTasks.value.filter((entry) => entry.orderId !== order.id),
    task,
  ]
  selectedMachineId.value = machine.id
  activeSection.value = 'overview'
  orderWorkspaceMode.value = 'table'
  liveMessage.value = `${order.orderNo}已本地预排到${machine.machineNo}，未保存到服务器`
  dialog.value = {
    tone: 'success',
    title: manualExceptionReason ? '已人工确认本地预排' : '已加入本地预排',
    message: `${order.orderNo}已放入${machine.machineNo}的草稿时间轴。`,
    details: [
      ...(recommendation.eligible
        ? [`综合评分 ${Math.round(recommendation.score ?? 0)} 分`]
        : ['硬约束资料未完整，未进入自动评分']),
      `预计换型 ${recommendation.setupCost.totalMinutes} 分钟`,
      ...(manualExceptionReason ? [`人工例外：${manualExceptionReason}`] : []),
      '这是浏览器内预览，不是已保存或已发布计划。',
    ],
  }
}

function previewAssignment(payload: { orderId: string; machineId: string }) {
  const order = orderById.value.get(payload.orderId)
  const machine = machineById.value.get(payload.machineId)
  const recommendation = recommendationFor(payload.machineId, payload.orderId)
  if (!order || !machine || !recommendation) {
    dialog.value = {
      tone: 'danger',
      title: '无法建立预排',
      message: '订单、机台或匹配结果不存在，请重新选择。',
      details: [],
    }
    return
  }

  const hardFailure = recommendation.hardConstraints.find((constraint) =>
    constraint.status === 'fail')
  const unknownBlockers = recommendation.hardConstraints.filter((constraint) =>
    constraint.status === 'unknown')
  if (hardFailure || unknownBlockers.length > 0) {
    selectedMachineId.value = machine.id
    orderWorkspaceMode.value = 'match'
    activeSection.value = 'orders'
    liveMessage.value = hardFailure
      ? `${order.orderNo}不能预排到${machine.machineNo}：${hardFailure.reason}`
      : `${order.orderNo}需要人工确认后才能排入${machine.machineNo}`
    pendingManualAssignment.value = hardFailure
      ? null
      : { orderId: order.id, machineId: machine.id }
    manualConfirmationReason.value = ''
    manualConfirmationError.value = ''
    dialog.value = {
      tone: hardFailure ? 'danger' : 'warning',
      title: hardFailure ? '机台不兼容' : '资料缺失，需人工确认',
      message: hardFailure
        ? hardFailure.reason
        : isFormalWorkspace.value
          ? '缺少硬约束主数据，不能自动推荐；可人工确认后写入正式草稿与审计，但仍阻止无人值守发布。'
          : '缺少硬约束主数据，不能自动推荐或自动发布；可人工确认后仅加入回退预览。',
      details: recommendation.hardConstraints
        .filter((constraint) => constraint.status !== 'pass')
        .map((constraint) => `${constraint.label}：${constraint.reason}`),
    }
    return
  }

  pendingManualAssignment.value = null
  commitPreviewAssignment(order, machine, recommendation)
}

function confirmManualPreview() {
  const payload = pendingManualAssignment.value
  if (!payload) return
  const reason = manualConfirmationReason.value.trim()
  if (reason.length < 4) {
    manualConfirmationError.value = '请填写至少 4 个字符的具体确认原因'
    return
  }
  const order = orderById.value.get(payload.orderId)
  const machine = machineById.value.get(payload.machineId)
  const recommendation = recommendationFor(payload.machineId, payload.orderId)
  if (!order || !machine || !recommendation) {
    pendingManualAssignment.value = null
    return
  }
  pendingManualAssignment.value = null
  manualConfirmationReason.value = ''
  manualConfirmationError.value = ''
  commitPreviewAssignment(
    order,
    machine,
    recommendation,
    reason,
  )
}

function closeDialog() {
  dialog.value = null
  pendingManualAssignment.value = null
  pendingManualOperation.value = null
  pendingPhase4Preview.value = null
  manualConfirmationReason.value = ''
  manualConfirmationError.value = ''
}

async function confirmManualOperation() {
  const pending = pendingManualOperation.value
  if (!pending) return
  const manualReason = manualConfirmationReason.value.trim()
  if (manualReason.length < 4) {
    manualConfirmationError.value = '请填写至少 4 个字符的具体确认原因'
    return
  }
  const commands = pending.commands.map((command) => (
    command.type === 'assign' || command.type === 'move' || command.type === 'split'
      ? {
          ...command,
          manualConfirmation: {
            confirmed: true,
            reason: manualReason,
            constraintCodes: [],
          },
        }
      : command
  ))
  pendingManualOperation.value = null
  dialog.value = null
  manualConfirmationReason.value = ''
  manualConfirmationError.value = ''
  const saved = await submitScheduleCommands(commands, pending.successMessage)
  if (saved) taskInspectorOpen.value = false
}

function selectCandidateMachine(machineId: string) {
  selectedMachineId.value = machineId
  const recommendation = selectedRecommendations.value.find((entry) => entry.machineId === machineId)
  const machine = machineById.value.get(machineId)
  if (!recommendation) return
  const state = candidateDisplayState(recommendation)
  liveMessage.value = state === 'eligible'
    ? `已选择${machine?.machineNo ?? machineId}，${candidateScoreLabel(recommendation)}`
    : state === 'manual'
      ? `已选择${machine?.machineNo ?? machineId}，资料待确认 · ${candidateScoreLabel(recommendation)}`
      : `已选择${machine?.machineNo ?? machineId}，${recommendation.hardConstraints.find((item) => item.status !== 'pass')?.reason ?? '硬约束失败'}`
}

function validateSelectedCandidate() {
  const recommendation = selectedCandidate.value
  const machine = selectedCandidateMachine.value
  if (!recommendation || !machine || !selectedOrder.value) {
    validateDraft()
    return
  }
  const blockers = recommendation.hardConstraints.filter((constraint) => constraint.status !== 'pass')
  dialog.value = {
    tone: blockers.length > 0 ? 'warning' : 'success',
    title: `${selectedOrder.value.orderNo} × ${machine.machineNo} 校验结果`,
    message: blockers.length > 0
      ? '当前候选仍有硬约束失败或资料待确认，不能自动发布。'
      : isFormalWorkspace.value
        ? '硬约束全部通过，可排入正式草稿。'
        : '硬约束全部通过，可加入回退预览。',
    details: recommendation.hardConstraints.map((constraint) =>
      `${constraintStatusLabel(constraint)} · ${constraint.label}：${constraint.reason}`),
  }
}

function undoPreview() {
  const lastTask = previewTasks.value.at(-1)
  if (!lastTask) return
  const order = orderById.value.get(lastTask.orderId)
  previewTasks.value = previewTasks.value.slice(0, -1)
  liveMessage.value = `${order?.orderNo ?? lastTask.orderId}的本地预排已撤销`
}

async function validateDraft() {
  if (isFormalWorkspace.value) {
    const version = activeVersion.value
    if (!version) {
      activeSection.value = 'versions'
      dialog.value = {
        tone: 'warning',
        title: '还没有可校验的计划版本',
        message: '请先确认 Excel 导入或建立草稿版本。',
        details: [],
      }
      return
    }
    if (version.status !== 'draft') {
      activeSection.value = 'versions'
      dialog.value = {
        tone: 'info',
        title: '已发布版本保持不可变',
        message: `V${version.versionNo}已经发布，不能重新校验或覆盖。`,
        details: ['如需调整，请从该版本建立新的草稿'],
      }
      return
    }
    try {
      const validation = await scheduleStore.validateActiveVersion(version.revision)
      const againstVersionId = version.baseVersionId
        ?? scheduleStore.formalWorkspace?.versions.find((entry) =>
          entry.id !== version.id && entry.status === 'published')?.id
      await scheduleStore.loadVersionDiff(againstVersionId ?? null)
      if (!validation) return
      const actionableValidationItems = validation.items.filter(
        (conflict) => conflict.status !== 'pass',
      )
      dialog.value = {
        tone: validation.status === 'passed' ? 'success' : 'warning',
        title: validation.status === 'passed' ? '草稿通过发布校验' : '草稿仍有发布阻断项',
        message: validation.status === 'passed'
          ? `V${version.versionNo} revision ${validation.versionRevision} 可以进入发布确认。`
          : `发现 ${validation.blockingCount} 条阻断冲突。`,
        details: actionableValidationItems.length
          ? actionableValidationItems.slice(0, 8).map((conflict) =>
              `${conflict.blocking ? '阻断' : '提示'} · ${conflict.message}`)
          : ['无任务重叠、跨厂、停机窗或主数据阻断'],
      }
      liveMessage.value = validation.status === 'passed'
        ? `V${version.versionNo}已通过发布校验`
        : `V${version.versionNo}校验发现阻断冲突`
    } catch {
      dialog.value = {
        tone: 'danger',
        title: '服务端校验失败',
        message: scheduleStore.errorMessage || '未能完成本次校验。',
        details: ['计划版本没有被发布或修改'],
      }
    }
    return
  }
  const missingMachineCount = dataset.value.machines.filter((machine) =>
    machine.maxShotWeightG == null
    || machine.tieBarWidthMm == null
    || machine.tieBarHeightMm == null).length
  const missingOrderCount = pendingOrders.value.filter((order) =>
    order.dataQualityFlags.length > 0).length
  dialog.value = {
    tone: missingMachineCount || missingOrderCount ? 'warning' : 'success',
    title: '回退预览校验完成',
    message: '当前是明确标识的只读回退预览，不代表服务端发布校验。',
    details: [
      `${previewTasks.value.length} 条本地预排任务`,
      `${missingMachineCount} 台机缺少射胶量或空间参数`,
      `${missingOrderCount} 条待排订单有资料缺失`,
      '跨厂区数据未载入，未发现串厂记录',
    ],
  }
}

async function refreshDraftMasters(versionId: string) {
  if (!isFormalWorkspace.value || activeVersion.value?.id !== versionId) return
  if (!canEditSchedule.value) {
    dialog.value = {
      tone: 'danger',
      title: '不能同步主数据',
      message: '只有本厂区可编辑草稿允许刷新主数据快照。',
      details: ['需要 injection_schedule:edit 权限'],
    }
    return
  }
  const saved = await submitScheduleCommands([
    {
      type: 'refresh_masters',
      reason: '计划员确认同步最新机台、模具和订单主数据',
      manualConfirmation: null,
    },
  ], '草稿已同步最新主数据并重新计算受影响机台')
  if (saved) await validateDraft()
}

function explainPublishBoundary() {
  if (isFormalWorkspace.value) {
    activeSection.value = 'versions'
    liveMessage.value = canPublishSchedule.value
      ? '请在版本面板填写发布原因并确认'
      : '请先完成草稿校验并处理阻断冲突'
    return
  }
  dialog.value = {
    tone: 'warning',
    title: '当前不能发布计划',
    message: '当前回退预览尚未接入正式数据库、权限、版本锁和审计接口；正式实现存在，但服务暂不可用。',
    details: [
      '回退数据不会进入正式计划版本',
      '不会恢复已删除的旧注塑排产表',
      '接口恢复后可重新载入正式工作区',
    ],
  }
}

function inspectTask(taskId: string) {
  const task = allTasks.value.find((entry) => entry.id === taskId)
  const order = task ? orderById.value.get(task.orderId) : null
  if (!task) return
  if (isFormalWorkspace.value) {
    inspectedTaskId.value = taskId
    taskInspectorOpen.value = true
    return
  }
  dialog.value = {
    tone: task.id.startsWith('preview-') ? 'info' : 'success',
    title: order?.productName ?? '排程任务',
    message: `${order?.orderNo ?? task.orderId} · ${machineById.value.get(task.machineId)?.machineNo ?? task.machineId}`,
    details: [
      `计划数量 ${task.plannedShots.toLocaleString('zh-CN')}`,
      `换型 ${task.setupMinutesBefore} 分钟`,
      task.id.startsWith('preview-') ? '本地预排 · 未保存' : 'Excel 快照映射任务',
    ],
  }
}

async function handleScheduleDrop(payload: {
  taskId: string
  machineId: string
  beforeTaskId: string | null
}) {
  const task = allTasks.value.find((entry) => entry.id === payload.taskId)
  if (!task || !isFormalWorkspace.value) return
  if (payload.beforeTaskId === task.id) return
  const targetTasks = allTasks.value
    .filter((entry) => entry.machineId === payload.machineId && entry.id !== task.id)
    .sort((left, right) => (left.sequence ?? 0) - (right.sequence ?? 0))
  const beforeIndex = payload.beforeTaskId
    ? targetTasks.findIndex((entry) => entry.id === payload.beforeTaskId)
    : -1
  const targetIndex = beforeIndex >= 0 ? beforeIndex : targetTasks.length
  const reason = task.machineId === payload.machineId
    ? '计划员拖拽调整机台内任务顺序'
    : `计划员拖拽任务至${machineById.value.get(payload.machineId)?.machineNo ?? payload.machineId}`
  const command: InjectionScheduleOperation = task.machineId === payload.machineId
    ? {
        type: 'reorder',
        taskId: task.id,
        targetIndex,
        reason,
        manualConfirmation: null,
      }
    : {
        type: 'move',
        taskId: task.id,
        machineId: payload.machineId,
        targetIndex,
        reason,
        manualConfirmation: null,
      }
  await submitScheduleCommands(
    [command],
    task.machineId === payload.machineId
      ? '任务顺序已保存，当前机台已增量重排'
      : '跨机移动已保存，两台受影响机台已增量重排',
    { allowManualRetry: command.type === 'move' },
  )
}

async function toggleTaskLock(payload: {
  taskId: string
  locked: boolean
  reason: string
}) {
  const saved = await submitScheduleCommands([
    {
      type: payload.locked ? 'lock' : 'unlock',
      taskId: payload.taskId,
      reason: payload.reason,
      manualConfirmation: null,
    },
  ], payload.locked ? '任务已锁定并写入审计' : '任务已解锁并写入审计')
  if (saved) taskInspectorOpen.value = false
}

async function splitTask(payload: {
  taskId: string
  splitShots: number
  targetMachineId: string
  reason: string
}) {
  const task = allTasks.value.find((entry) => entry.id === payload.taskId)
  if (!task) return
  const remainingShots = task.plannedShots - payload.splitShots
  if (remainingShots <= 0) return
  const targetIndex = allTasks.value.filter(
    (entry) => entry.machineId === payload.targetMachineId,
  ).length
  const saved = await submitScheduleCommands([
    {
      type: 'split',
      taskId: task.id,
      splitQty: payload.splitShots,
      machineId: payload.targetMachineId,
      targetIndex,
      reason: payload.reason,
      manualConfirmation: null,
    },
  ], payload.targetMachineId === task.machineId
    ? '拆单已保存，数量守恒并重新计算当前机台'
    : '拆单与跨机移动已在同一事务保存，两台机已增量重排', {
    allowManualRetry: true,
  })
  if (!saved) return
  taskInspectorOpen.value = false
}

async function previewExcelImport(file: File) {
  if (!canConfigureSchedule.value) {
    dialog.value = {
      tone: 'danger',
      title: '没有导入配置权限',
      message: '当前账号不能向本厂区导入排产主数据。',
      details: ['需要 injection_schedule:config 权限'],
    }
    return
  }
  try {
    const batch = await scheduleStore.previewImport(file)
    if (!batch) return
    liveMessage.value = `已生成${batch.sourceFileName}导入预览，共 ${batch.issues.length} 条问题`
  } catch {
    dialog.value = {
      tone: 'danger',
      title: 'Excel 预览生成失败',
      message: scheduleStore.errorMessage || '文件没有写入正式主数据。',
      details: ['解析失败不会覆盖上一批已确认数据'],
    }
  }
}

async function confirmExcelImport(payload: {
  batchId: string
  expectedRevision: number
  businessDate: string
  reason: string
}) {
  try {
    const batch = await scheduleStore.confirmImport(payload.batchId, {
      expectedRevision: payload.expectedRevision,
      mode: 'merge',
      resolutions: {},
      businessDate: payload.businessDate,
      reason: payload.reason,
    })
    if (!batch) return
    liveMessage.value = 'Excel 已确认合并，并建立正式草稿版本'
    activeSection.value = 'overview'
    dialog.value = {
      tone: 'success',
      title: '导入确认完成',
      message: `${batch.sourceFileName}已合并到${factory.value.shortName}正式工作区。`,
      details: [
        `${scheduleStore.formalWorkspace?.machines.length ?? 0} 台机`,
        `${scheduleStore.formalWorkspace?.orders.length ?? 0} 条订单`,
        activeVersion.value
          ? `当前草稿 V${activeVersion.value.versionNo}`
          : '导入已确认，可新建排产草稿',
      ],
    }
  } catch {
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: '导入确认未完成',
      message: scheduleStore.errorMessage || '本次导入没有合并。',
      details: ['上一正式批次和当前计划版本保持不变'],
    }
  }
}

function resetImportPreview() {
  scheduleStore.importBatch = null
}

async function createScheduleDraft() {
  if (!canEditSchedule.value && activeVersion.value?.status === 'draft') return
  if (!authStore.can('injection_schedule:edit', resolvedFactoryId.value)) {
    dialog.value = {
      tone: 'danger',
      title: '没有新建草稿权限',
      message: '需要本厂区 injection_schedule:edit 权限。',
      details: [],
    }
    return
  }
  const baseVersion = activeVersion.value?.status === 'published'
    ? activeVersion.value
    : scheduleStore.formalWorkspace?.versions.find((entry) => entry.status === 'published')
  try {
    await scheduleStore.createDraft({
      name: `${dataset.value.businessDate} 手工排产草稿`,
      businessDate: dataset.value.businessDate,
      baseVersionId: baseVersion?.id ?? null,
      planBaseAt: dataset.value.planBaseAt,
    })
    liveMessage.value = `已建立草稿 V${activeVersion.value?.versionNo ?? '—'}`
  } catch {
    dialog.value = {
      tone: 'danger',
      title: '草稿建立失败',
      message: scheduleStore.errorMessage || '服务端未建立草稿。',
      details: [],
    }
  }
}

async function selectScheduleVersion(versionId: string) {
  try {
    await scheduleStore.loadVersion(versionId)
    const version = activeVersion.value
    const againstVersionId = version?.baseVersionId
      ?? scheduleStore.formalWorkspace?.versions.find((entry) =>
        entry.id !== versionId && entry.status === 'published')?.id
    await scheduleStore.loadVersionDiff(againstVersionId ?? null)
    liveMessage.value = `已载入计划 V${activeVersion.value?.versionNo ?? '—'}`
  } catch {
    dialog.value = {
      tone: 'danger',
      title: '版本载入失败',
      message: scheduleStore.errorMessage || '无法读取所选版本。',
      details: [],
    }
  }
}

async function cloneScheduleVersion(versionId: string) {
  try {
    const source = scheduleStore.formalWorkspace?.versions.find((entry) => entry.id === versionId)
    await scheduleStore.cloneHistoricalAsDraft(versionId, {
      name: source ? `基于 V${source.versionNo} 的手工草稿` : '历史版本复制草稿',
      reason: '计划员从历史发布版本建立新草稿',
    })
    liveMessage.value = `已复制为草稿 V${activeVersion.value?.versionNo ?? '—'}`
  } catch {
    dialog.value = {
      tone: 'danger',
      title: '历史版本复制失败',
      message: scheduleStore.errorMessage || '没有建立新草稿。',
      details: [],
    }
  }
}

async function publishScheduleVersion(payload: { versionId: string; reason: string }) {
  const version = activeVersion.value
  if (!version || version.id !== payload.versionId) return
  if (!authStore.can('injection_schedule:publish', resolvedFactoryId.value)) {
    dialog.value = {
      tone: 'danger',
      title: '没有计划发布权限',
      message: '当前账号可以查看草稿，但不能发布本厂区计划。',
      details: ['需要 injection_schedule:publish 权限'],
    }
    return
  }
  if (!scheduleStore.canPublish || !scheduleStore.validation) {
    await validateDraft()
    activeSection.value = 'versions'
    if (scheduleStore.canPublish && scheduleStore.validation) {
      dialog.value = {
        tone: 'info',
        title: '校验完成，请先审核发布影响',
        message: `V${version.versionNo} revision ${version.revision} 已通过校验，本次操作不会直接发布。`,
        details: [
          '请检查版本差异、受影响订单与发布校验结果',
          '确认无误后，再次进入发布确认并明确提交',
        ],
      }
    }
    return
  }
  try {
    const detail = await scheduleStore.publishActiveVersion({
      expectedRevision: version.revision,
      validationRunId: scheduleStore.validation.id,
      reason: payload.reason,
    })
    if (!detail) return
    liveMessage.value = `V${detail.versionNo}已发布`
    dialog.value = {
      tone: 'success',
      title: `计划 V${detail.versionNo} 发布成功`,
      message: '该发布版本已经冻结，后续调整需要复制为新草稿。',
      details: [
        `发布原因：${payload.reason}`,
        `${scheduleStore.formalWorkspace?.tasks.length ?? 0} 条不可原地修改的任务快照`,
        '发布事务、版本状态和审计记录已同时提交',
      ],
    }
  } catch {
    dialog.value = {
      tone: scheduleStore.revisionConflict ? 'warning' : 'danger',
      title: '计划发布失败',
      message: scheduleStore.errorMessage || '没有生成发布版本。',
      details: ['当前草稿和上一发布版本保持不变'],
    }
  }
}

function constraintStatusLabel(result: ConstraintResult) {
  const labels: Record<ConstraintResult['status'], string> = {
    pass: '通过',
    fail: '失败',
    unknown: '待确认',
    override: '人工例外',
  }
  return labels[result.status]
}

function machineStatusLabel(machine: InjectionMachine) {
  if (machine.schedulingLocked) return '快照锁定'
  if (machine.availableFrom) return '有完成时间'
  return '未见代表任务'
}

function armLabel(machine: InjectionMachine) {
  return machine.armType === 'double'
    ? '双臂五轴'
    : machine.armType === 'single'
      ? '单臂三轴'
      : '无机械手'
}

function machineProcessRemark(machine: InjectionMachine) {
  const prefix = '计划表机头备注：'
  const remark = machine.dataQualityFlags.find((flag) => flag.startsWith(prefix))
  return remark ? remark.slice(prefix.length) : '—'
}

function machineCompletenessPercent(machine: InjectionMachine) {
  return Math.round(machine.dataCompleteness * 100)
}

function armLabelByMachineId(machineId: string) {
  const machine = machineById.value.get(machineId)
  return machine ? armLabel(machine) : '待确认'
}

function scoreBarWidth(value: number, max: number) {
  if (max === 0) return '0%'
  return `${Math.min(100, Math.max(0, (Math.abs(value) / Math.abs(max)) * 100))}%`
}

function recommendationPlacementStyle(recommendation: Recommendation) {
  if (candidateDisplayState(recommendation) === 'blocked') {
    return { marginLeft: '12%', width: '76%' }
  }
  const horizonStart = Date.parse(dataset.value.planBaseAt)
  const horizonEnd = Date.parse(timelineEndAt.value)
  const estimatedStart = recommendation.estimatedStartAt
    ? Date.parse(recommendation.estimatedStartAt)
    : Number.NaN
  const estimatedEnd = recommendation.estimatedEndAt
    ? Date.parse(recommendation.estimatedEndAt)
    : Number.NaN
  if (
    Number.isNaN(estimatedStart)
    || Number.isNaN(estimatedEnd)
    || horizonEnd <= horizonStart
  ) {
    return { marginLeft: '0%', width: '100%' }
  }
  const left = Math.min(94, Math.max(0, ((estimatedStart - horizonStart) / (horizonEnd - horizonStart)) * 100))
  const available = Math.max(0, 100 - left)
  const duration = ((estimatedEnd - estimatedStart) / (horizonEnd - horizonStart)) * 100
  const width = Math.min(available, Math.max(6, duration))
  return {
    marginLeft: `${left}%`,
    width: `${width}%`,
  }
}

function candidateExistingTaskLabel(machineId: string) {
  const task = allTasks.value
    .filter((entry) => entry.machineId === machineId)
    .sort((left, right) => left.startAt.localeCompare(right.startAt))[0]
  if (!task) return ''
  const order = orderById.value.get(task.orderId)
  return order
    ? `${order.orderNo} · ${order.productName} · 完成 ${formatShortDate(task.endAt)}`
    : `已有任务 · 完成 ${formatShortDate(task.endAt)}`
}

function utilizationWidth(value: number | null) {
  if (value == null) return '0%'
  return `${Math.min(100, Math.max(0, value * 100))}%`
}

function utilizationLabel(value: number | null) {
  if (value == null) return '资料不足，无法量化'
  return `占安全能力 ${Math.round(value * 100)}%`
}

function constraintRowKey(constraint: ConstraintResult) {
  if (
    constraint.actual
    && typeof constraint.actual === 'object'
    && 'sourceCode' in constraint.actual
  ) {
    return String((constraint.actual as { sourceCode: unknown }).sourceCode)
  }
  return constraint.code
}

function signedScore(value: number) {
  if (!Number.isFinite(value)) return '资料缺失'
  const rounded = Math.round(value * 10) / 10
  return rounded > 0 ? `+${rounded}` : String(rounded)
}

function deliverySlackLabel(value: number | null) {
  if (value == null || !Number.isFinite(value)) return '资料缺失 / 未纳入'
  if (value < 0) return `逾期 ${Math.abs(Math.round(value * 10) / 10)} 小时`
  return `${Math.round(value * 10) / 10} 小时`
}

function formatShortDate(value: string | null) {
  if (!value) return '未排程'
  const date = new Date(value)
  if (Number.isNaN(date.getTime()) || date.getUTCFullYear() <= 1900) return '未排程'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function trapDialogFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !dialogElement.value) return
  const focusable = [...dialogElement.value.querySelectorAll<HTMLElement>(
    'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
  )]
  if (focusable.length === 0) {
    event.preventDefault()
    return
  }

  const first = focusable[0]
  const last = focusable.at(-1)!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(resolvedFactoryId, (factoryId) => {
  appStore.setActiveFactory(factoryId)
  loadFactory(factoryId)
}, { immediate: true })

watch(
  () => route.query.section,
  (section) => {
    const nextSection = hubSectionFromQuery(section)
    if (nextSection !== activeSection.value) selectSection(nextSection)
  },
)

watch(selectedRecommendations, (recommendations) => {
  if (!recommendations.length) return
  if (!recommendations.some((recommendation) => recommendation.machineId === selectedMachineId.value)) {
    selectedMachineId.value = recommendations[0].machineId
  }
})

watch(
  () => [
    activeVersion.value?.id ?? '',
    activeVersion.value?.revision ?? 0,
  ] as const,
  (next, previous) => {
    if (
      next[0] === previous?.[0]
      && next[1] === previous?.[1]
    ) return
    if (
      isFormalWorkspace.value
      && orderWorkspaceMode.value === 'match'
      && selectedOrderId.value
    ) {
      void loadFormalRecommendations(selectedOrderId.value)
    }
  },
)

watch([machineSearch, workshopFilter], () => {
  visibleMachineLimit.value = 18
  const selectedStillVisible = filteredMachines.value.some(
    (machine) => machine.id === selectedMachineId.value,
  )
  if (!selectedStillVisible) {
    selectedMachineId.value = filteredMachines.value[0]?.id ?? ''
  }
})

watch(dialog, async (nextDialog, previousDialog) => {
  if (nextDialog && !previousDialog) {
    dialogReturnFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    await nextTick()
    dialogElement.value?.querySelector<HTMLElement>('button')?.focus()
    return
  }

  if (!nextDialog && previousDialog) {
    await nextTick()
    dialogReturnFocus?.focus()
    dialogReturnFocus = null
  }
})

onMounted(() => {
  document.title = '注塑排产中枢 · Royal Regent Nexus'
})
</script>

<template>
  <div class="injection-hub">
    <a href="#injection-hub-main" class="skip-link">跳到注塑排产工作区</a>
    <InjectionHubHeader
      :active-section="activeSection"
      :factory-name="factoryDisplayName"
      :date-range-label="hasPreviewData ? dateRangeLabel : ''"
      :preview-label="provenanceLabel"
      :title-override="currentTitle"
      :description-override="currentDescription"
      :action-busy="scheduleStore.versionLoading || scheduleStore.mutationPending"
      :validate-disabled="isFormalWorkspace && activeVersion?.status !== 'draft'"
      :publish-disabled="isFormalWorkspace && activeVersion?.status !== 'draft'"
      @update:active-section="selectSection"
      @back="goBack"
      @validate="validateDraft"
      @publish="explainPublishBoundary"
    >
      <template #toolbar>
        <div v-if="activeSection === 'overview'" class="header-workbench-toolbar">
          <div class="overview-chips">
            <span>{{ factory.shortName }} · {{ hasPreviewData ? '全部车间' : '独立厂区' }}</span>
            <template v-if="hasPreviewData">
              <span>旧车间 {{ workshopCounts.old }} 台</span>
              <span>新车间 {{ workshopCounts.new }} 台</span>
            </template>
            <button
              v-if="hasPreviewData"
              type="button"
              class="overview-chips__risk"
              :aria-pressed="riskOnly"
              @click="riskOnly = !riskOnly"
            >
              {{ riskOnly ? '显示全部' : '仅看风险' }}
            </button>
          </div>
          <div v-if="hasPreviewData || isFormalWorkspace" class="overview-toolbar__status">
            <span v-if="isFormalWorkspace">
              {{ activeVersion
                ? `正式${activeVersion.status === 'draft' ? '草稿' : '版本'} V${activeVersion.versionNo} · revision ${activeVersion.revision}`
                : '正式工作区 · 尚无计划版本' }}
            </span>
            <span v-else>回退预览 · 不可发布</span>
            <button
              type="button"
              :disabled="isFormalWorkspace && activeVersion?.status !== 'draft'"
              @click="validateDraft"
            >
              <ShieldCheck aria-hidden="true" />
              校验冲突
            </button>
            <button
              v-if="!isFormalWorkspace && previewTasks.length > 0"
              type="button"
              @click="undoPreview"
            >
              <RotateCcw aria-hidden="true" />
              撤销本次预排
            </button>
            <button type="button" class="overview-publish-boundary" @click="explainPublishBoundary">
              <LockKeyhole aria-hidden="true" />
              {{ isFormalWorkspace ? '发布计划' : '发布前置条件' }}
            </button>
          </div>
          <div v-else class="overview-toolbar__status">
            <span>尚未导入快照 · 不显示其他厂区排产数据</span>
          </div>
        </div>

        <div
          v-else-if="activeSection === 'orders' && orderWorkspaceMode === 'match'"
          class="header-workbench-toolbar"
        >
          <span v-if="selectedOrder" class="header-order-chip">
            选中：{{ selectedOrder.orderNo }} · {{ selectedOrder.productName }}
          </span>
          <div class="match-toolbar">
            <button type="button" @click="orderWorkspaceMode = 'table'">
              <ArrowLeft aria-hidden="true" />
              返回订单池
            </button>
            <button type="button" class="match-toolbar__save" @click="validateSelectedCandidate">
              <ShieldCheck aria-hidden="true" />
              校验建议
            </button>
            <button
              v-if="isFormalWorkspace"
              type="button"
              :disabled="scheduleStore.recommendationLoading"
              @click="retryFormalRecommendations"
            >
              <RefreshCw
                :class="{ 'recommendation-request-state__spinner': scheduleStore.recommendationLoading }"
                aria-hidden="true"
              />
              重新计算
            </button>
            <button
              type="button"
              class="match-toolbar__confirm"
              :class="{ 'match-toolbar__confirm--manual': selectedCandidateAllowsManualPreview }"
              :disabled="
                scheduleStore.recommendationLoading
                || (isFormalWorkspace && (!canEditSchedule || activeVersion?.status !== 'draft'))
                || (!selectedCandidate?.eligible && !selectedCandidateAllowsManualPreview)
              "
              @click="selectedOrder && selectedCandidate && previewAssignment({
                orderId: selectedOrder.id,
                machineId: selectedCandidate.machineId,
              })"
            >
              <CheckCircle2 aria-hidden="true" />
              {{ isFormalWorkspace && !canEditSchedule
                ? '只读：不可排入'
                : isFormalWorkspace && activeVersion?.status !== 'draft'
                  ? '版本只读'
                  : selectedCandidateAllowsManualPreview
                    ? isFormalWorkspace ? '人工确认后排入' : '人工确认本地预排'
                    : isFormalWorkspace ? '排入正式草稿' : '加入回退预览' }}
            </button>
          </div>
        </div>

        <div
          v-else-if="activeSection === 'operations'"
          class="header-workbench-toolbar"
        >
          <div class="overview-chips">
            <span>自动草稿 · PASS-only</span>
            <span>急单 / 停机局部重排</span>
            <span>白班（A）/ 夜班（B）实绩</span>
          </div>
          <div class="overview-toolbar__status">
            <span>
              {{ isFormalWorkspace && activeVersion
                ? `V${activeVersion.versionNo} · revision ${activeVersion.revision}`
                : '正式草稿未就绪' }}
            </span>
            <button
              type="button"
              :disabled="!canWriteScheduleActuals || scheduleStore.actualsLoading"
              @click="reloadPhase4Actuals"
            >
              <RefreshCw aria-hidden="true" />
              读取实绩
            </button>
          </div>
        </div>

        <div
          v-else-if="activeSection === 'masters' || activeSection === 'rules'"
          class="master-toolbar"
        >
          <nav aria-label="主数据与规则二级导航">
            <button
              v-for="entry in masterWorkspaceEntries"
              :key="entry.id"
              type="button"
              :class="{ active: masterWorkspaceTab === entry.id }"
              :aria-current="masterWorkspaceTab === entry.id ? 'page' : undefined"
              @click="selectMasterWorkspaceTab(entry.id)"
            >
              {{ entry.label }}
            </button>
          </nav>
          <div>
            <button type="button" @click="explainMasterAction('import')">
              <FileSpreadsheet aria-hidden="true" />
              导入 Excel
            </button>
            <button
              type="button"
              class="master-toolbar__primary"
              @click="explainMasterAction('create')"
            >
              <Plus aria-hidden="true" />
              新增机台
            </button>
          </div>
        </div>

        <div v-else class="header-workbench-toolbar">
          <div v-if="activeSection === 'orders'" class="order-summary-chips" aria-label="待排订单摘要">
            <span>未排 {{ pendingOrders.length }}</span>
            <span>欠 {{ pendingOrderSummary.outstandingShots.toLocaleString('zh-CN') }}</span>
            <span>已超期 {{ pendingOrderSummary.overdue }}</span>
            <span>7 天内到期 {{ pendingOrderSummary.dueWithinSevenDays }}</span>
          </div>
          <span v-else class="header-order-chip">
            {{ factory.shortName }} · {{ activeSection === 'versions' ? '正式版本与发布' : '主数据与规则' }}
          </span>
          <div class="match-toolbar">
            <button
              type="button"
              :disabled="isFormalWorkspace && activeVersion?.status !== 'draft'"
              @click="validateDraft"
            >
              <ShieldCheck aria-hidden="true" />
              {{ isFormalWorkspace ? '校验当前版本' : '校验回退快照' }}
            </button>
            <button type="button" class="match-toolbar__confirm" @click="explainPublishBoundary">
              <LockKeyhole aria-hidden="true" />
              {{ isFormalWorkspace ? '进入发布确认' : '发布不可用' }}
            </button>
          </div>
        </div>
      </template>
    </InjectionHubHeader>

    <main id="injection-hub-main" class="hub-main">
      <section
        v-if="!hasPreviewData && !isFormalWorkspace"
        class="factory-empty"
        aria-labelledby="factory-empty-title"
      >
        <span class="factory-empty__icon"><Factory aria-hidden="true" /></span>
        <p class="factory-empty__eyebrow">{{ factory.shortName }} · 独立厂区数据</p>
        <h2 id="factory-empty-title">当前厂区暂无注塑排产快照</h2>
        <p>
          这不是华兴数据的复制。正式导入前，{{ factory.shortName }}只显示独立空状态，
          机台、模具、订单和规则不会跨厂区混用。
        </p>
        <button type="button" @click="goBack">
          <ArrowLeft aria-hidden="true" />
          返回生产部模块中心
        </button>
      </section>

      <template v-else>
        <section v-if="activeSection === 'overview'" class="overview-workspace">
          <ScheduleKpiStrip :items="kpis" />

          <section class="overview-board" aria-label="机台时间轴与待排订单池">
            <MachineTimelineBoard
              :machines="dataset.machines"
              :tasks="allTasks"
              :orders="dataset.orders"
              :molds="dataset.molds"
              :selected-order="selectedOrder"
              :candidate-state-by-machine="candidateStateByMachine"
              :timeline-start-at="dataset.planBaseAt"
              :timeline-end-at="timelineEndAt"
              :plan-base-at="dataset.planBaseAt"
              @inspect-machine="selectedMachineId = $event"
              @inspect-task="inspectTask"
              @preview-assignment="previewAssignment"
              @schedule-drop="handleScheduleDrop"
            />
            <UnscheduledOrderPool
              :orders="overviewPendingOrders"
              :molds="dataset.molds"
              :plan-base-at="dataset.planBaseAt"
              :selected-order-id="selectedOrderId"
              @select="selectOrder"
              @inspect="openMatch"
              @open-orders="openOrders"
            />
          </section>
        </section>

        <section
          v-else-if="activeSection === 'orders' && orderWorkspaceMode === 'table'"
          class="orders-section"
        >
          <UnscheduledOrderTable
            :orders="pendingOrders"
            :molds="dataset.molds"
            :plan-base-at="dataset.planBaseAt"
            :selected-order-id="selectedOrderId"
            @select="selectOrder"
            @inspect-match="openMatch"
          />
        </section>

        <section
          v-else-if="activeSection === 'orders'"
          class="match-workspace"
          aria-labelledby="matching-workspace-title"
        >
          <div
            v-if="selectedOrder && selectedMold && (!isFormalWorkspace || activeVersion)"
            class="match-grid"
          >
            <section class="candidate-panel" aria-labelledby="matching-workspace-title">
              <header>
                <div>
                  <h2 id="matching-workspace-title">候选机台时间窗</h2>
                  <p>
                    选择候选机台，右侧解释“为什么可排 / 为什么需确认 / 为什么不可排”。
                    <span v-if="recommendationBasisLabel">{{ recommendationBasisLabel }}</span>
                  </p>
                </div>
              </header>

              <article class="selected-order-summary">
                <span class="priority-chip">{{ selectedOrder.priority }} 紧急</span>
                <div>
                  <h3>{{ selectedOrder.productName }}</h3>
                  <p>
                    模具 {{ selectedMold.moldNo }} · 单号 {{ selectedOrder.orderNo }}
                    · {{ selectedOrder.colorName || '颜色待定' }} · {{ selectedOrder.materialCode || '材料待定' }}
                  </p>
                </div>
                <dl>
                  <div><dt>欠数</dt><dd>{{ selectedOrder.outstandingShots.toLocaleString('zh-CN') }}</dd></div>
                  <div><dt>日目标</dt><dd>{{ selectedOrder.targetShotsPerDay?.toLocaleString('zh-CN') ?? '待确认' }}</dd></div>
                  <div><dt>要求机型</dt><dd>{{ selectedMold.recommendedMachineClass ?? '待确认' }}</dd></div>
                  <div><dt>机械手</dt><dd>{{ selectedMold.armRequirement === 'double' ? '双臂' : selectedMold.armRequirement === 'single' ? '单臂' : '通用' }}</dd></div>
                  <div><dt>夹具</dt><dd>{{ selectedMold.fixtureRequirements.join(' / ') || '无特殊要求' }}</dd></div>
                  <div><dt>交货完成期</dt><dd>{{ formatShortDate(selectedOrder.deliveryDueAt) }}</dd></div>
                </dl>
              </article>

              <div
                v-if="isFormalWorkspace && scheduleStore.recommendationLoading"
                class="recommendation-request-state"
                role="status"
              >
                <RefreshCw class="recommendation-request-state__spinner" aria-hidden="true" />
                <div>
                  <strong>正在按当前版本计算候选机台</strong>
                  <span>服务端正在校验硬约束、相邻换型和规则快照。</span>
                </div>
              </div>
              <div
                v-else-if="isFormalWorkspace && !formalRecommendationResponse && scheduleStore.errorMessage"
                class="recommendation-request-state recommendation-request-state--error"
                role="alert"
              >
                <CircleAlert aria-hidden="true" />
                <div>
                  <strong>候选推荐暂未生成</strong>
                  <span>{{ scheduleStore.errorMessage }}</span>
                </div>
                <button type="button" @click="retryFormalRecommendations">重新计算</button>
              </div>
              <div
                v-else-if="isFormalWorkspace && formalRecommendationResponse && candidateRows.length === 0"
                class="recommendation-request-state"
                role="status"
              >
                <Info aria-hidden="true" />
                <div>
                  <strong>当前没有候选机台</strong>
                  <span>没有跨厂回退或浏览器补算结果，请先维护本厂机台主数据。</span>
                </div>
              </div>

              <div v-if="candidateRows.length > 0" class="candidate-calendar" aria-hidden="true">
                <span v-for="day in calendarDays" :key="day">{{ day }}</span>
              </div>

              <div
                v-if="candidateRows.length > 0"
                class="candidate-list"
                role="list"
                aria-label="候选机台排名"
              >
                <div
                  v-for="recommendation in candidateRows"
                  :key="recommendation.machineId"
                  role="listitem"
                  class="candidate-list-item"
                >
                  <button
                    type="button"
                    class="candidate-row"
                    :class="{
                      'candidate-row--selected': selectedMachineId === recommendation.machineId,
                      'candidate-row--blocked': candidateDisplayState(recommendation) === 'blocked',
                      'candidate-row--manual': candidateDisplayState(recommendation) === 'manual',
                    }"
                    :aria-pressed="selectedMachineId === recommendation.machineId"
                    @click="selectCandidateMachine(recommendation.machineId)"
                  >
                    <span class="candidate-machine">
                      <strong :class="{
                        'candidate-machine__blocked': candidateDisplayState(recommendation) === 'blocked',
                      }">
                        {{ machineById.get(recommendation.machineId)?.machineNo }}
                      </strong>
                      <span class="candidate-rank">
                        {{ formalCandidateByMachineId.get(recommendation.machineId)?.status === 'manual_review'
                          ? `参考 ${formalCandidateByMachineId.get(recommendation.machineId)?.advisoryRank ?? '—'}`
                          : `#${recommendation.rank ?? '—'}` }}
                      </span>
                      <span>{{ machineById.get(recommendation.machineId)?.machineClass }}</span>
                      <small>{{ armLabelByMachineId(recommendation.machineId) }}</small>
                    </span>
                    <span class="candidate-verdict">
                      <span :class="{
                        'verdict-pass': candidateDisplayState(recommendation) === 'eligible',
                        'verdict-manual': candidateDisplayState(recommendation) === 'manual',
                        'verdict-fail': candidateDisplayState(recommendation) === 'blocked',
                      }">
                        {{ candidateStatusLabel(recommendation) }}
                      </span>
                      <strong v-if="recommendation.score != null">{{ candidateScoreLabel(recommendation) }}</strong>
                      <strong v-else>
                        {{ recommendation.hardConstraints.find((item) => item.status !== 'pass')?.label }}
                      </strong>
                    </span>
                    <span class="candidate-window">
                      <span
                        v-if="candidateExistingTaskLabel(recommendation.machineId)"
                        class="existing-task"
                        :title="candidateExistingTaskLabel(recommendation.machineId)"
                      >
                        {{ candidateExistingTaskLabel(recommendation.machineId) }}
                      </span>
                      <span
                        class="candidate-placement"
                        :class="{
                          'candidate-placement--blocked': candidateDisplayState(recommendation) === 'blocked',
                          'candidate-placement--manual': candidateDisplayState(recommendation) === 'manual',
                        }"
                        :style="recommendationPlacementStyle(recommendation)"
                        :title="candidateDisplayState(recommendation) !== 'blocked'
                          ? `${formatShortDate(recommendation.estimatedStartAt)} 至 ${formatShortDate(recommendation.estimatedEndAt)}`
                          : `阻断原因（不代表排入时间）：${recommendation.hardConstraints.find((item) => item.status !== 'pass')?.reason}`"
                      >
                        {{ candidateDisplayState(recommendation) !== 'blocked'
                          ? `${formatShortDate(recommendation.estimatedStartAt)} ${candidateDisplayState(recommendation) === 'manual' ? '待确认' : '建议排入'} · ${selectedOrder.outstandingShots.toLocaleString('zh-CN')} 啤`
                          : `阻断 · ${recommendation.hardConstraints.find((item) => item.status !== 'pass')?.reason}` }}
                      </span>
                    </span>
                  </button>
                </div>
              </div>
            </section>

            <aside class="explanation-panel" aria-labelledby="match-explanation-title">
              <header>
                <div>
                  <h2 id="match-explanation-title">匹配解释</h2>
                  <p>PASS 进入正式排名；UNKNOWN 仅显示隔离参考分；FAIL 不评分。</p>
                </div>
                <span
                  v-if="selectedCandidateMachine"
                  :class="{
                    'recommendation-badge': true,
                    'recommendation-badge--manual': selectedCandidate && candidateDisplayState(selectedCandidate) === 'manual',
                    'recommendation-badge--blocked': selectedCandidate && candidateDisplayState(selectedCandidate) === 'blocked',
                  }"
                >
                  {{ selectedCandidate && candidateDisplayState(selectedCandidate) === 'eligible'
                    ? `建议：${selectedCandidateMachine.machineNo}`
                    : selectedCandidate && candidateDisplayState(selectedCandidate) === 'manual'
                      ? `需确认：${selectedCandidateMachine.machineNo}`
                      : '当前不可排' }}
                </span>
              </header>

              <div
                v-if="formalRecommendationResponse"
                class="recommendation-basis"
              >
                <span>
                  候选 {{ formalRecommendationResponse.totalCandidates }} 台 ·
                  可排 {{ formalRecommendationResponse.eligibleCount }} ·
                  需确认 {{ formalRecommendationResponse.manualReviewCount }} ·
                  阻断 {{ formalRecommendationResponse.blockedCount }}
                </span>
                <span>{{ recommendationBasisLabel }}</span>
                <strong
                  v-if="formalRecommendationResponse.currentRuleConfigRevision !== formalRecommendationResponse.ruleConfigRevision"
                >
                  当前配置已到 revision {{ formalRecommendationResponse.currentRuleConfigRevision }}，本推荐仍按版本快照计算
                </strong>
              </div>

              <section class="capacity-card">
                <h3>容量与尺寸</h3>
                <div>
                  <span>模具尺寸</span>
                  <strong>
                    {{ selectedMold.lengthMm ?? '—' }} × {{ selectedMold.widthMm ?? '—' }} × {{ selectedMold.heightMm ?? '—' }} mm
                  </strong>
                  <small>
                    机台空间 {{ selectedCandidateMachine?.tieBarWidthMm ?? '待维护' }} ×
                    {{ selectedCandidateMachine?.tieBarHeightMm ?? '待维护' }} mm
                  </small>
                </div>
                <div v-if="selectedDimensionUsage != null" class="capacity-track">
                  <span
                    role="progressbar"
                    aria-label="模具空间占用"
                    aria-valuemin="0"
                    aria-valuemax="100"
                    :aria-valuenow="Math.round(selectedDimensionUsage * 100)"
                    :style="{ width: utilizationWidth(selectedDimensionUsage) }"
                  />
                </div>
                <p v-else class="capacity-unavailable">尺寸资料不足，无法量化空间占用</p>
                <div>
                  <span>整啤毛重</span>
                  <strong>{{ selectedOrder.grossShotWeightG ?? selectedMold.grossShotWeightG ?? '当前仅有净重资料' }}</strong>
                  <small class="capacity-card__warning">
                    {{ selectedCandidateMachine?.maxShotWeightG == null
                      ? '射胶量字段待维护'
                      : `安全射胶量 ${Math.round(selectedCandidateMachine.maxShotWeightG * activeShotSafetyFactor)}g` }}
                  </small>
                </div>
                <p v-if="selectedOrder.grossShotWeightG == null && selectedMold.grossShotWeightG == null" class="capacity-net-weight">
                  工程净重 {{ selectedMold.engineeringNetWeightG ?? '待确认' }}g，仅供资料参考，不能替代整啤毛重校验
                </p>
                <div v-if="selectedShotUsage != null" class="capacity-track">
                  <span
                    :class="{ 'capacity-track__danger': selectedShotUsage > 1 }"
                    role="progressbar"
                    aria-label="安全射胶量占用"
                    aria-valuemin="0"
                    aria-valuemax="100"
                    :aria-valuenow="Math.round(selectedShotUsage * 100)"
                    :style="{ width: utilizationWidth(selectedShotUsage) }"
                  />
                </div>
                <p v-else class="capacity-unavailable">{{ utilizationLabel(selectedShotUsage) }}</p>
              </section>

              <section class="constraint-section">
                <h3>硬约束校验</h3>
                <ul>
                  <li
                    v-for="constraint in selectedConstraintRows"
                    :key="constraintRowKey(constraint)"
                  >
                    <span>{{ constraint.label }}</span>
                    <small :title="constraint.reason">{{ constraint.reason }}</small>
                    <strong :class="`constraint-status constraint-status--${constraint.status}`">
                      <Check v-if="constraint.status === 'pass'" aria-hidden="true" />
                      <CircleX v-else-if="constraint.status === 'fail'" aria-hidden="true" />
                      <Info v-else aria-hidden="true" />
                      {{ constraintStatusLabel(constraint) }}
                    </strong>
                  </li>
                </ul>
              </section>

              <section v-if="selectedCandidate?.score != null" class="score-section">
                <h3>软目标得分</h3>
                <p
                  v-if="selectedFormalCandidate?.score?.advisory"
                  class="score-section__advisory"
                >
                  这是资料待确认候选的参考分，不代表硬约束通过，也不能自动发布。
                </p>
                <div v-for="row in scoreRows" :key="row.code" class="score-row">
                  <span>
                    {{ row.label }}
                    <small v-if="row.explanation">{{ row.explanation }}</small>
                  </span>
                  <span class="score-track">
                    <span
                      :class="`score-fill score-fill--${row.tone}`"
                      :style="{ width: scoreBarWidth(Math.abs(row.value), row.max) }"
                    />
                  </span>
                  <strong :class="{ 'score-value--negative': row.value < 0 }">
                    {{ signedScore(row.value) }}
                  </strong>
                </div>
              </section>
              <section v-else class="score-section score-section--blocked">
                <h3>软目标得分</h3>
                <p>
                  {{ scheduleStore.recommendationLoading
                    ? '候选评分正在计算。'
                    : selectedCandidate
                      ? '存在失败硬约束；硬约束尚未全部通过，本候选未进入自动评分。'
                      : '请选择已生成的候选机台查看解释。' }}
                </p>
              </section>

              <section v-if="selectedFormalCandidate?.score" class="transition-explanation">
                <h3>相邻任务与换型影响</h3>
                <dl>
                  <div>
                    <dt>模具链</dt>
                    <dd>
                      {{ selectedFormalCandidate.score.transition.previousMoldCode || '无前序' }}
                      →
                      <strong>{{ selectedMold.moldNo }}</strong>
                      →
                      {{ selectedFormalCandidate.score.transition.nextMoldCode || '无后序' }}
                      · 前序到当前
                      {{ selectedFormalCandidate.score.transition.previousMoldCode
                        && selectedFormalCandidate.score.transition.previousMoldCode.toLocaleLowerCase()
                          === selectedMold.moldNo.toLocaleLowerCase()
                        ? '同模连排'
                        : '需要换模' }}
                    </dd>
                  </div>
                  <div>
                    <dt>颜色链</dt>
                    <dd>
                      {{ selectedFormalCandidate.score.transition.previousColor || '无前序' }}
                      <template v-if="selectedFormalCandidate.score.transition.previousColorRank != null">
                        (等级 {{ selectedFormalCandidate.score.transition.previousColorRank }})
                      </template>
                      →
                      <strong>
                        {{ selectedFormalCandidate.score.transition.targetColor || selectedOrder.colorCode || selectedOrder.colorName || '当前未知' }}
                        <template v-if="selectedFormalCandidate.score.transition.targetColorRank != null">
                          (等级 {{ selectedFormalCandidate.score.transition.targetColorRank }})
                        </template>
                      </strong>
                      → {{ selectedFormalCandidate.score.transition.nextColor || '无后序' }}
                      <template v-if="selectedFormalCandidate.score.transition.nextColorRank != null">
                        (等级 {{ selectedFormalCandidate.score.transition.nextColorRank }})
                      </template>
                      · 前→当前 {{ selectedFormalCandidate.score.transition.colorMinutes ?? '资料缺失' }} 分钟
                      [{{ selectedFormalCandidate.score.transition.colorMatrixMatch || '未命中矩阵' }}]；
                      当前→后序 {{ selectedFormalCandidate.score.transition.afterColorMinutes ?? 0 }} 分钟
                      [{{ selectedFormalCandidate.score.transition.afterColorMatrixMatch || '无后序' }}]；
                      原前→后 {{ selectedFormalCandidate.score.transition.replacedColorMinutes ?? 0 }} 分钟
                      [{{ selectedFormalCandidate.score.transition.replacedColorMatrixMatch || '无原间隙' }}]
                    </dd>
                  </div>
                  <div>
                    <dt>材料链</dt>
                    <dd>
                      {{ selectedFormalCandidate.score.transition.previousMaterial || '无前序' }}
                      → <strong>{{ selectedOrder.materialCode || '当前未知' }}</strong>
                      → {{ selectedFormalCandidate.score.transition.nextMaterial || '无后序' }}
                      · 前→当前 {{ selectedFormalCandidate.score.transition.materialMinutes ?? '资料缺失' }} 分钟
                      [{{ selectedFormalCandidate.score.transition.materialMatrixMatch || '未命中矩阵' }}]；
                      当前→后序 {{ selectedFormalCandidate.score.transition.afterMaterialMinutes ?? 0 }} 分钟
                      [{{ selectedFormalCandidate.score.transition.afterMaterialMatrixMatch || '无后序' }}]；
                      原前→后 {{ selectedFormalCandidate.score.transition.replacedMaterialMinutes ?? 0 }} 分钟
                      [{{ selectedFormalCandidate.score.transition.replacedMaterialMatrixMatch || '无原间隙' }}]
                    </dd>
                  </div>
                  <div>
                    <dt>换型与交期</dt>
                    <dd>
                      前序 → 当前 {{ selectedFormalCandidate.score.transition.setupMinutesBefore }} 分钟；
                      当前 → 后序 {{ selectedFormalCandidate.score.transition.setupMinutesAfter }} 分钟；
                      替换原间隙 {{ selectedFormalCandidate.score.transition.replacedSetupMinutes }} 分钟，
                      净影响 {{ signedScore(selectedFormalCandidate.score.transition.setupMinutesDelta) }} 分钟；
                      交期余量 {{ deliverySlackLabel(selectedFormalCandidate.score.estimated.deliverySlackHours) }}
                    </dd>
                  </div>
                  <div>
                    <dt>日历占机</dt>
                    <dd>
                      <template v-if="selectedFormalCandidate.score.estimated.skippedUnavailableWindows.length">
                        已跳过 {{ selectedFormalCandidate.score.estimated.skippedUnavailableWindows.length }} 个不可用窗口：
                        <template
                          v-for="(window, index) in selectedFormalCandidate.score.estimated.skippedUnavailableWindows"
                          :key="`${window.startAt}-${window.endAt}-${index}`"
                        >
                          {{ formatShortDate(window.startAt) }} 至 {{ formatShortDate(window.endAt) }}
                          （{{ window.reason || '未填写原因' }}）<template
                            v-if="index < selectedFormalCandidate.score.estimated.skippedUnavailableWindows.length - 1"
                          >；</template>
                        </template>。
                      </template>
                      <template v-else>未命中停机或锁定窗口；</template>
                      建议占机 {{ formatShortDate(selectedFormalCandidate.score.estimated.slotStartAt) }}，
                      生产 {{ formatShortDate(selectedFormalCandidate.score.estimated.productionStartAt) }}
                    </dd>
                  </div>
                </dl>
              </section>

              <p class="explanation-warning" role="note">
                <AlertTriangle aria-hidden="true" />
                {{ activeAllowsUnknownManualConfirmation
                  ? '当前版本允许资料 UNKNOWN 在填写具体原因后人工确认；失败硬约束禁止排入。'
                  : '当前版本已关闭缺失资料人工确认，UNKNOWN 与 FAIL 均阻断排入。' }}
                自动排程草稿与批量应用仍属于 Phase 4。
              </p>
            </aside>
          </div>
          <div v-else class="match-prerequisite-state" role="status">
            <template v-if="!selectedOrder">
              <CircleAlert aria-hidden="true" />
              <h2>订单不存在或已无待排数量</h2>
              <p>该订单可能已被其他计划员排完，或主数据已刷新。请返回订单池重新选择。</p>
              <button type="button" @click="orderWorkspaceMode = 'table'">返回订单池</button>
            </template>
            <template v-else-if="isFormalWorkspace && !activeVersion">
              <Layers3 aria-hidden="true" />
              <h2>尚无可用于推荐的计划版本</h2>
              <p>
                订单 {{ selectedOrder.orderNo }} 已选择，但候选推荐必须绑定计划版本和规则快照。
                请先创建草稿或选择已有版本。
              </p>
              <button type="button" @click="selectSection('versions')">前往计划版本</button>
            </template>
            <template v-else>
              <Database aria-hidden="true" />
              <h2>订单引用的模具主数据未匹配</h2>
              <p>
                订单 {{ selectedOrder.orderNo }} · 模号
                {{ formalOrderById.get(selectedOrder.id)?.moldCode || selectedOrder.moldId || '未填写' }}。
                该项属于 mold_master UNKNOWN，不能自动推荐或发布。
              </p>
              <button
                type="button"
                @click="selectSection('masters'); selectMasterWorkspaceTab('molds')"
              >
                前往维护模具
              </button>
            </template>
          </div>
        </section>

        <section v-else-if="activeSection === 'operations'" class="phase4-section">
          <Phase4DynamicSchedulingPanel
            v-if="isFormalWorkspace"
            :version="phase4VersionView"
            :orders="phase4OrderOptions"
            :machines="phase4MachineOptions"
            :tasks="phase4TaskOptions"
            :actuals="phase4ActualViews"
            :last-run="phase4LastRunView"
            :impacts="phase4ImpactViews"
            :skipped="phase4SkippedViews"
            :barriers="phase4BarrierViews"
            :last-actual-replay="Boolean(scheduleStore.lastActualResult?.idempotentReplay)"
            :can-automate="canEditSchedule && activeVersion?.status === 'draft'"
            :can-write-actuals="canWriteScheduleActuals"
            :busy="scheduleStore.phase4Loading || scheduleStore.mutationPending"
            :actuals-loading="scheduleStore.actualsLoading"
            :error="scheduleStore.errorMessage"
            @generate-auto-draft="generatePhase4AutoDraft"
            @run-replan="runPhase4Replan"
            @write-actual="writePhase4Actual"
            @correct-actual="correctPhase4Actual"
            @reload-actuals="reloadPhase4Actuals"
          />
          <div v-else class="phase2-fallback-boundary">
            <ShieldAlert aria-hidden="true" />
            <h2>Phase 4 正式服务未就绪</h2>
            <p>
              自动排程、局部重排和白夜班实绩不会在 Excel 回退预览中模拟成功；
              需要打开本厂区正式草稿并具备编辑权限。
            </p>
          </div>
        </section>

        <section v-else-if="activeSection === 'versions'" class="versions-workspace">
          <ScheduleVersionPanel
            v-if="isFormalWorkspace"
            :versions="versionViews"
            :current-version-id="activeVersion?.id"
            :diff="versionDiffView"
            :conflicts="versionConflictViews"
            :publish-ready="canPublishSchedule"
            :busy="scheduleStore.versionLoading || scheduleStore.mutationPending"
            :error="scheduleStore.errorMessage"
            @select-version="selectScheduleVersion"
            @create-draft="createScheduleDraft"
            @clone-as-draft="cloneScheduleVersion"
            @refresh-masters="refreshDraftMasters"
            @validate="validateDraft"
            @publish="publishScheduleVersion"
          />
          <div v-else class="phase2-fallback-boundary">
            <ShieldAlert aria-hidden="true" />
            <h2>正式版本服务暂不可用</h2>
            <p>当前回退快照不会伪造草稿、发布版或审计记录。接口恢复后重新载入即可。</p>
          </div>
        </section>

        <section
          v-else-if="masterWorkspaceTab === 'machines'"
          class="masters-workspace"
        >
          <section class="machine-master-panel" aria-labelledby="machine-master-title">
            <header>
              <div>
                <h2 id="machine-master-title">{{ factory.shortName }}机台主数据</h2>
                <p>来源：计划表机台分组 + 机台完成时间；缺失射胶量与空间参数需补录。</p>
              </div>
              <span>{{ dataset.machines.length }} 台</span>
              <label>
                <span class="sr-only">搜索机台</span>
                <input v-model="machineSearch" type="search" placeholder="搜索机号 / 机型 / 限制">
              </label>
              <select v-model="workshopFilter" aria-label="按车间筛选">
                <option value="all">旧 / 新车间</option>
                <option value="old">旧车间</option>
                <option value="new">新车间</option>
              </select>
              <button
                v-if="isFormalWorkspace"
                type="button"
                class="machine-master-edit"
                :disabled="!selectedMachine || !canConfigureSchedule"
                @click="editSelectedMachine"
              >
                <Settings2 aria-hidden="true" />
                编辑所选机台
              </button>
            </header>

            <div class="machine-table-scroll" tabindex="0" aria-label="机台主数据表">
              <table>
                <thead>
                  <tr>
                    <th scope="col">机台</th>
                    <th scope="col">车间</th>
                    <th scope="col">机安 / 吨位</th>
                    <th scope="col">机型</th>
                    <th scope="col">机械手</th>
                    <th scope="col">射胶量</th>
                    <th scope="col">模具空间</th>
                    <th scope="col">工艺限制</th>
                    <th scope="col">快照占用</th>
                    <th scope="col">数据完整度</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="machine in visibleMasterMachines"
                    :key="machine.id"
                    :class="{ selected: selectedMachine?.id === machine.id }"
                    :aria-selected="selectedMachine?.id === machine.id"
                    @click="selectedMachineId = machine.id"
                  >
                    <td>
                      <button
                        type="button"
                        :aria-pressed="selectedMachine?.id === machine.id"
                        @click.stop="selectedMachineId = machine.id"
                      >
                        {{ machine.machineNo }}
                      </button>
                    </td>
                    <td>{{ machine.workshop === 'old' ? '旧' : '新' }}</td>
                    <td><strong>{{ machine.machineClass }}</strong></td>
                    <td>{{ machine.speedType || '普通' }}</td>
                    <td>{{ armLabel(machine) }}</td>
                    <td><span :class="{ missing: machine.maxShotWeightG == null }">{{ machine.maxShotWeightG ?? '待补' }}</span></td>
                    <td>
                      <span :class="{ missing: machine.tieBarWidthMm == null || machine.tieBarHeightMm == null }">
                        {{ machine.tieBarWidthMm && machine.tieBarHeightMm ? `${machine.tieBarWidthMm}×${machine.tieBarHeightMm}` : '待补' }}
                      </span>
                    </td>
                    <td>{{ machineProcessRemark(machine) }}</td>
                    <td><span :class="`machine-status machine-status--${machine.status}`">{{ machineStatusLabel(machine) }}</span></td>
                    <td>
                      <span class="completeness-value">{{ machineCompletenessPercent(machine) }}%</span>
                      <span class="completeness-track">
                        <span :style="{ width: `${machineCompletenessPercent(machine)}%` }" />
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <footer>
              <span>
                已展示 {{ visibleMasterMachines.length }} / {{ filteredMachines.length }} 台 ·
                旧车间 {{ workshopCounts.old }} 台 / 新车间 {{ workshopCounts.new }} 台
              </span>
              <button
                v-if="visibleMasterMachines.length < filteredMachines.length"
                type="button"
                @click="visibleMachineLimit += 18"
              >
                加载更多
              </button>
            </footer>
          </section>

          <aside v-if="selectedMachine" class="machine-detail-panel">
            <header>
              <div>
                <h2>{{ selectedMachine.machineNo }} · 机台详情</h2>
                <span>{{ factory.shortName }} / {{ selectedMachine.workshop === 'old' ? '旧车间' : '新车间' }}</span>
              </div>
              <strong>{{ selectedMachineCompleteness === 100 ? '资料完整' : `资料完整度 ${selectedMachineCompleteness}%` }}</strong>
            </header>

            <div class="machine-detail-cards">
              <span><small>机安 / 吨位</small><strong>{{ selectedMachine.machineClass }}</strong></span>
              <span><small>机型</small><strong>{{ selectedMachine.speedType || '普通' }}</strong></span>
              <span><small>机械手</small><strong>{{ armLabel(selectedMachine) }}</strong></span>
              <span><small>螺杆类型</small><strong>{{ selectedMachine.screwType || '待维护' }}</strong></span>
              <span><small>工艺限制</small><strong>{{ machineProcessRemark(selectedMachine) }}</strong></span>
            </div>

            <section class="required-data">
              <h3>自动匹配必填参数</h3>
              <div
                v-for="entry in missingMachineFields"
                :key="entry.field"
                :class="{ complete: entry.value != null }"
              >
                <strong>{{ entry.field }}</strong>
                <span>{{ entry.value ?? '待维护' }}</span>
                <small>{{ entry.use }}</small>
              </div>
            </section>

            <section class="rule-weights">
              <h3>{{ factory.shortName }}排程策略（可配置）</h3>
              <div v-for="row in ruleWeightRows" :key="row.id">
                <strong>{{ row.label }}</strong>
                <span>{{ row.value }}</span>
                <small>{{ row.hint }}</small>
              </div>
            </section>

            <p class="factory-boundary">
              <Database aria-hidden="true" />
              所有主数据、班次和策略均以 factoryId 隔离
            </p>
          </aside>
        </section>

        <section v-else class="config-workspace">
          <section class="config-primary-panel">
            <header>
              <div>
                <h2 :key="masterWorkspaceTab">
                  {{ masterWorkspaceEntries.find((entry) => entry.id === masterWorkspaceTab)?.label }}
                </h2>
                <p>
                  {{ isFormalWorkspace
                    ? `${factory.shortName}厂区正式主数据 · 更新使用 revision 乐观锁并记录审计`
                    : `${factory.shortName}厂区回退预览 · 不会保存浏览器内更改` }}
                </p>
              </div>
              <div class="master-actions">
                <span>factoryId: {{ dataset.factoryId }}</span>
                <template v-if="isFormalWorkspace && masterWorkspaceTab === 'molds'">
                  <button
                    type="button"
                    :disabled="!canConfigureSchedule"
                    @click="openMasterEditor('mold')"
                  >
                    <Plus aria-hidden="true" />
                    新增模具
                  </button>
                  <button
                    type="button"
                    :disabled="!canConfigureSchedule || !selectedMasterMoldId"
                    @click="openMasterEditor('mold', selectedMasterMoldId)"
                  >
                    <Settings2 aria-hidden="true" />
                    编辑所选
                  </button>
                </template>
                <template v-if="isFormalWorkspace && masterWorkspaceTab === 'orders'">
                  <button
                    type="button"
                    :disabled="!canConfigureSchedule"
                    @click="openMasterEditor('order')"
                  >
                    <Plus aria-hidden="true" />
                    新增订单
                  </button>
                  <button
                    type="button"
                    :disabled="!canConfigureSchedule || !selectedMasterOrderId"
                    @click="openMasterEditor('order', selectedMasterOrderId)"
                  >
                    <Settings2 aria-hidden="true" />
                    编辑所选
                  </button>
                </template>
              </div>
            </header>

            <div v-if="masterWorkspaceTab === 'molds'" class="config-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">模号</th>
                    <th scope="col">名称</th>
                    <th scope="col">推荐机安</th>
                    <th scope="col">机械手</th>
                    <th scope="col">夹具</th>
                    <th scope="col">整啤毛重</th>
                    <th scope="col">模具尺寸</th>
                    <th scope="col">模厚 / 开模</th>
                    <th scope="col">螺杆</th>
                    <th scope="col">资料状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="mold in dataset.molds"
                    :key="mold.id"
                    :class="{ selected: selectedMasterMoldId === mold.id }"
                    @click="selectedMasterMoldId = mold.id"
                  >
                    <td>
                      <button
                        type="button"
                        :aria-pressed="selectedMasterMoldId === mold.id"
                        @click.stop="selectedMasterMoldId = mold.id"
                      >
                        {{ mold.moldNo }}
                      </button>
                    </td>
                    <td>{{ mold.name }}</td>
                    <td>{{ mold.recommendedMachineClass ?? '待确认' }}</td>
                    <td>{{ mold.armRequirement === 'double' ? '双臂' : mold.armRequirement === 'single' ? '单臂' : '无要求' }}</td>
                    <td>{{ mold.fixtureRequirements.join('、') || '待确认' }}</td>
                    <td>{{ mold.grossShotWeightG == null ? '待补' : `${mold.grossShotWeightG}g` }}</td>
                    <td>
                      {{ mold.lengthMm && mold.widthMm && mold.heightMm
                        ? `${mold.lengthMm}×${mold.widthMm}×${mold.heightMm}`
                        : '待补' }}
                    </td>
                    <td>
                      {{ mold.moldThicknessMm == null ? '待补' : `${mold.moldThicknessMm}mm` }}
                      /
                      {{ mold.requiredOpeningStrokeMm == null ? '待补' : `${mold.requiredOpeningStrokeMm}mm` }}
                    </td>
                    <td>{{ mold.requiredScrewTypes.join('、') || '待确认' }}</td>
                    <td>
                      <span :class="mold.grossShotWeightG == null || mold.moldThicknessMm == null || mold.requiredOpeningStrokeMm == null ? 'config-status config-status--warning' : 'config-status'">
                        {{ mold.grossShotWeightG == null || mold.moldThicknessMm == null || mold.requiredOpeningStrokeMm == null ? '需补硬约束' : '可校验' }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else-if="masterWorkspaceTab === 'orders'" class="config-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">订单号</th>
                    <th scope="col">产品</th>
                    <th scope="col">模号</th>
                    <th scope="col">订单 / 欠数</th>
                    <th scope="col">交货日期</th>
                    <th scope="col">材料 / 颜色</th>
                    <th scope="col">下游 / 缓冲</th>
                    <th scope="col">指定机台</th>
                    <th scope="col">资料状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="order in visibleMasterOrders"
                    :key="order.id"
                    :class="{ selected: selectedMasterOrderId === order.id }"
                    @click="selectedMasterOrderId = order.id"
                  >
                    <td>
                      <button
                        type="button"
                        :aria-pressed="selectedMasterOrderId === order.id"
                        @click.stop="selectedMasterOrderId = order.id"
                      >
                        {{ order.orderNo }}
                      </button>
                    </td>
                    <td>
                      <strong>{{ order.productName }}</strong>
                      <small>{{ order.itemNo || '未录产品编号' }}</small>
                    </td>
                    <td>{{ moldById.get(order.moldId)?.moldNo ?? order.moldId }}</td>
                    <td>
                      {{ order.orderShots.toLocaleString('zh-CN') }} /
                      <strong>{{ order.outstandingShots.toLocaleString('zh-CN') }}</strong>
                    </td>
                    <td>
                      <span :class="{ missing: !order.deliveryDueAt }">
                        {{ order.deliveryDueAt ? formatShortDate(order.deliveryDueAt) : '待补' }}
                      </span>
                    </td>
                    <td>
                      {{ order.materialCode || '待补' }} / {{ order.colorName || '待补' }}
                      <small>颜色等级 {{ order.colorRank ?? '待补' }}</small>
                    </td>
                    <td>
                      紧急度 {{ isFormalWorkspace
                        ? formalOrderById.get(order.id)?.downstreamUrgency ?? '未纳入'
                        : order.downstreamUrgency }}
                      <small>
                        仓 {{ order.warehouseBufferHours }}h / 下游 {{ order.downstreamBufferHours }}h
                      </small>
                    </td>
                    <td>
                      {{ formalOrderById.get(order.id)?.importedAssignedMachineCode || '未指定' }}
                    </td>
                    <td>
                      <span :class="order.deliveryDueAt ? 'config-status' : 'config-status config-status--warning'">
                        {{ order.deliveryDueAt ? '可校验' : '缺交期' }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
              <footer class="config-table-footer">
                <span>
                  第 {{ masterOrderPage }} / {{ masterOrderPageCount }} 页 ·
                  当前 {{ visibleMasterOrders.length }} 条 / 共 {{ dataset.orders.length }} 条
                </span>
                <span class="config-table-footer__pager">
                  <button
                    type="button"
                    :disabled="masterOrderPage <= 1"
                    @click="masterOrderPage = Math.max(1, masterOrderPage - 1)"
                  >
                    上一页
                  </button>
                  <button
                    type="button"
                    :disabled="masterOrderPage >= masterOrderPageCount"
                    @click="masterOrderPage = Math.min(masterOrderPageCount, masterOrderPage + 1)"
                  >
                    下一页
                  </button>
                </span>
              </footer>
            </div>

            <div v-else-if="masterWorkspaceTab === 'transitions'" class="transition-config">
              <div
                v-if="isFormalWorkspace && scheduleStore.ruleConfigLoading && !ruleConfigDraft"
                class="config-empty-state"
                role="status"
              >
                <RefreshCw class="recommendation-request-state__spinner" aria-hidden="true" />
                <h3>正在读取厂区转换矩阵</h3>
                <p>读取完成前不会展示浏览器默认值。</p>
              </div>
              <template v-else-if="isFormalWorkspace && ruleConfigDraft">
                <article
                  v-for="matrix in ruleMatrixEditors"
                  :key="matrix.id"
                  class="transition-matrix-editor"
                >
                  <header>
                    <div>
                      <h3>{{ matrix.title }}</h3>
                      <p>按方向匹配，`* / *` 为必须保留的厂区兜底规则。</p>
                    </div>
                    <button
                      v-if="canConfigureSchedule"
                      type="button"
                      @click="addTransitionRule(matrix.id)"
                    >
                      <Plus aria-hidden="true" />
                      新增方向
                    </button>
                    <span v-else class="config-readonly-badge">只读</span>
                  </header>
                  <div class="transition-matrix-editor__rows">
                    <div
                      v-for="(row, index) in matrix.rows"
                      :key="`${matrix.id}-${index}`"
                      class="transition-matrix-row"
                    >
                      <label>
                        <span>从</span>
                        <input
                          v-model.trim="row.fromCode"
                          type="text"
                          :disabled="!canConfigureSchedule"
                          :aria-label="`${matrix.title}第${index + 1}行来源代码`"
                        >
                      </label>
                      <span aria-hidden="true">→</span>
                      <label>
                        <span>到</span>
                        <input
                          v-model.trim="row.toCode"
                          type="text"
                          :disabled="!canConfigureSchedule"
                          :aria-label="`${matrix.title}第${index + 1}行目标代码`"
                        >
                      </label>
                      <label>
                        <span>分钟</span>
                        <input
                          v-model.number="row.minutes"
                          type="number"
                          min="0"
                          max="1440"
                          :disabled="!canConfigureSchedule"
                          :aria-label="`${matrix.title}第${index + 1}行分钟`"
                        >
                      </label>
                      <button
                        v-if="canConfigureSchedule"
                        type="button"
                        :disabled="row.fromCode === '*' && row.toCode === '*'"
                        :aria-label="`删除${matrix.title}第${index + 1}行`"
                        @click="removeTransitionRule(matrix.id, index)"
                      >
                        <Trash2 aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                </article>

                <article class="setup-minutes-editor">
                  <header>
                    <div>
                      <h3>按机型换模时间</h3>
                      <p>推荐时按候选机型读取；`*` 为未命中机型的兜底。</p>
                    </div>
                    <button v-if="canConfigureSchedule" type="button" @click="addSetupRule">
                      <Plus aria-hidden="true" />
                      新增机型
                    </button>
                  </header>
                  <div class="setup-minutes-editor__rows">
                    <div
                      v-for="(row, index) in ruleConfigDraft.config.setupMinutes"
                      :key="`setup-${index}`"
                    >
                      <label>
                        <span>机型</span>
                        <input v-model.trim="row.machineClass" type="text" :disabled="!canConfigureSchedule">
                      </label>
                      <label>
                        <span>同模分钟</span>
                        <input v-model.number="row.sameMoldMinutes" type="number" min="0" max="1440" :disabled="!canConfigureSchedule">
                      </label>
                      <label>
                        <span>换模分钟</span>
                        <input v-model.number="row.moldChangeMinutes" type="number" min="0" max="1440" :disabled="!canConfigureSchedule">
                      </label>
                      <button
                        v-if="canConfigureSchedule"
                        type="button"
                        :disabled="row.machineClass === '*'"
                        aria-label="删除换模时间规则"
                        @click="removeSetupRule(index)"
                      >
                        <Trash2 aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                </article>

                <section class="rule-save-panel">
                  <div>
                    <strong>规则 revision {{ ruleConfigDraft.revision }}</strong>
                    <span>当前版本仍使用创建时的规则快照；保存只影响后续推荐或新版本。</span>
                  </div>
                  <label v-if="canConfigureSchedule">
                    <span>变更原因</span>
                    <input
                      v-model="ruleChangeReason"
                      type="text"
                      maxlength="2000"
                      placeholder="例如：按啤机部洗机验证结果更新"
                    >
                  </label>
                  <p v-if="ruleDraftError" role="alert">{{ ruleDraftError }}</p>
                  <div>
                    <button type="button" @click="loadFormalRuleConfig(true)">
                      <RefreshCw aria-hidden="true" />
                      重新读取
                    </button>
                    <button type="button" @click="resetRulePreview">
                      <RotateCcw aria-hidden="true" />
                      撤销未保存
                    </button>
                    <button
                      v-if="canConfigureSchedule"
                      type="button"
                      class="master-toolbar__primary"
                      :disabled="scheduleStore.ruleConfigSaving"
                      @click="saveFormalRuleConfig"
                    >
                      <Save aria-hidden="true" />
                      {{ scheduleStore.ruleConfigSaving ? '保存中…' : '保存规则' }}
                    </button>
                  </div>
                </section>
              </template>
              <div v-else-if="isFormalWorkspace" class="config-empty-state">
                <CircleAlert aria-hidden="true" />
                <h3>规则配置未读取</h3>
                <p>{{ ruleDraftError || scheduleStore.errorMessage || '请重新读取当前厂区规则。' }}</p>
                <button type="button" @click="loadFormalRuleConfig(true)">重新读取</button>
              </div>
              <template v-else>
                <article>
                  <h3>颜色转换</h3>
                  <p>默认浅色 → 深色；深色 → 浅色需要更多洗机时间。</p>
                  <dl>
                    <div><dt>同色</dt><dd>{{ dataset.ruleConfig.setup.sameColorChangeMinutes }} 分钟</dd></div>
                    <div><dt>浅色 → 深色</dt><dd>{{ dataset.ruleConfig.setup.lightToDarkColorMinutes }} 分钟</dd></div>
                    <div><dt>深色 → 浅色</dt><dd>{{ dataset.ruleConfig.setup.darkToLightColorMinutes }} 分钟</dd></div>
                    <div><dt>颜色未知</dt><dd>{{ dataset.ruleConfig.setup.unknownColorTransitionMinutes }} 分钟</dd></div>
                  </dl>
                </article>
                <article>
                  <h3>材料转换</h3>
                  <p>回退预览只展示本地默认值，不会保存。</p>
                  <dl>
                    <div><dt>同料</dt><dd>{{ dataset.ruleConfig.setup.sameMaterialChangeMinutes }} 分钟</dd></div>
                    <div><dt>不同材料</dt><dd>{{ dataset.ruleConfig.setup.differentMaterialChangeMinutes }} 分钟</dd></div>
                    <div><dt>颜色矩阵</dt><dd>{{ dataset.ruleConfig.setup.colorTransitionMatrix.length }} 条</dd></div>
                    <div><dt>材料矩阵</dt><dd>{{ dataset.ruleConfig.setup.materialTransitionMatrix.length }} 条</dd></div>
                  </dl>
                </article>
              </template>
            </div>

            <div v-else-if="masterWorkspaceTab === 'calendar'" class="calendar-rule-editor">
              <div
                v-if="isFormalWorkspace && scheduleStore.ruleConfigLoading && !ruleConfigDraft"
                class="config-empty-state"
                role="status"
              >
                <RefreshCw class="recommendation-request-state__spinner" aria-hidden="true" />
                <h3>正在读取班次与停机日历</h3>
                <p>日历核验范围未返回前，系统不会假设机台可用。</p>
              </div>
              <template v-else-if="isFormalWorkspace && ruleConfigDraft">
                <article class="calendar-verification-card">
                  <header>
                    <div>
                      <h3>可用日历核验范围</h3>
                      <p>超过截止时间的候选会进入“需确认”，不会被自动排入或发布。</p>
                    </div>
                    <span v-if="!canConfigureSchedule" class="config-readonly-badge">只读</span>
                  </header>
                  <label>
                    <span>已核验至</span>
                    <input
                      v-model.trim="ruleConfigDraft.config.availabilityCalendarVerifiedThrough"
                      type="text"
                      placeholder="例如：2026-07-31T23:59:59+08:00"
                      :disabled="!canConfigureSchedule"
                      aria-label="可用日历核验截止时间"
                    >
                  </label>
                  <small>请保留时区偏移；用于判定候选时间窗口是 PASS 还是 UNKNOWN。</small>
                </article>

                <article class="unavailable-window-editor">
                  <header>
                    <div>
                      <h3>不可用窗口</h3>
                      <p>登记全厂停产、机台保养和临时停机；推荐会跳过这些窗口并解释影响。</p>
                    </div>
                    <button
                      v-if="canConfigureSchedule"
                      type="button"
                      @click="addUnavailableWindow"
                    >
                      <Plus aria-hidden="true" />
                      新增窗口
                    </button>
                  </header>
                  <div class="unavailable-window-editor__head" aria-hidden="true">
                    <span>范围</span>
                    <span>机台</span>
                    <span>开始</span>
                    <span>结束</span>
                    <span>原因</span>
                    <span>操作</span>
                  </div>
                  <div
                    v-if="ruleConfigDraft.config.unavailableWindows.length === 0"
                    class="unavailable-window-editor__empty"
                  >
                    当前没有停机窗口；候选仍受“已核验至”截止时间约束。
                  </div>
                  <div
                    v-for="(window, index) in ruleConfigDraft.config.unavailableWindows"
                    :key="`unavailable-${index}`"
                    class="unavailable-window-row"
                  >
                    <label>
                      <span>范围</span>
                      <select
                        v-model="window.scope"
                        :disabled="!canConfigureSchedule"
                        :aria-label="`停机窗口第${index + 1}行范围`"
                      >
                        <option value="factory">全厂</option>
                        <option value="machine">指定机台</option>
                      </select>
                    </label>
                    <label>
                      <span>机台</span>
                      <select
                        v-model="window.machineId"
                        :disabled="!canConfigureSchedule || window.scope === 'factory'"
                        :aria-label="`停机窗口第${index + 1}行机台`"
                      >
                        <option value="">请选择</option>
                        <option
                          v-for="machine in scheduleStore.formalWorkspace?.machines ?? []"
                          :key="machine.id"
                          :value="machine.id"
                        >
                          {{ machine.machineCode }} · {{ machine.machineName }}
                        </option>
                      </select>
                    </label>
                    <label>
                      <span>开始</span>
                      <input
                        v-model.trim="window.startAt"
                        type="text"
                        placeholder="2026-07-24T08:00:00+08:00"
                        :disabled="!canConfigureSchedule"
                        :aria-label="`停机窗口第${index + 1}行开始时间`"
                      >
                    </label>
                    <label>
                      <span>结束</span>
                      <input
                        v-model.trim="window.endAt"
                        type="text"
                        placeholder="2026-07-24T12:00:00+08:00"
                        :disabled="!canConfigureSchedule"
                        :aria-label="`停机窗口第${index + 1}行结束时间`"
                      >
                    </label>
                    <label>
                      <span>原因</span>
                      <input
                        v-model.trim="window.reason"
                        type="text"
                        maxlength="500"
                        placeholder="保养、停电或盘点"
                        :disabled="!canConfigureSchedule"
                        :aria-label="`停机窗口第${index + 1}行原因`"
                      >
                    </label>
                    <button
                      v-if="canConfigureSchedule"
                      type="button"
                      :aria-label="`删除停机窗口第${index + 1}行`"
                      @click="removeUnavailableWindow(index)"
                    >
                      <Trash2 aria-hidden="true" />
                    </button>
                  </div>
                </article>

                <section class="rule-save-panel">
                  <div>
                    <strong>规则 revision {{ ruleConfigDraft.revision }}</strong>
                    <span>当前版本使用创建时的日历快照；保存影响后续推荐或新版本。</span>
                  </div>
                  <label v-if="canConfigureSchedule">
                    <span>变更原因</span>
                    <input
                      v-model="ruleChangeReason"
                      type="text"
                      maxlength="2000"
                      placeholder="例如：录入本周机台保养计划"
                    >
                  </label>
                  <p v-if="ruleDraftError" role="alert">{{ ruleDraftError }}</p>
                  <div>
                    <button type="button" @click="loadFormalRuleConfig(true)">
                      <RefreshCw aria-hidden="true" />
                      重新读取
                    </button>
                    <button type="button" @click="resetRulePreview">
                      <RotateCcw aria-hidden="true" />
                      撤销未保存
                    </button>
                    <button
                      v-if="canConfigureSchedule"
                      type="button"
                      class="master-toolbar__primary"
                      :disabled="scheduleStore.ruleConfigSaving"
                      @click="saveFormalRuleConfig"
                    >
                      <Save aria-hidden="true" />
                      {{ scheduleStore.ruleConfigSaving ? '保存中…' : '保存日历规则' }}
                    </button>
                  </div>
                </section>
              </template>
              <div v-else-if="isFormalWorkspace" class="config-empty-state">
                <CircleAlert aria-hidden="true" />
                <h3>班次与停机日历未读取</h3>
                <p>{{ ruleDraftError || scheduleStore.errorMessage || '请重新读取当前厂区规则。' }}</p>
                <button type="button" @click="loadFormalRuleConfig(true)">重新读取</button>
              </div>
              <div v-else class="config-empty-state">
                <CalendarClock aria-hidden="true" />
                <h3>班次与停机日历尚未导入</h3>
                <p>当前 Excel 快照没有结构化班次、保养或停机窗口，系统不会虚构可用产能。</p>
                <button type="button" @click="explainMasterAction('import')">查看导入边界</button>
              </div>
            </div>

            <div v-else-if="masterWorkspaceTab === 'weights'" class="weight-editor">
              <p class="weight-editor__notice">
                {{ isFormalWorkspace
                  ? '候选推荐使用当前计划版本的规则快照。这里保存的规则用于后续推荐或新版本，不会改写已发布版本。'
                  : '仅在硬约束全部通过后计算。回退预览中可即时查看候选排序变化，但不会保存或发布。' }}
              </p>
              <div
                v-if="isFormalWorkspace && scheduleStore.ruleConfigLoading && !ruleConfigDraft"
                class="config-empty-state"
                role="status"
              >
                <RefreshCw class="recommendation-request-state__spinner" aria-hidden="true" />
                <h3>正在读取评分权重</h3>
              </div>
              <template v-else-if="!isFormalWorkspace || ruleConfigDraft">
                <label
                  v-for="row in ruleWeightRows"
                  :key="row.id"
                >
                  <span>
                    <strong>{{ row.label }}</strong>
                    <small>{{ row.hint }}</small>
                  </span>
                  <input
                    v-if="isFormalWorkspace && ruleConfigDraft"
                    v-model.number="ruleConfigDraft.config.scoringWeights[row.configKey]"
                    type="number"
                    min="0"
                    max="100"
                    :aria-label="`${row.label}权重`"
                    :disabled="!canConfigureSchedule"
                  >
                  <input
                    v-else
                    v-model.number="dataset.ruleConfig.scoring.weights[row.id]"
                    type="number"
                    :aria-label="`${row.label}权重`"
                  >
                </label>
              </template>
              <div v-if="isFormalWorkspace && ruleConfigDraft" class="weight-editor__foundation">
                <label>
                  <span>
                    <strong>射胶安全系数</strong>
                    <small>整啤毛重上限 = 最大射胶量 × 系数</small>
                  </span>
                  <input
                    v-model.number="ruleConfigDraft.config.shotSafetyFactor"
                    type="number"
                    min="0.01"
                    max="1"
                    step="0.01"
                    :disabled="!canConfigureSchedule"
                  >
                </label>
                <label>
                  <span>
                    <strong>深色阈值</strong>
                    <small>颜色等级达到此值后视为深色</small>
                  </span>
                  <input
                    v-model.number="ruleConfigDraft.config.colorRankDarkThreshold"
                    type="number"
                    min="1"
                    max="100"
                    :disabled="!canConfigureSchedule"
                  >
                </label>
                <label class="weight-editor__switch">
                  <span>
                    <strong>缺失资料允许人工确认</strong>
                    <small>关闭后，UNKNOWN 候选直接阻断，不能人工例外排入</small>
                  </span>
                  <input
                    v-model="ruleConfigDraft.config.allowMissingDataInDraftWithManualConfirmation"
                    type="checkbox"
                    :disabled="!canConfigureSchedule"
                    aria-label="允许缺失资料人工确认"
                  >
                </label>
              </div>
              <section v-if="isFormalWorkspace && ruleConfigDraft" class="rule-save-panel">
                <div>
                  <strong>规则 revision {{ ruleConfigDraft.revision }}</strong>
                  <span v-if="canConfigureSchedule">保存后已打开的候选结果会失效，需要重新计算。</span>
                  <span v-else>当前账号只有读取权限。</span>
                </div>
                <label v-if="canConfigureSchedule">
                  <span>变更原因</span>
                  <input
                    v-model="ruleChangeReason"
                    type="text"
                    maxlength="2000"
                    placeholder="例如：调整急单与同模连排权重"
                  >
                </label>
                <p v-if="ruleDraftError" role="alert">{{ ruleDraftError }}</p>
                <div>
                  <button type="button" @click="loadFormalRuleConfig(true)">
                    <RefreshCw aria-hidden="true" />
                    重新读取
                  </button>
                  <button type="button" @click="resetRulePreview">
                    <RotateCcw aria-hidden="true" />
                    撤销未保存
                  </button>
                  <button
                    v-if="canConfigureSchedule"
                    type="button"
                    class="master-toolbar__primary"
                    :disabled="scheduleStore.ruleConfigSaving"
                    @click="saveFormalRuleConfig"
                  >
                    <Save aria-hidden="true" />
                    {{ scheduleStore.ruleConfigSaving ? '保存中…' : '保存规则' }}
                  </button>
                </div>
              </section>
              <button v-else-if="!isFormalWorkspace" type="button" @click="resetRulePreview">
                <RotateCcw aria-hidden="true" />
                恢复首期建议值
              </button>
            </div>

            <ExcelImportPanel
              v-else-if="isFormalWorkspace"
              :preview="importPreviewView"
              :busy="scheduleStore.importLoading"
              :error="scheduleStore.errorMessage"
              @preview-file="previewExcelImport"
              @confirm-import="confirmExcelImport"
              @reset="resetImportPreview"
            />

            <div v-else class="import-mapping">
              <article v-for="mapping in [
                ['计划表', '订单、模号、机安、欠数、交期、颜色、材料'],
                ['机安', '模具、推荐安数、机械手、夹具、工程净重'],
                ['机台完成时间', '代表任务完成时间、机安、机型'],
              ]" :key="mapping[0]">
                <FileSpreadsheet aria-hidden="true" />
                <div><h3>{{ mapping[0] }}</h3><p>{{ mapping[1] }}</p></div>
                <span>回退只读</span>
              </article>
            </div>
          </section>

          <aside class="config-boundary-panel">
            <header>
              <ShieldAlert aria-hidden="true" />
              <div>
                <h2>自动排程边界</h2>
                <p>资料不足时停在人工确认，不生成“看似精确”的计划。</p>
              </div>
            </header>
            <ul>
              <li><CheckCircle2 aria-hidden="true" />厂区、机台状态和锁定状态先校验</li>
              <li><CircleAlert aria-hidden="true" />整啤毛重、射胶量、模具尺寸缺失即阻止自动发布</li>
              <li><CircleAlert aria-hidden="true" />机械手、夹具、抽芯、材料与螺杆能力必须兼容</li>
              <li><GitCompareArrows aria-hidden="true" />颜色与材料转换成本来自厂区矩阵</li>
              <li><LockKeyhole aria-hidden="true" />人工例外必须记录原因并进入版本审计</li>
            </ul>
            <dl>
              <div><dt>机台</dt><dd>{{ dataset.machines.length }} 台</dd></div>
              <div><dt>模具</dt><dd>{{ dataset.molds.length }} 套</dd></div>
              <div><dt>待排</dt><dd>{{ pendingOrders.length }} 单</dd></div>
              <div>
                <dt>可发布</dt>
                <dd>
                  {{ isFormalWorkspace
                    ? scheduleStore.validation?.status === 'passed'
                      && scheduleStore.validation.blockingCount === 0
                      ? '是 · 已校验'
                      : '否 · 待校验'
                    : '否 · 回退预览' }}
                </dd>
              </div>
            </dl>
            <p class="factory-boundary">
              <Database aria-hidden="true" />
              主数据、班次和策略均按 factoryId 隔离
            </p>
          </aside>
        </section>
      </template>
    </main>

    <p class="hub-footnote">
      {{ isFormalWorkspace
        ? 'Phase 2 · 正式版本、任务变更、校验与发布均由服务端持久化并按厂区隔离'
        : '回退预览 · 数据仅来自只读 Excel 快照，不代表正式发布排程' }}
    </p>
    <p class="sr-only" aria-live="polite">{{ liveMessage }}</p>

    <ScheduleTaskInspector
      :open="taskInspectorOpen"
      :task="inspectedTask"
      :order="inspectedOrder"
      :machine="inspectedMachine"
      :machines="dataset.machines"
      :conflict-messages="inspectedTaskConflictMessages"
      :busy="scheduleStore.mutationPending"
      :error="scheduleStore.errorMessage"
      @close="taskInspectorOpen = false"
      @toggle-lock="toggleTaskLock"
      @split="splitTask"
    />

    <MachineMasterEditor
      :open="machineEditorOpen"
      :factory-name="factoryDisplayName"
      :machine="machineEditorMachine"
      :busy="machineSavePending"
      :error="scheduleStore.errorMessage"
      @close="machineEditorOpen = false"
      @save="saveMachineMaster"
    />

    <ScheduleMasterEditor
      :open="masterEditorOpen"
      :kind="masterEditorKind"
      :factory-name="factoryDisplayName"
      :mold="masterEditorMold"
      :order="masterEditorOrder"
      :busy="masterSavePending"
      :error="scheduleStore.errorMessage"
      @close="masterEditorOpen = false"
      @save-mold="saveMoldMaster"
      @save-order="saveOrderMaster"
    />

    <Teleport to="body">
      <div
        v-if="dialog"
        class="hub-dialog-backdrop"
        role="presentation"
        @click.self="closeDialog"
      >
        <section
          ref="dialogElement"
          class="hub-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="hub-dialog-title"
          @keydown.esc="closeDialog"
          @keydown="trapDialogFocus"
        >
          <header>
            <span :class="`hub-dialog__icon hub-dialog__icon--${dialog.tone}`">
              <CheckCircle2 v-if="dialog.tone === 'success'" aria-hidden="true" />
              <CircleX v-else-if="dialog.tone === 'danger'" aria-hidden="true" />
              <AlertTriangle v-else-if="dialog.tone === 'warning'" aria-hidden="true" />
              <Info v-else aria-hidden="true" />
            </span>
            <div>
              <h2 id="hub-dialog-title">{{ dialog.title }}</h2>
              <p>{{ dialog.message }}</p>
            </div>
            <button type="button" aria-label="关闭提示" @click="closeDialog">
              <X aria-hidden="true" />
            </button>
          </header>
          <ul v-if="dialog.details.length > 0">
            <li v-for="detail in dialog.details" :key="detail">
              <Check aria-hidden="true" />
              {{ detail }}
            </li>
          </ul>
          <div
            v-if="pendingManualAssignment || pendingManualOperation"
            class="hub-dialog__manual-reason"
          >
            <label>
              <span>人工确认原因（必填）</span>
              <textarea
                v-model="manualConfirmationReason"
                rows="3"
                maxlength="500"
                placeholder="请写明已核对的资料、风险承担或后续回填安排"
                aria-describedby="manual-confirmation-hint"
                @input="manualConfirmationError = ''"
              />
            </label>
            <small id="manual-confirmation-hint">
              至少 4 个字符；将随同一条原子命令写入任务快照和操作审计。
            </small>
            <p v-if="manualConfirmationError" role="alert">{{ manualConfirmationError }}</p>
          </div>
          <footer>
            <template
              v-if="pendingManualAssignment || pendingManualOperation || pendingPhase4Preview"
            >
              <button type="button" class="hub-dialog__secondary" @click="closeDialog">取消</button>
              <button
                v-if="pendingManualOperation"
                type="button"
                :disabled="manualConfirmationReason.trim().length < 4"
                @click="confirmManualOperation"
              >
                确认例外并重试
              </button>
              <button
                v-else-if="pendingManualAssignment"
                type="button"
                :disabled="manualConfirmationReason.trim().length < 4"
                @click="confirmManualPreview"
              >
                {{ isFormalWorkspace ? '确认并写入正式草稿' : '人工确认本地预排' }}
              </button>
              <button
                v-else
                type="button"
                :disabled="scheduleStore.phase4Loading || scheduleStore.mutationPending"
                @click="confirmPhase4Preview"
              >
                确认应用到草稿
              </button>
            </template>
            <button v-else type="button" @click="closeDialog">知道了</button>
          </footer>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.injection-hub {
  min-height: 100vh;
  background: #f4f7f8;
  color: #0f172a;
  font-family: 'Microsoft YaHei', 'PingFang SC', 'Segoe UI', sans-serif;
}

.skip-link {
  position: fixed;
  z-index: 120;
  top: 8px;
  left: 14px;
  border-radius: 8px;
  background: #fff;
  padding: 9px 13px;
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
  transform: translateY(-160%);
}

.skip-link:focus {
  transform: translateY(0);
}

.hub-main {
  width: 100%;
  padding: 14px 28px 18px;
}

.overview-workspace {
  display: grid;
  gap: 12px;
}

.header-workbench-toolbar {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.master-toolbar {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.master-toolbar nav,
.master-toolbar > div {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.master-toolbar nav {
  overflow-x: auto;
  scrollbar-width: none;
}

.master-toolbar nav::-webkit-scrollbar {
  display: none;
}

.master-toolbar button {
  display: inline-flex;
  height: 34px;
  flex: none;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid #dbe5e8;
  border-radius: 999px;
  background: #fff;
  padding: 0 13px;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
}

.master-toolbar nav button.active {
  border-color: #99e1d6;
  background: #e6f7f4;
  color: #0f766e;
}

.master-toolbar > div button {
  height: 40px;
  border-radius: 9px;
  font-size: 12px;
}

.master-toolbar svg {
  width: 15px;
  height: 15px;
}

.master-toolbar .master-toolbar__primary {
  border-color: #0f766e;
  background: #0f766e;
  color: #fff;
}

.overview-chips,
.overview-toolbar__status {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.overview-chips span,
.overview-chips button {
  display: inline-flex;
  height: 28px;
  align-items: center;
  border: 1px solid #dbe5e8;
  border-radius: 999px;
  background: #fff;
  padding: 0 11px;
  color: #475569;
  font-size: 10px;
  white-space: nowrap;
}

.overview-chips span:first-child {
  border-color: #99e1d6;
  background: #e6f7f4;
  color: #0f766e;
  font-weight: 700;
}

.overview-chips__risk {
  cursor: pointer;
  color: #475569 !important;
}

.overview-chips__risk[aria-pressed='true'] {
  border-color: #fca5a5;
  background: #fff1f2;
  color: #b91c1c !important;
  font-weight: 800;
}

.overview-chips__risk:focus-visible {
  outline: 2px solid #0f766e;
  outline-offset: 2px;
}

.overview-toolbar__status {
  color: #64748b;
  font-size: 10px;
}

.overview-toolbar__status button {
  display: inline-flex;
  height: 28px;
  align-items: center;
  gap: 5px;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #fff;
  padding: 0 9px;
  color: #334155;
  font-size: 10px;
  font-weight: 700;
}

.overview-toolbar__status button:hover {
  border-color: #5eead4;
  color: #0f766e;
}

.overview-toolbar__status .overview-publish-boundary {
  border-color: #0f766e;
  background: #0f766e;
  color: #fff;
}

.overview-toolbar__status .overview-publish-boundary:hover {
  background: #115e59;
  color: #fff;
}

.overview-toolbar__status svg {
  width: 13px;
  height: 13px;
}

.overview-board {
  display: grid;
  height: calc(100vh - 367px);
  min-height: 600px;
  min-width: 0;
  grid-template-columns: minmax(0, 1fr) minmax(380px, 482px);
  overflow: hidden;
  border: 1px solid #dbe5e8;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 14px 32px -30px rgb(15 23 42 / 28%);
}

.orders-section {
  height: calc(100vh - 258px);
  min-height: 620px;
}

.match-toolbar {
  display: flex;
  min-height: 44px;
  align-items: center;
  justify-content: flex-end;
  gap: 9px;
  margin-bottom: 12px;
}

.header-workbench-toolbar .match-toolbar {
  min-height: 0;
  margin: 0;
}

.header-order-chip {
  overflow: hidden;
  max-width: 48vw;
  border: 1px solid #99e1d6;
  border-radius: 999px;
  background: #e6f7f4;
  padding: 6px 12px;
  color: #0f766e;
  font-size: 11px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-summary-chips {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.order-summary-chips span {
  display: inline-flex;
  height: 28px;
  align-items: center;
  border: 1px solid #dbe5e8;
  border-radius: 999px;
  background: #fff;
  padding: 0 11px;
  color: #475569;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}

.order-summary-chips span:first-child {
  border-color: #99e1d6;
  background: #e6f7f4;
  color: #0f766e;
}

.order-summary-chips span:nth-child(2) {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}

.order-summary-chips span:nth-child(3) {
  border-color: #fecaca;
  background: #fff1f2;
  color: #b91c1c;
}

.order-summary-chips span:nth-child(4) {
  border-color: #fde68a;
  background: #fffbeb;
  color: #b45309;
}

.match-toolbar > span {
  margin-right: auto;
  border: 1px solid #99e1d6;
  border-radius: 999px;
  background: #e6f7f4;
  padding: 6px 12px;
  color: #0f766e;
  font-size: 11px;
  font-weight: 700;
}

.match-toolbar button {
  display: inline-flex;
  height: 40px;
  align-items: center;
  gap: 6px;
  border: 1px solid #cbd5e1;
  border-radius: 9px;
  background: #fff;
  padding: 0 15px;
  color: #334155;
  font-size: 11px;
  font-weight: 700;
}

.match-toolbar button:hover {
  border-color: #5eead4;
  background: #ecfdf8;
  color: #0f766e;
}

.match-toolbar button:disabled {
  cursor: not-allowed;
  border-color: #e2e8f0;
  background: #f8fafc;
  color: #94a3b8;
}

.match-toolbar svg {
  width: 15px;
  height: 15px;
}

.match-toolbar__confirm {
  border-color: #0f766e !important;
  background: #0f766e !important;
  color: #fff !important;
}

.match-toolbar__confirm--manual {
  border-color: #b45309 !important;
  background: #b45309 !important;
}

.match-toolbar__confirm:disabled {
  border-color: #cbd5e1 !important;
  background: #e2e8f0 !important;
  color: #94a3b8 !important;
}

.match-grid {
  display: grid;
  height: calc(100vh - 261px);
  min-height: 700px;
  grid-template-columns: minmax(0, 1.7fr) minmax(460px, 1fr);
  gap: 20px;
}

.match-prerequisite-state {
  display: grid;
  min-height: 420px;
  align-content: center;
  justify-items: center;
  border: 1px solid #dbe5e8;
  border-radius: 12px;
  background: #fff;
  padding: 38px;
  text-align: center;
}

.match-prerequisite-state > svg {
  width: 44px;
  height: 44px;
  color: #b45309;
}

.match-prerequisite-state h2 {
  margin-top: 14px;
  color: #0f172a;
  font-size: 18px;
}

.match-prerequisite-state p {
  max-width: 620px;
  margin-top: 8px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.7;
}

.match-prerequisite-state button {
  min-height: 38px;
  margin-top: 18px;
  border: 1px solid #99e1d6;
  border-radius: 8px;
  background: #e6f7f4;
  padding: 0 14px;
  color: #0f766e;
  font: inherit;
  font-size: 11px;
  font-weight: 800;
}

.candidate-panel,
.explanation-panel,
.version-list,
.version-diff,
.machine-master-panel,
.machine-detail-panel {
  overflow: hidden;
  border: 1px solid #dbe5e8;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 12px 28px -28px rgb(15 23 42 / 24%);
}

.candidate-panel {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.candidate-panel > header,
.explanation-panel > header,
.version-list > header,
.version-diff > header,
.machine-master-panel > header,
.machine-detail-panel > header {
  display: flex;
  min-height: 78px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 20px;
}

.candidate-panel h2,
.explanation-panel h2,
.version-list h2,
.version-diff h2,
.machine-master-panel h2,
.machine-detail-panel h2 {
  color: #0f172a;
  font-size: 20px;
  font-weight: 800;
}

.candidate-panel header p,
.explanation-panel header p,
.version-list header p,
.version-diff header p,
.machine-master-panel header p {
  margin-top: 5px;
  color: #64748b;
  font-size: 11px;
}

.selected-order-summary {
  display: grid;
  min-height: 99px;
  grid-template-columns: auto minmax(0, 1fr) minmax(400px, 1fr);
  align-items: center;
  gap: 20px;
  margin: 0 20px 12px;
  border: 1px solid #dbe5e8;
  border-radius: 11px;
  background: #f7fafa;
  padding: 14px 16px;
}

.priority-chip {
  display: inline-flex;
  height: 28px;
  align-items: center;
  border-radius: 999px;
  background: #fff4d8;
  padding: 0 11px;
  color: #b45309;
  font-size: 11px;
  font-weight: 800;
}

.selected-order-summary h3 {
  color: #0f172a;
  font-size: 19px;
  font-weight: 800;
}

.selected-order-summary p {
  margin-top: 5px;
  overflow: hidden;
  color: #64748b;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selected-order-summary dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px 16px;
}

.selected-order-summary dt {
  color: #64748b;
  font-size: 9px;
}

.selected-order-summary dd {
  margin-top: 4px;
  color: #0f172a;
  font-size: 11px;
  font-weight: 800;
}

.candidate-calendar {
  display: grid;
  min-height: 39px;
  grid-template-columns: repeat(7, 1fr);
  margin: 0 20px 0 252px;
  border-bottom: 1px solid #e8eef0;
  color: #64748b;
  font-size: 9px;
  text-align: center;
}

.candidate-calendar span {
  display: flex;
  align-items: center;
  justify-content: center;
  border-left: 1px solid #e8eef0;
}

.candidate-list {
  min-height: 0;
  flex: 1;
  margin: 0 20px;
  overflow-y: auto;
}

.candidate-list-item {
  margin: 0;
  padding: 0;
}

.candidate-row {
  display: grid;
  width: 100%;
  min-height: 116px;
  grid-template-columns: 142px 104px minmax(0, 1fr);
  align-items: center;
  border: 0;
  border-bottom: 1px solid #e8eef0;
  background: #fff;
  color: #334155;
  text-align: left;
}

.candidate-row:nth-child(even) {
  background: #fbfcfc;
}

.candidate-row--selected {
  background: #eefbf8 !important;
  box-shadow: inset 3px 0 0 #14b8a6;
}

.candidate-row--blocked {
  background: #fffafa;
}

.candidate-row--manual {
  background: #fffbeb;
}

.candidate-row:focus-visible {
  box-shadow: inset 0 0 0 2px #0f766e;
  outline: none;
}

.candidate-machine {
  display: grid;
  gap: 4px;
  padding-left: 16px;
}

.candidate-machine strong {
  color: #0f766e;
  font-size: 18px;
}

.candidate-row--blocked .candidate-machine strong {
  color: #b91c1c;
}

.candidate-row--manual .candidate-machine strong {
  color: #b45309;
}

.candidate-rank {
  width: fit-content;
  border-radius: 999px;
  background: #e6f7f4;
  padding: 2px 6px;
  color: #0f766e !important;
  font-size: 9px !important;
  font-weight: 800;
}

.candidate-row--manual .candidate-rank {
  background: #fff4d8;
  color: #92400e !important;
}

.candidate-row--blocked .candidate-rank {
  background: #feecec;
  color: #b91c1c !important;
}

.candidate-machine span {
  color: #0f172a;
  font-size: 11px;
  font-weight: 700;
}

.candidate-machine small {
  color: #64748b;
  font-size: 10px;
}

.candidate-verdict {
  display: grid;
  gap: 7px;
}

.candidate-verdict > span {
  width: fit-content;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 800;
}

.verdict-pass {
  background: #eaf8ee;
  color: #15803d;
}

.verdict-manual {
  background: #fff4d8;
  color: #92400e;
}

.verdict-fail {
  background: #feecec;
  color: #dc2626;
}

.candidate-verdict strong {
  font-size: 10px;
}

.candidate-window {
  position: relative;
  display: flex;
  height: 100%;
  align-items: center;
  overflow: hidden;
  border-left: 1px solid #e8eef0;
  background: #fbfcfc;
}

.existing-task {
  position: absolute;
  top: 21px;
  left: 7px;
  border-radius: 5px;
  background: #cbd5e1;
  padding: 6px 12px;
  color: #334155;
  font-size: 10px;
  font-weight: 700;
}

.candidate-placement {
  display: block;
  overflow: hidden;
  border-radius: 6px;
  background: #0f766e;
  padding: 9px 12px;
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-placement--blocked {
  border: 1px solid #fca5a5;
  background: #feecec;
  color: #b91c1c;
  text-align: center;
}

.candidate-placement--manual {
  border: 1px solid #f59e0b;
  background: #b45309;
}

.recommendation-request-state {
  display: flex;
  min-height: 92px;
  align-items: center;
  gap: 12px;
  margin: 4px 20px 12px;
  border: 1px dashed #9fc4c7;
  border-radius: 10px;
  background: #f0fdfa;
  padding: 16px;
  color: #0f766e;
}

.recommendation-request-state > svg {
  width: 24px;
  height: 24px;
  flex: none;
}

.recommendation-request-state > div {
  display: grid;
  flex: 1;
  gap: 4px;
}

.recommendation-request-state strong {
  color: #0f172a;
  font-size: 12px;
}

.recommendation-request-state span {
  color: #64748b;
  font-size: 10px;
}

.recommendation-request-state button {
  min-height: 34px;
  border: 1px solid currentcolor;
  border-radius: 8px;
  background: #fff;
  padding: 0 12px;
  color: inherit;
  font: inherit;
  font-size: 10px;
  font-weight: 800;
}

.recommendation-request-state--error {
  border-color: #fca5a5;
  background: #fffafa;
  color: #b91c1c;
}

.recommendation-request-state__spinner {
  animation: recommendation-spin 0.85s linear infinite;
}

@keyframes recommendation-spin {
  to { transform: rotate(360deg); }
}

.explanation-panel {
  overflow-y: auto;
  padding-bottom: 14px;
}

.recommendation-badge {
  border-radius: 999px;
  background: #eaf8ee;
  padding: 6px 10px;
  color: #15803d;
  font-size: 10px;
  font-weight: 800;
}

.recommendation-badge--blocked {
  background: #feecec;
  color: #dc2626;
}

.recommendation-badge--manual {
  background: #fff4d8;
  color: #92400e;
}

.recommendation-basis {
  display: grid;
  gap: 4px;
  margin: 0 20px 14px;
  border: 1px solid #dbe5e8;
  border-radius: 9px;
  background: #f8fafc;
  padding: 10px 12px;
  color: #64748b;
  font-size: 9px;
  line-height: 1.5;
}

.recommendation-basis strong {
  color: #b45309;
}

.capacity-card {
  margin: 0 20px 16px;
  border: 1px solid #dbe5e8;
  border-radius: 10px;
  background: #f7fafa;
  padding: 14px 16px;
}

.capacity-card h3,
.constraint-section h3,
.score-section h3,
.required-data h3,
.rule-weights h3 {
  margin-bottom: 10px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
}

.capacity-card > div:not(.capacity-track) {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  color: #64748b;
  font-size: 10px;
}

.capacity-card strong {
  color: #0f172a;
  font-size: 10px;
}

.capacity-card small {
  color: #64748b;
  font-size: 10px;
}

.capacity-card__warning {
  color: #d97706 !important;
}

.capacity-track,
.score-track,
.completeness-track {
  display: block;
  overflow: hidden;
  border-radius: 999px;
  background: #e2e8f0;
}

.capacity-track {
  height: 10px;
  margin: 8px 0 14px 100px;
}

.capacity-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #15803d;
}

.capacity-track span.capacity-track__danger {
  background: #dc2626;
}

.capacity-unavailable {
  margin: 7px 0 12px 100px;
  color: #b45309;
  font-size: 10px;
  font-weight: 700;
}

.capacity-net-weight {
  margin: 5px 0 10px 100px;
  color: #64748b;
  font-size: 10px;
  line-height: 1.5;
}

.constraint-section,
.score-section {
  margin: 0 20px 14px;
}

.constraint-section ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.constraint-section li {
  display: grid;
  min-height: 41px;
  grid-template-columns: 114px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid #e8eef0;
  color: #64748b;
  font-size: 10px;
}

.constraint-section li small {
  overflow: hidden;
  color: #334155;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.constraint-status {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border-radius: 999px;
  padding: 3px 7px;
  font-size: 9px;
  font-weight: 800;
}

.constraint-status svg {
  width: 11px;
  height: 11px;
}

.constraint-status--pass { background: #eaf8ee; color: #15803d; }
.constraint-status--fail { background: #feecec; color: #dc2626; }
.constraint-status--unknown { background: #fff4d8; color: #92400e; }
.constraint-status--override { background: #f2ecff; color: #7c3aed; }

.score-row {
  display: grid;
  min-height: 30px;
  grid-template-columns: 150px minmax(0, 1fr) 44px;
  align-items: center;
  gap: 10px;
  color: #64748b;
  font-size: 10px;
}

.score-row > span:first-child {
  display: grid;
  gap: 2px;
}

.score-row > span:first-child small {
  overflow: hidden;
  color: #94a3b8;
  font-size: 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.score-section__advisory {
  margin-bottom: 8px;
  border-radius: 7px;
  background: #fff4d8;
  padding: 8px 10px;
  color: #92400e;
  font-size: 9px;
  line-height: 1.5;
}

.score-section--blocked p {
  border-radius: 8px;
  background: #fff4d8;
  padding: 10px 12px;
  color: #92400e;
  font-size: 10px;
  font-weight: 700;
}

.score-row strong {
  color: #334155;
  text-align: right;
}

.score-row strong.score-value--negative {
  color: #dc2626;
}

.score-track {
  height: 9px;
}

.score-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.score-fill--red { background: #dc2626; }
.score-fill--teal { background: #0f766e; }
.score-fill--blue { background: #2563eb; }
.score-fill--violet { background: #7c3aed; }
.score-fill--amber { background: #d97706; }
.score-fill--green { background: #15803d; }

.transition-explanation {
  margin: 0 20px 14px;
}

.transition-explanation h3 {
  margin-bottom: 10px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
}

.transition-explanation dl {
  overflow: hidden;
  border: 1px solid #dbe5e8;
  border-radius: 9px;
}

.transition-explanation dl > div {
  display: grid;
  grid-template-columns: 105px minmax(0, 1fr);
  gap: 10px;
  border-bottom: 1px solid #e8eef0;
  padding: 9px 11px;
  font-size: 9px;
  line-height: 1.5;
}

.transition-explanation dl > div:last-child {
  border-bottom: 0;
}

.transition-explanation dt {
  color: #64748b;
}

.transition-explanation dd {
  color: #334155;
  font-weight: 700;
}

.explanation-warning {
  display: flex;
  min-height: 36px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 0 20px;
  border-radius: 8px;
  background: #fff4d8;
  color: #92400e;
  font-size: 9px;
  font-weight: 700;
}

.explanation-warning svg {
  width: 14px;
  height: 14px;
}

.versions-workspace {
  display: grid;
  height: calc(100vh - 261px);
  min-height: 650px;
  grid-template-columns: minmax(0, 1.55fr) minmax(420px, 0.9fr);
  gap: 20px;
}

.phase2-fallback-boundary {
  grid-column: 1 / -1;
  display: grid;
  min-height: 320px;
  place-items: center;
  align-content: center;
  gap: 10px;
  padding: 32px;
  border: 1px dashed #cbd5e1;
  border-radius: 16px;
  color: #64748b;
  text-align: center;
  background: #fff;
}

.phase2-fallback-boundary > svg {
  width: 32px;
  color: #b45309;
}

.phase2-fallback-boundary h2,
.phase2-fallback-boundary p {
  margin: 0;
}

.phase2-fallback-boundary h2 {
  color: #0f172a;
  font-size: 20px;
}

.machine-master-edit {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid #99f6e4;
  border-radius: 9px;
  padding: 0 12px;
  color: #0f766e;
  background: #f0fdfa;
  font-size: 12px;
  font-weight: 800;
}

.machine-master-edit svg {
  width: 15px;
}

.machine-master-edit:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.version-list > header,
.version-diff > header {
  border-bottom: 1px solid #e8eef0;
}

.version-list > header > span {
  border-radius: 999px;
  background: #eaf1ff;
  padding: 5px 9px;
  color: #2563eb;
  font-size: 10px;
  font-weight: 800;
}

.version-card {
  display: grid;
  min-height: 94px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  margin: 14px 18px 0;
  border: 1px solid #dbe5e8;
  border-radius: 10px;
  padding: 14px;
}

.version-card--current {
  border-color: #5eead4;
  background: #eefbf8;
}

.version-icon {
  display: flex;
  width: 42px;
  height: 42px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: #e6f7f4;
  color: #0f766e;
}

.version-icon svg {
  width: 20px;
  height: 20px;
}

.version-card strong {
  color: #0f172a;
  font-size: 13px;
}

.version-card p {
  margin-top: 6px;
  color: #64748b;
  font-size: 10px;
}

.version-state {
  border-radius: 999px;
  background: #e6f7f4;
  padding: 5px 9px;
  color: #0f766e;
  font-size: 9px;
  font-weight: 800;
}

.version-state--published {
  background: #eaf8ee;
  color: #15803d;
}

.version-state--archived {
  background: #eef2f7;
  color: #64748b;
}

.version-diff > header svg {
  width: 26px;
  height: 26px;
  color: #0f766e;
}

.diff-kpis {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 18px;
}

.diff-kpis span {
  display: grid;
  justify-items: center;
  gap: 5px;
  border: 1px solid #dbe5e8;
  border-radius: 10px;
  background: #f8fafc;
  padding: 14px;
}

.diff-kpis strong {
  color: #0f172a;
  font-size: 22px;
}

.diff-kpis small {
  color: #64748b;
  font-size: 9px;
}

.version-diff ul {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0 18px;
  list-style: none;
}

.version-diff li {
  display: flex;
  min-height: 46px;
  align-items: center;
  gap: 9px;
  border: 1px solid #e8eef0;
  border-radius: 9px;
  padding: 0 12px;
  color: #475569;
  font-size: 10px;
}

.version-diff li svg {
  width: 15px;
  height: 15px;
  flex: none;
  color: #0f766e;
}

.version-diff > button {
  display: flex;
  height: 42px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin: 20px 18px;
  border: 0;
  border-radius: 9px;
  background: #0f766e;
  padding: 0 15px;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
}

.version-diff > button svg {
  width: 15px;
  height: 15px;
}

.masters-workspace {
  display: grid;
  height: calc(100vh - 261px);
  min-height: 650px;
  grid-template-columns: minmax(0, 1.7fr) minmax(470px, 1fr);
  gap: 20px;
}

.machine-master-panel > header {
  min-height: 80px;
  border-bottom: 1px solid #e8eef0;
}

.machine-master-panel > header > span {
  border-radius: 999px;
  background: #eaf1ff;
  padding: 5px 9px;
  color: #2563eb;
  font-size: 10px;
  font-weight: 800;
}

.machine-master-panel > header label {
  margin-left: auto;
}

.machine-master-panel > header input,
.machine-master-panel > header select {
  height: 40px;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  font-size: 10px;
}

.machine-master-panel > header input {
  width: 240px;
  padding: 0 11px;
}

.machine-master-panel > header select {
  padding: 0 11px;
}

.machine-table-scroll {
  flex: 1;
  overflow: auto;
  outline: none;
}

.machine-table-scroll:focus-visible {
  box-shadow: inset 0 0 0 3px rgb(20 184 166 / 20%);
}

.machine-master-panel table {
  width: 100%;
  min-width: 960px;
  border-collapse: collapse;
  color: #334155;
  font-size: 11px;
}

.machine-master-panel th {
  height: 46px;
  background: #f1f6f6;
  color: #475569;
  font-size: 10px;
  text-align: left;
}

.machine-master-panel th,
.machine-master-panel td {
  padding: 0 9px;
}

.machine-master-panel tbody tr {
  height: 57px;
  border-bottom: 1px solid #edf2f3;
}

.machine-master-panel tbody tr:nth-child(even) {
  background: #fafcfc;
}

.machine-master-panel tbody tr:hover,
.machine-master-panel tbody tr.selected {
  background: #eaf7f5;
}

.machine-master-panel td button {
  border: 0;
  border-radius: 7px;
  background: #e6f7f4;
  padding: 6px 8px;
  color: #0f766e;
  font-weight: 800;
}

.machine-master-panel td .missing {
  border-radius: 999px;
  background: #fff4d8;
  padding: 4px 7px;
  color: #b45309;
  font-weight: 700;
}

.machine-status {
  border-radius: 999px;
  padding: 4px 7px;
  font-weight: 800;
}

.machine-status--running { background: #eaf8ee; color: #15803d; }
.machine-status--idle { background: #eaf1ff; color: #2563eb; }
.machine-status--setup { background: #fff4d8; color: #b45309; }
.machine-status--maintenance,
.machine-status--stopped,
.machine-status--locked { background: #feecec; color: #dc2626; }

.completeness-value {
  display: block;
  color: #64748b;
  font-size: 10px;
  text-align: right;
}

.completeness-track {
  width: 78px;
  height: 8px;
  margin-top: 4px;
}

.completeness-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #d97706;
}

.machine-master-panel > footer {
  display: flex;
  min-height: 50px;
  align-items: center;
  border-top: 1px solid #e8eef0;
  padding: 0 20px;
  color: #64748b;
  justify-content: space-between;
  gap: 14px;
  font-size: 10px;
}

.machine-master-panel > footer button {
  flex: none;
  border: 1px solid #99e1d6;
  border-radius: 8px;
  background: #e6f7f4;
  padding: 6px 10px;
  color: #0f766e;
  font-size: 10px;
  font-weight: 800;
}

.machine-master-panel,
.machine-detail-panel {
  min-height: 0;
}

.machine-master-panel {
  display: flex;
  flex-direction: column;
}

.machine-detail-panel {
  overflow-y: auto;
}

.machine-detail-panel > header strong {
  border-radius: 999px;
  background: #fff4d8;
  padding: 5px 9px;
  color: #b45309;
  font-size: 9px;
}

.machine-detail-panel > header span {
  display: inline-flex;
  margin-top: 6px;
  border-radius: 999px;
  background: #e6f7f4;
  padding: 4px 8px;
  color: #0f766e;
  font-size: 9px;
}

.machine-detail-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 0 20px 18px;
}

.machine-detail-cards span {
  display: grid;
  min-height: 70px;
  align-content: center;
  gap: 7px;
  border: 1px solid #dbe5e8;
  border-radius: 9px;
  background: #f8fafc;
  padding: 10px;
}

.machine-detail-cards small {
  color: #64748b;
  font-size: 10px;
}

.machine-detail-cards strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.required-data,
.rule-weights {
  padding: 0 20px 12px;
}

.required-data > div,
.rule-weights > div {
  display: grid;
  min-height: 50px;
  grid-template-columns: minmax(132px, 1fr) auto minmax(150px, 1fr);
  align-items: center;
  gap: 9px;
  margin-bottom: 7px;
  border: 1px solid #f7d68b;
  border-radius: 9px;
  background: #fff9e9;
  padding: 0 11px;
  font-size: 10px;
}

.required-data > div.complete {
  border-color: #bcebd0;
  background: #f0fdf4;
}

.required-data strong,
.rule-weights strong {
  color: #334155;
}

.required-data span {
  border-radius: 999px;
  background: #d97706;
  padding: 4px 7px;
  color: #fff;
  font-weight: 800;
}

.required-data .complete span {
  background: #15803d;
}

.required-data small,
.rule-weights small {
  color: #64748b;
}

.rule-weights > div {
  min-height: 37px;
  border-color: #e8eef0;
  background: #f8fafc;
}

.rule-weights span {
  border-radius: 999px;
  background: #eaf1ff;
  padding: 3px 7px;
  color: #2563eb;
  font-weight: 800;
}

.factory-boundary {
  display: flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 0 20px 12px;
  border-radius: 8px;
  background: #e6f7f4;
  color: #0f766e;
  font-size: 9px;
  font-weight: 700;
}

.factory-boundary svg {
  width: 14px;
  height: 14px;
}

.config-workspace {
  display: grid;
  height: calc(100vh - 261px);
  min-height: 650px;
  grid-template-columns: minmax(0, 1.7fr) minmax(420px, 0.9fr);
  gap: 20px;
}

.config-primary-panel,
.config-boundary-panel {
  min-height: 0;
  overflow: hidden;
  border: 1px solid #dbe5e8;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 12px 28px -28px rgb(15 23 42 / 24%);
}

.config-primary-panel {
  display: flex;
  flex-direction: column;
}

.config-primary-panel > header,
.config-boundary-panel > header {
  display: flex;
  min-height: 78px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid #e8eef0;
  padding: 0 20px;
}

.config-primary-panel h2,
.config-boundary-panel h2 {
  color: #0f172a;
  font-size: 20px;
  font-weight: 800;
}

.config-primary-panel header p,
.config-boundary-panel header p {
  margin-top: 5px;
  color: #64748b;
  font-size: 11px;
}

.master-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.master-actions > span {
  border-radius: 999px;
  background: #e6f7f4;
  padding: 5px 9px;
  color: #0f766e;
  font-size: 10px;
  font-weight: 800;
}

.master-actions button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  gap: 6px;
  border: 1px solid #bdd3d8;
  border-radius: 8px;
  background: #fff;
  padding: 0 10px;
  color: #155e75;
  font-size: 11px;
  font-weight: 800;
  cursor: pointer;
}

.master-actions button svg {
  width: 14px;
}

.master-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.config-table-scroll {
  flex: 1;
  overflow: auto;
}

.config-table-scroll table {
  width: 100%;
  min-width: 1050px;
  border-collapse: collapse;
  color: #334155;
  font-size: 11px;
}

.config-table-scroll th {
  height: 46px;
  background: #f1f6f6;
  color: #475569;
  font-size: 10px;
  text-align: left;
}

.config-table-scroll th,
.config-table-scroll td {
  padding: 0 12px;
}

.config-table-scroll tbody tr {
  height: 54px;
  border-bottom: 1px solid #edf2f3;
}

.config-table-scroll tbody tr:nth-child(even) {
  background: #fafcfc;
}

.config-table-scroll tbody tr.selected {
  background: #e9f8f5;
  box-shadow: inset 3px 0 #0f766e;
}

.config-table-scroll td button {
  border: 0;
  background: transparent;
  color: #0f5d69;
  font: inherit;
  font-weight: 800;
  cursor: pointer;
}

.config-table-scroll td small {
  display: block;
  margin-top: 4px;
  color: #7b8c9a;
}

.config-table-footer {
  position: sticky;
  bottom: 0;
  display: flex;
  min-width: 1050px;
  min-height: 48px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-top: 1px solid #dce7e9;
  background: rgb(255 255 255 / 96%);
  padding: 0 14px;
  color: #64748b;
  font-size: 11px;
  backdrop-filter: blur(8px);
}

.config-table-footer button {
  min-height: 32px;
  border: 1px solid #9fc4c7;
  border-radius: 7px;
  background: #f0fdfa;
  padding: 0 12px;
  color: #0f766e;
  font: inherit;
  font-weight: 800;
  cursor: pointer;
}

.config-table-footer__pager {
  display: inline-flex;
  gap: 8px;
}

.config-table-footer button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.config-table-scroll .missing {
  color: #b45309;
  font-weight: 800;
}

.config-status {
  border-radius: 999px;
  background: #eaf8ee;
  padding: 4px 7px;
  color: #15803d;
  font-size: 10px;
  font-weight: 800;
}

.config-status--warning {
  background: #fff4d8;
  color: #b45309;
}

.transition-config {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  padding: 20px;
}

.transition-config article {
  border: 1px solid #dbe5e8;
  border-radius: 11px;
  background: #f8fafc;
  padding: 18px;
}

.transition-matrix-editor,
.setup-minutes-editor,
.calendar-verification-card,
.unavailable-window-editor {
  min-width: 0;
}

.transition-matrix-editor > header,
.setup-minutes-editor > header,
.calendar-verification-card > header,
.unavailable-window-editor > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.transition-matrix-editor header p,
.setup-minutes-editor header p,
.calendar-verification-card header p,
.unavailable-window-editor header p {
  margin-top: 5px;
  color: #64748b;
  font-size: 10px;
  line-height: 1.5;
}

.transition-matrix-editor header button,
.setup-minutes-editor header button,
.unavailable-window-editor header button {
  display: inline-flex;
  min-height: 34px;
  flex: none;
  align-items: center;
  gap: 5px;
  border: 1px solid #99e1d6;
  border-radius: 8px;
  background: #e6f7f4;
  padding: 0 11px;
  color: #0f766e;
  font: inherit;
  font-size: 10px;
  font-weight: 800;
}

.transition-matrix-editor header button svg,
.setup-minutes-editor header button svg,
.unavailable-window-editor header button svg {
  width: 14px;
  height: 14px;
}

.transition-matrix-editor__rows,
.setup-minutes-editor__rows {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.transition-matrix-row,
.setup-minutes-editor__rows > div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) minmax(84px, .55fr) 32px;
  align-items: end;
  gap: 8px;
  border-radius: 8px;
  background: #fff;
  padding: 9px;
}

.setup-minutes-editor {
  grid-column: 1 / -1;
}

.setup-minutes-editor__rows > div {
  grid-template-columns: minmax(0, 1fr) minmax(110px, .7fr) minmax(110px, .7fr) 32px;
}

.transition-matrix-row label,
.setup-minutes-editor__rows label,
.calendar-verification-card > label,
.unavailable-window-row label,
.rule-save-panel > label {
  display: grid;
  gap: 4px;
}

.transition-matrix-row label > span,
.setup-minutes-editor__rows label > span,
.calendar-verification-card > label > span,
.unavailable-window-row label > span,
.rule-save-panel > label > span {
  color: #64748b;
  font-size: 9px;
  font-weight: 700;
}

.transition-matrix-row input,
.setup-minutes-editor__rows input,
.calendar-verification-card input,
.unavailable-window-row input,
.unavailable-window-row select,
.rule-save-panel input {
  width: 100%;
  min-width: 0;
  height: 34px;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
  background: #fff;
  padding: 0 9px;
  color: #0f172a;
  font: inherit;
  font-size: 10px;
}

.transition-matrix-row input:disabled,
.setup-minutes-editor__rows input:disabled,
.calendar-verification-card input:disabled,
.unavailable-window-row input:disabled,
.unavailable-window-row select:disabled,
.weight-editor input:disabled {
  cursor: not-allowed;
  background: #f1f5f9;
  color: #64748b;
}

.transition-matrix-row > button,
.setup-minutes-editor__rows > div > button,
.unavailable-window-row > button {
  display: flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 7px;
  background: #feecec;
  color: #b91c1c;
}

.transition-matrix-row > button:disabled,
.setup-minutes-editor__rows > div > button:disabled {
  cursor: not-allowed;
  opacity: .35;
}

.transition-matrix-row > button svg,
.setup-minutes-editor__rows > div > button svg,
.unavailable-window-row > button svg {
  width: 14px;
  height: 14px;
}

.config-readonly-badge {
  width: fit-content;
  border-radius: 999px;
  background: #f1f5f9;
  padding: 4px 8px;
  color: #475569;
  font-size: 9px;
  font-weight: 800;
}

.rule-save-panel {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: minmax(220px, .9fr) minmax(260px, 1fr);
  align-items: end;
  gap: 12px 16px;
  border: 1px solid #99e1d6;
  border-radius: 10px;
  background: #f0fdfa;
  padding: 14px 16px;
}

.rule-save-panel > div:first-child {
  display: grid;
  gap: 4px;
}

.rule-save-panel > div:first-child strong {
  color: #0f172a;
  font-size: 11px;
}

.rule-save-panel > div:first-child span {
  color: #64748b;
  font-size: 9px;
  line-height: 1.5;
}

.rule-save-panel > p {
  grid-column: 1 / -1;
  margin: 0;
  border-radius: 7px;
  background: #feecec;
  padding: 8px 10px;
  color: #b91c1c;
  font-size: 10px;
  font-weight: 700;
}

.rule-save-panel > div:last-child {
  display: flex;
  grid-column: 1 / -1;
  justify-content: flex-end;
  gap: 8px;
}

.rule-save-panel button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  gap: 5px;
  border: 1px solid #9fc4c7;
  border-radius: 8px;
  background: #fff;
  padding: 0 11px;
  color: #0f766e;
  font: inherit;
  font-size: 10px;
  font-weight: 800;
}

.rule-save-panel button svg {
  width: 14px;
  height: 14px;
}

.rule-save-panel button:disabled {
  cursor: not-allowed;
  opacity: .55;
}

.transition-config h3,
.weight-editor strong,
.import-mapping h3 {
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
}

.transition-config article > p {
  margin-top: 6px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.6;
}

.transition-config dl {
  display: grid;
  gap: 8px;
  margin-top: 16px;
}

.transition-config dl div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-radius: 8px;
  background: #fff;
  padding: 11px 12px;
  color: #475569;
  font-size: 11px;
}

.transition-config dd {
  color: #0f766e;
  font-weight: 800;
}

.config-empty-state {
  display: grid;
  flex: 1;
  align-content: center;
  justify-items: center;
  padding: 40px;
  text-align: center;
}

.config-empty-state > svg {
  width: 48px;
  height: 48px;
  color: #0f766e;
}

.config-empty-state h3 {
  margin-top: 16px;
  color: #0f172a;
  font-size: 18px;
}

.config-empty-state p {
  max-width: 540px;
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.7;
}

.config-empty-state button,
.weight-editor > button {
  display: inline-flex;
  height: 40px;
  align-items: center;
  gap: 6px;
  margin-top: 18px;
  border: 1px solid #99e1d6;
  border-radius: 9px;
  background: #e6f7f4;
  padding: 0 14px;
  color: #0f766e;
  font-size: 11px;
  font-weight: 800;
}

.weight-editor {
  overflow-y: auto;
  padding: 18px 20px 24px;
}

.weight-editor__foundation {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
  margin: 12px 0;
  border: 1px solid #dbe5e8;
  border-radius: 9px;
  background: #f8fafc;
  padding: 0 12px;
}

.weight-editor .rule-save-panel {
  margin-top: 14px;
}

.weight-editor__notice {
  margin-bottom: 12px;
  border-radius: 8px;
  background: #fff4d8;
  padding: 10px 12px;
  color: #92400e;
  font-size: 11px;
  line-height: 1.6;
}

.weight-editor label {
  display: grid;
  min-height: 58px;
  grid-template-columns: minmax(0, 1fr) 88px;
  align-items: center;
  gap: 14px;
  border-bottom: 1px solid #e8eef0;
}

.weight-editor label > span {
  display: grid;
  gap: 4px;
}

.weight-editor small {
  color: #64748b;
  font-size: 10px;
}

.weight-editor input {
  width: 88px;
  height: 36px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #f8fafc;
  padding: 0 10px;
  color: #0f172a;
  font-size: 12px;
  font-weight: 800;
}

.weight-editor__foundation .weight-editor__switch {
  grid-column: 1 / -1;
}

.weight-editor input[type='checkbox'] {
  width: 20px;
  height: 20px;
  justify-self: end;
  accent-color: #0f766e;
}

.calendar-rule-editor {
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
}

.calendar-rule-editor > template + * {
  margin-top: 0;
}

.calendar-verification-card,
.unavailable-window-editor {
  border: 1px solid #dbe5e8;
  border-radius: 11px;
  background: #f8fafc;
  padding: 16px;
}

.calendar-verification-card > label {
  max-width: 520px;
  margin-top: 14px;
}

.calendar-verification-card > small {
  display: block;
  margin-top: 7px;
  color: #64748b;
  font-size: 9px;
}

.unavailable-window-editor {
  margin-top: 14px;
}

.unavailable-window-editor__head,
.unavailable-window-row {
  display: grid;
  grid-template-columns: 92px 140px minmax(170px, 1fr) minmax(170px, 1fr) minmax(130px, .8fr) 32px;
  align-items: end;
  gap: 8px;
}

.unavailable-window-editor__head {
  margin-top: 14px;
  padding: 0 9px 6px;
  color: #64748b;
  font-size: 9px;
  font-weight: 800;
}

.unavailable-window-row {
  border-top: 1px solid #e8eef0;
  padding: 9px;
}

.unavailable-window-row label > span {
  display: none;
}

.unavailable-window-editor__empty {
  margin-top: 12px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  padding: 18px;
  color: #64748b;
  font-size: 10px;
  text-align: center;
}

.calendar-rule-editor > .rule-save-panel {
  margin-top: 14px;
}

.import-mapping {
  display: grid;
  gap: 10px;
  overflow-y: auto;
  padding: 18px 20px;
}

.import-mapping article {
  display: grid;
  min-height: 74px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  border: 1px solid #dbe5e8;
  border-radius: 10px;
  padding: 12px 14px;
}

.import-mapping article > svg {
  width: 22px;
  height: 22px;
  color: #0f766e;
}

.import-mapping p {
  margin-top: 4px;
  color: #64748b;
  font-size: 10px;
}

.import-mapping article > span {
  border-radius: 999px;
  background: #eaf1ff;
  padding: 4px 8px;
  color: #2563eb;
  font-size: 10px;
  font-weight: 800;
}

.config-boundary-panel {
  overflow-y: auto;
}

.config-boundary-panel > header {
  justify-content: flex-start;
}

.config-boundary-panel > header > svg {
  width: 28px;
  height: 28px;
  flex: none;
  color: #b45309;
}

.config-boundary-panel ul {
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 18px 20px;
  list-style: none;
}

.config-boundary-panel li {
  display: flex;
  min-height: 46px;
  align-items: center;
  gap: 9px;
  border: 1px solid #e8eef0;
  border-radius: 9px;
  padding: 0 12px;
  color: #475569;
  font-size: 11px;
}

.config-boundary-panel li svg {
  width: 15px;
  height: 15px;
  flex: none;
  color: #0f766e;
}

.config-boundary-panel dl {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 9px;
  padding: 0 20px 18px;
}

.config-boundary-panel dl div {
  display: grid;
  gap: 5px;
  border-radius: 9px;
  background: #f8fafc;
  padding: 12px;
}

.config-boundary-panel dt {
  color: #64748b;
  font-size: 10px;
}

.config-boundary-panel dd {
  color: #0f172a;
  font-size: 15px;
  font-weight: 800;
}

.factory-empty {
  display: grid;
  min-height: 610px;
  align-content: center;
  justify-items: center;
  border: 1px solid #dbe5e8;
  border-radius: 14px;
  background: #fff;
  padding: 50px;
  text-align: center;
}

.factory-empty__icon {
  display: flex;
  width: 64px;
  height: 64px;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  background: #e6f7f4;
  color: #0f766e;
}

.factory-empty__icon svg {
  width: 30px;
  height: 30px;
}

.factory-empty__eyebrow {
  margin-top: 18px;
  color: #0f766e;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.factory-empty h2 {
  margin-top: 8px;
  color: #0f172a;
  font-size: 26px;
  font-weight: 800;
}

.factory-empty > p:not(.factory-empty__eyebrow) {
  max-width: 580px;
  margin-top: 12px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.8;
}

.factory-empty button {
  display: inline-flex;
  height: 42px;
  align-items: center;
  gap: 7px;
  margin-top: 24px;
  border: 0;
  border-radius: 9px;
  background: #0f766e;
  padding: 0 15px;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
}

.factory-empty button svg {
  width: 15px;
  height: 15px;
}

.hub-footnote {
  position: relative;
  z-index: 2;
  margin: 0;
  background: #f4f7f8;
  padding: 7px 28px 10px;
  color: #94a3b8;
  font-size: 9px;
}

.hub-dialog-backdrop {
  position: fixed;
  z-index: 140;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(15 23 42 / 45%);
  padding: 20px;
  backdrop-filter: blur(3px);
}

.hub-dialog {
  width: min(480px, 100%);
  overflow: hidden;
  border: 1px solid #dbe5e8;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 26px 70px -30px rgb(15 23 42 / 60%);
}

.hub-dialog > header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 12px;
  border-bottom: 1px solid #e8eef0;
  padding: 18px;
}

.hub-dialog__icon {
  display: flex;
  width: 38px;
  height: 38px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
}

.hub-dialog__icon svg {
  width: 20px;
  height: 20px;
}

.hub-dialog__icon--success { background: #eaf8ee; color: #15803d; }
.hub-dialog__icon--danger { background: #feecec; color: #dc2626; }
.hub-dialog__icon--warning { background: #fff4d8; color: #b45309; }
.hub-dialog__icon--info { background: #eaf1ff; color: #2563eb; }

.hub-dialog h2 {
  color: #0f172a;
  font-size: 16px;
  font-weight: 800;
}

.hub-dialog header p {
  margin-top: 5px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.6;
}

.hub-dialog header > button {
  display: flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 8px;
  background: #f8fafc;
  color: #64748b;
}

.hub-dialog header > button svg {
  width: 16px;
  height: 16px;
}

.hub-dialog ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 16px 18px;
  list-style: none;
}

.hub-dialog li {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  color: #475569;
  font-size: 10px;
  line-height: 1.6;
}

.hub-dialog li svg {
  width: 13px;
  height: 13px;
  flex: none;
  margin-top: 2px;
  color: #0f766e;
}

.hub-dialog__manual-reason {
  display: grid;
  gap: 6px;
  border-top: 1px solid #e8eef0;
  padding: 14px 18px;
}

.hub-dialog__manual-reason label {
  display: grid;
  gap: 6px;
}

.hub-dialog__manual-reason label span {
  color: #0f172a;
  font-size: 11px;
  font-weight: 800;
}

.hub-dialog__manual-reason textarea {
  width: 100%;
  resize: vertical;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  padding: 9px 10px;
  color: #0f172a;
  font: inherit;
  font-size: 11px;
  line-height: 1.5;
}

.hub-dialog__manual-reason small {
  color: #64748b;
  font-size: 9px;
}

.hub-dialog__manual-reason p {
  margin: 0;
  color: #b91c1c;
  font-size: 10px;
  font-weight: 700;
}

.hub-dialog footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid #e8eef0;
  background: #f8fafc;
  padding: 12px 18px;
}

.hub-dialog footer button {
  height: 36px;
  border: 0;
  border-radius: 8px;
  background: #0f766e;
  padding: 0 15px;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
}

.hub-dialog footer button:disabled {
  cursor: not-allowed;
  opacity: .5;
}

.hub-dialog footer .hub-dialog__secondary {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #475569;
}

@media (max-width: 1360px) {
  .overview-board {
    grid-template-columns: minmax(0, 1fr) 390px;
  }

  .match-grid,
  .masters-workspace,
  .config-workspace {
    grid-template-columns: minmax(0, 1.45fr) minmax(420px, 1fr);
  }

  .selected-order-summary {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .selected-order-summary dl {
    grid-column: 1 / -1;
  }
}

@media (max-width: 1099px) {
  .hub-main {
    padding-right: 16px;
    padding-left: 16px;
  }

  .overview-board,
  .match-grid,
  .versions-workspace,
  .masters-workspace,
  .config-workspace {
    height: auto;
    grid-template-columns: 1fr;
  }

  .overview-board :deep(.order-pool) {
    height: 480px;
    border-top: 1px solid #dbe5e8;
  }

  .candidate-panel,
  .explanation-panel,
  .version-list,
  .version-diff,
  .machine-master-panel,
  .machine-detail-panel {
    min-height: auto;
  }

  .overview-toolbar {
    align-items: flex-start;
  }

  .overview-toolbar__status > span {
    display: none;
  }

  .header-order-chip {
    max-width: 38vw;
  }

  .order-summary-chips {
    overflow-x: auto;
  }
}

@media (max-width: 720px) {
  .hub-main {
    padding: 10px;
  }

  .overview-toolbar,
  .match-toolbar {
    flex-wrap: wrap;
  }

  .header-workbench-toolbar {
    flex-wrap: wrap;
  }

  .master-toolbar {
    flex-wrap: wrap;
  }

  .master-toolbar nav {
    width: 100%;
  }

  .header-order-chip {
    display: none;
  }

  .order-summary-chips {
    width: 100%;
  }

  .overview-chips {
    width: 100%;
    overflow-x: auto;
  }

  .overview-board {
    border-radius: 9px;
  }

  .match-toolbar > span {
    width: 100%;
    margin-right: 0;
  }

  .selected-order-summary {
    grid-template-columns: 1fr;
  }

  .selected-order-summary dl {
    grid-template-columns: repeat(2, 1fr);
  }

  .candidate-calendar {
    display: none;
  }

  .candidate-row {
    grid-template-columns: 105px 90px minmax(420px, 1fr);
  }

  .candidate-list {
    overflow-x: auto;
  }

  .machine-detail-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .transition-config {
    grid-template-columns: 1fr;
  }

  .machine-master-panel > header {
    flex-wrap: wrap;
    padding-top: 12px;
    padding-bottom: 12px;
  }

  .machine-master-panel > header label,
  .machine-master-panel > header input {
    width: 100%;
    margin-left: 0;
  }

  .required-data > div,
  .rule-weights > div {
    grid-template-columns: 1fr auto;
    padding-top: 8px;
    padding-bottom: 8px;
  }

  .required-data small,
  .rule-weights small {
    grid-column: 1 / -1;
  }

  .hub-footnote {
    padding-right: 10px;
    padding-left: 10px;
  }
}
</style>

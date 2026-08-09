export type FactoryId = 'huaxing' | 'huakang-a' | 'huakang-b' | 'huakang-c' | 'huakang-d' | 'huadeng'
export type WorkspaceView = 'plan' | 'timeline' | 'backlog' | 'alerts' | 'history' | 'analytics'
export type ColumnPreset = 'planner' | 'production' | 'fit' | 'full'
export type TaskStatus = 'RUNNING' | 'QUEUED' | 'BLOCKED' | 'COMPLETED' | 'CANCELLED' | 'REVIEW'
export type FitDecision = 'PASS' | 'REVIEW_REQUIRED' | 'FAIL'
export type PlanSliceKey = 'execution' | 'planning'
export type ImportDocumentKind = 'DEMAND_ORDER' | 'PLANNED_SCHEDULE' | 'SYSTEM_ROUND_TRIP' | 'MASTER_DATA'
export type ImportDocumentKindChoice = ImportDocumentKind | 'AUTO'
export type ImportBatchState = 'IDENTIFYING' | 'MAPPING_REQUIRED' | 'PROFILE_REVIEW_PENDING' | 'MASTER_REVIEW_REQUIRED' | 'RESOLUTION_REVIEW_REQUIRED' | 'RECONCILIATION_CONFLICT' | 'PREVIEW_READY' | 'PARTIALLY_CONFIRMED' | 'CONFIRMED' | 'FAILED' | string
export type PlanExportMode = 'SOURCE_COMPATIBLE' | 'SYSTEM_STANDARD'

export interface PlanExportResult {
  blob: Blob
  fileName: string
  auditId: string
  fileSha256: string
  mode: PlanExportMode
  profileId: string
  profileRevision: number
  rendererCode: string
}

export interface ImportIssueRecord {
  id: string
  severity: 'ERROR' | 'WARNING'
  code: string
  message: string
  sheetName: string
  sourceRow: number | null
  fieldName: string
  cellRef: string
  rawValue: string
  blocking: boolean
}

export interface DemandImportRowRecord {
  rowId: string
  source: Record<string, unknown>
  canonical: Record<string, unknown>
  resolutionStatus: string
  resolutionReasons: string[]
  resolvedValues: Record<string, unknown>
  confirmationState: string
  resolutionDigest: string
}

export interface MasterDataImportRowRecord {
  rowId: string
  entityType: string
  source: Record<string, unknown>
  canonical: Record<string, unknown>
  resolutionStatus: string
  confirmationState: string
  activationBlockers: string[]
  rowDigest: string
}

export interface ImportBatchRecord {
  id: string
  factoryId: string
  sourceFileName: string
  sourceFileHash: string
  batchState: ImportBatchState
  previewGeneration: number
  documentKind: ImportDocumentKind
  sourceNamespaceId: string
  profile: Record<string, unknown> | null
  sheetRoles: Array<Record<string, unknown>>
  mapping: Array<Record<string, unknown>>
  scheduledBaselineTasks: Array<Record<string, unknown>>
  backlogOrders: Array<Record<string, unknown>>
  invalidRows: Array<Record<string, unknown>>
  masterDifferences: Array<Record<string, unknown>>
  calculationComparisons: Array<Record<string, unknown>>
  reconciliationActions: Array<Record<string, unknown>>
  demandRows: DemandImportRowRecord[]
  masterDataRows: MasterDataImportRowRecord[]
  resolutionDigest: string
  mappingDraft: Record<string, unknown>
  partialConfirmation: Record<string, unknown>
  planContext: Record<string, unknown>
  actionFingerprint: string
  summary: Record<string, unknown>
  status: 'PREVIEW' | 'PARTIALLY_CONFIRMED' | 'CONFIRMED'
  revision: number
  confirmedPlanId: string
  confirmedPlanRevision: number
  result: Record<string, unknown>
  artifactAvailable: boolean
  artifactExpiresAt: string
  issues: ImportIssueRecord[]
  idempotentReplay: boolean
}

export interface ManualAppendPreviewRecord {
  factoryId: string
  planId: string
  planRevision: number
  orderId: string
  orderRevision: number
  machineId: string
  sequence: number
  decision: FitDecision
  hardFailures: Array<Record<string, unknown>>
  warnings: Array<Record<string, unknown>>
  advisories: Array<Record<string, unknown>>
  plannedQuantity: number
  shiftTargetQuantity: number
  plannedStart: string
  plannedFinish: string
  continuationAnchor: Record<string, unknown>
  calculation: Record<string, unknown>
  ruleRevision: number
  inputFingerprint: string
}

export interface MachineRecord {
  id: string
  code: string
  position: string
  area: string
  aClass: number | null
  aClassRaw: string
  injectionCapacityG: number | null
  armCapabilities: string[]
  fixtureCapabilities: string[]
  processRestrictions: string[]
  machineType: string
  specialMachineType: string
  status: 'available' | 'running' | 'maintenance' | 'offline'
  normalizationStatus: 'COMPLETE' | 'REVIEW_REQUIRED'
}

export interface MoldRecord {
  id: string
  moldNo: string
  name: string
  aClass: number | null
  aClassRaw: string
  netWeightG: number | null
  grossWeightG: number | null
  requiredArmType: string
  requiredFixtureType: string
  materialCode: string
  materialName: string
  colorProfile: string
  processRequirements: string[]
  specialMachineType: string
  normalizationStatus: 'COMPLETE' | 'REVIEW_REQUIRED'
}

export interface OrderRecord {
  id: string
  orderNo: string
  itemNo: string
  productName: string
  moldId: string | null
  orderQuantity: number
  sourceCompletedQuantity: number
  completedQuantity: number
  outstandingQuantity: number
  completionRate: number
  deliveryStartDate: string
  deliveryDueDate: string
  deliverySlackDays: number | null
  priorityCode: 'NORMAL' | 'URGENT' | 'CRITICAL'
  materialReadinessStatus: 'unknown' | 'ready' | 'partial' | 'blocked'
  warehouseText: string
  remark: string
  status: 'BACKLOG' | 'SCHEDULED' | 'COMPLETED' | 'CANCELLED'
  lineage: Record<string, unknown>
  revision: number
}

export interface ScheduleTaskRecord {
  id: string
  planId: string
  machineId: string
  orderId: string
  moldId: string | null
  sequence: number
  status: TaskStatus
  plannedStart: string
  plannedFinish: string
  targetQuantity: number
  reportedQuantity: number
  sourceSheetName: string
  sourceRow: number | null
  locked: boolean
  manualOverrideReason: string
  activeExecution: boolean
  estimatedStart: string
  estimatedFinish: string
  estimatedRemainingShifts: number
  deliverySlackDays: number | null
  revision: number
  setupMinutes?: number
  productionMinutes?: number
  plannedDowntimeMinutes?: number
  changeoverType?: string
  autoScheduleRunId?: string | null
  autoScore?: number | null
  autoExplanation?: Record<string, unknown>
  manualAdjusted?: boolean
  allocatedQuantity?: number
  takeoverSourceCompletedQuantity?: number
  origin?: string
  stableOrderKey?: string
  stableRowKey?: string
  sourceTaskId?: string | null
  inheritedReportCounter?: number
  completedAtClone?: number
  reportEventWatermark?: number
  profileId?: string | null
  profileRevision?: number | null
}

export interface AutoScheduleAssignmentRecord {
  id: string
  orderId: string
  existingTaskId: string | null
  moldId: string | null
  moldCopyNo: number
  machineId: string | null
  sequence: number | null
  plannedStart: string
  plannedFinish: string
  setupMinutes: number
  productionMinutes: number
  plannedDowntimeMinutes: number
  changeoverType: string
  decision: 'PASS' | 'REVIEW_REQUIRED' | 'UNASSIGNED'
  score: number | null
  explanation: Record<string, unknown>
  unassignedReasonCode: string
}

export interface AutoScheduleMetricDelta {
  before: number
  after: number
  change: number
}

export interface AutoScheduleObjectiveWeights {
  tardinessWeight: number
  transitionWeight: number
  classGapWeight: number
  loadBalanceWeight: number
  existingTaskMoveCost: number
}

export interface AutoScheduleGenerationOptions {
  solver: 'HEURISTIC' | 'CP_SAT' | 'AUTO'
  scenarioName: string
  objectiveWeights: AutoScheduleObjectiveWeights
  scenarioGroupId?: string
  alternativeNo?: number
  replayOfRunId?: string | null
}

export interface AutoScheduleRunSummary {
  inputOrderCount: number
  scheduledCount: number
  reviewCount: number
  unassignedCount: number
  movedTaskCount: number
  localImprovementMoveCount: number
  frozenTaskCount: number
  overdue: AutoScheduleMetricDelta
  moldChanges: AutoScheduleMetricDelta
  darkToLightChanges: AutoScheduleMetricDelta
  machineLoads: Array<{ machineId: string; machineCode: string; scheduledMinutes: number; loadRatio: number }>
  solverElapsedMs: number
  solverStatus: 'NOT_RUN' | 'HEURISTIC' | 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE' | 'TIME_LIMIT' | 'UNAVAILABLE'
  objectiveValue: number | null
  bestObjectiveBound: number | null
  fallbackUsed: boolean
  fallbackReason: string
  continuationAnchors?: Array<{
    machineId: string
    startsAt: string
    sources: Array<Record<string, unknown>>
  }>
}

export interface AutoScheduleRunRecord {
  id: string
  factoryId: string
  planId: string
  expectedPlanRevision: number
  ruleRevision: number
  solverType: 'HEURISTIC' | 'CP_SAT'
  requestedSolver: 'HEURISTIC' | 'CP_SAT' | 'AUTO'
  solverVersion: string
  solverStatus: AutoScheduleRunSummary['solverStatus']
  fallbackUsed: boolean
  fallbackReason: string
  scenarioGroupId: string
  scenarioName: string
  alternativeNo: number
  replayOfRunId: string | null
  objectiveWeights: AutoScheduleObjectiveWeights
  status: 'CREATED' | 'VALIDATING' | 'GENERATING_CANDIDATES' | 'SOLVING' | 'SUCCEEDED' | 'PARTIAL' | 'FAILED' | 'CANCELLED' | 'APPLIED'
  horizonStart: string
  horizonEnd: string
  summary: AutoScheduleRunSummary
  errorDetail: string
  createdByName: string
  createdAt: string
  appliedByName: string
  appliedAt: string
  assignments: AutoScheduleAssignmentRecord[]
}

export interface Phase5MetricRecord {
  value: number
  numerator: number
  denominator: number
  unit: string
  sampleCount: number
  formula: string
}

export interface IntegrationStatusRecord {
  sourceType: 'ERP' | 'DEVICE'
  sourceKey: string
  cursor: string
  status: 'ACTIVE' | 'ERROR' | 'NOT_CONFIGURED'
  lastReceivedAt: string
  lastSuccessAt: string
  lastError: string
  eventCount: number
  revision: number
}

export interface SpeedModelRecord {
  id: string
  factoryId: string
  moldId: string
  moldNo: string
  sampleCount: number
  calibratedCycleSeconds: number
  unitsPerCycle: number
  calibratedUnitsPerHour: number
  confidence: number
  status: 'ACTIVE' | 'INSUFFICIENT_DATA'
  sourceWindowStart: string
  sourceWindowEnd: string
  lastObservedAt: string
  revision: number
  updatedAt: string
}

export interface Phase5AnalyticsRecord {
  factoryId: string
  dateFrom: string
  dateTo: string
  generatedAt: string
  planAccuracy: Phase5MetricRecord
  moldChangeCount: Phase5MetricRecord
  overdueRate: Phase5MetricRecord
  machineUtilization: Phase5MetricRecord
  integrationStatuses: IntegrationStatusRecord[]
  speedModels: SpeedModelRecord[]
  deviceInterfaceConfigured: boolean
  notes: string[]
}

export interface EligibilityCheck {
  key: string
  label: string
  decision: FitDecision
  detail: string
}

export interface ScheduleGridRow {
  rowType: 'machine' | 'task'
  id: string
  machine: MachineRecord
  task?: ScheduleTaskRecord
  order?: OrderRecord
  mold?: MoldRecord
  status: string
  sequence: number | string
  position: string
  machineCode: string
  automation: string
  marker: string
  moldA: string
  moldNo: string
  productName: string
  orderNo: string
  itemNo: string
  setQuantity: number | string
  orderQuantity: number | string
  completedQuantity: number | string
  outstandingQuantity: number | string
  progress: number
  targetQuantity: number | string
  shiftCompleted: number | string
  sprueRatio: string
  color: string
  powder: string
  material: string
  netWeightG: number | string
  grossWeightG: number | string
  materialKg: number | string
  unitPrice: number | string
  ratio: string
  orderDate: string
  deliveryStart: string
  deliveryDue: string
  moldChangeRef: string
  colorChangeRef: string
  setupTime: string
  downtime: number | string
  exception: string
  plannedStart: string
  plannedFinish: string
  planMonth: string
  warehouseDate: string
  slack: number | string
  spray: string
  productionDays: number | string
  machineA: string
  shotCapacity: number | string
  fit: FitDecision
  warehouse: string
  remark: string
  shipDate: string
  arm: string
  fixture: string
  priority: string
  materialReadiness: string
}

export interface SchedulingColumnDefinition {
  key: keyof ScheduleGridRow
  title: string
  group: string
  width: number
  presets: ColumnPreset[]
  align?: 'left' | 'center' | 'right'
  frozen?: boolean
}

export interface AuditEvent {
  id: string
  sequence: number
  eventType: string
  entityType: string
  entityId: string
  entityRevision: number
  requestId: string
  actorName: string
  createdAt: string
  detail: Record<string, unknown>
}

export interface SchedulingPlanRecord {
  id: string
  status: string
  revision: number
  ruleRevision: number
  businessDate: string
  basedOnPlanId?: string
  basedOnEventSequence?: number
  basedOnReportWatermark?: number
  exportProfileId?: string | null
  exportProfileRevision?: number | null
  exportProfileFamily?: string
  exportRendererCode?: string
  exportBindingSource?: 'LEGACY_UNKNOWN' | 'SYSTEM_STANDARD' | 'IMPORT_PROFILE' | string
  calculationVersion?: string
}

export type EditableCellKey =
  | 'status'
  | 'targetQuantity'
  | 'shiftCompleted'
  | 'completedQuantity'
  | 'downtime'
  | 'exception'
  | 'plannedStart'
  | 'plannedFinish'
  | 'warehouse'
  | 'remark'

export interface CellDraft {
  taskId: string
  orderId: string
  key: EditableCellKey
  value: string | number
  originalValue: string | number
}

export interface ShiftReportDraft {
  taskId: string
  expectedRevision: number
  reportedQuantity: number
  shiftTargetQuantity: number
  downtimeMinutes: number
  exceptionCode: string
  exceptionDetail: string
  reportedStatus: 'QUEUED' | 'RUNNING' | 'BLOCKED' | 'COMPLETED'
}

export interface MovePreview {
  taskId: string
  targetMachineId: string
  targetSequence: number
  plannedStart: string
  plannedFinish: string
  decision: FitDecision
  explanation: string
  hardFailures: Array<{ label: string; detail: string }>
  warnings: Array<{ label: string; detail: string }>
  setupReview: string
  overrideReason: string
}

export interface RevisionConflict {
  title: string
  message: string
  localValues: Record<string, unknown>
  serverValues: Record<string, unknown>
  retry: (() => Promise<void>) | null
}

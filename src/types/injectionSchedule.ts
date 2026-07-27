export type InjectionArmType = 'none' | 'single' | 'double'

export type InjectionMachineStatus =
  | 'idle'
  | 'running'
  | 'setup'
  | 'maintenance'
  | 'stopped'
  | 'locked'

export type InjectionMachineCapability =
  | 'core_pull'
  | 'double_core_pull'
  | 'deep_nozzle'
  | 'high_pressure'
  | 'two_color'
  | 'automatic_pull'
  | 'submersible'

export type InjectionOrderPriority = 'P0' | 'P1' | 'P2' | 'P3'

export type InjectionTaskSource = 'manual' | 'recommended' | 'auto'

export type InjectionTaskStatus =
  | 'draft'
  | 'published'
  | 'running'
  | 'completed'
  | 'cancelled'

export type DataProvenanceSource =
  | 'workbook_preview'
  | 'manual'
  | 'system'
  | 'derived'
  | 'mock'

export type DataProvenanceConfidence = 'verified' | 'declared' | 'inferred' | 'unknown'

/**
 * Identifies where a preview or master-data record came from without implying
 * that a workbook or mock row has already become authoritative production data.
 */
export interface DataProvenance {
  source: DataProvenanceSource
  confidence: DataProvenanceConfidence
  sourceId: string | null
  sourceFileName: string | null
  sourceFileSha256: string | null
  sheetName: string | null
  sourceRow: number | null
  capturedAt: string | null
  importedAt: string | null
  importedBy: string | null
}

export interface InjectionTimeWindow {
  id: string
  startAt: string
  endAt: string
  reason: string
  kind: 'maintenance' | 'stopped' | 'locked'
}

export type InjectionMaterialRule =
  | {
      id: string
      mode: 'allow_only' | 'deny'
      materialCodes: string[]
      reason: string
    }
  | {
      id: string
      mode: 'requires_screw'
      materialCodes: string[]
      allowedScrewTypes: string[]
      reason: string
    }

export interface InjectionMachine {
  id: string
  factoryId: string
  workshop: 'old' | 'new' | string
  machineNo: string
  machineClass: string
  tonnage: number | null
  speedType: string | null
  armType: InjectionArmType
  /**
   * null means that fixture master data has not been confirmed. An empty array
   * means it has been confirmed that this machine has no supported fixture.
   */
  supportedFixtures: string[] | null
  screwType: string | null
  /**
   * null means capability data is missing. An empty array is a known "none".
   */
  capabilities: InjectionMachineCapability[] | null
  /**
   * null means material restrictions have not been reviewed. An empty array
   * means no material restriction applies.
   */
  materialRules: InjectionMaterialRule[] | null
  maxShotWeightG: number | null
  tieBarWidthMm: number | null
  tieBarHeightMm: number | null
  minMoldThicknessMm: number | null
  maxMoldThicknessMm: number | null
  maxOpeningStrokeMm: number | null
  maxEjectorClearanceMm: number | null
  status: InjectionMachineStatus
  schedulingLocked: boolean
  availableFrom: string | null
  unavailableWindows: InjectionTimeWindow[]
  dataCompleteness: number
  dataQualityFlags: string[]
  provenance: DataProvenance
}

export interface InjectionMold {
  id: string
  factoryId: string
  moldNo: string
  name: string
  recommendedMachineClass: string | null
  minTonnage: number | null
  grossShotWeightG: number | null
  engineeringNetWeightG: number | null
  lengthMm: number | null
  widthMm: number | null
  heightMm: number | null
  moldThicknessMm: number | null
  requiredOpeningStrokeMm: number | null
  requiredEjectorClearanceMm: number | null
  moldWeightKg: number | null
  armRequirement: InjectionArmType
  fixtureRequirements: string[]
  capabilitiesRequired: InjectionMachineCapability[]
  materialCode: string | null
  requiredScrewTypes: string[]
  defaultColor: string | null
  defaultColorRank: number | null
  cavityCount: number | null
  standardCycleSeconds: number | null
  dataQualityFlags: string[]
  provenance: DataProvenance
}

export interface InjectionOrder {
  id: string
  factoryId: string
  orderNo: string
  itemNo: string | null
  moldId: string
  productName: string
  orderShots: number
  producedShots: number
  outstandingShots: number
  targetShotsPerDay: number | null
  grossShotWeightG: number | null
  colorName: string | null
  colorCode: string | null
  colorRank: number | null
  materialCode: string | null
  armRequirement: InjectionArmType | null
  fixtureRequirements: string[]
  capabilitiesRequired: InjectionMachineCapability[]
  orderedAt: string | null
  deliveryStartAt: string | null
  deliveryDueAt: string | null
  warehouseBufferHours: number
  downstreamBufferHours: number
  downstreamProcess: string | null
  downstreamUrgency: number
  priority: InjectionOrderPriority
  status?: 'open' | 'completed' | 'canceled'
  dataQualityFlags: string[]
  sourceWorkbookRow: number | null
  provenance: DataProvenance
}

export type InjectionConstraintCode =
  | 'factory_match'
  | 'machine_status'
  | 'mold_dimensions'
  | 'mold_thickness'
  | 'opening_stroke'
  | 'shot_capacity'
  | 'arm_type'
  | 'fixtures'
  | 'capabilities'
  | 'material_restrictions'

export type InjectionConstraintStatus = 'pass' | 'fail' | 'unknown' | 'override'

export interface InjectionConstraintOverride {
  reason: string
  actorId: string | null
  actorName: string | null
  createdAt: string | null
}

export interface ConstraintResult {
  code: InjectionConstraintCode
  label: string
  status: InjectionConstraintStatus
  /**
   * A blocking result prevents the candidate from being placed automatically.
   * A reviewed override is non-blocking for manual planning.
   */
  blocking: boolean
  /**
   * Overrides remain visible manual exceptions and never authorize an
   * unattended publish. Only an all-pass result permits automatic publishing.
   */
  autoPublishBlocked: boolean
  reason: string
  missingFields: string[]
  actual: unknown
  expected: unknown
  originalStatus: 'fail' | 'unknown' | null
  override: InjectionConstraintOverride | null
}

export interface InjectionConstraintEvaluation {
  results: ConstraintResult[]
  eligible: boolean
  autoPublishAllowed: boolean
  hasUnknownData: boolean
  failureReasons: string[]
}

export interface InjectionSetupProfile {
  moldId: string | null
  productName: string | null
  materialCode: string | null
  colorCode: string | null
  colorRank: number | null
}

export interface InjectionColorTransitionRule {
  fromColorCode: string
  toColorCode: string
  minutes: number
}

export interface InjectionMaterialTransitionRule {
  fromMaterialCode: string
  toMaterialCode: string
  minutes: number
}

export interface InjectionSetupRuleConfig {
  firstTaskSetupMinutes: number
  sameMoldChangeMinutes: number
  differentMoldChangeMinutes: number
  sameMaterialChangeMinutes: number
  differentMaterialChangeMinutes: number
  sameColorChangeMinutes: number
  lightToDarkColorMinutes: number
  darkToLightColorMinutes: number
  unknownColorTransitionMinutes: number
  colorTransitionMatrix: InjectionColorTransitionRule[]
  materialTransitionMatrix: InjectionMaterialTransitionRule[]
}

export interface InjectionSetupOverride {
  colorTransitionMinutes: number
  reason: string
  actorId: string | null
}

export interface InjectionSetupCost {
  totalMinutes: number
  moldChangeMinutes: number
  materialChangeMinutes: number
  colorChangeMinutes: number
  sameMold: boolean
  sameMaterial: boolean
  colorDirection: 'same' | 'light_to_dark' | 'dark_to_light' | 'matrix' | 'unknown'
  reasons: string[]
  dataQualityFlags: string[]
  colorOverride: InjectionSetupOverride | null
}

export interface InjectionScoringWeights {
  dueUrgency: number
  sameMoldMaterial: number
  setupCost: number
  colorTransition: number
  loadBalance: number
  downstreamImpact: number
  exactMatch: number
  splitPenalty: number
  specialHandlingPenalty: number
}

export interface InjectionScoringRuleConfig {
  weights: InjectionScoringWeights
  dueUrgencyHorizonHours: number
  setupCostCeilingMinutes: number
  colorTransitionCeilingMinutes: number
}

export interface InjectionRuleConfig {
  factoryId: string
  shotSafetyFactor: number
  lossRate: number
  schedulableMachineStatuses: InjectionMachineStatus[]
  setup: InjectionSetupRuleConfig
  scoring: InjectionScoringRuleConfig
}

export interface InjectionScoreBreakdown {
  dueUrgency: number
  sameMoldMaterial: number
  setupCost: number
  colorTransition: number
  loadBalance: number
  downstreamImpact: number
  exactMatch: number
  splitPenalty: number
  specialHandlingPenalty: number
}

export interface Recommendation {
  machineId: string
  factoryId: string
  rank: number | null
  eligible: boolean
  autoPublishAllowed: boolean
  score: number | null
  hardConstraints: ConstraintResult[]
  scoreBreakdown: InjectionScoreBreakdown
  setupCost: InjectionSetupCost
  estimatedStartAt: string | null
  estimatedEndAt: string | null
  deliverySlackHours: number | null
  reasons: string[]
}

export interface InjectionScheduleTask {
  id: string
  planVersionId: string
  factoryId: string
  machineId: string
  orderId: string
  /**
   * Formal versions preserve these display values as immutable task snapshots.
   * Preview-only tasks omit them and continue to resolve labels from masters.
   */
  orderNoSnapshot?: string
  productNameSnapshot?: string
  moldCodeSnapshot?: string
  machineCodeSnapshot?: string
  startAt: string
  endAt: string
  plannedShots: number
  setupMinutesBefore: number
  setupReason: string[]
  score: number | null
  scoreBreakdown: InjectionScoreBreakdown
  constraintSnapshot: ConstraintResult[]
  source: InjectionTaskSource
  locked: boolean
  status: InjectionTaskStatus
  provenance: DataProvenance
  /**
   * Phase 1 preview rows predate formal draft sequencing. Formal Phase 2
   * workspaces always return these fields; they remain optional here so an
   * imported workbook preview cannot be mistaken for a persisted task.
   */
  sequence?: number
  splitGroupId?: string | null
  parentTaskId?: string | null
  revision?: number
  changeReason?: string | null
  recommendationContextHash?: string | null
}

export type InjectionMasterKind = 'machine' | 'mold' | 'order'

export type InjectionMasterReadinessStatus = 'ready' | 'incomplete' | 'blocked'

/**
 * Server-derived readiness is authoritative for publishing. The frontend may
 * display dataCompleteness, but must not infer publishability from a percentage.
 */
export interface InjectionMasterReadiness {
  status: InjectionMasterReadinessStatus
  publishReady: boolean
  completeness: number
  blockingCodes: string[]
  missingFields: string[]
  warnings: string[]
  checkedAt: string | null
}

export interface InjectionFormalRecordMetadata {
  id: string
  factoryId: string
  revision: number
  provenance: Record<string, unknown>
  sourceBatchId: string
  createdBy: string
  createdAt: string
  updatedBy: string
  updatedAt: string
}

export type InjectionFormalMachineStatus =
  | 'available'
  | 'maintenance'
  | 'stopped'
  | 'retired'

export interface InjectionMachineRecord extends InjectionFormalRecordMetadata {
  machineCode: string
  machineName: string
  workshop: string
  machineClass: string
  tonnageT: number | null
  processType: string
  screwType?: string
  robotType: string
  fixtureType: string
  maxShotWeightG: number | null
  tieBarXMm: number | null
  tieBarYMm: number | null
  moldThicknessMinMm: number | null
  moldThicknessMaxMm: number | null
  openingStrokeMm: number | null
  ejectorStrokeMm: number | null
  status: InjectionFormalMachineStatus
  availableAt: string
  capabilities: string[]
  materialRules: string[]
  qualityStatus: string
}

export interface InjectionMoldRecord extends InjectionFormalRecordMetadata {
  moldCode: string
  normalizedMoldCode: string
  moldName: string
  machineClass: string
  robotType: string
  fixtureType: string
  lengthMm: number | null
  widthMm: number | null
  heightMm: number | null
  moldWeightKg: number | null
  grossShotWeightG: number | null
  moldThicknessMm?: number | null
  requiredOpeningStrokeMm?: number | null
  requiredScrewType?: string
  cavities: number | null
  cycleSeconds: number | null
  requiredCapabilities: string[]
  materialRules: string[]
  qualityStatus: string
}

export type InjectionFormalOrderStatus = 'open' | 'completed' | 'canceled'

export interface InjectionOrderRecord extends InjectionFormalRecordMetadata {
  naturalKey: string
  orderNo: string
  productCode: string
  productName: string
  moldCode: string
  color: string
  pigment: string
  material: string
  machineClass: string
  orderQty: number
  producedQty: number
  outstandingQty: number
  dailyTargetQty: number | null
  deliveryDueDate: string
  /**
   * Server-normalized scheduling priority. This is the only priority value
   * used for ordering and scheduling decisions; priorityFlag remains the raw
   * workbook/master-data text for traceability and editing.
   */
  priorityCode: InjectionOrderPriority
  priorityFlag: string
  colorRank?: number | null
  downstreamUrgency?: number | null
  warehouseBufferHours?: number
  downstreamBufferHours?: number
  specialHandlingReason?: string
  status: InjectionFormalOrderStatus
  importedAssignedMachineCode: string
  qualityStatus: string
  importedPlanStartAt: string
  importedPlanFinishAt: string
  sourceSheet: string
  sourceRow: number
  sourceValues: Record<string, unknown>
}

export interface InjectionFormalScheduleTask {
  id: string
  factoryId: string
  versionId: string
  orderId: string
  orderNo: string
  productCode: string
  productName: string
  moldId: string | null
  moldCode: string
  machineId: string
  machineCode: string
  sequenceNo: number
  plannedQty: number
  plannedStartAt: string
  plannedFinishAt: string
  setupHours: number
  durationHours: number
  locked: boolean
  splitGroupId: string
  parentTaskId: string
  riskLevel: string
  riskReasons: string[]
  source?: 'import' | 'manual' | 'recommendation' | 'auto' | 'legacy'
  /**
   * Phase 4 execution state comes from production writeback. Running,
   * completed, locked, or otherwise protected tasks are barriers and must not
   * be moved by automatic drafting or local replanning.
   */
  executionStatus?: string
  protected?: boolean
  recommendationScore?: number | null
  scoreBreakdown?: Array<Record<string, unknown>>
  constraintSnapshot?: Array<Record<string, unknown>>
  recommendationContextHash?: string
  revision: number
  /**
   * The authoritative reason lives in the audit event. This transient field is
   * populated while a command is optimistic and is cleared by server refresh.
   */
  changeReason?: string | null
}

export type InjectionImportStatus =
  | 'previewed'
  | 'confirmed'
  | 'rejected'

export type InjectionImportIssueSeverity = 'error' | 'warning' | 'info'

export type InjectionImportEntityKind =
  | 'machine'
  | 'mold'
  | 'order'
  | 'schedule_task'
  | 'calendar'
  | 'mapping'

export type InjectionImportResolutionAction =
  | 'accept'
  | 'map'
  | 'ignore'
  | 'replace'

export interface InjectionImportIssueResolution {
  issueId?: string
  action: InjectionImportResolutionAction
  replacementValue?: unknown
  reason: string
}

export interface InjectionImportIssue {
  id: string
  factoryId: string
  batchId: string
  sourceSheet: string
  sourceRow: number
  severity: InjectionImportIssueSeverity
  code: string
  fieldName: string
  blocking: boolean
  rawValue: string
  message: string
}

export interface InjectionImportBatch {
  id: string
  factoryId: string
  status: InjectionImportStatus
  sourceFileName: string
  sourceContentType: string
  sourceSizeBytes: number
  sourceSha256: string
  parserVersion: string
  detectedSheets: string[]
  draftVersionId: string
  revision: number
  businessDate: string
  summary: Record<string, unknown>
  preview: Record<string, unknown>
  issues: InjectionImportIssue[]
  createdAt: string
  createdBy: string
  createdByName: string
  confirmedAt: string
  confirmedBy: string
  confirmedByName: string
  confirmReason: string
  rejectedAt: string
  rejectedBy: string
  rejectedByName: string
  rejectionReason: string
}

export interface InjectionImportConfirmInput {
  expectedRevision: number
  mode: 'merge'
  businessDate: string
  reason: string
  resolutions: Record<string, unknown>
}

export type InjectionPlanVersionStatus = 'draft' | 'published' | 'superseded'

export interface InjectionPlanVersion {
  id: string
  factoryId: string
  versionNo: number
  name: string
  status: InjectionPlanVersionStatus
  revision: number
  businessDate: string
  planBaseAt: string
  baseVersionId: string | null
  sourceBatchId: string
  rulesSnapshot: Record<string, unknown>
  dataHash: string
  validationHash: string
  summary: Record<string, unknown>
  createdAt: string
  createdBy: string
  createdByName: string
  updatedAt: string
  updatedBy: string
  publishedAt: string
  publishedBy: string
  publishedByName: string
  publishReason: string
  supersededAt: string
}

export interface InjectionScheduleConflict {
  id: string
  runId: string
  versionId: string
  taskId: string
  constraintCode: string
  status: 'pass' | 'fail' | 'unknown'
  severity: string
  blocking: boolean
  message: string
  details: Record<string, unknown>
}

export interface InjectionManualConfirmation {
  confirmed: boolean
  reason: string
  constraintCodes: InjectionConstraintCode[]
}

interface InjectionScheduleOperationBase {
  reason?: string
  manualConfirmation?: InjectionManualConfirmation | null
}

export interface InjectionAssignOperation extends InjectionScheduleOperationBase {
  type: 'assign'
  orderId: string
  machineId: string
  targetIndex?: number
  plannedQty?: number
  recommendationContextHash?: string
}

export interface InjectionMoveOperation extends InjectionScheduleOperationBase {
  type: 'move'
  taskId: string
  machineId: string
  targetIndex?: number
}

export interface InjectionReorderOperation extends InjectionScheduleOperationBase {
  type: 'reorder'
  taskId: string
  targetIndex: number
}

export interface InjectionLockOperation extends InjectionScheduleOperationBase {
  type: 'lock' | 'unlock'
  taskId: string
}

export interface InjectionSplitOperation extends InjectionScheduleOperationBase {
  type: 'split'
  taskId: string
  splitQty: number
  machineId?: string
  targetIndex?: number
}

export interface InjectionRefreshMastersOperation extends InjectionScheduleOperationBase {
  type: 'refresh_masters'
  taskId?: string
}

export type InjectionScheduleOperation =
  | InjectionAssignOperation
  | InjectionMoveOperation
  | InjectionReorderOperation
  | InjectionLockOperation
  | InjectionSplitOperation
  | InjectionRefreshMastersOperation

export interface InjectionScheduleOperationRequest {
  expectedRevision: number
  reason: string
  requestId?: string
  commands: InjectionScheduleOperation[]
}

export interface InjectionValidationResult {
  id: string
  factoryId: string
  versionId: string
  versionRevision: number
  dataHash: string
  resultHash: string
  status: 'passed' | 'blocked'
  blockingCount: number
  warningCount: number
  createdBy: string
  createdByName: string
  createdAt: string
  items: InjectionScheduleConflict[]
}

export interface InjectionScheduleOperationResult {
  version: InjectionPlanVersion
  tasks: InjectionFormalScheduleTask[]
  conflicts: InjectionScheduleConflict[]
  affectedMachineIds: string[]
}

export type InjectionAutomationTriggerType =
  | 'auto_draft'
  | 'urgent_order'
  | 'machine_downtime'
  | 'shift_actual'

export interface InjectionAutomationImpactRow {
  taskId: string
  sourceTaskId: string
  orderId: string
  machineIdBefore: string
  machineIdAfter: string
  sequenceNoBefore: number | null
  sequenceNoAfter: number | null
  plannedQtyBefore: number
  plannedQtyAfter: number
  plannedStartAtBefore: string
  plannedStartAtAfter: string
  plannedFinishAtBefore: string
  plannedFinishAtAfter: string
  setupHoursBefore: number
  setupHoursAfter: number
  etaShiftMinutes: number
  executionStatusBefore: string
  executionStatusAfter: string
}

export interface InjectionAutomationImpact {
  consideredOrderCount: number
  scheduledOrderCount: number
  manualReviewOrderCount: number
  blockedOrderCount: number
  unscheduledOrderIds: string[]
  movedTaskCount: number
  etaDelayedTaskCount: number
  totalEtaShiftMinutes: number
  beforeTaskCount: number
  afterTaskCount: number
  rows: InjectionAutomationImpactRow[]
}

export interface InjectionAutomationRun {
  id: string
  factoryId: string
  sourceVersionId: string
  resultVersionId: string
  triggerType: InjectionAutomationTriggerType
  status: 'previewed' | 'applied'
  sourceRevision: number
  resultRevision: number
  contextHash: string
  reason: string
  requestId: string
  affectedMachineIds: string[]
  affectedOrderIds: string[]
  affectedTaskIds: string[]
  impact: InjectionAutomationImpact
  createdBy: string
  createdByName: string
  createdAt: string
}

export interface InjectionAutomationResult {
  version: InjectionPlanVersion
  tasks: InjectionFormalScheduleTask[]
  conflicts: InjectionScheduleConflict[]
  affectedMachineIds: string[]
  affectedOrderIds: string[]
  affectedTaskIds: string[]
  run: InjectionAutomationRun
}

export interface InjectionAutoDraftInput {
  expectedRevision: number
  reason: string
  name?: string
  orderIds?: string[]
  planningHorizonEndAt?: string
  requestId?: string
  dryRun?: boolean
  expectedContextHash?: string
}

export type InjectionReplanTrigger =
  | {
      type: 'urgent_order'
      orderId: string
      reason: string
    }
  | {
      type: 'machine_downtime'
      machineId: string
      startAt: string
      endAt: string
      reason: string
    }

export interface InjectionReplanScope {
  freezeBeforeAt?: string
  maxAffectedMachines: number
  maxAffectedTasks: number
}

export interface InjectionReplanInput {
  expectedRevision: number
  trigger: InjectionReplanTrigger
  scope: InjectionReplanScope
  reason: string
  requestId?: string
  dryRun?: boolean
  expectedContextHash?: string
}

export type InjectionShiftCode = 'day' | 'night'

export interface InjectionShiftActual {
  id: string
  factoryId: string
  versionId: string
  taskId: string
  sourceVersionId: string
  sourceTaskId: string
  orderId: string
  machineId: string
  shiftDate: string
  shift: InjectionShiftCode
  source: 'manual' | 'workbook'
  legacyShiftCode: '' | 'A' | 'B'
  targetQty: number | null
  actualQty: number
  varianceQty: number | null
  varianceReason: string
  producedBaselineQty: number
  outstandingQtyBefore: number
  outstandingQtyAfter: number
  shortageQty: number
  requestId: string
  revision: number
  correctionCount: number
  createdBy: string
  createdByName: string
  createdAt: string
  correctedBy: string
  correctedByName: string
  correctedAt: string
}

export interface InjectionActualProjection {
  taskId: string
  orderId: string
  machineId: string
  machineCode: string
  plannedQtyBefore: number
  plannedQtyAfter: number
  plannedFinishAtBefore: string
  plannedFinishAtAfter: string
  etaShiftMinutes: number
  shortageQty: number
}

export interface InjectionShiftActualCreateInput {
  versionId: string
  taskId: string
  orderId: string
  machineId: string
  shiftDate: string
  shift: InjectionShiftCode
  source?: 'manual' | 'workbook'
  legacyShiftCode?: '' | 'A' | 'B'
  targetQty?: number | null
  actualQty: number
  varianceReason?: string
  expectedVersionRevision: number
  expectedOrderRevision: number
  reason: string
  requestId: string
}

export interface InjectionShiftActualCorrectionInput {
  expectedRevision: number
  expectedVersionRevision: number
  expectedOrderRevision: number
  actualQty: number
  reason: string
  requestId: string
}

export interface InjectionShiftActualResult {
  actual: InjectionShiftActual
  updatedOrder: InjectionOrderRecord
  version: InjectionPlanVersion
  tasks: InjectionFormalScheduleTask[]
  projections: InjectionActualProjection[]
  affectedMachineIds: string[]
  idempotentReplay: boolean
}

export interface InjectionShiftActualListOptions {
  versionId?: string
  dateFrom?: string
  dateTo?: string
}

export interface InjectionPlanVersionDetail {
  version: InjectionPlanVersion
  tasks: InjectionFormalScheduleTask[]
  conflicts: InjectionScheduleConflict[]
}

export type InjectionVersionTaskChangeType =
  | 'added'
  | 'removed'
  | 'moved'
  | 'rescheduled'
  | 'quantity_changed'

export interface InjectionVersionTaskChange {
  orderId: string
  orderNo: string
  changeType: InjectionVersionTaskChangeType
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
}

export interface InjectionVersionDiff {
  versionId: string
  againstVersionId: string | null
  summary: Record<string, number>
  items: InjectionVersionTaskChange[]
}

export type InjectionRecommendationConstraintStatus = 'pass' | 'fail' | 'unknown'

export interface InjectionRecommendationHardConstraint {
  code: string
  status: InjectionRecommendationConstraintStatus
  blocking: boolean
  message: string
  details: Record<string, unknown>
}

export interface InjectionRecommendationScoreItem {
  code: string
  label: string
  weight: number
  rawScore: number
  weightedScore: number
  explanation: string
}

export interface InjectionRecommendationTransition {
  previousTaskId: string
  nextTaskId: string
  previousMoldCode: string
  nextMoldCode: string
  previousColor: string
  previousColorRank: number | null
  targetColor: string
  targetColorRank: number | null
  nextColor: string
  nextColorRank: number | null
  previousMaterial: string
  nextMaterial: string
  sameMold: boolean
  colorMinutes: number | null
  materialMinutes: number | null
  afterColorMinutes: number | null
  afterMaterialMinutes: number | null
  replacedColorMinutes: number | null
  replacedMaterialMinutes: number | null
  setupMinutesBefore: number
  setupMinutesAfter: number
  replacedSetupMinutes: number
  setupMinutesDelta: number
  colorMatrixMatch: string
  materialMatrixMatch: string
  afterColorMatrixMatch: string
  afterMaterialMatrixMatch: string
  replacedColorMatrixMatch: string
  replacedMaterialMatrixMatch: string
}

export interface InjectionRecommendationEstimate {
  slotStartAt: string
  productionStartAt: string
  finishAt: string
  durationHours: number
  deliverySlackHours: number | null
  downstreamShiftMinutes: number
  skippedUnavailableWindows: Array<Record<string, string>>
}

export interface InjectionMachineRecommendation {
  rank: number | null
  advisoryRank: number | null
  machineId: string
  machineCode: string
  machineName: string
  targetIndex: number
  status: 'eligible' | 'manual_review' | 'blocked'
  eligible: boolean
  requiresManualConfirmation: boolean
  autoPublishAllowed: boolean
  hardConstraints: InjectionRecommendationHardConstraint[]
  score: {
    total: number
    maxTotal: number
    advisory: boolean
    breakdown: InjectionRecommendationScoreItem[]
    transition: InjectionRecommendationTransition
    estimated: InjectionRecommendationEstimate
  } | null
  recommendationContextHash: string
}

export interface InjectionOrderRecommendationResponse {
  factoryId: string
  versionId: string
  versionRevision: number
  orderId: string
  orderRevision: number
  plannedQty: number
  ruleConfigRevision: number
  currentRuleConfigRevision: number
  ruleConfigHash: string
  usesVersionRuleSnapshot: true
  generatedAt: string
  totalCandidates: number
  eligibleCount: number
  manualReviewCount: number
  blockedCount: number
  candidates: InjectionMachineRecommendation[]
}

export interface InjectionTransitionMatrixEntry {
  fromCode: string
  toCode: string
  minutes: number
}

export interface InjectionSetupMinutesEntry {
  machineClass: string
  sameMoldMinutes: number
  moldChangeMinutes: number
}

export interface InjectionScheduleUnavailableWindow {
  scope: 'factory' | 'machine'
  machineId: string
  startAt: string
  endAt: string
  reason: string
}

export interface InjectionScheduleRuleConfigDocument {
  schemaVersion: 1
  shotSafetyFactor: number
  defaultSetupHours: number
  minimumTaskHours: number
  allowMissingDataInDraftWithManualConfirmation: boolean
  availabilityCalendarVerifiedThrough: string
  colorRankDarkThreshold: number
  scoringWeights: Record<string, number>
  colorTransitionMatrix: InjectionTransitionMatrixEntry[]
  materialTransitionMatrix: InjectionTransitionMatrixEntry[]
  setupMinutes: InjectionSetupMinutesEntry[]
  unavailableWindows: InjectionScheduleUnavailableWindow[]
}

export interface InjectionScheduleRuleConfigV3 {
  factoryId: string
  config: InjectionScheduleRuleConfigDocument
  revision: number
  updatedBy: string
  updatedAt: string
}

export interface InjectionScheduleRuleConfigUpdateInput {
  expectedRevision: number
  reason: string
  config: InjectionScheduleRuleConfigDocument
}

export interface InjectionFormalRuleConfig {
  factoryId: string
  config: Record<string, unknown>
  revision: number
  updatedBy: string
  updatedAt: string
}

export interface InjectionScheduleWorkspace {
  mode: 'formal'
  factoryId: string
  workspaceRevision: number
  activeVersion: InjectionPlanVersion | null
  versions: InjectionPlanVersion[]
  machines: InjectionMachineRecord[]
  molds: InjectionMoldRecord[]
  orders: InjectionOrderRecord[]
  tasks: InjectionFormalScheduleTask[]
  conflicts: InjectionScheduleConflict[]
  ruleConfig: InjectionFormalRuleConfig
}

export interface InjectionRevisionConflict {
  code: 'revision_conflict'
  message: string
  currentRevision: number
  expectedRevision: number
  entityId: string
}

export interface InjectionDraftCreateInput {
  name: string
  businessDate: string
  baseVersionId: string | null
  planBaseAt: string
}

export interface InjectionVersionPublishInput {
  expectedRevision: number
  validationRunId: string | null
  reason: string
}

export interface InjectionVersionCloneInput {
  name: string
  reason: string
}

type InjectionMachineMutableFields = Omit<
  InjectionMachineRecord,
  keyof InjectionFormalRecordMetadata | 'machineCode'
>
export type InjectionMachineCreateInput = {
  machineCode: string
} & Partial<InjectionMachineMutableFields>
export type InjectionMachineUpdateInput = Partial<
  InjectionMachineMutableFields
>
type InjectionMoldMutableFields = Omit<
  InjectionMoldRecord,
  keyof InjectionFormalRecordMetadata | 'normalizedMoldCode' | 'moldCode'
>
export type InjectionMoldCreateInput = {
  moldCode: string
} & Partial<InjectionMoldMutableFields>
export type InjectionMoldUpdateInput = Partial<
  InjectionMoldMutableFields
>
type InjectionOrderMutableFields = Omit<
  InjectionOrderRecord,
  keyof InjectionFormalRecordMetadata
    | 'naturalKey'
    | 'outstandingQty'
    | 'priorityCode'
    | 'importedPlanStartAt'
    | 'importedPlanFinishAt'
    | 'sourceSheet'
    | 'sourceRow'
    | 'sourceValues'
>
export type InjectionOrderCreateInput = {
  naturalKey?: string | null
} & Partial<InjectionOrderMutableFields>
export type InjectionOrderUpdateInput = Partial<
  InjectionOrderMutableFields
>

/**
 * Phase 1 deliberately transports preview-only data. Keeping this marker in the
 * contract prevents workbook/mock content from being mistaken for a published
 * production schedule.
 */
export interface InjectionPreviewDataset {
  mode: 'preview'
  publishable: false
  id: string
  factoryId: string
  businessDate: string
  planBaseAt: string
  provenance: DataProvenance
  machines: InjectionMachine[]
  molds: InjectionMold[]
  orders: InjectionOrder[]
  tasks: InjectionScheduleTask[]
  recommendations: Record<string, Recommendation[]>
  ruleConfig: InjectionRuleConfig
  dataQualityFlags: string[]
}

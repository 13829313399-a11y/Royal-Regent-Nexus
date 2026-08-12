export type AIPilotAccessStatus =
  | 'DISABLED'
  | 'TLS_REQUIRED'
  | 'CONTROL_REQUIRED'
  | 'PROVIDER_REQUIRED'
  | 'GRANTED'
  | 'UNKNOWN'

export interface AICapabilities {
  enabled: boolean
  available: boolean
  provider: string
  model: string
  streaming: boolean
  vision_enabled: boolean
  conversation_persistence: false
  tool_groups: string[]
  pilot_access: {
    granted: boolean
    status: AIPilotAccessStatus
    read_only: boolean
    max_tool_risk_level?: 'READ_ONLY' | 'PREVIEW_WITH_AUDIT'
  }
}

export interface AIInjectionSchedulingPageContext {
  route_name: 'injection-scheduling-v2'
  path: '/modules/production/injection-scheduling'
  factory_id: string | null
  module_id: 'injection-scheduling'
  selected_entity: null
}

export interface AIInternalQuotePageContext {
  route_name: 'internal-quote-desk-home'
  path: '/modules/sales-business/internal-quote-desk'
  factory_id: string | null
  module_id: 'internal-quote'
  selected_entity: null
}

export interface AIMoldingSamplePageContext {
  route_name: 'molding-sample'
  path: '/modules/molding-sample'
  factory_id: string | null
  module_id: 'molding-sample'
  selected_entity: null
}

export interface AICartonProcurementPageContext {
  route_name: 'carton-procurement'
  path: '/modules/pmc-warehouse/carton-procurement'
  factory_id: string | null
  module_id: 'carton-procurement'
  selected_entity: null
}

export interface AIRawMaterialPageContext {
  route_name: 'raw-material-management'
  path: '/modules/pmc-warehouse/raw-material-management'
  factory_id: string | null
  module_id: 'raw-material'
  selected_entity: null
}

export interface AICustomerOrderPageContext {
  route_name: 'customer-order-center'
  path: '/modules/sales-business/po-schedule-intake'
  factory_id: string | null
  module_id: 'customer-order'
  selected_entity: null
}

export type AIPageContext = AIInjectionSchedulingPageContext
  | AIInternalQuotePageContext
  | AIMoldingSamplePageContext
  | AICartonProcurementPageContext
  | AIRawMaterialPageContext
  | AICustomerOrderPageContext

export type AIMessageRole = 'user' | 'assistant'

export interface AIConversationMessage {
  id: string
  role: AIMessageRole
  text: string
  status: 'complete' | 'streaming' | 'truncated' | 'error' | 'cancelled'
  createdAt: string
}

export interface AIFailure {
  code: string
  message: string
  retryable: boolean
  retryAfterSeconds?: number
}

export interface AIStreamEnvelope {
  schema_version: '1'
  request_id: string
  sequence: number
  type: string
  timestamp: string
  payload: Record<string, unknown>
}

export interface AIToolActivityItem {
  id: string
  label: string
  status: 'running' | 'complete' | 'error'
}

export interface AIEntityLink {
  label: string
  route: string
  query?: Record<string, string>
}

export interface AISourceSummary {
  id: string
  level: 'FORMAL' | 'MODULE_KNOWLEDGE' | 'USER_PROVIDED' | 'MODEL_INFERENCE' | 'UNKNOWN'
  label: string
  factoryId?: string
  updatedAt?: string
  links: AIEntityLink[]
}

export interface AIBusinessResult {
  id: string
  kind: 'generic'
    | 'plan_context'
    | 'backlog'
    | 'internal_quote_list'
    | 'molding_sample_list'
    | 'carton_procurement_list'
    | 'raw_material_master_list'
    | 'raw_material_inventory_list'
    | 'customer_order_capabilities'
    | 'customer_order_export_audit_list'
    | 'scheduling_preview'
    | 'scheduling_comparison'
    | 'action_confirmation'
  title: string
  summary: string
  sourceType: string
  factoryId?: string
  asOf?: string
  truncated?: boolean
  links: AIEntityLink[]
  planContext?: {
    executionPublished: AIPlanSummary | null
    planningDraft: AIPlanSummary | null
    pollingRevision?: number
  }
  backlog?: {
    total?: number
    returned?: number
    sourceScope?: string
    sourceBusinessLabel?: string
  }
  internalQuote?: {
    total: number
    returned: number
    limit: number
    offset: number
    quotes: AIInternalQuoteSummary[]
  }
  moldingSample?: {
    total: number
    returned: number
    limit: number
    offset: number
    orders: AIMoldingSampleSummary[]
  }
  cartonProcurement?: {
    total: number
    returned: number
    limit: number
    offset: number
    orders: AICartonProcurementSummary[]
  }
  rawMaterialMaster?: {
    total: number
    returned: number
    limit: number
    offset: number
    materials: AIRawMaterialMasterSummary[]
  }
  rawMaterialInventory?: {
    total: number
    returned: number
    limit: number
    offset: number
    batches: AIRawMaterialInventorySummary[]
  }
  customerOrderCapabilities?: {
    authoritativeOrderLedger: false
    officialOrderTotalAvailable: false
    supportedOperations: Array<'PREVIEW' | 'CONTROLLED_EXPORT' | 'EXPORT_AUDIT'>
    customers: AICustomerOrderCustomerCapability[]
  }
  customerOrderExportAudits?: {
    returned: number
    limit: number
    offset: number
    audits: AICustomerOrderExportAuditSummary[]
  }
  schedulingPreviews?: {
    candidateLabel: '候选方案，尚未应用'
    comparableSnapshot?: boolean
    comparisonWarning?: string
    runs: AISchedulingPreviewRun[]
  }
  actionConfirmation?: AIActionConfirmation
}

export type AIActionConfirmationStatus = 'PENDING' | 'CONFIRMED' | 'EXECUTED'
  | 'EXPIRED' | 'CANCELLED' | 'STALE' | 'FAILED'

export interface AIActionConfirmation {
  confirmationId: string
  toolName: 'injection_scheduling.apply_preview_run'
  riskLevel: 'CONSEQUENTIAL_WRITE'
  factoryId: string
  entityType: 'auto_schedule_run'
  entityId: string
  entityRevision: number
  argsHash: string
  expiresAt: string
  status: AIActionConfirmationStatus
  createdAt: string
  confirmedAt: string
  executedAt: string
  failureCode: string
  actionSummary: {
    actionType: 'APPLY_INJECTION_AUTO_SCHEDULE_RUN'
    runId: string
    planId: string
    planRevision: number
    ruleRevision: number
    assignmentCount: number
    reviewRequiredCount: number
    effectLabel: '应用到 DRAFT，不会发布生产'
    requiresOverrideReason: boolean
  }
}

export interface AIActionExecutionResult {
  run_id: string
  run_status: 'APPLIED'
  plan_id: string
  plan_revision: number
  plan_status: 'DRAFT'
  audit_sequence: number
  idempotent_replay: boolean
  outcome_label: '已应用到 DRAFT，尚未发布生产'
}

export interface AISchedulingMetricDelta {
  before: number | null
  after: number | null
  change: number | null
}

export interface AISchedulingPreviewMetrics {
  inputOrderCount: number | null
  scheduledCount: number | null
  reviewCount: number | null
  unassignedCount: number | null
  movedTaskCount: number | null
  overdue: AISchedulingMetricDelta
  moldChanges: AISchedulingMetricDelta
  darkToLightChanges: AISchedulingMetricDelta
  loadRatioMin: number | null
  loadRatioMax: number | null
  loadRatioAverage: number | null
  solverElapsedMs: number | null
}

export interface AISchedulingPreviewRun {
  runId: string
  planId: string
  planRevision: number
  ruleRevision: number
  status: 'SUCCEEDED' | 'PARTIAL'
  requestedSolver: 'HEURISTIC' | 'CP_SAT' | 'AUTO'
  actualSolver: 'HEURISTIC' | 'CP_SAT'
  solverStatus: string
  fallbackUsed: boolean
  scenarioGroupId: string
  scenarioName: string
  alternativeNo: number
  horizonStart: string
  horizonEnd: string
  metrics: AISchedulingPreviewMetrics
}

export interface AIInternalQuoteSummary {
  quoteId: string
  quoteNo: string
  customer: string
  statusCode: string
  statusLabel: string
  currentStageCode: string
  currentStageLabel: string
  versionLabel: string
  updatedAt: string
  navigationTarget: 'collaboration' | 'summary'
}

export interface AIMoldingSampleSummary {
  orderId: string
  orderNumber: string
  productName: string
  clientName: string
  status: string
  stage: string
  orderDate: string
  productionFactoryId: string | null
  updatedAt: string
}

export interface AICartonProcurementSummary {
  orderId: string
  orderNo: string
  customerName: string
  contractNo: string
  itemNo: string
  productName: string
  orderDate: string
  dueDate: string
  status: string
  revision: number
  updatedAt: string
}

export interface AIRawMaterialMasterSummary {
  materialId: string
  materialCode: string
  materialName: string
  category: string
  spec: string
  unit: string
  safetyStockKg: number | null
  status: '启用' | '停用'
  updatedAt: string
}

export interface AIRawMaterialInventorySummary {
  batchId: string
  materialName: string
  batchNo: string
  location: string
  initialWeightKg: number
  availableWeightKg: number
  updatedAt: string
}

export interface AICustomerOrderCustomerCapability {
  customerCode: string
  customerName: string
  batchPreviewAvailable: true
  controlledExportAvailable: true
}

export interface AICustomerOrderExportAuditSummary {
  auditId: string
  customerCode: string
  receivedDate: string
  previewSchemaVersion: string
  outputFileName: string
  outputTemplate: string
  confirmedIssueCount: number
  manualOverrideCount: number
  createdAt: string
}

export interface AIPlanSummary {
  planId?: string
  businessDate?: string
  revision?: number
  taskCount?: number
  runningCount?: number
}

export interface AIChatRequestMessage {
  role: AIMessageRole
  content: Array<{
    type: 'input_text'
    text: string
  }>
}

export type AIAttachmentMediaType = 'image/png' | 'image/jpeg' | 'image/webp'

export interface AIRequestAttachment {
  id: string
  media_type: AIAttachmentMediaType
  data_url: string
}

export interface AICloudProcessingConsent {
  accepted: true
  notice_version: 'aliyun-cn-beijing-v1'
  attachment_ids: string[]
}

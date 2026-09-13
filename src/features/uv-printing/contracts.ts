/**
 * 华康A · UV打印管理｜前后端共同契约 v1
 *
 * 事实源：docs/uv-printing/UV_PRINT_SHARED_SPEC.md 第 11 节。
 * 任何字段、枚举或单位调整必须先更新共同规格与 DECISIONS.md，再同步样例、页面与后端。
 *
 * 金额一律为「币种 + Decimal 字符串」，前端数值预览不作为正式入账结果。
 * 对象 ID、货号、订单号、任务名、机号全部是字符串，保留前导零。
 */

export const UV_CONTRACT_VERSION = 'uv-printing/1.0.0' as const

export type UvFactoryId = 'huakang-a'
/** RFC3339，必须带 Z 或明确 offset。 */
export type IsoInstant = string
/** YYYY-MM-DD，上海班次业务日期。 */
export type BusinessDate = string
export type DecimalString = string
export type Id = string

export type ShiftCode = 'day' | 'night'
/** 查询全天时省略 shift；响应 summary 可用 'all' 表示全天。 */
export type ShiftScope = ShiftCode | 'all'

export interface Money {
  currency: string
  amount: DecimalString
}

export type UvDataMode = 'live' | 'sample'
export type UvCoverage = 'complete' | 'partial' | 'no_data'
export type UvWarningTone = 'info' | 'warning' | 'error'

export interface UvWarning {
  code: string
  message: string
  tone?: UvWarningTone
}

export interface UvMeta {
  factory_id: UvFactoryId
  as_of: IsoInstant
  data_mode: UvDataMode
  coverage: UvCoverage
  warnings: UvWarning[]
}

export interface UvResponse<T> {
  meta: UvMeta
  data: T
}

export interface UvPage<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface UvEntity {
  id: Id
  factory_id: UvFactoryId
  version: number
  created_at: IsoInstant
  updated_at: IsoInstant
}

/** 查询作用域。常规查询必须传明确 factory_id，不回落到华康A。 */
export interface UvScope {
  factory_id: UvFactoryId
  business_date?: BusinessDate
  date_from?: BusinessDate
  date_to?: BusinessDate
  shift?: ShiftCode
  machine_id?: Id
  product_id?: Id
  status?: string
  q?: string
  page?: number
  page_size?: number
}

/* ------------------------------------------------------------------ *
 * 质量四分法：reported = good + defective + pending + semi_finished
 * ------------------------------------------------------------------ */

export interface UvQuality {
  reported_qty: number
  good_qty: number
  defective_qty: number
  pending_qty: number
  semi_finished_qty: number
}

export type UvQualityBucket = 'good' | 'defective' | 'pending' | 'semi_finished'
export type UvQualityStatus = 'pending' | 'partial' | 'complete'

/* ------------------------------------------------------------------ *
 * 机台：行政状态、遥测状态、采集新鲜度是三个维度
 * ------------------------------------------------------------------ */

export type UvInkMaterial = 'hard' | 'soft' | 'other'
export type UvAdminStatus = 'normal' | 'maintenance' | 'disabled'
export type UvRuntimeStatus = 'printing' | 'idle' | 'offline' | 'error' | 'unknown'
export type UvFreshness = 'fresh' | 'stale' | 'never_seen'

export interface UvMachineCapabilities {
  /** 适配器是否提供准确进度 */
  progress: boolean
  /** 是否有可信完工信号（三次读不到 UI 不算） */
  exact_completion: boolean
  /** 是否提供分色耗墨 */
  ink_by_color: boolean
  /** 是否有持久稳定作业 ID */
  stable_job_id: boolean
}

export interface UvMachine extends UvEntity {
  code: string
  name: string
  brand: string
  model: string
  ink_material: UvInkMaterial
  admin_status: UvAdminStatus
  runtime_status: UvRuntimeStatus
  freshness: UvFreshness
  last_heartbeat_at: IsoInstant | null
  current_task_name: string | null
  progress_pct: number | null
  connector_id: string | null
  connector_mode: string | null
  capabilities: UvMachineCapabilities
  note: string
}

/* ------------------------------------------------------------------ *
 * 产品、工艺版本、价规版本
 * ------------------------------------------------------------------ */

export interface UvProcessVersion extends UvEntity {
  product_id: Id
  version_label: string
  effective_from: BusinessDate
  material: string
  /** 每板件数，正整数；未确认时必须为 null，不能猜。 */
  pieces_per_board: number | null
  board_seconds: number | null
  width_cm: DecimalString | null
  length_cm: DecimalString | null
  /** 产品计价面积 cm² = 长cm × 宽cm；与机器打印面积、计费面积分开保存。 */
  pricing_area_cm2: DecimalString | null
  machine_area_m2: DecimalString | null
  ink_reference_ml: DecimalString | null
  is_active: boolean
}

export interface UvProduct extends UvEntity {
  product_no: string
  name: string
  customer_name: string
  /** 外部引用单号；未接入上游时手工录入并标记为外部引用。 */
  external_ref: string | null
  external_ref_kind: 'order' | 'quotation' | 'none'
  aliases: string[]
  is_active: boolean
  process_versions: UvProcessVersion[]
}

export type UvRateKind = 'commercial' | 'piece_wage' | 'area'

export interface UvRateVersion extends UvEntity {
  rate_kind: UvRateKind
  product_id: Id | null
  process_version_id: Id | null
  /** 精确机台覆盖优先于价组覆盖，再到标准价。 */
  machine_id: Id | null
  price_group: string | null
  currency: string
  unit_price: DecimalString
  effective_from: BusinessDate
  effective_to: BusinessDate | null
  note: string
}

/* ------------------------------------------------------------------ *
 * 采集作业（设备事实）与来源分配
 * ------------------------------------------------------------------ */

export type UvJobState = 'observed' | 'running' | 'completed' | 'cancelled' | 'uncertain'
export type UvReconciliation =
  | 'unmatched'
  | 'needs_unit'
  | 'ready'
  | 'partially_allocated'
  | 'allocated'
  | 'ignored'
export type UvRawUnit = 'piece' | 'board' | 'cycle' | 'unknown'
export type UvTimeEvidence = 'observed' | 'inferred' | 'unknown'

export interface UvJobInkLine {
  color: string
  ml: DecimalString
}

export interface UvPrintJob extends UvEntity {
  machine_id: Id
  source_job_id: string
  source_event_id: string
  connector_id: string
  generation: string
  raw_task_name: string
  raw_product_name: string | null
  product_id: Id | null
  process_version_id: Id | null
  candidates: Array<{ product_id: Id; reason: string; confidence: number }>
  state: UvJobState
  reconciliation: UvReconciliation
  reconcile_note: string
  started_at: IsoInstant | null
  completed_at: IsoInstant | null
  time_evidence: UvTimeEvidence
  raw_count: DecimalString | null
  raw_unit: UvRawUnit
  suggested_piece_qty: number | null
  available_piece_qty: number | null
  print_time_seconds: number | null
  print_area_m2: DecimalString | null
  ink_total_ml: DecimalString | null
  ink_by_color: UvJobInkLine[]
  resolution: string | null
  color_count: number | null
  duplicate_suspect: boolean
}

export interface UvSourceAllocation extends UvEntity {
  job_id: Id
  report_id: Id
  piece_qty: number
  reversed: boolean
}

export type UvHandoverState = 'reconciled' | 'difference' | 'pending'

export interface UvHandoverRecord extends UvEntity {
  business_date: BusinessDate
  product_id: Id
  product_no: string
  product_name: string
  report_id: Id | null
  reported_qty: number
  received_qty: number
  difference_qty: number
  state: UvHandoverState
  receiver: string
  note: string
}

/* ------------------------------------------------------------------ *
 * 业务报工
 * ------------------------------------------------------------------ */

export type UvReportStatus = 'draft' | 'confirmed' | 'corrected' | 'voided'
export type UvSourceKind = 'manual' | 'device' | 'import' | 'mixed'
export type UvPricingState = 'priced' | 'unpriced'
export type UvPayrollState = 'unpriced' | 'provisional' | 'confirmed'

/** 无相应权限时，服务端完全省略对应字段。 */
export interface UvReportCommercial {
  output_value: Money | null
  area_value: Money | null
  pricing_state: UvPricingState
  /** 计价基准：默认已确认合格件。 */
  basis: 'good_qty' | 'reported_qty' | 'board_count'
  unit_price: DecimalString | null
  rate_version_id: Id | null
}

export interface UvReportPayroll {
  amount: Money | null
  state: UvPayrollState
  piece_wage: DecimalString | null
  rate_version_id: Id | null
  worker_count: number
}

export interface UvReportWorkerShare {
  worker_id: Id
  worker_name: string
  amount: Money | null
  state: UvPayrollState
}

export interface UvReport extends UvEntity, UvQuality {
  business_date: BusinessDate
  shift: ShiftCode
  shift_template_version_id: Id
  machine_id: Id
  product_id: Id
  process_version_id: Id
  product_no: string
  product_name: string
  source_kind: UvSourceKind
  status: UvReportStatus
  quality_status: UvQualityStatus
  worker_ids: Id[]
  worker_names: string[]
  notes: string
  replaces_report_id: Id | null
  correction_reason: string
  allocation_total: number
  commercial?: UvReportCommercial
  payroll?: UvReportPayroll
  worker_shares?: UvReportWorkerShare[]
}

export interface UvCommandMeta {
  factory_id: UvFactoryId
  operation_id: string
  /** 新建 0；更改使用读取到的对象版本。 */
  expected_version: number
}

export interface UvSourceAllocationInput {
  job_id: Id
  piece_qty: number
  job_version: number
}

export interface CreateUvReport extends UvCommandMeta, UvQuality {
  business_date: BusinessDate
  shift: ShiftCode
  shift_template_version_id: Id
  machine_id: Id
  product_id: Id
  process_version_id: Id
  worker_ids: Id[]
  notes: string
  source_allocations: UvSourceAllocationInput[]
  /** 仅附证据，不声明已核实件数。 */
  evidence_job_ids: Id[]
}

export interface UvMutationResult<T> {
  entity: T
  operation_id: string
  replayed: boolean
}

/* ------------------------------------------------------------------ *
 * 驾驶舱摘要（服务端全量过滤后聚合，不求和当前页）
 * ------------------------------------------------------------------ */

export interface UvSummaryCounts {
  enabled_machines: number
  fresh_connected_machines: number
  good_qty: number
  pending_qty: number
  unmatched_jobs: number
  needs_unit_jobs: number
  reports_needing_quality: number
  low_stock_skus: number
  handover_differences: number
}

export interface UvSummary {
  business_date: BusinessDate
  shift: ShiftScope
  counts: UvSummaryCounts
  permissions: string[]
  /** 只有具备成本权限时才返回。 */
  commercial?: {
    output_value: Money | null
    unpriced_report_count: number
    pricing_complete: boolean
  }
}

/* ------------------------------------------------------------------ *
 * 墨水账本
 * ------------------------------------------------------------------ */

export type UvInkMovementKind =
  | 'opening'
  | 'purchase_in'
  | 'issue_out'
  | 'return_in'
  | 'stocktake'
  | 'reversal'

export interface UvInkSku extends UvEntity {
  supplier: string
  material: UvInkMaterial
  color: string
  color_aliases: string[]
  /** 包装容量是 SKU 配置，不能把以后 500ml/瓶 也乘 1000。 */
  package_ml: DecimalString
  location: string
  threshold_ml: DecimalString
  unit_cost: DecimalString | null
  currency: string | null
  is_active: boolean
}

export interface UvInkBalance {
  sku_id: Id
  available_ml: DecimalString
  package_ml: DecimalString
  bottle_equivalent: DecimalString
  threshold_ml: DecimalString
  low_stock: boolean
  cost_pending: boolean
}

export interface UvInkMovement extends UvEntity {
  sku_id: Id
  sku_label: string
  kind: UvInkMovementKind
  occurred_on: BusinessDate
  posted_on: BusinessDate
  quantity_ml: DecimalString
  signed_ml: DecimalString
  bottle_input: DecimalString | null
  unit_cost: DecimalString | null
  amount: Money | null
  cost_pending: boolean
  machine_id: Id | null
  purpose: string
  source_doc: string
  evidence: string
  created_by_name: string
  reverses_movement_id: Id | null
  reversed_by_id: Id | null
  balance_after_ml: DecimalString
}

export interface UvInkIssueInput {
  factory_id: UvFactoryId
  operation_id: string
  sku_id: Id
  quantity_ml: DecimalString
  bottle_input: DecimalString | null
  occurred_on: BusinessDate
  machine_id: Id | null
  purpose: string
  source_doc: string
  created_by_name: string
}

export interface UvInkPurchaseInput extends UvInkIssueInput {
  unit_cost: DecimalString | null
  currency: string | null
}

/* ------------------------------------------------------------------ *
 * 人员、排班、班次质量与工资预览
 * ------------------------------------------------------------------ */

export type UvEmployState = 'active' | 'left'
export type UvWorkerRole = 'operator' | 'foreman' | 'master' | 'assistant'

export interface UvWorkerRef extends UvEntity {
  employee_profile_id: Id | null
  employee_no: string
  display_name: string
  role: UvWorkerRole
  employ_state: UvEmployState
  left_on: BusinessDate | null
  note: string
}

export interface UvShiftTemplate extends UvEntity {
  label: string
  shift: ShiftCode
  start_local: string
  end_local: string
  effective_from: BusinessDate
  effective_to: BusinessDate | null
  /** 班次跨度不是净工作时间；休息与停工需明确记录。 */
  break_minutes: number
  note: string
}

export interface UvAssignment extends UvEntity {
  business_date: BusinessDate
  shift: ShiftCode
  machine_id: Id
  worker_id: Id
  /** 同工作批次等分；跨机兼岗用份额表达，不从班次名单推测。 */
  share: number
  work_batch: string
  note: string
}

export type UvPayrollLineState = UvPayrollState

export interface UvPayrollLine {
  worker_id: Id
  worker_name: string
  employee_no: string
  report_count: number
  good_qty: number
  amount: Money | null
  state: UvPayrollLineState
  allocation_basis: string
  /** 分摊后仍保持合计完全一致。 */
  remainder_adjusted: boolean
  reason: string
}

export interface UvPayrollPreview {
  date_from: BusinessDate
  date_to: BusinessDate
  shift: ShiftScope
  currency: string
  batch_total: Money | null
  lines: UvPayrollLine[]
  unpriced_reports: number
  unassigned_reports: number
  quality_pending_reports: number
  coverage: UvCoverage
  warnings: UvWarning[]
}

/* ------------------------------------------------------------------ *
 * 费用、月参数、定价测算
 * ------------------------------------------------------------------ */

export type UvExpenseCategory =
  | 'equipment'
  | 'tooling'
  | 'material'
  | 'sundry'
  | 'maintenance'
  | 'ink'
  | 'processing'
  | 'rent'
  | 'utilities'
  | 'management_wage'
  | 'night_subsidy'
  | 'recoverable_wage'
  | 'recoverable_paint'

export interface UvExpense extends UvEntity {
  category: UvExpenseCategory
  occurred_on: BusinessDate
  /** 归属期 YYYY-MM；分摊时使用。 */
  period: string
  amount: Money
  machine_id: Id | null
  evidence: string
  source: 'manual' | 'ink_issue' | 'import'
  note: string
  reverses_expense_id: Id | null
}

export interface UvMonthlyPolicy extends UvEntity {
  month: string
  /** 工作日集合由用户明确选择，不采用 26/26/21 默认值作为制度。 */
  working_days: BusinessDate[]
  allocation_method: 'working_days' | 'calendar_days'
  rent: Money | null
  utilities: Money | null
  management_wage: Money | null
  note: string
}

export interface UvPricingInput {
  currency: string
  daily_hours: DecimalString
  board_hours: DecimalString
  pieces_per_board: DecimalString
  labor_cost_per_day: DecimalString
  ink_cost_per_day: DecimalString
  markup_rate: DecimalString
  target_margin_rate: DecimalString
  loss_rate: DecimalString | null
}

export interface UvPricingStep {
  key: string
  label: string
  formula: string
  value: DecimalString | null
  unit: string
}

export interface UvPricingResult {
  input: UvPricingInput
  steps: UvPricingStep[]
  boards_per_day: DecimalString | null
  full_boards_per_day: number | null
  pieces_per_day: DecimalString | null
  direct_unit_cost: DecimalString | null
  markup_price: DecimalString | null
  /** 成本加成 40% 对应的实际毛利率，与目标毛利率报价区分。 */
  markup_implied_margin: DecimalString | null
  target_margin_price: DecimalString | null
  currency: string
  formula_version: string
  not_computable_reason: string | null
  cost_scope: string
  warnings: UvWarning[]
}

export interface UvPricingQuote extends UvEntity {
  label: string
  input: UvPricingInput
  result: UvPricingResult
  product_id: Id | null
  adopted_rate_version_id: Id | null
  created_by_name: string
  note: string
}

/* ------------------------------------------------------------------ *
 * 经营报表
 * ------------------------------------------------------------------ */

export interface UvMetricValue {
  key: string
  label: string
  value: DecimalString | null
  unit: string
  formula: string
  sources: string[]
  note: string
  /** 暂算/待核的指标必须显式说明原因，不能显示为 0。 */
  provisional: boolean
  unpriced: boolean
}

export interface UvReportRow {
  key: string
  label: string
  value: DecimalString | null
  unit: string
  drill_kind: UvDrillKind | null
  drill_ref: string | null
  provisional: boolean
}

export type UvDrillKind =
  | 'reports'
  | 'jobs'
  | 'ink_movements'
  | 'expenses'
  | 'payroll'
  | 'handovers'
  | 'unpriced_reports'

export interface UvDailyProjection {
  business_date: BusinessDate
  good_qty: number
  reported_qty: number
  yield_rate: DecimalString | null
  output_value: Money | null
  payroll_amount: Money | null
  ink_cost: Money | null
  expense_amount: Money | null
  operating_result: Money | null
  unpriced_reports: number
  quality_pending_reports: number
  planned_day_off: boolean
  off_plan_production: boolean
}

export interface UvMonthlyProjection {
  month: string
  months: Array<{
    month: string
    good_qty: number
    reported_qty: number
    /** 月分子合计 / 月分母合计，不平均每天百分比。 */
    yield_rate: DecimalString | null
    output_value: Money | null
    payroll_amount: Money | null
    payroll_ratio: DecimalString | null
    operating_result: Money | null
    result_ratio: DecimalString | null
    cost_coverage: UvCoverage
  }>
  structure: UvReportRow[]
  coverage_note: string
  provisional_reasons: string[]
}

export interface UvDailyReport {
  business_date: BusinessDate
  shift: ShiftScope
  headline: string
  metrics: UvMetricValue[]
  rows: UvReportRow[]
  coverage: UvCoverage
}

export interface UvReportExport {
  kind: string
  file_name: string
  generated_at: IsoInstant
  row_count: number
  /** 导出必须与网页使用同一过滤条件。 */
  scope_label: string
}

/* ------------------------------------------------------------------ *
 * 传输契约
 * ------------------------------------------------------------------ */

export interface UvTransport {
  summary(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvSummary>>
  machines(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvMachine>>>
  jobs(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvPrintJob>>>
  reports(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvReport>>>
  createReport(input: CreateUvReport): Promise<UvResponse<UvMutationResult<UvReport>>>
}

/**
 * 完整的前端消费面：页面只依赖该接口，不直接拼接 HTTP、不读 PocketBase、
 * 不自己维护第二份工资或存货公式。
 */
export interface UvWorkspaceTransport extends UvTransport {
  products(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvProduct>>>
  productDetail(productId: Id, signal?: AbortSignal): Promise<UvResponse<UvProduct>>
  saveProduct(input: UvProductSaveInput): Promise<UvResponse<UvMutationResult<UvProduct>>>
  addProcessVersion(input: UvProcessVersionInput): Promise<UvResponse<UvMutationResult<UvProcessVersion>>>
  rateVersions(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvRateVersion>>>
  saveRateVersion(input: UvRateVersionInput): Promise<UvResponse<UvMutationResult<UvRateVersion>>>

  machineDetail(machineId: Id, scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvMachineDetail>>
  saveMachine(input: UvMachineSaveInput): Promise<UvResponse<UvMutationResult<UvMachine>>>

  reconcileJob(input: UvJobReconcileInput): Promise<UvResponse<UvMutationResult<UvPrintJob>>>
  confirmReport(input: UvReportCommandInput): Promise<UvResponse<UvMutationResult<UvReport>>>
  updateQuality(input: UvQualityCommandInput): Promise<UvResponse<UvMutationResult<UvReport>>>
  correctReport(input: UvCorrectionInput): Promise<UvResponse<UvMutationResult<UvReport>>>
  voidReport(input: UvVoidInput): Promise<UvResponse<UvMutationResult<UvReport>>>

  handovers(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvHandoverRecord>>>
  saveHandover(input: UvHandoverInput): Promise<UvResponse<UvMutationResult<UvHandoverRecord>>>

  inkSkus(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvInkSku>>>
  inkBalances(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvInkBalance>>>
  inkMovements(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvInkMovement>>>
  createInkIssue(input: UvInkIssueInput): Promise<UvResponse<UvMutationResult<UvInkMovement>>>
  createInkPurchase(input: UvInkPurchaseInput): Promise<UvResponse<UvMutationResult<UvInkMovement>>>
  reverseInkMovement(input: UvReverseInput): Promise<UvResponse<UvMutationResult<UvInkMovement>>>

  workers(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvWorkerRef>>>
  shiftTemplates(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvShiftTemplate>>>
  assignments(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvAssignment>>>
  saveAssignments(input: UvAssignmentInput): Promise<UvResponse<UvMutationResult<UvAssignment[]>>>
  payrollPreview(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPayrollPreview>>

  expenses(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvExpense>>>
  createExpense(input: UvExpenseInput): Promise<UvResponse<UvMutationResult<UvExpense>>>
  monthlyPolicy(month: string, scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvMonthlyPolicy | null>>
  saveMonthlyPolicy(input: UvMonthlyPolicyInput): Promise<UvResponse<UvMutationResult<UvMonthlyPolicy>>>

  pricingPreview(input: UvPricingInput): Promise<UvResponse<UvPricingResult>>
  pricingQuotes(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvPricingQuote>>>
  savePricingQuote(input: UvPricingQuoteInput): Promise<UvResponse<UvMutationResult<UvPricingQuote>>>
  adoptPricingQuote(input: UvPricingAdoptInput): Promise<UvResponse<UvMutationResult<UvRateVersion>>>

  dailyReport(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvDailyReport>>
  dailyProjection(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvPage<UvDailyProjection>>>
  monthlyProjection(scope: UvScope, signal?: AbortSignal): Promise<UvResponse<UvMonthlyProjection>>
  exportReport(input: UvExportInput): Promise<UvResponse<UvReportExport>>
  operationResult(operationId: string, scope: UvScope): Promise<UvResponse<UvOperationRecord | null>>
}

export interface UvMachineDetail {
  machine: UvMachine
  jobs: UvPrintJob[]
  reports: UvReport[]
  assignments: UvAssignment[]
  expenses: UvExpense[]
  runtime_windows: UvRuntimeWindow[]
}

export interface UvRuntimeWindow {
  id: Id
  machine_id: Id
  start_at: IsoInstant
  end_at: IsoInstant | null
  duration_minutes: number | null
  kind: 'run' | 'idle' | 'gap'
  job_id: Id | null
  label: string
  evidence: UvTimeEvidence
}

export interface UvProductSaveInput extends UvCommandMeta {
  id?: Id
  product_no: string
  name: string
  customer_name: string
  external_ref: string | null
  external_ref_kind: 'order' | 'quotation' | 'none'
  aliases: string[]
}

export interface UvProcessVersionInput extends UvCommandMeta {
  product_id: Id
  version_label: string
  effective_from: BusinessDate
  material: string
  pieces_per_board: number | null
  board_seconds: number | null
  width_cm: DecimalString | null
  length_cm: DecimalString | null
  machine_area_m2: DecimalString | null
  ink_reference_ml: DecimalString | null
}

export interface UvRateVersionInput extends UvCommandMeta {
  id?: Id
  rate_kind: UvRateKind
  product_id: Id | null
  process_version_id: Id | null
  machine_id: Id | null
  price_group: string | null
  currency: string
  unit_price: DecimalString
  effective_from: BusinessDate
  effective_to: BusinessDate | null
  note: string
}

export interface UvMachineSaveInput extends UvCommandMeta {
  id: Id
  admin_status: UvAdminStatus
  ink_material: UvInkMaterial
  note: string
  enabled: boolean
}

export interface UvJobReconcileInput extends UvCommandMeta {
  job_id: Id
  product_id: Id | null
  process_version_id: Id | null
  confirmed_unit: UvRawUnit
  confirmed_piece_qty: number | null
  note: string
  ignore: boolean
}

export interface UvReportCommandInput extends UvCommandMeta {
  report_id: Id
}

export interface UvQualityCommandInput extends UvCommandMeta {
  report_id: Id
  quality: UvQuality
  reason: string
}

export interface UvCorrectionInput extends UvCommandMeta {
  report_id: Id
  correction: CreateUvReport
  reason: string
}

export interface UvVoidInput extends UvCommandMeta {
  report_id: Id
  reason: string
}

export interface UvHandoverInput extends UvCommandMeta {
  id?: Id
  business_date: BusinessDate
  report_id: Id | null
  product_id: Id
  received_qty: number
  receiver: string
  note: string
}

export interface UvReverseInput extends UvCommandMeta {
  target_id: Id
  reason: string
}

export interface UvAssignmentInput extends UvCommandMeta {
  business_date: BusinessDate
  shift: ShiftCode
  machine_id: Id
  worker_ids: Id[]
  note: string
}

export interface UvExpenseInput extends UvCommandMeta {
  category: UvExpenseCategory
  occurred_on: BusinessDate
  period: string
  currency: string
  amount: DecimalString
  machine_id: Id | null
  evidence: string
  note: string
}

export interface UvMonthlyPolicyInput extends UvCommandMeta {
  month: string
  working_days: BusinessDate[]
  allocation_method: 'working_days' | 'calendar_days'
  rent: Money | null
  utilities: Money | null
  management_wage: Money | null
  note: string
}

export interface UvPricingQuoteInput extends UvCommandMeta {
  id?: Id
  label: string
  product_id: Id | null
  input: UvPricingInput
  note: string
}

export interface UvPricingAdoptInput extends UvCommandMeta {
  quote_id: Id
  rate_kind: UvRateKind
  effective_from: BusinessDate
}

export interface UvExportInput extends UvCommandMeta {
  kind: 'daily' | 'monthly' | 'reports' | 'ink_movements' | 'payroll' | 'expenses'
  scope: UvScope
}

export interface UvOperationRecord {
  operation_id: string
  command: string
  result_kind: string
  result_id: Id | null
  accepted_at: IsoInstant
  summary: string
}

/* ------------------------------------------------------------------ *
 * 权限码：必须由 Codex 在后端注册后才是真实权限。
 * ------------------------------------------------------------------ */

export const UV_PERMISSIONS = {
  read: 'uv_printing:read',
  report: 'uv_printing:report',
  quality: 'uv_printing:quality',
  masterWrite: 'uv_printing:master_write',
  shiftWrite: 'uv_printing:shift_write',
  inkWrite: 'uv_printing:ink_write',
  costRead: 'uv_printing:cost_read',
  costWrite: 'uv_printing:cost_write',
  payrollRead: 'uv_printing:payroll_read',
  payrollWrite: 'uv_printing:payroll_write',
  import: 'uv_printing:import',
  export: 'uv_printing:export',
  close: 'uv_printing:close',
} as const

export type UvPermissionKey = keyof typeof UV_PERMISSIONS
export type UvPermissionCode = (typeof UV_PERMISSIONS)[UvPermissionKey]

export const UV_PERMISSION_CODES: UvPermissionCode[] = Object.values(UV_PERMISSIONS)

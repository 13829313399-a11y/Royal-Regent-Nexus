import type {
  BusinessDate,
  CreateUvReport,
  Id,
  IsoInstant,
  Money,
  ShiftCode,
  ShiftScope,
  UvAssignment,
  UvAssignmentInput,
  UvCorrectionInput,
  UvCoverage,
  UvDailyProjection,
  UvDailyReport,
  UvExpense,
  UvExpenseInput,
  UvExportInput,
  UvHandoverInput,
  UvHandoverRecord,
  UvInkBalance,
  UvInkIssueInput,
  UvInkMovement,
  UvInkPurchaseInput,
  UvInkSku,
  UvJobReconcileInput,
  UvMachine,
  UvMachineDetail,
  UvMachineSaveInput,
  UvMetricValue,
  UvMonthlyPolicy,
  UvMonthlyPolicyInput,
  UvMonthlyProjection,
  UvMutationResult,
  UvOperationRecord,
  UvPage,
  UvPayrollLine,
  UvPayrollPreview,
  UvPricingAdoptInput,
  UvPricingInput,
  UvPricingQuote,
  UvPricingQuoteInput,
  UvPricingResult,
  UvPrintJob,
  UvProcessVersion,
  UvProcessVersionInput,
  UvProduct,
  UvProductSaveInput,
  UvQuality,
  UvQualityCommandInput,
  UvRateVersion,
  UvRateVersionInput,
  UvReport,
  UvReportCommandInput,
  UvReportExport,
  UvResponse,
  UvReverseInput,
  UvRuntimeWindow,
  UvScope,
  UvShiftTemplate,
  UvSourceAllocation,
  UvSummary,
  UvVoidInput,
  UvWarning,
  UvWorkerRef,
  UvWorkspaceTransport,
} from '../contracts'
import { UV_PRICING_FORMULA_VERSION } from '../domain/pricing'
import {
  bottlesFromMl,
  currencyMinorUnits,
  decimalAdd,
  decimalCompare,
  decimalDivide,
  decimalIsZero,
  decimalMultiply,
  decimalRound,
  decimalSum,
  money,
} from '../domain/decimal'
import { computePricing } from '../domain/pricing'
import {
  aggregateDailyRows,
  coverageNotes,
  expenseStructure,
  operatingResult,
  prorationTotals,
} from '../domain/reporting'
import { splitRemainder } from '../domain/decimal'
import { EXPENSE_CATEGORY_LABELS, DRILL_KIND_LABELS } from '../domain/status'
import {
  DEFAULT_SHIFT_TEMPLATES,
  addDays,
  daysInMonth,
  isSunday,
  monthOf,
  shiftMembership,
  splitByShift,
} from '../domain/businessTime'
import {
  SAMPLE_AS_OF,
  SAMPLE_CURRENCY,
  SAMPLE_FACTORY_ID,
  SAMPLE_MONTH,
  sampleAllocations,
  sampleAssignments,
  sampleExpenses,
  sampleHandovers,
  sampleInkMovements,
  sampleInkSkus,
  sampleJobs,
  sampleMachines,
  sampleMonthlyPolicy,
  samplePricingQuotes,
  sampleProducts,
  sampleRateVersions,
  sampleReports,
  sampleShiftTemplates,
  sampleWorkers,
} from './fixtures'
import {
  UV_ERROR_CODES,
  UvError,
  assertScopeFactory,
  assertVersion,
  metaFor,
  nowIso,
  paginate,
  validateDraft,
  validateQualityTotals,
} from './transportSupport'

/**
 * DEV 样例内存事实源。
 *
 * 所有页面共享同一份数据：页面上的新增、核对、更正、失败与重试都会改变这里的
 * 内存事实，并联动汇总、库存余额、工资预览与经营报表。它不是数据库，
 * 也不访问任何真实 UV 接口。
 */

export type {
  UvSampleRole,
  UvSampleRoleProfile,
} from './roles'
export {
  SAMPLE_ROLE_IDS,
  SAMPLE_ROLE_LABELS,
  SAMPLE_ROLE_DESCRIPTIONS,
  SAMPLE_ROLE_PERMISSIONS,
  sampleRoleProfiles,
} from './roles'
import {
  SAMPLE_ROLE_LABELS,
  SAMPLE_ROLE_PERMISSIONS,
  type UvSampleRole,
} from './roles'

interface FailureInjection {
  readFailure: boolean
  writeFailure: boolean
  latencyMs: number
}

export interface UvMemoryStoreState {
  role: UvSampleRole
  failure: FailureInjection
}

export interface UvMemoryStoreApi extends UvWorkspaceTransport {
  /** 当前样例角色权限码。 */
  permissions: string[]
  can(permission: string): boolean
  /** 推进样例时钟，用于演示心跳新鲜度与陈旧状态。 */
  advanceClock(minutes: number): void
  /** 重置回固定种子样例。 */
  reset(): void
  /** 样例数据截止时间。 */
  asOf: string
}

export class UvMemoryStore implements UvMemoryStoreApi {
  private _machines: UvMachine[] = []
  private _products: UvProduct[] = []
  private _rateVersions: UvRateVersion[] = []
  private _jobs: UvPrintJob[] = []
  private _reports: UvReport[] = []
  private _allocations: UvSourceAllocation[] = []
  private _handovers: UvHandoverRecord[] = []
  private _inkSkus: UvInkSku[] = []
  private _inkMovements: UvInkMovement[] = []
  private _workers: UvWorkerRef[] = []
  private _shiftTemplates: UvShiftTemplate[] = []
  private _assignments: UvAssignment[] = []
  private _expenses: UvExpense[] = []
  private _monthlyPolicies: UvMonthlyPolicy[] = []
  private _pricingQuotes: UvPricingQuote[] = []
  private _operations = new Map<string, UvOperationRecord>()
  private _operationBodies = new Map<string, string>()
  private _sequence = 9000

  role: UvSampleRole = 'manager'
  failure: FailureInjection = { readFailure: false, writeFailure: false, latencyMs: 0 }
  /** 服务端“数据截止时间”，刷新时前移，用于演示新鲜度。 */
  asOf: IsoInstant = SAMPLE_AS_OF

  constructor() {
    this.reset()
  }

  reset(): void {
    const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
    this._machines = clone(sampleMachines)
    this._products = clone(sampleProducts)
    this._rateVersions = clone(sampleRateVersions)
    this._jobs = clone(sampleJobs)
    this._reports = clone(sampleReports)
    this._allocations = clone(sampleAllocations)
    this._handovers = clone(sampleHandovers)
    this._inkSkus = clone(sampleInkSkus)
    this._inkMovements = clone(sampleInkMovements)
    this._workers = clone(sampleWorkers)
    this._shiftTemplates = clone(sampleShiftTemplates)
    this._assignments = clone(sampleAssignments)
    this._expenses = clone(sampleExpenses)
    this._monthlyPolicies = [clone(sampleMonthlyPolicy)]
    this._pricingQuotes = clone(samplePricingQuotes)
    this._operations = new Map()
    this._operationBodies = new Map()
    this._sequence = 9000
    this.asOf = SAMPLE_AS_OF
    this.recomputeDerived()
  }

  /* ---------------- 权限与注入 ---------------- */

  get permissions(): string[] {
    return SAMPLE_ROLE_PERMISSIONS[this.role] ?? ['uv_printing:read']
  }

  can(permission: string): boolean {
    return this.permissions.includes(permission)
  }

  /** 取当前可变报工对象；不存在时统一返回 404。 */
  private mutableReport(reportId: Id): UvReport {
    const report = this._reports.find((candidate) => candidate.id === reportId)
    if (!report) {
      throw new UvError(UV_ERROR_CODES.notFound, '报工不存在或已被合并到其他修订。', { status: 404 })
    }
    return report
  }

  private requirePermission(permission: string): void {
    if (!this.can(permission)) {
      throw new UvError(
        UV_ERROR_CODES.forbidden,
        `当前样例角色「${SAMPLE_ROLE_LABELS[this.role] ?? this.role}」没有 ${permission} 权限。`,
        { status: 403 },
      )
    }
  }

  private async gate(read: boolean): Promise<void> {
    if (this.failure.latencyMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.failure.latencyMs))
    }
    if (read && this.failure.readFailure) {
      throw new UvError(UV_ERROR_CODES.serviceUnavailable, '样例读取被注入失败，用于验证错误与重试表现。', {
        status: 503,
        retryable: true,
      })
    }
    if (!read && this.failure.writeFailure) {
      throw new UvError(UV_ERROR_CODES.serviceUnavailable, '样例写入被注入失败，表单内容已保留，可重试。', {
        status: 503,
        retryable: true,
      })
    }
  }

  private wrap<T>(data: T, options: { coverage?: UvCoverage; warnings?: UvWarning[] } = {}): UvResponse<T> {
    return { meta: metaFor({ coverage: options.coverage, warnings: options.warnings, asOf: this.asOf }), data }
  }

  private nextId(prefix: string): string {
    this._sequence += 1
    return `DEMO-${prefix}-${this._sequence}`
  }

  private idempotent<T>(operationId: string, body: unknown, produce: () => UvMutationResult<T>): UvMutationResult<T> {
    if (!operationId) {
      throw new UvError(UV_ERROR_CODES.invalidField, '缺少 operation_id，写入必须携带幂等键。', {
        status: 422,
        fields: { operation_id: '必填' },
      })
    }
    const fingerprint = JSON.stringify(body)
    const existing = this._operations.get(operationId)
    if (existing) {
      if (this._operationBodies.get(operationId) !== fingerprint) {
        throw new UvError(
          UV_ERROR_CODES.operationConflict,
          '同一 operation_id 提交了不同内容，服务端拒绝覆盖原结果。',
          { status: 409 },
        )
      }
      const replay = produce()
      return { ...replay, operation_id: operationId, replayed: true }
    }
    const result = produce()
    this._operations.set(operationId, {
      operation_id: operationId,
      command: 'sample',
      result_kind: 'entity',
      result_id: result.entity && typeof result.entity === 'object' && 'id' in result.entity
        ? String((result.entity as { id: unknown }).id)
        : null,
      accepted_at: nowIso(),
      summary: '样例操作已接受',
    })
    this._operationBodies.set(operationId, fingerprint)
    return { ...result, operation_id: operationId, replayed: false }
  }

  /* ---------------- 派生计算 ---------------- */

  private recomputeDerived(): void {
    // 来源可分配量：原始建议量减去未被冲销的分配量。
    for (const job of this._jobs) {
      const allocated = this._allocations
        .filter((allocation) => allocation.job_id === job.id && !allocation.reversed)
        .reduce((total, allocation) => total + allocation.piece_qty, 0)
      const base = job.suggested_piece_qty ?? 0
      job.available_piece_qty = job.suggested_piece_qty === null ? null : Math.max(0, base - allocated)
      if (job.reconciliation === 'ignored') continue
      if (job.suggested_piece_qty === null) continue
      job.reconciliation = allocated === 0
        ? 'ready'
        : allocated >= base
          ? 'allocated'
          : 'partially_allocated'
    }

    for (const report of this._reports) {
      report.allocation_total = this._allocations
        .filter((allocation) => allocation.report_id === report.id && !allocation.reversed)
        .reduce((total, allocation) => total + allocation.piece_qty, 0)
      report.commercial = this.commercialFor(report)
      report.payroll = this.payrollFor(report)
      report.worker_shares = this.workerSharesFor(report)
    }
  }

  private priceOn(rateKind: UvRateVersion['rate_kind'], productId: Id, processVersionId: Id, machineId: Id, businessDate: BusinessDate) {
    const candidates = this._rateVersions.filter((rate) =>
      rate.rate_kind === rateKind
      && rate.product_id === productId
      && (!rate.process_version_id || rate.process_version_id === processVersionId)
      && rate.effective_from <= businessDate
      && (rate.effective_to === null || businessDate <= rate.effective_to),
    )
    const score = (rate: UvRateVersion) => (rate.machine_id === machineId ? 3 : rate.machine_id === null && rate.price_group ? 2 : rate.machine_id === null ? 1 : 0)
    return candidates.sort((a, b) => score(b) - score(a))[0] ?? null
  }

  private commercialFor(report: UvReport): UvReport['commercial'] {
    const rate = this.priceOn('commercial', report.product_id, report.process_version_id, report.machine_id, report.business_date)
    const areaRate = this.priceOn('area', report.product_id, report.process_version_id, report.machine_id, report.business_date)
    const product = this._products.find((candidate) => candidate.id === report.product_id)
    const processVersion = product?.process_versions.find((candidate) => candidate.id === report.process_version_id)
    const pricedQty = report.good_qty
    const outputValue = rate ? money(rate.currency, decimalRound(decimalMultiply(String(pricedQty), rate.unit_price), 6)) : null
    const areaValue = areaRate && processVersion?.pricing_area_cm2
      ? money(areaRate.currency, decimalRound(decimalMultiply(decimalMultiply(String(pricedQty), processVersion.pricing_area_cm2), areaRate.unit_price), 6))
      : null
    return {
      output_value: outputValue,
      area_value: areaValue,
      pricing_state: rate ? 'priced' : 'unpriced',
      basis: 'good_qty',
      unit_price: rate?.unit_price ?? null,
      rate_version_id: rate?.id ?? null,
    }
  }

  private payrollFor(report: UvReport): UvReport['payroll'] {
    const rate = this.priceOn('piece_wage', report.product_id, report.process_version_id, report.machine_id, report.business_date)
    if (!rate) {
      return {
        amount: null,
        state: 'unpriced',
        piece_wage: null,
        rate_version_id: null,
        worker_count: report.worker_ids.length,
      }
    }
    const amount = decimalRound(decimalMultiply(String(report.good_qty), rate.unit_price), 6)
    const state = report.status === 'confirmed' && report.quality_status === 'complete' ? 'confirmed' : 'provisional'
    return {
      amount: money(rate.currency, amount),
      state,
      piece_wage: rate.unit_price,
      rate_version_id: rate.id,
      worker_count: report.worker_ids.length,
    }
  }

  private workerSharesFor(report: UvReport): UvReport['worker_shares'] {
    const payroll = report.payroll
    if (!payroll || payroll.amount === null || !report.worker_ids.length) return []
    const order = [...report.worker_ids].sort((a, b) => a.localeCompare(b))
    const shares = splitRemainder(payroll.amount.amount, order.length, payroll.amount.currency)
    return order.map((workerId, index) => {
      const worker = this._workers.find((candidate) => candidate.id === workerId)
      return {
        worker_id: workerId,
        worker_name: worker?.display_name ?? workerId,
        amount: money(payroll.amount!.currency, shares[index] ?? '0'),
        state: payroll.state,
      }
    })
  }

  inkBalancesSync(): UvInkBalance[] {
    return this._inkSkus.map((sku) => {
      const movements = this._inkMovements.filter((movement) => movement.sku_id === sku.id)
      const available = movements.reduce((total, movement) => decimalAdd(total, movement.signed_ml), '0')
      const costPending = movements.some((movement) => movement.cost_pending)
      return {
        sku_id: sku.id,
        available_ml: available,
        package_ml: sku.package_ml,
        bottle_equivalent: bottlesFromMl(available, sku.package_ml) ?? '0',
        threshold_ml: sku.threshold_ml,
        low_stock: decimalCompare(available, sku.threshold_ml) < 0,
        cost_pending: costPending,
      }
    })
  }

  private lowStockCount(): number {
    return this.inkBalancesSync().filter((balance) => balance.low_stock).length
  }

  private reportsForScope(scope: UvScope): UvReport[] {
    return this._reports.filter((report) => {
      if (scope.business_date && report.business_date !== scope.business_date) return false
      if (scope.date_from && report.business_date < scope.date_from) return false
      if (scope.date_to && report.business_date > scope.date_to) return false
      if (scope.shift && report.shift !== scope.shift) return false
      if (scope.machine_id && report.machine_id !== scope.machine_id) return false
      if (scope.product_id && report.product_id !== scope.product_id) return false
      if (scope.status && report.status !== scope.status) return false
      if (scope.q) {
        const needle = scope.q.toLowerCase()
        const haystack = `${report.product_no} ${report.product_name} ${report.machine_id} ${report.notes}`.toLowerCase()
        if (!haystack.includes(needle)) return false
      }
      return true
    })
  }

  private effectiveReports(scope: UvScope): UvReport[] {
    return this.reportsForScope(scope).filter((report) => report.status === 'confirmed')
  }

  /* ---------------- 查询 ---------------- */

  async summary(scope: UvScope): Promise<UvResponse<UvSummary>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const date = scope.business_date ?? SAMPLE_AS_OF.slice(0, 10)
    const reports = this.effectiveReports({ ...scope, business_date: date })
    const jobs = this._jobs.filter((job) => {
      if (scope.machine_id && job.machine_id !== scope.machine_id) return false
      const membership = job.completed_at ?? job.started_at
      if (!membership) return job.reconciliation === 'unmatched' || job.reconciliation === 'needs_unit'
      return shiftMembership(membership).business_date === date
    })

    const enabledMachines = this._machines.filter((machine) => machine.admin_status !== 'disabled')
    const freshMachines = this._machines.filter((machine) => machine.freshness === 'fresh')
    const outputValues = reports
      .map((report) => report.commercial?.output_value ?? null)
      .filter((value): value is Money => value !== null)
    const unpriced = reports.filter((report) => report.commercial?.pricing_state === 'unpriced').length

    const counts = {
      enabled_machines: enabledMachines.length,
      fresh_connected_machines: freshMachines.length,
      good_qty: reports.reduce((total, report) => total + report.good_qty, 0),
      pending_qty: reports.reduce((total, report) => total + report.pending_qty, 0),
      unmatched_jobs: jobs.filter((job) => job.reconciliation === 'unmatched').length,
      needs_unit_jobs: jobs.filter((job) => job.reconciliation === 'needs_unit').length,
      reports_needing_quality: reports.filter((report) => report.quality_status !== 'complete').length,
      low_stock_skus: this.lowStockCount(),
      handover_differences: this._handovers.filter((handover) => handover.state === 'difference').length,
    }

    const summary: UvSummary = {
      business_date: date,
      shift: scope.shift ?? 'all',
      counts,
      permissions: this.permissions,
    }
    if (this.can('uv_printing:cost_read')) {
      summary.commercial = {
        output_value: outputValues.length && outputValues.length === reports.length
          ? money(SAMPLE_CURRENCY, decimalSum(outputValues.map((value) => value.amount)))
          : outputValues.length
            ? money(SAMPLE_CURRENCY, decimalSum(outputValues.map((value) => value.amount)))
            : null,
        unpriced_report_count: unpriced,
        pricing_complete: unpriced === 0 && reports.length > 0,
      }
    }

    const warnings: UvWarning[] = []
    if (unpriced > 0) {
      warnings.push({ code: 'unpriced_reports', message: `${unpriced} 条报工没有生效执行价，产值暂算`, tone: 'warning' })
    }
    if (counts.reports_needing_quality > 0) {
      warnings.push({ code: 'quality_pending', message: `${counts.reports_needing_quality} 条报工质量未判清`, tone: 'warning' })
    }
    if (counts.unmatched_jobs + counts.needs_unit_jobs > 0) {
      warnings.push({
        code: 'reconcile_pending',
        message: `${counts.unmatched_jobs + counts.needs_unit_jobs} 条采集作业待核对`,
        tone: 'warning',
      })
    }
    const coverage: UvCoverage = reports.length === 0 ? 'no_data' : warnings.length ? 'partial' : 'complete'
    return this.wrap(summary, { coverage, warnings })
  }

  async machines(scope: UvScope): Promise<UvResponse<UvPage<UvMachine>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._machines
      .filter((machine) => !scope.q || `${machine.code} ${machine.name} ${machine.brand} ${machine.model}`.toLowerCase().includes(scope.q.toLowerCase()))
      .sort((a, b) => a.code.localeCompare(b.code, 'en'))
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async jobs(scope: UvScope): Promise<UvResponse<UvPage<UvPrintJob>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._jobs
      .filter((job) => {
        if (scope.machine_id && job.machine_id !== scope.machine_id) return false
        if (scope.status && job.reconciliation !== scope.status && job.state !== scope.status) return false
        if (scope.business_date) {
          const reference = job.completed_at ?? job.started_at
          if (reference && shiftMembership(reference).business_date !== scope.business_date) return false
        }
        if (scope.date_from && job.started_at && job.started_at.slice(0, 10) < scope.date_from) return false
        if (scope.date_to && job.started_at && job.started_at.slice(0, 10) > scope.date_to) return false
        if (scope.q) {
          const needle = scope.q.toLowerCase()
          if (!`${job.raw_task_name} ${job.raw_product_name ?? ''} ${job.source_job_id}`.toLowerCase().includes(needle)) return false
        }
        return true
      })
      .sort((a, b) => (b.completed_at ?? b.started_at ?? '').localeCompare(a.completed_at ?? a.started_at ?? ''))
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async reports(scope: UvScope): Promise<UvResponse<UvPage<UvReport>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this.reportsForScope(scope).sort((a, b) =>
      b.business_date === a.business_date
        ? (b.updated_at ?? '').localeCompare(a.updated_at ?? '')
        : b.business_date.localeCompare(a.business_date),
    )
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async products(scope: UvScope): Promise<UvResponse<UvPage<UvProduct>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._products
      .filter((product) => !scope.q || `${product.product_no} ${product.name} ${product.customer_name}`.toLowerCase().includes(scope.q.toLowerCase()))
      .sort((a, b) => a.product_no.localeCompare(b.product_no, 'en'))
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async productDetail(productId: Id): Promise<UvResponse<UvProduct>> {
    await this.gate(true)
    const product = this._products.find((candidate) => candidate.id === productId)
    if (!product) throw new UvError(UV_ERROR_CODES.notFound, '产品不存在或不属于华康A。', { status: 404 })
    return this.wrap(product)
  }

  async rateVersions(scope: UvScope): Promise<UvResponse<UvPage<UvRateVersion>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._rateVersions
      .filter((rate) => (!scope.product_id || rate.product_id === scope.product_id) && (!scope.status || rate.rate_kind === scope.status))
      .sort((a, b) => a.rate_kind.localeCompare(b.rate_kind) || (b.effective_from ?? '').localeCompare(a.effective_from ?? ''))
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async machineDetail(machineId: Id, scope: UvScope): Promise<UvResponse<UvMachineDetail>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const machine = this._machines.find((candidate) => candidate.id === machineId)
    if (!machine) throw new UvError(UV_ERROR_CODES.notFound, '机台不存在或不属于华康A。', { status: 404 })
    const date = scope.business_date ?? SAMPLE_AS_OF.slice(0, 10)
    const jobs = this._jobs.filter((job) => job.machine_id === machineId)
    const reports = this._reports.filter((report) => report.machine_id === machineId)
    const assignments = this._assignments.filter((assignment) => assignment.machine_id === machineId)
    const expenses = this._expenses.filter((expense) => expense.machine_id === machineId)
    return this.wrap({
      machine,
      jobs: jobs.sort((a, b) => (b.completed_at ?? b.started_at ?? '').localeCompare(a.completed_at ?? a.started_at ?? '')),
      reports: reports.sort((a, b) => b.business_date.localeCompare(a.business_date)),
      assignments: assignments.filter((assignment) => assignment.business_date === date),
      expenses,
      runtime_windows: this.runtimeWindows(machineId),
    })
  }

  /** 运行时序按真实时间刻度，数据缺口留空并标注，不制造连续数据。 */
  private runtimeWindows(machineId: Id): UvRuntimeWindow[] {
    const jobs = this._jobs
      .filter((job) => job.machine_id === machineId && job.started_at)
      .sort((a, b) => (a.started_at ?? '').localeCompare(b.started_at ?? ''))
    const windows: UvRuntimeWindow[] = []
    let previousEnd: string | null = null
    for (const job of jobs) {
      if (previousEnd && job.started_at && job.started_at > previousEnd) {
        const gapMinutes = Math.round((new Date(job.started_at).getTime() - new Date(previousEnd).getTime()) / 60_000)
        if (gapMinutes >= 30) {
          windows.push({
            id: `${job.id}-gap`,
            machine_id: machineId,
            start_at: previousEnd,
            end_at: job.started_at,
            duration_minutes: gapMinutes,
            kind: 'gap',
            job_id: null,
            label: '无采集数据，缺口不补零',
            evidence: 'unknown',
          })
        }
      }
      const duration = job.started_at && job.completed_at
        ? Math.round((new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 60_000)
        : null
      windows.push({
        id: job.id,
        machine_id: machineId,
        start_at: job.started_at!,
        end_at: job.completed_at,
        duration_minutes: duration,
        kind: job.state === 'cancelled' ? 'idle' : 'run',
        job_id: job.id,
        label: job.raw_task_name,
        evidence: job.time_evidence,
      })
      previousEnd = job.completed_at ?? previousEnd
    }
    return windows
  }

  async handovers(scope: UvScope): Promise<UvResponse<UvPage<UvHandoverRecord>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._handovers.filter((handover) => {
      if (scope.business_date && handover.business_date !== scope.business_date) return false
      if (scope.date_from && handover.business_date < scope.date_from) return false
      if (scope.date_to && handover.business_date > scope.date_to) return false
      if (scope.product_id && handover.product_id !== scope.product_id) return false
      return true
    })
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async inkSkus(scope: UvScope): Promise<UvResponse<UvPage<UvInkSku>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._inkSkus.filter((sku) => {
      if (scope.q) {
        const needle = scope.q.toLowerCase()
        const haystack = `${sku.supplier} ${sku.color} ${sku.material} ${sku.color_aliases.join(' ')}`.toLowerCase()
        if (!haystack.includes(needle)) return false
      }
      if (scope.status && scope.status !== sku.material) return false
      return true
    })
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async inkBalances(scope: UvScope): Promise<UvResponse<UvPage<UvInkBalance>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const balances = this.inkBalancesSync()
      .filter((balance) => (scope.status === 'low' ? balance.low_stock : true))
    return this.wrap(paginate(balances, scope.page, scope.page_size))
  }

  async inkMovements(scope: UvScope): Promise<UvResponse<UvPage<UvInkMovement>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._inkMovements
      .filter((movement) => {
        if (scope.status && movement.kind !== scope.status) return false
        if (scope.date_from && movement.occurred_on < scope.date_from) return false
        if (scope.date_to && movement.occurred_on > scope.date_to) return false
        if (scope.q) {
          const needle = scope.q.toLowerCase()
          if (!`${movement.sku_label} ${movement.purpose} ${movement.source_doc}`.toLowerCase().includes(needle)) return false
        }
        return true
      })
      .sort((a, b) => b.occurred_on.localeCompare(a.occurred_on) || b.id.localeCompare(a.id))
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async workers(scope: UvScope): Promise<UvResponse<UvPage<UvWorkerRef>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._workers.filter((worker) => {
      if (scope.status && worker.employ_state !== scope.status) return false
      if (scope.q && !worker.display_name.includes(scope.q) && !worker.employee_no.includes(scope.q)) return false
      return true
    })
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async shiftTemplates(scope: UvScope): Promise<UvResponse<UvPage<UvShiftTemplate>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    return this.wrap(paginate(this._shiftTemplates, scope.page, scope.page_size))
  }

  async assignments(scope: UvScope): Promise<UvResponse<UvPage<UvAssignment>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._assignments.filter((assignment) => {
      if (scope.business_date && assignment.business_date !== scope.business_date) return false
      if (scope.shift && assignment.shift !== scope.shift) return false
      if (scope.machine_id && assignment.machine_id !== scope.machine_id) return false
      return true
    })
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async expenses(scope: UvScope): Promise<UvResponse<UvPage<UvExpense>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const items = this._expenses
      .filter((expense) => {
        if (scope.date_from && expense.occurred_on < scope.date_from) return false
        if (scope.date_to && expense.occurred_on > scope.date_to) return false
        if (scope.status && expense.category !== scope.status) return false
        return true
      })
      .sort((a, b) => b.occurred_on.localeCompare(a.occurred_on))
    return this.wrap(paginate(items, scope.page, scope.page_size))
  }

  async monthlyPolicy(month: string, scope: UvScope): Promise<UvResponse<UvMonthlyPolicy | null>> {
    await this.gate(true)
    assertScopeFactory(scope)
    return this.wrap(this._monthlyPolicies.find((policy) => policy.month === month) ?? null)
  }

  async pricingQuotes(scope: UvScope): Promise<UvResponse<UvPage<UvPricingQuote>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    return this.wrap(paginate(this._pricingQuotes, scope.page, scope.page_size))
  }

  async payrollPreview(scope: UvScope): Promise<UvResponse<UvPayrollPreview>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const dateFrom = scope.date_from ?? SAMPLE_AS_OF.slice(0, 10)
    const dateTo = scope.date_to ?? dateFrom
    const reports = this._reports.filter((report) =>
      report.business_date >= dateFrom
      && report.business_date <= dateTo
      && report.status !== 'voided'
      && (!scope.shift || report.shift === scope.shift),
    )

    const warnings: UvWarning[] = []
    const unpricedReports = reports.filter((report) => !report.payroll || report.payroll.state === 'unpriced').length
    const qualityPendingReports = reports.filter((report) => report.quality_status !== 'complete').length
    const unassignedReports = reports.filter((report) => report.worker_ids.length === 0).length

    const byWorker = new Map<string, UvPayrollLine>()
    let batchTotalMinor = 0n
    const currency = SAMPLE_CURRENCY

    for (const report of reports) {
      const payroll = report.payroll
      if (!payroll || payroll.amount === null) continue
      const assignments = this._assignments.filter((assignment) =>
        assignment.business_date === report.business_date
        && assignment.shift === report.shift
        && assignment.machine_id === report.machine_id,
      )
      const participantIds = (assignments.length ? assignments.map((assignment) => assignment.worker_id) : report.worker_ids)
        .filter((workerId, index, list) => list.indexOf(workerId) === index)
        .sort((a, b) => a.localeCompare(b))
      if (!participantIds.length) continue

      const shares = splitRemainder(payroll.amount.amount, participantIds.length, currency)
      participantIds.forEach((workerId, index) => {
        const worker = this._workers.find((candidate) => candidate.id === workerId)
        const existing = byWorker.get(workerId) ?? {
          worker_id: workerId,
          worker_name: worker?.display_name ?? workerId,
          employee_no: worker?.employee_no ?? '',
          report_count: 0,
          good_qty: 0,
          amount: money(currency, '0'),
          state: payroll.state,
          allocation_basis: '同机同班同工作批次等分，余数按稳定员工顺序补最小币种单位',
          remainder_adjusted: false,
          reason: '',
        }
        existing.report_count += 1
        existing.good_qty += report.good_qty
        existing.amount = money(currency, decimalAdd(existing.amount?.amount ?? '0', shares[index] ?? '0'))
        if (payroll.state === 'unpriced') existing.state = 'unpriced'
        byWorker.set(workerId, existing)
      })
      const minor = currencyMinorUnits(currency)
      batchTotalMinor += BigInt(decimalRound(payroll.amount.amount, minor).replace('.', ''))
    }

    if (unpricedReports > 0) {
      warnings.push({ code: 'payroll_unpriced', message: `${unpricedReports} 条报工没有生效计件工价，工资未定价`, tone: 'warning' })
    }
    if (unassignedReports > 0) {
      warnings.push({ code: 'payroll_unassigned', message: `${unassignedReports} 条报工没有排班人员，未参与分摊`, tone: 'warning' })
    }
    if (qualityPendingReports > 0) {
      warnings.push({ code: 'payroll_quality', message: `${qualityPendingReports} 条报工质量未判清，按已判合格量暂算`, tone: 'warning' })
    }

    const lines = [...byWorker.values()].sort((a, b) => a.employee_no.localeCompare(b.employee_no))

    return this.wrap(
      {
        date_from: dateFrom,
        date_to: dateTo,
        shift: scope.shift ?? 'all',
        currency,
        batch_total: lines.length ? money(currency, decimalSum(lines.map((line) => line.amount?.amount ?? '0'))) : null,
        lines,
        unpriced_reports: unpricedReports,
        unassigned_reports: unassignedReports,
        quality_pending_reports: qualityPendingReports,
        coverage: unpricedReports || qualityPendingReports || unassignedReports ? 'partial' : 'complete',
        warnings,
      },
      { coverage: unpricedReports || qualityPendingReports || unassignedReports ? 'partial' : 'complete', warnings },
    )
  }

  async dailyReport(scope: UvScope): Promise<UvResponse<UvDailyReport>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const date = scope.business_date ?? SAMPLE_AS_OF.slice(0, 10)
    const projections = await this.dailyProjection({ ...scope, date_from: date, date_to: date })
    const row = projections.data.items[0]
    if (!row) throw new UvError(UV_ERROR_CODES.notFound, '该业务日期没有可用数据。', { status: 404 })

    const metrics: UvMetricValue[] = [
      {
        key: 'good_qty', label: '合格件数', value: String(row.good_qty), unit: '件',
        formula: '已确认报工的合格件合计', sources: ['业务报工'], note: '只统计已确认报工', provisional: false, unpriced: false,
      },
      {
        key: 'yield_rate', label: '合格率', value: row.yield_rate, unit: '',
        formula: '合格 ÷ (合格 + 不良)，分母为 0 显示 —', sources: ['业务报工'], note: '待判与半成品不计入分母', provisional: row.quality_pending_reports > 0, unpriced: false,
      },
      {
        key: 'output_value', label: '产值', value: row.output_value?.amount ?? null, unit: SAMPLE_CURRENCY,
        formula: '合格件 × 商业执行价快照', sources: ['价规版本', '业务报工'], note: '未定价报工不计入', provisional: row.unpriced_reports > 0, unpriced: row.unpriced_reports > 0,
      },
      {
        key: 'payroll_amount', label: '班组计件工资', value: row.payroll_amount?.amount ?? null, unit: SAMPLE_CURRENCY,
        formula: '合格件 × 计件工价快照', sources: ['工资预览'], note: '与商业产值严格分开', provisional: true, unpriced: false,
      },
      {
        key: 'ink_cost', label: '油墨领用成本', value: row.ink_cost?.amount ?? null, unit: SAMPLE_CURRENCY,
        formula: '当日出库流水成本合计', sources: ['墨水流水'], note: '领用成本不是精确到作业的实际耗用', provisional: true, unpriced: false,
      },
      {
        key: 'operating_result', label: '经营结余', value: row.operating_result?.amount ?? null, unit: SAMPLE_CURRENCY,
        formula: '产值 − 各项费用 + 可回收项', sources: ['费用', '工资预览', '墨水流水'], note: '旧管理口径，不是法定净利润', provisional: true, unpriced: false,
      },
    ]

    const rows = [
      { key: 'reports', label: '业务报工', value: String(row.reported_qty), unit: '报工件数', drill_kind: 'reports' as const, drill_ref: date, provisional: false },
      { key: 'jobs', label: '采集作业', value: String(this._jobs.length), unit: '条', drill_kind: 'jobs' as const, drill_ref: date, provisional: false },
      { key: 'handovers', label: '入库核数', value: String(this._handovers.filter((handover) => handover.business_date === date).length), unit: '条', drill_kind: 'handovers' as const, drill_ref: date, provisional: false },
      { key: 'expenses', label: '费用记录', value: String(this._expenses.filter((expense) => expense.occurred_on === date).length), unit: '条', drill_kind: 'expenses' as const, drill_ref: date, provisional: false },
    ]

    const coverage = row.unpriced_reports || row.quality_pending_reports ? 'partial' : 'complete'
    const headline = row.unpriced_reports
      ? `当日有 ${row.unpriced_reports} 条报工未定价，产值与结余暂算`
      : row.quality_pending_reports
        ? `当日有 ${row.quality_pending_reports} 条报工质量未判清，良率暂算`
        : `当日数据完整，可核对`

    return this.wrap(
      { business_date: date, shift: scope.shift ?? 'all', headline, metrics, rows, coverage },
      { coverage, warnings: coverageNotes({
        unpricedReports: row.unpriced_reports,
        qualityPendingReports: row.quality_pending_reports,
        missingCostCategories: [],
        closed: false,
        asOf: this.asOf,
      }).map((message) => ({ code: 'coverage', message })) },
    )
  }

  async dailyProjection(scope: UvScope): Promise<UvResponse<UvPage<UvDailyProjection>>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const dates = scope.date_from && scope.date_to
      ? this.dateRange(scope.date_from, scope.date_to)
      : [scope.business_date ?? SAMPLE_AS_OF.slice(0, 10)]
    const policy = this._monthlyPolicies.find((candidate) => candidate.month === monthOf(dates[0] ?? SAMPLE_MONTH))
    const items = dates.map((date) => this.projectDate(date, scope.shift, policy))
    return this.wrap(paginate(items, 1, 200))
  }

  private dateRange(from: BusinessDate, to: BusinessDate): BusinessDate[] {
    const result: BusinessDate[] = []
    let cursor = from
    let guard = 0
    while (cursor <= to && guard < 400) {
      result.push(cursor)
      cursor = addDays(cursor, 1)
      guard += 1
    }
    return result
  }

  private projectDate(date: BusinessDate, shift: ShiftScope | undefined, policy: UvMonthlyPolicy | undefined): UvDailyProjection {
    const reports = this._reports.filter((report) =>
      report.business_date === date
      && report.status === 'confirmed'
      && (!shift || report.shift === shift),
    )
    const goodQty = reports.reduce((total, report) => total + report.good_qty, 0)
    const reportedQty = reports.reduce((total, report) => total + report.reported_qty, 0)
    const pricedReports = reports.filter((report) => report.commercial?.pricing_state === 'priced')
    const outputValue = pricedReports.length === reports.length && reports.length > 0
      ? money(SAMPLE_CURRENCY, decimalSum(pricedReports.map((report) => report.commercial!.output_value?.amount ?? '0')))
      : pricedReports.length
        ? money(SAMPLE_CURRENCY, decimalSum(pricedReports.map((report) => report.commercial!.output_value?.amount ?? '0')))
        : null
    const payrollAmount = reports.length
      ? money(SAMPLE_CURRENCY, decimalSum(reports.map((report) => report.payroll?.amount?.amount ?? '0')))
      : null
    const movements = this._inkMovements.filter((movement) => movement.occurred_on === date && movement.kind === 'issue_out')
    // 当天没有出库流水时，领用成本是「缺失」而不是 0。缺单价（cost_pending）也一样。
    const inkCostPending = movements.some((movement) => movement.cost_pending)
    const inkCost = movements.length && !inkCostPending
      ? money(SAMPLE_CURRENCY, decimalSum(movements.map((movement) => movement.amount?.amount ?? '0')))
      : null
    const expenses = this._expenses.filter((expense) => expense.occurred_on === date)
    const expenseAmount = expenses.length
      ? money(SAMPLE_CURRENCY, decimalSum(expenses.map((expense) => expense.amount.amount)))
      : null

    const policyDay = policy?.working_days.includes(date) ?? true
    const isPlannedOff = !policyDay || isSunday(date)

    const operating = operatingResult({
      currency: SAMPLE_CURRENCY,
      outputValue: outputValue?.amount ?? null,
      employeeWage: payrollAmount?.amount ?? null,
      managementWage: null,
      equipment: expenses.filter((expense) => expense.category === 'equipment').reduce<string | null>((total, expense) => decimalAdd(total ?? '0', expense.amount.amount), null),
      tooling: this.categoryTotal(expenses, 'tooling'),
      rent: this.categoryTotal(expenses, 'rent'),
      utilities: this.categoryTotal(expenses, 'utilities'),
      material: this.categoryTotal(expenses, 'material'),
      sundry: this.categoryTotal(expenses, 'sundry'),
      maintenance: this.categoryTotal(expenses, 'maintenance'),
      nightSubsidy: this.categoryTotal(expenses, 'night_subsidy'),
      inkIssueCost: inkCost?.amount ?? null,
      noOutputWage: null,
      processing: this.categoryTotal(expenses, 'processing'),
      recoverableWage: this.categoryTotal(expenses, 'recoverable_wage'),
      recoverablePaint: this.categoryTotal(expenses, 'recoverable_paint'),
    })

    const denominator = goodQty + reports.reduce((total, report) => total + report.defective_qty, 0)

    return {
      business_date: date,
      good_qty: goodQty,
      reported_qty: reportedQty,
      yield_rate: denominator > 0 ? decimalDivide(String(goodQty), String(denominator), 6) : null,
      output_value: outputValue,
      payroll_amount: payrollAmount,
      ink_cost: inkCost,
      expense_amount: expenseAmount,
      operating_result: operating.operatingResult === null ? null : money(SAMPLE_CURRENCY, operating.operatingResult),
      unpriced_reports: reports.filter((report) => report.commercial?.pricing_state !== 'priced').length,
      quality_pending_reports: reports.filter((report) => report.quality_status !== 'complete').length,
      planned_day_off: isPlannedOff,
      off_plan_production: isPlannedOff && reports.length > 0,
    }
  }

  /**
   * 分类费用合计。**没有任何该类记录时返回 `null`**，而不是 `'0'`：
   * 规格 FIX-03 要求 null 表示缺失、0 是有效数据，否则「缺成本」在报表里
   * 无法与「真实 0」区分，5.8 的缺成本口径说明也就无法实现。
   * 有记录但金额本身是 0 时，返回 '0'。
   */
  private categoryTotal(expenses: UvExpense[], category: string): string | null {
    const matched = expenses.filter((expense) => expense.category === category)
    if (!matched.length) return null
    return decimalSum(matched.map((expense) => expense.amount.amount))
  }

  async monthlyProjection(scope: UvScope): Promise<UvResponse<UvMonthlyProjection>> {
    await this.gate(true)
    assertScopeFactory(scope)
    const month = scope.status ?? monthOf(scope.business_date ?? SAMPLE_AS_OF.slice(0, 10))
    const policy = this._monthlyPolicies.find((candidate) => candidate.month === month)
    const dates = this.dateRange(`${month}-01`, addDays(`${month}-01`, daysInMonth(month).length - 1))
    const rows = dates.map((date) => this.projectDate(date, scope.shift, policy))
    const withData = rows.filter((row) => row.reported_qty > 0)
    const aggregate = aggregateDailyRows(SAMPLE_CURRENCY, withData, withData.some((row) => row.unpriced_reports) ? 'partial' : 'complete')

    const policyMonthExpenses = this._expenses.filter((expense) => expense.period === month)
    const staffCosts = policyMonthExpenses.filter((expense) => expense.category === 'management_wage')
    const structure = expenseStructure(
      SAMPLE_CURRENCY,
      policyMonthExpenses,
      EXPENSE_CATEGORY_LABELS,
      aggregate?.output_value?.amount ?? null,
    )

    const proration = policy
      ? [
          ...(policy.rent ? prorationTotals(policy.rent.amount, policy.working_days, policy.rent.currency, policy.allocation_method).days.map((day) => ({ category: 'rent', ...day })) : []),
          ...(policy.utilities ? prorationTotals(policy.utilities.amount, policy.working_days, policy.utilities.currency, policy.allocation_method).days.map((day) => ({ category: 'utilities', ...day })) : []),
          ...(policy.management_wage ? prorationTotals(policy.management_wage.amount, policy.working_days, policy.management_wage.currency, policy.allocation_method).days.map((day) => ({ category: 'management_wage', ...day })) : []),
        ]
      : []

    const prorationRows = proration.map((entry) => ({
      key: `proration_${entry.category}_${entry.business_date}`,
      label: `${EXPENSE_CATEGORY_LABELS[entry.category] ?? entry.category} · ${entry.business_date}`,
      value: entry.amount,
      unit: SAMPLE_CURRENCY,
      drill_kind: 'expenses' as const,
      drill_ref: entry.business_date,
      provisional: false,
    }))

    const aggregateRows: UvMonthlyProjection['months'] = aggregate
      ? [{
          month,
          good_qty: aggregate.good_qty,
          reported_qty: aggregate.reported_qty,
          yield_rate: aggregate.yield_rate,
          output_value: aggregate.output_value,
          payroll_amount: aggregate.payroll_amount,
          payroll_ratio: aggregate.payroll_ratio,
          operating_result: aggregate.operating_result,
          result_ratio: aggregate.result_ratio,
          cost_coverage: aggregate.cost_coverage,
        }]
      : []

    const provisionalReasons: string[] = []
    const unpriced = withData.reduce((total, row) => total + row.unpriced_reports, 0)
    const qualityPending = withData.reduce((total, row) => total + row.quality_pending_reports, 0)
    if (unpriced) provisionalReasons.push(`${unpriced} 条报工未定价，产值与结余暂算`)
    if (qualityPending) provisionalReasons.push(`${qualityPending} 条报工质量未判清，良率暂算`)
    if (!staffCosts.length) provisionalReasons.push('管理人员工资未按月配置，结余暂算')
    if (!policy) provisionalReasons.push('该月未配置分摊政策，房租水电与管理工资未分摊')

    const supplementRows = [
      ...structure.map((row) => ({
        key: `expense_${row.category}`,
        label: row.label,
        value: row.amount?.amount ?? null,
        unit: SAMPLE_CURRENCY,
        drill_kind: 'expenses' as const,
        drill_ref: row.category,
        provisional: row.amount === null,
      })),
      ...(aggregate ? operatingResult({
        currency: SAMPLE_CURRENCY,
        outputValue: aggregate.output_value?.amount ?? null,
        employeeWage: aggregate.payroll_amount?.amount ?? null,
        managementWage: this.categoryTotal(policyMonthExpenses, 'management_wage'),
        equipment: this.categoryTotal(policyMonthExpenses, 'equipment'),
        tooling: this.categoryTotal(policyMonthExpenses, 'tooling'),
        rent: this.categoryTotal(policyMonthExpenses, 'rent'),
        utilities: this.categoryTotal(policyMonthExpenses, 'utilities'),
        material: this.categoryTotal(policyMonthExpenses, 'material'),
        sundry: this.categoryTotal(policyMonthExpenses, 'sundry'),
        maintenance: this.categoryTotal(policyMonthExpenses, 'maintenance'),
        nightSubsidy: this.categoryTotal(policyMonthExpenses, 'night_subsidy'),
        inkIssueCost: (() => {
          const monthIssues = this._inkMovements.filter((movement) => movement.occurred_on.startsWith(month) && movement.kind === 'issue_out')
          if (!monthIssues.length || monthIssues.some((movement) => movement.cost_pending)) return null
          return decimalSum(monthIssues.map((movement) => movement.amount?.amount ?? '0'))
        })(),
        noOutputWage: null,
        processing: this.categoryTotal(policyMonthExpenses, 'processing'),
        recoverableWage: this.categoryTotal(policyMonthExpenses, 'recoverable_wage'),
        recoverablePaint: this.categoryTotal(policyMonthExpenses, 'recoverable_paint'),
      }).rows.map((row) => ({ ...row, key: `operating_${row.key}` })) : []),
      ...prorationRows,
    ]

    return this.wrap(
      {
        month,
        months: aggregateRows,
        structure: supplementRows,
        coverage_note: coverageNotes({
          unpricedReports: unpriced,
          qualityPendingReports: qualityPending,
          missingCostCategories: staffCosts.length ? [] : ['管理人员工资'],
          closed: false,
          asOf: this.asOf,
        }).join('；'),
        provisional_reasons: provisionalReasons,
      },
      { coverage: provisionalReasons.length ? 'partial' : 'complete' },
    )
  }

  async operationResult(operationId: string, scope: UvScope): Promise<UvResponse<UvOperationRecord | null>> {
    await this.gate(true)
    assertScopeFactory(scope)
    return this.wrap(this._operations.get(operationId) ?? null)
  }

  /* ---------------- 命令 ---------------- */

  async createReport(input: CreateUvReport): Promise<UvResponse<UvMutationResult<UvReport>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:report')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const result = this.buildReport(input)
      this.recomputeDerived()
      return { entity: result, operation_id: input.operation_id, replayed: false }
    }))
  }

  private buildReport(input: CreateUvReport, options: { replaces?: Id | null; status?: UvReport['status']; correctionReason?: string } = {}): UvReport {
    const machine = this._machines.find((candidate) => candidate.id === input.machine_id)
    const product = this._products.find((candidate) => candidate.id === input.product_id)
    const processVersion = product?.process_versions.find((candidate) => candidate.id === input.process_version_id)
    validateDraft(input, Boolean(machine), Boolean(processVersion))
    validateQualityTotals(input)

    const timestamp = nowIso()
    const report: UvReport = {
      id: this.nextId('R'),
      factory_id: SAMPLE_FACTORY_ID,
      version: 1,
      created_at: timestamp,
      updated_at: timestamp,
      business_date: input.business_date,
      shift: input.shift,
      shift_template_version_id: input.shift_template_version_id,
      machine_id: input.machine_id,
      product_id: input.product_id,
      process_version_id: input.process_version_id,
      product_no: product?.product_no ?? '',
      product_name: product?.name ?? '',
      reported_qty: input.reported_qty,
      good_qty: input.good_qty,
      defective_qty: input.defective_qty,
      pending_qty: input.pending_qty,
      semi_finished_qty: input.semi_finished_qty,
      source_kind: input.source_allocations.length || input.evidence_job_ids.length ? 'mixed' : 'manual',
      status: options.status ?? (input.source_allocations.length ? 'confirmed' : 'confirmed'),
      quality_status: input.pending_qty === input.reported_qty && input.reported_qty > 0
        ? 'pending'
        : input.pending_qty > 0 || input.semi_finished_qty > 0
          ? 'partial'
          : 'complete',
      worker_ids: [...input.worker_ids],
      worker_names: input.worker_ids.map((workerId) => this._workers.find((worker) => worker.id === workerId)?.display_name ?? workerId),
      notes: input.notes,
      replaces_report_id: options.replaces ?? null,
      correction_reason: options.correctionReason ?? '',
      allocation_total: 0,
    }

    const allocations = input.source_allocations.map((allocation) => {
      const job = this._jobs.find((candidate) => candidate.id === allocation.job_id)
      if (!job) {
        throw new UvError(UV_ERROR_CODES.notFound, `采集作业 ${allocation.job_id} 不存在。`, { status: 404 })
      }
      assertVersion(allocation.job_version, job.version)
      const available = job.available_piece_qty
      if (available === null) {
        throw new UvError(
          UV_ERROR_CODES.invalidField,
          `作业 ${job.source_job_id} 的原始单位尚未确认，不能伪造可分配件数。`,
          { status: 422, fields: { source_allocations: '单位待确认' } },
        )
      }
      if (allocation.piece_qty > available) {
        throw new UvError(
          UV_ERROR_CODES.allocationOverflow,
          `作业 ${job.source_job_id} 只剩 ${available} 件可分配，本次申请 ${allocation.piece_qty} 件。`,
          { status: 422, fields: { source_allocations: `剩余 ${available}` } },
        )
      }
      return allocation
    })

    this._reports.push(report)
    for (const allocation of allocations) {
      const job = this._jobs.find((candidate) => candidate.id === allocation.job_id)!
      job.version += 1
      this._allocations.push({
        id: this.nextId('SA'),
        factory_id: SAMPLE_FACTORY_ID,
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        job_id: allocation.job_id,
        report_id: report.id,
        piece_qty: allocation.piece_qty,
        reversed: false,
      })
    }
    for (const jobId of input.evidence_job_ids) {
      const job = this._jobs.find((candidate) => candidate.id === jobId)
      if (job) job.reconcile_note = `${job.reconcile_note} 已作为证据附在 ${report.id}，未声明已核实件数。`.trim()
    }

    return report
  }

  async confirmReport(input: UvReportCommandInput): Promise<UvResponse<UvMutationResult<UvReport>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:report')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const report = this.mutableReport(input.report_id)
      assertVersion(input.expected_version, report.version)
      if (report.status !== 'draft') {
        throw new UvError(UV_ERROR_CODES.invalidField, '只有草稿可以确认。', { status: 422 })
      }
      validateQualityTotals(report)
      report.status = 'confirmed'
      report.version += 1
      report.updated_at = nowIso()
      this.recomputeDerived()
      return { entity: report, operation_id: input.operation_id, replayed: false }
    }))
  }

  async updateQuality(input: UvQualityCommandInput): Promise<UvResponse<UvMutationResult<UvReport>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:quality')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const report = this.mutableReport(input.report_id)
      assertVersion(input.expected_version, report.version)
      if (report.status === 'voided') {
        throw new UvError(UV_ERROR_CODES.invalidField, '已作废报工不能补录质量。', { status: 422 })
      }
      const next: UvQuality = {
        reported_qty: report.reported_qty,
        good_qty: input.quality.good_qty,
        defective_qty: input.quality.defective_qty,
        pending_qty: input.quality.pending_qty,
        semi_finished_qty: input.quality.semi_finished_qty,
      }
      validateQualityTotals(next)
      Object.assign(report, next)
      report.quality_status = next.pending_qty === next.reported_qty && next.reported_qty > 0
        ? 'pending'
        : next.pending_qty > 0 || next.semi_finished_qty > 0
          ? 'partial'
          : 'complete'
      report.notes = input.reason ? `${report.notes} 质量补录：${input.reason}`.trim() : report.notes
      report.version += 1
      report.updated_at = nowIso()
      this.recomputeDerived()
      return { entity: report, operation_id: input.operation_id, replayed: false }
    }))
  }

  async correctReport(input: UvCorrectionInput): Promise<UvResponse<UvMutationResult<UvReport>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:report')
    if (!input.reason.trim()) {
      throw new UvError(UV_ERROR_CODES.invalidField, '更正必须填写原因。', { status: 422, fields: { reason: '必填' } })
    }
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const original = this.mutableReport(input.report_id)
      assertVersion(input.expected_version, original.version)
      if (original.status === 'voided') {
        throw new UvError(UV_ERROR_CODES.invalidField, '已作废报工不能再更正。', { status: 422 })
      }
      // 原记录不放任覆盖：作废并保留原值，新修订引用原单。
      original.status = 'voided'
      original.version += 1
      original.updated_at = nowIso()
      original.notes = `${original.notes} 被更正：${input.reason}`.trim()
      for (const allocation of this._allocations.filter((candidate) => candidate.report_id === original.id)) {
        allocation.reversed = true
        allocation.version += 1
      }
      const replacement = this.buildReport({ ...input.correction, operation_id: input.operation_id }, {
        replaces: original.id,
        status: 'corrected',
        correctionReason: input.reason,
      })
      this.recomputeDerived()
      return { entity: replacement, operation_id: input.operation_id, replayed: false }
    }))
  }

  async voidReport(input: UvVoidInput): Promise<UvResponse<UvMutationResult<UvReport>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:report')
    if (!input.reason.trim()) {
      throw new UvError(UV_ERROR_CODES.invalidField, '作废必须填写原因。', { status: 422, fields: { reason: '必填' } })
    }
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const report = this.mutableReport(input.report_id)
      assertVersion(input.expected_version, report.version)
      report.status = 'voided'
      report.version += 1
      report.updated_at = nowIso()
      report.notes = `${report.notes} 作废：${input.reason}`.trim()
      for (const allocation of this._allocations.filter((candidate) => candidate.report_id === report.id)) {
        allocation.reversed = true
        allocation.version += 1
      }
      this.recomputeDerived()
      return { entity: report, operation_id: input.operation_id, replayed: false }
    }))
  }

  async reconcileJob(input: UvJobReconcileInput): Promise<UvResponse<UvMutationResult<UvPrintJob>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:report')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const job = this._jobs.find((candidate) => candidate.id === input.job_id)
      if (!job) throw new UvError(UV_ERROR_CODES.notFound, '采集作业不存在。', { status: 404 })
      assertVersion(input.expected_version, job.version)
      job.version += 1
      job.updated_at = nowIso()
      job.reconcile_note = input.note

      if (input.ignore) {
        job.reconciliation = 'ignored'
        job.product_id = null
        job.process_version_id = null
        job.suggested_piece_qty = null
        job.available_piece_qty = null
        this.recomputeDerived()
        return { entity: job, operation_id: input.operation_id, replayed: false }
      }

      job.product_id = input.product_id
      job.process_version_id = input.process_version_id
      job.raw_unit = input.confirmed_unit
      if (input.confirmed_unit === 'unknown' || input.confirmed_piece_qty === null) {
        job.suggested_piece_qty = null
        job.available_piece_qty = null
        job.reconciliation = 'needs_unit'
        this.recomputeDerived()
        return { entity: job, operation_id: input.operation_id, replayed: false }
      }
      job.suggested_piece_qty = input.confirmed_piece_qty
      job.reconciliation = job.reconciliation === 'allocated' ? 'allocated' : 'ready'
      this.recomputeDerived()
      return { entity: job, operation_id: input.operation_id, replayed: false }
    }))
  }

  async saveHandover(input: UvHandoverInput): Promise<UvResponse<UvMutationResult<UvHandoverRecord>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:report')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const report = input.report_id ? this._reports.find((candidate) => candidate.id === input.report_id) : null
      const product = this._products.find((candidate) => candidate.id === input.product_id)
      if (!product) throw new UvError(UV_ERROR_CODES.notFound, '产品不存在。', { status: 404 })
      const existing = input.id ? this._handovers.find((candidate) => candidate.id === input.id) : null
      const timestamp = nowIso()
      const reported = report?.reported_qty ?? existing?.reported_qty ?? 0
      const difference = input.received_qty - reported
      const record: UvHandoverRecord = {
        id: existing?.id ?? this.nextId('H'),
        factory_id: SAMPLE_FACTORY_ID,
        version: (existing?.version ?? 0) + 1,
        created_at: existing?.created_at ?? timestamp,
        updated_at: timestamp,
        business_date: input.business_date,
        product_id: input.product_id,
        product_no: product.product_no,
        product_name: product.name,
        report_id: input.report_id,
        reported_qty: reported,
        received_qty: input.received_qty,
        difference_qty: difference,
        state: !input.receiver ? 'pending' : difference === 0 ? 'reconciled' : 'difference',
        receiver: input.receiver,
        note: input.note,
      }
      if (existing) Object.assign(existing, record)
      else this._handovers.unshift(record)
      return { entity: record, operation_id: input.operation_id, replayed: false }
    }))
  }

  async createInkIssue(input: UvInkIssueInput): Promise<UvResponse<UvMutationResult<UvInkMovement>>> {
    return this.createInkMovement(input, 'issue_out')
  }

  async createInkPurchase(input: UvInkPurchaseInput): Promise<UvResponse<UvMutationResult<UvInkMovement>>> {
    return this.createInkMovement(input, 'purchase_in')
  }

  private async createInkMovement(
    input: UvInkIssueInput | UvInkPurchaseInput,
    kind: 'issue_out' | 'purchase_in',
  ): Promise<UvResponse<UvMutationResult<UvInkMovement>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:ink_write')
    return this.wrap(this.idempotent(input.operation_id, { input, kind }, () => {
      const sku = this._inkSkus.find((candidate) => candidate.id === input.sku_id)
      if (!sku) throw new UvError(UV_ERROR_CODES.notFound, '墨水 SKU 不存在。', { status: 404 })
      const quantity = decimalRound(input.quantity_ml, 3)
      if (decimalCompare(quantity, '0') <= 0) {
        throw new UvError(UV_ERROR_CODES.invalidField, '数量必须大于 0。', { status: 422, fields: { quantity_ml: '必须大于 0' } })
      }
      const balances = this.inkBalancesSync()
      const balance = balances.find((candidate) => candidate.sku_id === sku.id)!
      const signed = kind === 'issue_out' ? `-${quantity}` : quantity
      const nextBalance = decimalAdd(balance.available_ml, signed)
      if (kind === 'issue_out' && decimalCompare(nextBalance, '0') < 0) {
        throw new UvError(
          UV_ERROR_CODES.insufficientStock,
          `可用库存只有 ${balance.available_ml}ml，本次领用 ${quantity}ml 会变成负数。`,
          { status: 422, fields: { quantity_ml: `可用 ${balance.available_ml}ml` }, retryable: false },
        )
      }
      const unitCost = 'unit_cost' in input ? input.unit_cost : sku.unit_cost
      const currency = 'currency' in input ? input.currency : sku.currency
      const costPending = !unitCost || !currency
      const amount = costPending ? null : money(currency!, decimalMultiply(quantity, unitCost!))
      const timestamp = nowIso()
      const movement: UvInkMovement = {
        id: this.nextId('IM'),
        factory_id: SAMPLE_FACTORY_ID,
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        sku_id: sku.id,
        sku_label: `${sku.supplier} · ${sku.material === 'hard' ? '硬墨' : sku.material === 'soft' ? '软墨' : '其他'} · ${sku.color}`,
        kind,
        occurred_on: input.occurred_on,
        posted_on: input.occurred_on,
        quantity_ml: quantity,
        signed_ml: signed,
        bottle_input: input.bottle_input,
        unit_cost: unitCost,
        amount,
        cost_pending: costPending,
        machine_id: input.machine_id,
        purpose: input.purpose,
        source_doc: input.source_doc,
        evidence: '',
        created_by_name: input.created_by_name,
        reverses_movement_id: null,
        reversed_by_id: null,
        balance_after_ml: nextBalance,
      }
      this._inkMovements.unshift(movement)
      return { entity: movement, operation_id: input.operation_id, replayed: false }
    }))
  }

  async reverseInkMovement(input: UvReverseInput): Promise<UvResponse<UvMutationResult<UvInkMovement>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:ink_write')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const original = this._inkMovements.find((candidate) => candidate.id === input.target_id)
      if (!original) throw new UvError(UV_ERROR_CODES.notFound, '原流水不存在。', { status: 404 })
      if (original.kind === 'reversal') {
        throw new UvError(UV_ERROR_CODES.invalidField, '冲销流水不能再被冲销。', { status: 422 })
      }
      if (original.reversed_by_id) {
        throw new UvError(UV_ERROR_CODES.invalidField, '该流水已经冲销过，不能重复冲销。', { status: 422 })
      }
      const balances = this.inkBalancesSync()
      const balance = balances.find((candidate) => candidate.sku_id === original.sku_id)!
      const signed = original.signed_ml.startsWith('-') ? original.signed_ml.slice(1) : `-${original.signed_ml}`
      const nextBalance = decimalAdd(balance.available_ml, signed)
      if (decimalCompare(nextBalance, '0') < 0) {
        throw new UvError(UV_ERROR_CODES.insufficientStock, '冲销后库存会变成负数，请先盘点。', { status: 422 })
      }
      const timestamp = nowIso()
      const movement: UvInkMovement = {
        ...original,
        id: this.nextId('IM'),
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        kind: 'reversal',
        quantity_ml: original.quantity_ml,
        signed_ml: signed,
        balance_after_ml: nextBalance,
        reverses_movement_id: original.id,
        reversed_by_id: null,
        purpose: `冲销：${input.reason}`,
        amount: original.amount ? money(original.amount.currency, `-${original.amount.amount}`.replace('--', '')) : null,
      }
      original.reversed_by_id = movement.id
      original.version += 1
      this._inkMovements.unshift(movement)
      return { entity: movement, operation_id: input.operation_id, replayed: false }
    }))
  }

  async saveAssignments(input: UvAssignmentInput): Promise<UvResponse<UvMutationResult<UvAssignment[]>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:shift_write')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const machine = this._machines.find((candidate) => candidate.id === input.machine_id)
      if (!machine) throw new UvError(UV_ERROR_CODES.notFound, '机台不存在。', { status: 404 })
      const template = DEFAULT_SHIFT_TEMPLATES[input.shift]
      this._assignments = this._assignments.filter((assignment) =>
        !(assignment.business_date === input.business_date
          && assignment.shift === input.shift
          && assignment.machine_id === input.machine_id),
      )
      const timestamp = nowIso()
      const batch = `DEMO-B-${input.business_date.replace(/-/g, '').slice(4)}-${machine.code}-${input.shift === 'day' ? 'D' : 'N'}`
      const created = input.worker_ids.map((workerId) => ({
        id: this.nextId('AS'),
        factory_id: SAMPLE_FACTORY_ID,
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        business_date: input.business_date,
        shift: input.shift,
        machine_id: input.machine_id,
        worker_id: workerId,
        share: 1,
        work_batch: batch,
        note: input.note || `班次模板 ${template.versionId}`,
      })) satisfies UvAssignment[]
      this._assignments.push(...created)
      return { entity: created, operation_id: input.operation_id, replayed: false }
    }))
  }

  async createExpense(input: UvExpenseInput): Promise<UvResponse<UvMutationResult<UvExpense>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:cost_write')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const timestamp = nowIso()
      const expense: UvExpense = {
        id: this.nextId('EX'),
        factory_id: SAMPLE_FACTORY_ID,
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        category: input.category,
        occurred_on: input.occurred_on,
        period: input.period,
        amount: money(input.currency, input.amount),
        machine_id: input.machine_id,
        evidence: input.evidence,
        source: 'manual',
        note: input.note,
        reverses_expense_id: null,
      }
      this._expenses.unshift(expense)
      return { entity: expense, operation_id: input.operation_id, replayed: false }
    }))
  }

  async saveMonthlyPolicy(input: UvMonthlyPolicyInput): Promise<UvResponse<UvMutationResult<UvMonthlyPolicy>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:cost_write')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      if (!input.working_days.length) {
        throw new UvError(UV_ERROR_CODES.invalidField, '工作日集合不能为空，分摊合计必须等于配置额。', {
          status: 422,
          fields: { working_days: '至少选择一天' },
        })
      }
      for (const [key, value] of [['rent', input.rent], ['utilities', input.utilities], ['management_wage', input.management_wage]] as const) {
        if (!value) continue
        const totals = prorationTotals(value.amount, input.working_days, value.currency, input.allocation_method)
        if (!totals.matches) {
          throw new UvError(UV_ERROR_CODES.invalidField, `${key} 分摊合计与配置额不一致。`, { status: 422 })
        }
      }
      const existing = this._monthlyPolicies.find((policy) => policy.month === input.month)
      const timestamp = nowIso()
      const policy: UvMonthlyPolicy = {
        id: existing?.id ?? this.nextId('MP'),
        factory_id: SAMPLE_FACTORY_ID,
        version: (existing?.version ?? 0) + 1,
        created_at: existing?.created_at ?? timestamp,
        updated_at: timestamp,
        month: input.month,
        working_days: [...input.working_days],
        allocation_method: input.allocation_method,
        rent: input.rent,
        utilities: input.utilities,
        management_wage: input.management_wage,
        note: input.note,
      }
      if (existing) Object.assign(existing, policy)
      else this._monthlyPolicies.push(policy)
      return { entity: policy, operation_id: input.operation_id, replayed: false }
    }))
  }

  async pricingPreview(input: UvPricingInput): Promise<UvResponse<UvPricingResult>> {
    await this.gate(true)
    this.requirePermission('uv_printing:cost_read')
    return this.wrap(computePricing(input))
  }

  async savePricingQuote(input: UvPricingQuoteInput): Promise<UvResponse<UvMutationResult<UvPricingQuote>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:cost_write')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const result = computePricing(input.input)
      const timestamp = nowIso()
      const quote: UvPricingQuote = {
        id: input.id ?? this.nextId('PQ'),
        factory_id: SAMPLE_FACTORY_ID,
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        label: input.label,
        input: input.input,
        result,
        product_id: input.product_id,
        adopted_rate_version_id: null,
        created_by_name: 'DEMO 成本员',
        note: input.note,
      }
      this._pricingQuotes.unshift(quote)
      return { entity: quote, operation_id: input.operation_id, replayed: false }
    }))
  }

  async adoptPricingQuote(input: UvPricingAdoptInput): Promise<UvResponse<UvMutationResult<UvRateVersion>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:cost_write')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const quote = this._pricingQuotes.find((candidate) => candidate.id === input.quote_id)
      if (!quote) throw new UvError(UV_ERROR_CODES.notFound, '测算记录不存在。', { status: 404 })
      if (!input.effective_from) {
        throw new UvError(UV_ERROR_CODES.invalidField, '采用为执行价必须指定生效日期。', { status: 422 })
      }
      const price = quote.result.markup_price
      if (price === null) {
        throw new UvError(UV_ERROR_CODES.invalidField, '测算结果不可计算，不能采用为执行价。', { status: 422 })
      }
      const timestamp = nowIso()
      const rate: UvRateVersion = {
        id: this.nextId('RV'),
        factory_id: SAMPLE_FACTORY_ID,
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        rate_kind: input.rate_kind,
        product_id: quote.product_id,
        process_version_id: null,
        machine_id: null,
        price_group: null,
        currency: quote.result.currency,
        unit_price: decimalRound(price, 6),
        effective_from: input.effective_from,
        effective_to: null,
        note: `由定价测算 ${quote.id} 显式采用，公式版本 ${UV_PRICING_FORMULA_VERSION}`,
      }
      this._rateVersions.push(rate)
      quote.adopted_rate_version_id = rate.id
      return { entity: rate, operation_id: input.operation_id, replayed: false }
    }))
  }

  async saveProduct(input: UvProductSaveInput): Promise<UvResponse<UvMutationResult<UvProduct>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:master_write')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      if (!input.product_no.trim()) {
        throw new UvError(UV_ERROR_CODES.invalidField, '货号不能为空。', { status: 422, fields: { product_no: '必填' } })
      }
      const duplicate = this._products.find((product) => product.product_no === input.product_no && product.id !== input.id)
      if (duplicate) {
        throw new UvError(UV_ERROR_CODES.invalidField, `货号 ${input.product_no} 已存在，货号不能按品名模糊覆盖。`, {
          status: 422,
          fields: { product_no: '已存在' },
        })
      }
      const timestamp = nowIso()
      const existing = input.id ? this._products.find((product) => product.id === input.id) : null
      if (existing) {
        assertVersion(input.expected_version, existing.version)
        existing.product_no = input.product_no
        existing.name = input.name
        existing.customer_name = input.customer_name
        existing.external_ref = input.external_ref
        existing.external_ref_kind = input.external_ref_kind
        existing.aliases = [...input.aliases]
        existing.version += 1
        existing.updated_at = timestamp
        return { entity: existing, operation_id: input.operation_id, replayed: false }
      }
      const product: UvProduct = {
        id: this.nextId('P'),
        factory_id: SAMPLE_FACTORY_ID,
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        product_no: input.product_no,
        name: input.name,
        customer_name: input.customer_name,
        external_ref: input.external_ref,
        external_ref_kind: input.external_ref_kind,
        aliases: [...input.aliases],
        is_active: true,
        process_versions: [],
      }
      this._products.push(product)
      return { entity: product, operation_id: input.operation_id, replayed: false }
    }))
  }

  async addProcessVersion(input: UvProcessVersionInput): Promise<UvResponse<UvMutationResult<UvProcessVersion>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:master_write')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const product = this._products.find((candidate) => candidate.id === input.product_id)
      if (!product) throw new UvError(UV_ERROR_CODES.notFound, '产品不存在。', { status: 404 })
      const timestamp = nowIso()
      const pricingArea = input.width_cm && input.length_cm
        ? decimalMultiply(input.width_cm, input.length_cm)
        : null
      const version: UvProcessVersion = {
        id: this.nextId('PV'),
        factory_id: SAMPLE_FACTORY_ID,
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        product_id: product.id,
        version_label: input.version_label,
        effective_from: input.effective_from,
        material: input.material,
        pieces_per_board: input.pieces_per_board,
        board_seconds: input.board_seconds,
        width_cm: input.width_cm,
        length_cm: input.length_cm,
        pricing_area_cm2: pricingArea,
        machine_area_m2: input.machine_area_m2,
        ink_reference_ml: input.ink_reference_ml,
        is_active: true,
      }
      product.process_versions = [...product.process_versions.map((candidate) => ({ ...candidate, is_active: false })), version]
      product.version += 1
      product.updated_at = timestamp
      return { entity: version, operation_id: input.operation_id, replayed: false }
    }))
  }

  async saveRateVersion(input: UvRateVersionInput): Promise<UvResponse<UvMutationResult<UvRateVersion>>> {
    await this.gate(false)
    assertScopeFactory(input)
    const permission = input.rate_kind === 'piece_wage' ? 'uv_printing:payroll_write' : 'uv_printing:cost_write'
    this.requirePermission(permission)
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const overlap = this._rateVersions.find((rate) =>
        rate.id !== input.id
        && rate.rate_kind === input.rate_kind
        && rate.product_id === input.product_id
        && rate.process_version_id === input.process_version_id
        && rate.machine_id === input.machine_id
        && rate.price_group === input.price_group
        && rate.currency === input.currency
        && input.effective_from <= (rate.effective_to ?? '9999-12-31')
        && rate.effective_from <= (input.effective_to ?? '9999-12-31'),
      )
      if (overlap) {
        throw new UvError(
          UV_ERROR_CODES.invalidField,
          `同优先级的同币种生效区间不得重叠（与 ${overlap.id} 冲突）。`,
          { status: 422, fields: { effective_from: '区间重叠' } },
        )
      }
      const timestamp = nowIso()
      const existing = input.id ? this._rateVersions.find((rate) => rate.id === input.id) : null
      if (existing) {
        assertVersion(input.expected_version, existing.version)
        Object.assign(existing, {
          unit_price: input.unit_price,
          effective_from: input.effective_from,
          effective_to: input.effective_to,
          note: input.note,
          version: existing.version + 1,
          updated_at: timestamp,
        })
        this.recomputeDerived()
        return { entity: existing, operation_id: input.operation_id, replayed: false }
      }
      const rate: UvRateVersion = {
        id: this.nextId('RV'),
        factory_id: SAMPLE_FACTORY_ID,
        version: 1,
        created_at: timestamp,
        updated_at: timestamp,
        rate_kind: input.rate_kind,
        product_id: input.product_id,
        process_version_id: input.process_version_id,
        machine_id: input.machine_id,
        price_group: input.price_group,
        currency: input.currency,
        unit_price: input.unit_price,
        effective_from: input.effective_from,
        effective_to: input.effective_to,
        note: input.note,
      }
      this._rateVersions.push(rate)
      this.recomputeDerived()
      return { entity: rate, operation_id: input.operation_id, replayed: false }
    }))
  }

  async saveMachine(input: UvMachineSaveInput): Promise<UvResponse<UvMutationResult<UvMachine>>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:master_write')
    return this.wrap(this.idempotent(input.operation_id, input, () => {
      const machine = this._machines.find((candidate) => candidate.id === input.id)
      if (!machine) throw new UvError(UV_ERROR_CODES.notFound, '机台不存在。', { status: 404 })
      assertVersion(input.expected_version, machine.version)
      machine.admin_status = input.admin_status
      machine.ink_material = input.ink_material
      machine.note = input.note
      // 普通 PATCH 不能伪造遥测：runtime_status 与 freshness 不在输入范围内。
      machine.last_heartbeat_at = input.enabled ? machine.last_heartbeat_at : machine.last_heartbeat_at
      machine.version += 1
      machine.updated_at = nowIso()
      this.recomputeDerived()
      return { entity: machine, operation_id: input.operation_id, replayed: false }
    }))
  }

  async exportReport(input: UvExportInput): Promise<UvResponse<UvReportExport>> {
    await this.gate(false)
    assertScopeFactory(input)
    this.requirePermission('uv_printing:export')
    const scope = input.scope
    const rows = this.reportsForScope(scope)
    const scopeParts = [
      scope.business_date ? `业务日 ${scope.business_date}` : '',
      scope.date_from ? `从 ${scope.date_from}` : '',
      scope.date_to ? `到 ${scope.date_to}` : '',
      scope.shift ? (scope.shift === 'day' ? '白班' : '夜班') : '全天',
      scope.q ? `搜索「${scope.q}」` : '',
    ].filter(Boolean)
    return this.wrap({
      kind: input.kind,
      file_name: `uv-${input.kind}-${this.asOf.slice(0, 10)}.csv`,
      generated_at: nowIso(),
      row_count: rows.length,
      scope_label: scopeParts.join(' · ') || '全部',
    })
  }

  /* ---------------- 测试辅助 ---------------- */

  /** 模拟时间推进：心跳与数据截止前移，用于演示新鲜度变化。 */
  advanceClock(minutes: number): void {
    this.asOf = new Date(new Date(this.asOf).getTime() + minutes * 60_000).toISOString()
    const asOf = this.asOf
    for (const machine of this._machines) {
      if (machine.last_heartbeat_at) {
        const age = (new Date(asOf).getTime() - new Date(machine.last_heartbeat_at).getTime()) / 60_000
        machine.freshness = age <= 5 ? 'fresh' : 'stale'
        if (machine.freshness === 'stale') machine.runtime_status = 'offline'
      }
    }
  }

  snapshot() {
    return {
      machines: this._machines,
      products: this._products,
      rateVersions: this._rateVersions,
      jobs: this._jobs,
      reports: this._reports,
      allocations: this._allocations,
      handovers: this._handovers,
      inkSkus: this._inkSkus,
      inkMovements: this._inkMovements,
      workers: this._workers,
      assignments: this._assignments,
      expenses: this._expenses,
      monthlyPolicies: this._monthlyPolicies,
      pricingQuotes: this._pricingQuotes,
    }
  }
}

export function sampleDailyStructureDrillLabel(kind: string): string {
  return DRILL_KIND_LABELS[kind] ?? kind
}

/** 报表行只暴露口径，不在这里重复计算业务公式。 */
export function assertSampleMonth(month: string): string {
  return month || SAMPLE_MONTH
}

export function sampleSplitByShift(startAt: IsoInstant, endAt: IsoInstant) {
  return splitByShift(startAt, endAt)
}

export function sampleProductOptionLabel(product: UvProduct): string {
  return `${product.product_no} · ${product.name}`
}

export function sampleMachineLabel(machine: UvMachine): string {
  return `${machine.code} · ${machine.name}`
}

export function sampleShiftLabel(shift: ShiftCode): string {
  return shift === 'day' ? '白班' : '夜班'
}

export function sampleDecimalGuard(value: string): boolean {
  return !decimalIsZero(value)
}

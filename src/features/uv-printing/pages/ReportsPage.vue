<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight,
  BadgeCheck,
  CalendarRange,
  ChartColumn,
  FileDown,
  Info,
  Printer,
  Receipt,
  RefreshCw,
  Rows3,
  SlidersHorizontal,
  TriangleAlert,
  Wallet,
} from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  UvDailyProjection,
  UvDailyReport,
  UvDrillKind,
  UvExpense,
  UvExpenseCategory,
  UvMachine,
  UvMeta,
  UvMonthlyProjection,
  UvReport,
  UvReportExport,
  UvScope,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand, useUvRequest } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import { daysInMonth, monthOf, SHIFT_LABELS, weekdayLabel } from '../domain/businessTime'
import {
  decimalAdd,
  decimalToNumber,
  formatDecimal,
  formatPercent,
  money,
  trimTrailingZeros,
} from '../domain/decimal'
import {
  OPERATING_RESULT_FORMULA_VERSION,
  aggregateDailyRows,
  coverageNotes,
  operatingResult,
  ratioOfSums,
  type OperatingResult,
} from '../domain/reporting'
import { COVERAGE, EXPENSE_CATEGORY_LABELS, QUALITY_STATUS, REPORT_STATUS, SOURCE_KIND } from '../domain/status'
import UvNumber from '../components/UvNumber.vue'
import UvStateBlock from '../components/UvStateBlock.vue'
import UvStatusPill from '../components/UvStatusPill.vue'
import UvFilterBar from '../components/UvFilterBar.vue'
import DailyTrendChart from '../components/DailyTrendChart.vue'
import ExpenseStructureChart from '../components/ExpenseStructureChart.vue'
import OperatingWaterfall from '../components/OperatingWaterfall.vue'
import MonthlyPolicyPanel from '../components/MonthlyPolicyPanel.vue'
import DrillDownDrawer from '../components/DrillDownDrawer.vue'
import ExpenseEntryDrawer from '../components/ExpenseEntryDrawer.vue'
import { readAllPages } from '../transport/pagination'

/**
 * 经营报表：先给结论，再给可核对的总表与下钻。
 *
 * 口径约定（docs/uv-printing/UV_PRINT_SHARED_SPEC.md 5.8 / 6.2 / 6.7）：
 * - 经营结余 = 产值 − 员工工资 − 管理人员工资 − 设备投资 − 工具费用 − 房租 − 水电 − 材料
 *   − 杂费 − 维修 − 夜班补贴 − 油墨领用成本 − 无产值工资 − 加工费 + 可回收工资 + 可回收油漆金额；
 *   这是旧管理口径，**不是法定净利润**，设备采购整笔扣减不得标成经营毛利；
 * - 月合格率、工资占比、结余率一律按月分子合计 / 月分母合计，不平均每天百分比；
 * - 缺日期的日子在趋势图里留空，不补 0；缺少成本项显示暂算，不显示 0；
 * - 金额需要 uv_printing:cost_read，个人工资需要 uv_printing:payroll_read；
 *   缺权限时显示「未授权」，不用隐藏列代替权限控制，后端才是权威；
 * - 失败不回落样例数据、不显示 0。
 */

const ctx = inject(UV_CONTEXT_KEY)!
const transport = inject(UV_TRANSPORT_KEY)!
const workspace = ctx.workspace
const route = useRoute()
const router = useRouter()
const toast = useUvToast()

const scope = computed<UvScope>(() => workspace.scope.value)
const revision = ctx.revision

const canReadCost = computed(() => workspace.can('uv_printing:cost_read'))
const canReadPayroll = computed(() => workspace.can('uv_printing:payroll_read'))
const canWriteCost = computed(() => workspace.can('uv_printing:cost_write'))
const canExport = computed(() => workspace.can('uv_printing:export'))

type ViewMode = 'daily' | 'monthly'
const viewMode = ref<ViewMode>(route.query.view === 'monthly' ? 'monthly' : 'daily')
const displayCurrency = ref('')
const CURRENCY_OPTIONS = [
  ['CNY', 'CNY 人民币'], ['HKD', 'HKD 港币'], ['USD', 'USD 美元'],
  ['JPY', 'JPY 日元'], ['EUR', 'EUR 欧元'], ['GBP', 'GBP 英镑'],
] as const

/** 月份：URL 参数优先；未指定时按当前业务日期所属自然月，不做「26 天/21 天」等制度假设。 */
const month = computed(() => {
  const raw = route.query.month
  const value = Array.isArray(raw) ? raw[0] : raw
  return typeof value === 'string' && /^\d{4}-\d{2}$/.test(value) ? value : monthOf(scope.value.business_date ?? '2026-09-01')
})

const monthDates = computed(() => daysInMonth(month.value))
const monthEnd = computed(() => monthDates.value[monthDates.value.length - 1] ?? `${month.value}-28`)

/** 日/月视图与月份都写回 URL query，保证可分享、刷新后仍在同一口径。 */
function setViewMode(mode: ViewMode) {
  viewMode.value = mode
  void router.replace({ query: { ...route.query, view: mode === 'monthly' ? 'monthly' : undefined } })
}

/* ---------------- 读取（同一 transport，失败不回落样例） ---------------- */

/**
 * 请求结果包装：字段名刻意不叫 `data`。
 * `useUvRequest` 内部用 shallowRef 保存结果，而 shallowRef 会自动解包顶层 `data` 属性，
 * 把 `{ data, meta }` 变成裸数组并丢掉 meta。这里改用 `payload` 保存数据、`meta` 保留截止时间。
 */
interface Loaded<T> {
  payload: T
  meta: UvMeta
}

const dailyScope = computed<UvScope>(() => ({ ...scope.value, page_size: 200 }))

const monthScope = computed<UvScope>(() => ({
  ...scope.value,
  business_date: undefined,
  date_from: `${month.value}-01`,
  date_to: monthEnd.value,
}))

const dailyProjectionRequest = useUvRequest<Loaded<UvDailyProjection[]>>(
  async (signal) => {
    const response = await readAllPages((nextScope, nextSignal) => transport.value.dailyProjection(nextScope, nextSignal), monthScope.value, signal)
    return { payload: response.data.items, meta: response.meta }
  },
  { watchSource: () => [scope.value.shift, month.value, revision.value] },
)

const dailyReportRequest = useUvRequest<Loaded<UvDailyReport>>(
  async (signal) => {
    const response = await transport.value.dailyReport(dailyScope.value, signal)
    return { payload: response.data, meta: response.meta }
  },
  { watchSource: () => [dailyScope.value.business_date, scope.value.shift, revision.value] },
)

const monthlyProjectionRequest = useUvRequest<Loaded<UvMonthlyProjection>>(
  async (signal) => {
    const response = await transport.value.monthlyProjection(
      { ...monthScope.value, status: month.value } as UvScope,
      signal,
    )
    return { payload: response.data, meta: response.meta }
  },
  { watchSource: () => [scope.value.shift, month.value, revision.value] },
)

const expenseRequest = useUvRequest<Loaded<UvExpense[]>>(
  async (signal) => {
    const response = await readAllPages((nextScope, nextSignal) => transport.value.expenses(nextScope, nextSignal), monthScope.value, signal)
    return { payload: response.data.items, meta: response.meta }
  },
  { watchSource: () => [month.value, revision.value] },
)

const reportRequest = useUvRequest<Loaded<UvReport[]>>(
  async (signal) => {
    const response = await readAllPages((nextScope, nextSignal) => transport.value.reports(nextScope, nextSignal), monthScope.value, signal)
    return { payload: response.data.items, meta: response.meta }
  },
  { watchSource: () => [scope.value.shift, month.value, revision.value] },
)

const machineRequest = useUvRequest<Loaded<UvMachine[]>>(
  async (signal) => {
    const response = await readAllPages((nextScope, nextSignal) => transport.value.machines(nextScope, nextSignal), scope.value, signal)
    return { payload: response.data.items, meta: response.meta }
  },
  { watchSource: () => [revision.value] },
)

const dailyProjection = computed(() => dailyProjectionRequest.data.value?.payload ?? [])
const dailyReport = computed(() => dailyReportRequest.data.value?.payload ?? null)
const monthlyProjection = computed(() => monthlyProjectionRequest.data.value?.payload ?? null)
const expenses = computed(() => expenseRequest.data.value?.payload ?? [])
const monthReports = computed(() => reportRequest.data.value?.payload ?? [])
const machines = computed(() => machineRequest.data.value?.payload ?? [])

const primaryLoading = computed(() =>
  dailyProjectionRequest.loading.value
  && !dailyProjectionRequest.settled.value
  && monthlyProjectionRequest.loading.value
  && !monthlyProjectionRequest.settled.value,
)

const primaryError = computed(() =>
  dailyProjectionRequest.error.value
  ?? monthlyProjectionRequest.error.value
  ?? expenseRequest.error.value
  ?? reportRequest.error.value,
)

const asOf = computed(() =>
  dailyReportRequest.data.value?.meta.as_of
  ?? monthlyProjectionRequest.data.value?.meta.as_of
  ?? dailyProjectionRequest.data.value?.meta.as_of
  ?? '',
)

function retryAll() {
  void dailyProjectionRequest.run()
  void dailyReportRequest.run()
  void monthlyProjectionRequest.run()
  void expenseRequest.run()
  void reportRequest.run()
  void machineRequest.run()
}

/* ---------------- 期间聚合与比率（全部由 reporting.ts 口径得出） ---------------- */

const dailyWithData = computed(() => dailyProjection.value.filter((row) => row.reported_qty > 0))

const monthAggregate = computed(() =>
  aggregateDailyRows(
    displayCurrency.value,
    dailyWithData.value,
    dailyWithData.value.some((row) => row.unpriced_reports > 0) ? 'partial' : 'complete',
  ),
)

const todayProjection = computed<UvDailyProjection | null>(() =>
  dailyProjection.value.find((row) => row.business_date === scope.value.business_date) ?? null,
)

/** 用户选择经营展示/录入币种；历史金额各自带币种，绝不把它们折算或猜成某一种。 */

/* ---------------- 经营结余输入（唯一权威聚合来自 operatingResult） ---------------- */

const COST_CATEGORY_KEYS: UvExpenseCategory[] = [
  'management_wage', 'equipment', 'tooling', 'rent', 'utilities',
  'material', 'sundry', 'maintenance', 'night_subsidy', 'processing',
  'recoverable_wage', 'recoverable_paint',
]

function sumExpensesByCategory(category: UvExpenseCategory): string | null {
  const matched = expenses.value.filter(
    (expense) => expense.category === category && expense.amount.currency === displayCurrency.value,
  )
  if (!matched.length) return null
  return matched.reduce((total, expense) => decimalAdd(total, expense.amount.amount), '0')
}

/**
 * 油墨领用成本直接取服务端口径的投影行（日=当日、月=整月），
 * 不在页面里再按流水方向重算一遍，避免同一口径出现两个数字。
 * 人工录入的「油墨」费用不并入这里，避免与墨水账本重复计入。
 */
const inkIssueCost = computed(() => {
  if (viewMode.value === 'daily') return todayProjection.value?.ink_cost?.amount ?? null
  return monthlyOperatingRows.value.find((row) => row.key === 'operating_inkIssueCost')?.value ?? null
})

const operatingInput = computed(() => {
  const outputValue = monthAggregate.value?.output_value?.amount ?? null
  return {
    currency: displayCurrency.value,
    outputValue,
    employeeWage: monthAggregate.value?.payroll_amount?.amount ?? null,
    managementWage: sumExpensesByCategory('management_wage'),
    equipment: sumExpensesByCategory('equipment'),
    tooling: sumExpensesByCategory('tooling'),
    rent: sumExpensesByCategory('rent'),
    utilities: sumExpensesByCategory('utilities'),
    material: sumExpensesByCategory('material'),
    sundry: sumExpensesByCategory('sundry'),
    maintenance: sumExpensesByCategory('maintenance'),
    nightSubsidy: sumExpensesByCategory('night_subsidy'),
    inkIssueCost: inkIssueCost.value,
    noOutputWage: null,
    processing: sumExpensesByCategory('processing'),
    recoverableWage: sumExpensesByCategory('recoverable_wage'),
    recoverablePaint: sumExpensesByCategory('recoverable_paint'),
  }
})

const computedOperating = computed<OperatingResult>(() => operatingResult(operatingInput.value))

/** 月度经营结余以月度投影的补充行为准（服务端口径），本地计算只用于稳定展示。 */
const monthlyOperatingRows = computed(() =>
  (monthlyProjection.value?.structure ?? []).filter((row) => row.key.startsWith('operating_')),
)

const monthlyNet = computed(() => {
  const row = monthlyProjection.value?.months[0]
  return row?.operating_result?.amount ?? computedOperating.value.operatingResult
})

const monthlyContribution = computed(() => {
  const equipment = monthlyOperatingRows.value.find((row) => row.key === 'operating_equipment')?.value
  if (monthlyNet.value === null) {
    return equipment ? decimalAdd('0', equipment) : computedOperating.value.operatingContribution
  }
  if (equipment && equipment.startsWith('-')) return decimalAdd(monthlyNet.value, equipment.slice(1))
  return computedOperating.value.operatingContribution
})

const monthlyEquipmentDifference = computed(() => {
  const value = monthlyOperatingRows.value.find((row) => row.key === 'operating_equipment')?.value
  if (!value) return null
  return value.startsWith('-') ? value.slice(1) : value
})

const waterfallRows = computed(() =>
  monthlyOperatingRows.value.length ? monthlyOperatingRows.value : computedOperating.value.rows,
)

const waterfallWarnings = computed(() => computedOperating.value.warnings)

/* ---------------- 口径说明（coverageNotes） ---------------- */

const unpricedCount = computed(() => {
  if (viewMode.value === 'monthly') {
    return dailyWithData.value.reduce((total, row) => total + row.unpriced_reports, 0)
  }
  return todayProjection.value?.unpriced_reports ?? 0
})

const qualityPendingCount = computed(() => {
  if (viewMode.value === 'monthly') {
    return dailyWithData.value.reduce((total, row) => total + row.quality_pending_reports, 0)
  }
  return todayProjection.value?.quality_pending_reports ?? 0
})

const costCoverageComplete = computed(() => {
  const required: UvExpenseCategory[] = ['rent', 'utilities', 'management_wage', 'material', 'tooling']
  if (!canReadCost.value) return false
  return required.every((category) => sumExpensesByCategory(category) !== null)
})

const missingCostCategories = computed(() => {
  if (!canReadCost.value) return []
  const required: UvExpenseCategory[] = [
    'rent', 'utilities', 'management_wage', 'tooling', 'material',
    'sundry', 'maintenance', 'night_subsidy', 'processing',
  ]
  return required
    .filter((category) => sumExpensesByCategory(category) === null)
    .map((category) => EXPENSE_CATEGORY_LABELS[category] ?? category)
})

const isClosed = ref(false)
const closedKnown = ref(false)

const coverageNoteList = computed(() =>
  coverageNotes({
    unpricedReports: unpricedCount.value,
    qualityPendingReports: qualityPendingCount.value,
    missingCostCategories: missingCostCategories.value,
    closed: isClosed.value,
    asOf: asOf.value || '未知',
  }),
)

const coverageKind = computed<'complete' | 'partial' | 'no_data'>(() => {
  if (!dailyProjection.value.length && !dailyProjectionRequest.loading.value) return 'no_data'
  if (unpricedCount.value || qualityPendingCount.value || missingCostCategories.value.length) return 'partial'
  return 'complete'
})

/* ---------------- 结论标题 ---------------- */

const dataGapDates = computed(() =>
  monthDates.value.filter((date) => !dailyWithData.value.some((row) => row.business_date === date)),
)

const headline = computed(() => {
  if (viewMode.value === 'daily') {
    const date = scope.value.business_date ?? ''
    if (!todayProjection.value || !dailyProjection.value.length) {
      return `${date} 没有可用数据，无法给出经营结论`
    }
    const parts: string[] = []
    if (unpricedCount.value) parts.push(`当日有 ${unpricedCount.value} 个班次还未定工价，产值与结余暂算`)
    if (qualityPendingCount.value) parts.push(`${qualityPendingCount.value} 个班次质量未判清，良率暂算`)
    if (missingCostCategories.value.length) parts.push(`缺 ${missingCostCategories.value.join('、')} 成本，结余暂算`)
    if (!parts.length) parts.push('当日数据完整，可核对')
    return `${date}（${weekdayLabel(date)} · ${SHIFT_LABELS[scope.value.shift ?? 'all']}）${parts.join('；')}`
  }

  const parts: string[] = []
  if (unpricedCount.value) parts.push(`本月仍有 ${unpricedCount.value} 个班次未定工价，结余暂算`)
  if (qualityPendingCount.value) parts.push(`${qualityPendingCount.value} 个班次质量未判清，月良率暂算`)
  if (missingCostCategories.value.length) parts.push(`缺 ${missingCostCategories.value.join('、')} 成本，结余按已填项目暂算`)
  if (!parts.length) parts.push(`${month.value} 数据完整，可核对`)
  return parts.join('；')
})

const headlineAttention = computed(() =>
  Boolean(unpricedCount.value || qualityPendingCount.value || missingCostCategories.value.length),
)

const conclusionStats = computed(() => {
  const stats: Array<{ label: string; value: string }> = [
    { label: '未定工价班次', value: String(unpricedCount.value) },
    { label: '质量未判清班次', value: String(qualityPendingCount.value) },
    { label: `缺成本项`, value: String(missingCostCategories.value.length) },
  ]
  if (viewMode.value === 'monthly') {
    stats.push({ label: '本月无报工日期', value: `${dataGapDates.value.length} 天` })
  }
  return stats
})

/* ---------------- 汇总指标（含公式文本） ---------------- */

const scaleItems = computed(() => {
  const aggregate = monthAggregate.value
  const items: Array<{ label: string; value: string; formula: string; state: 'normal' | 'provisional' | 'missing' }> = [
    {
      label: '月合格率',
      value: formatPercent(aggregate?.yield_rate ?? null, 2),
      formula: `公式：月合格件合计 ${aggregate?.good_qty ?? 0} ÷（合格 ${aggregate?.good_qty ?? 0} + 不良 ${aggregate?.defective_qty ?? 0}）（月分子合计 ÷ 月分母合计，不平均每天百分比）`,
      state: qualityPendingCount.value ? 'provisional' : aggregate?.yield_rate ? 'normal' : 'missing',
    },
  ]
  if (canReadCost.value) {
    items.push({
      label: '工资占比',
      value: formatPercent(aggregate?.payroll_ratio ?? null, 2),
      formula: `公式：月班组计件工资合计 ${aggregate?.payroll_amount ? formatDecimal(trimTrailingZeros(aggregate.payroll_amount.amount), 2) : '暂算'} ÷ 月产值合计 ${aggregate?.output_value ? formatDecimal(trimTrailingZeros(aggregate.output_value.amount), 2) : '暂算'}（同样按合计相除）`,
      state: aggregate?.payroll_ratio ? 'normal' : 'provisional',
    })
    items.push({
      label: '结余率',
      value: formatPercent(aggregate?.result_ratio ?? null, 2),
      formula: `公式：月经营结余合计 ${monthlyNet.value === null ? '暂算' : formatDecimal(trimTrailingZeros(monthlyNet.value), 2)} ÷ 月产值合计（旧管理口径，不是法定净利率）`,
      state: aggregate?.result_ratio ? 'normal' : 'provisional',
    })
  }
  return items
})

/** 机台开机率与时间利用率是两个独立指标，且都不叫 OEE。 */
const utilisation = computed(() => {
  const total = machines.value.length
  const enabled = machines.value.filter((machine) => machine.admin_status !== 'disabled')
  const running = machines.value.filter((machine) => machine.runtime_status === 'printing')
  const fresh = machines.value.filter((machine) => machine.freshness === 'fresh')
  const openedRate = total ? ratioOfSums(running.length, total) : null
  const timeRate = enabled.length ? ratioOfSums(fresh.length, enabled.length) : null
  return { total, enabled: enabled.length, running: running.length, fresh: fresh.length, openedRate, timeRate }
})

const headcountMetric = computed(() => {
  const aggregate = monthAggregate.value
  const workerIds = new Set<string>()
  const workerDays = new Set<string>()
  for (const report of monthReports.value) {
    if (report.status !== 'confirmed' && report.status !== 'corrected') continue
    for (const workerId of report.worker_ids) {
      workerIds.add(workerId)
      workerDays.add(`${report.business_date}:${workerId}`)
    }
  }
  const output = aggregate?.output_value?.amount ?? null
  const perPersonDay = output && workerDays.size ? ratioOfSums(decimalToNumber(output), workerDays.size) : null
  const perPerson = output && workerIds.size ? ratioOfSums(decimalToNumber(output), workerIds.size) : null
  return { workerIds: workerIds.size, workerDays: workerDays.size, perPersonDay, perPerson, output }
})

/* ---------------- 导出范围与导出 ---------------- */

const rangeLabel = computed(() =>
  viewMode.value === 'monthly'
    ? `${month.value}-01 至 ${monthEnd.value}`
    : `${scope.value.business_date ?? ''} 单日`,
)

const exportScope = computed<UvScope>(() => (viewMode.value === 'monthly'
  ? {
      factory_id: scope.value.factory_id,
      date_from: `${month.value}-01`,
      date_to: monthEnd.value,
      shift: scope.value.shift,
    }
  : { ...scope.value }))

const exportScopeLabel = computed(() => [
  `华康A 生产部`,
  `范围 ${rangeLabel.value}`,
  `班次 ${SHIFT_LABELS[scope.value.shift ?? 'all']}`,
  `视图 ${viewMode.value === 'monthly' ? '月报' : '日报'}`,
].join(' · '))

const exportCommand = useUvCommand<UvReportExport>()
const lastExport = ref<UvReportExport | null>(null)

async function runExport() {
  if (!canExport.value) {
    toast.push({
      message: '没有导出权限',
      detail: '需要 uv_printing:export；后端是权威判定，这里不做「隐藏按钮」式权限控制。',
      tone: 'red',
      retryable: false,
    })
    return
  }
  const operationId = newOperationId()
  const result = await exportCommand.execute(operationId, () => transport.value.exportReport({
    factory_id: scope.value.factory_id,
    operation_id: operationId,
    expected_version: 0,
    kind: viewMode.value === 'monthly' ? 'monthly' : 'daily',
    scope: exportScope.value,
  }).then((response) => response.data))

  if (!result) {
    toast.push({
      message: '导出失败',
      detail: exportCommand.error.value?.message ?? '导出没有返回结果，未生成文件。',
      tone: 'red',
      retryable: true,
    })
    return
  }
  lastExport.value = result
  toast.push({
    message: `已生成 ${result.file_name}`,
    detail: `${result.row_count} 行 · 范围 ${result.scope_label}`,
    tone: 'green',
    retryable: false,
  })
}

function printPage() {
  window.print()
}

/* ---------------- 下钻与录入 ---------------- */

const drill = ref<{ kind: UvDrillKind; ref: string | null; subject: string } | null>(null)
const expenseOpen = ref(false)

function openDrill(kind: UvDrillKind, drillRef: string | null, subject: string) {
  drill.value = { kind, ref: drillRef, subject }
}

function drillDailyRow(row: UvDailyProjection) {
  openDrill(
    row.unpriced_reports > 0 && row.reported_qty === 0 ? 'unpriced_reports' : 'reports',
    row.business_date,
    `业务日 ${row.business_date}`,
  )
}

function drillExpenseRow(category: UvExpenseCategory) {
  openDrill('expenses', category, EXPENSE_CATEGORY_LABELS[category] ?? '费用记录')
}

/* ---------------- 可核对总表 ---------------- */

const dailyRows = computed(() => dailyProjection.value)

const monthlyRows = computed(() => monthlyProjection.value?.months ?? [])

const monthlyStructureRows = computed(() =>
  (monthlyProjection.value?.structure ?? []).filter((row) => !row.key.startsWith('operating_')),
)

const aggregateForTable = computed(() => monthAggregate.value)

/** 核对列：日合计与月口径是否一致，不一致必须显式指出而不是抹平。 */
const reconciliation = computed(() => {
  const aggregate = monthAggregate.value
  const monthly = monthlyProjection.value?.months[0]
  if (!aggregate || !monthly) return null
  const qtyMatches = aggregate.good_qty === monthly.good_qty && aggregate.reported_qty === monthly.reported_qty
  const outputMatches = (aggregate.output_value?.amount ?? null) === (monthly.output_value?.amount ?? null)
  const netMatches = (aggregate.operating_result?.amount ?? null) === (monthly.operating_result?.amount ?? null)
  return { qtyMatches, outputMatches, netMatches }
})

function machineLabel(machineId: string): string {
  return machines.value.find((machine) => machine.id === machineId)?.code ?? machineId
}

function shiftLabel(shift: string | undefined): string {
  return SHIFT_LABELS[(shift ?? 'all') as 'day' | 'night' | 'all'] ?? '全天'
}

const unpricedReports = computed(() =>
  monthReports.value.filter(
    (report) => report.status !== 'voided' && report.commercial?.pricing_state !== 'priced',
  ),
)

const filterChips = computed(() => [
  {
    key: 'range',
    label: '范围',
    value: rangeLabel.value,
    active: viewMode.value === 'monthly',
    hint: '月报按归属期整月；日报按单业务日',
  },
  { key: 'shift', label: '班次', value: shiftLabel(scope.value.shift), active: scope.value.shift !== undefined },
  {
    key: 'month',
    label: '月份',
    value: month.value,
    active: month.value !== monthOf(scope.value.business_date ?? month.value),
    hint: '月报与分摊配置使用同一月份',
  },
])

function shiftMonth(offset: number) {
  const [year, monthNumber] = month.value.split('-').map(Number)
  const date = new Date(Date.UTC(year, (monthNumber ?? 1) - 1 + offset, 1))
  const next = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
  void router.replace({ query: { ...route.query, month: next, view: 'monthly' } })
  viewMode.value = 'monthly'
}

function goToday() {
  workspace.setBusinessDate(scope.value.business_date ?? '')
}

const settledKnown = ref(false)
const settled = ref(false)

/* 月度投影已经结束加载但没有任何月份行时，视为真实空数据。 */
const monthlyEmpty = computed(() =>
  monthlyProjectionRequest.settled.value
  && !monthlyProjectionRequest.loading.value
  && !monthlyProjection.value?.months.length,
)
</script>

<template>
  <div class="space-y-4">
    <header class="uv-page-head">
      <div class="uv-page-head__titles">
        <p class="uv-page-head__eyebrow">Operating Report</p>
        <h1>经营报表</h1>
        <p class="uv-page-head__desc">
          经营结余是旧管理口径（产值 − 各项费用 + 可回收项），不是法定净利润；设备投资整笔扣减，
          因此另外给出「排除设备投资的经营贡献」。所有金额按币种分别列示，不折汇相加。
        </p>
      </div>
      <div class="uv-page-head__actions">
        <label class="uv-filter">
          <span class="uv-filter__label">经营币种</span>
          <select v-model="displayCurrency" class="uv-input uv-select" aria-label="经营报表币种">
            <option value="">请选择币种</option>
            <option v-for="[code, label] in CURRENCY_OPTIONS" :key="code" :value="code">{{ label }}</option>
          </select>
        </label>
        <div class="uv-view-switch" role="group" aria-label="日/月视图切换">
          <button
            type="button"
            :aria-pressed="viewMode === 'daily'"
            @click="setViewMode('daily')"
          >
            日报
          </button>
          <button
            type="button"
            :aria-pressed="viewMode === 'monthly'"
            @click="setViewMode('monthly')"
          >
            月报
          </button>
        </div>
        <Button
          variant="outline"
          size="sm"
          type="button"
          :aria-pressed="canExport"
          :title="canExport ? '导出范围与当前页面完全一致' : '需要 uv_printing:export'"
          :disabled="exportCommand.pending.value"
          @click="runExport"
        >
          <FileDown class="size-3.5" aria-hidden="true" />
          {{ exportCommand.pending.value ? '正在导出…' : '导出当前范围' }}
        </Button>
        <Button variant="outline" size="sm" type="button" @click="printPage">
          <Printer class="size-3.5" aria-hidden="true" />
          打印
        </Button>
        <Button variant="outline" size="sm" type="button" @click="retryAll">
          <RefreshCw class="size-3.5" aria-hidden="true" />
          刷新
        </Button>
      </div>
    </header>

    <div v-if="!canExport" class="uv-callout uv-callout--warning" role="status">
      <TriangleAlert class="inline size-3.5" aria-hidden="true" />
      当前账号没有 uv_printing:export，导出不可用；页面仍可按当前筛选范围核对数据。后端是权威判定，
      隐藏按钮不是权限控制。
    </div>

    <UvFilterBar
      :chips="filterChips"
      :summary="`${exportScopeLabel}${viewMode === 'monthly' ? ` · 已关账状态${closedKnown ? (settled ? '：已关账' : '：未关账') : '未由接口下发'}` : ''}`"
      :clearable="false"
      @change="(key: string, value: string) => { if (key === 'month') { void router.replace({ query: { ...route.query, month: value, view: 'monthly' } }) } }"
    />

    <div v-if="lastExport" class="uv-callout uv-callout--accent" role="status">
      <strong>已导出 {{ lastExport.file_name }}</strong>：{{ lastExport.row_count }} 行 · 范围
      {{ lastExport.scope_label }} · 生成于 {{ lastExport.generated_at }}
    </div>

    <UvStateBlock
      v-if="primaryError && !dailyProjection.length && !monthlyProjection"
      state="error"
      subject="经营报表"
      :message="primaryError.message"
      :detail="`${primaryError.code} · ${exportScopeLabel}`"
      retryable
      @retry="retryAll"
    />

    <UvStateBlock
      v-else-if="primaryLoading"
      state="loading"
      subject="经营报表"
    />

    <UvStateBlock
      v-else-if="!dailyProjection.length && monthlyEmpty"
      state="empty"
      subject="经营报表数据"
      :hint="`${month} 没有任何已确认报工与费用记录；这是真实空数据，不是读取失败，也不会按 0 出结论。`"
    />

    <template v-else>
      <!-- 结论标题 -->
      <section
        class="uv-report-conclusion"
        :class="headlineAttention ? 'uv-report-conclusion--attention' : ''"
        aria-label="本期经营结论"
      >
        <div class="uv-report-conclusion__headline">
          <p>{{ headline }}</p>
          <div class="uv-report-conclusion__meta">
            <UvStatusPill :status="COVERAGE[coverageKind]" compact />
            <span>{{ exportScopeLabel }}</span>
            <span>数据截止 {{ asOf || '未知' }}（接口下发）</span>
          </div>
          <ul class="uv-report-conclusion__stats">
            <li v-for="stat in conclusionStats" :key="stat.label">
              {{ stat.label }} <strong>{{ stat.value }}</strong>
            </li>
          </ul>
          <p v-if="monthlyProjection?.provisional_reasons.length" class="uv-field__hint">
            暂算原因：{{ monthlyProjection.provisional_reasons.join('；') }}
          </p>
        </div>
        <div class="uv-actions uv-actions--end">
          <Button variant="outline" size="sm" type="button" @click="openDrill('unpriced_reports', null, '未定价报工')">
            <Receipt class="size-3.5" aria-hidden="true" />
            查看未定价报工
          </Button>
          <Button
            variant="outline"
            size="sm"
            type="button"
            :disabled="!canWriteCost"
            @click="expenseOpen = true"
          >
            <Wallet class="size-3.5" aria-hidden="true" />
            费用录入
          </Button>
        </div>
      </section>

      <!-- 口径说明 -->
      <section class="uv-panel" aria-label="口径说明">
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">
              <Info class="inline size-3.5" aria-hidden="true" />
              口径说明
            </h2>
            <p class="uv-panel__subtitle">
              已关账/未关账、未定价、未完成质量、缺成本、数据截止时间全部在这里列出；数字口径与图、表、下钻完全一致。
            </p>
          </div>
        </div>
        <div class="uv-panel__body">
          <ul class="uv-list">
            <li v-for="note in coverageNoteList" :key="note">
              <span class="uv-list__dot" aria-hidden="true" />
              <span>{{ note }}</span>
            </li>
          </ul>
          <p
            v-if="!closedKnown"
            class="uv-callout uv-callout--warning"
            style="margin-top: 10px"
          >
            关账状态未由接口下发：这里不假设「已关账」，也不把未关账当作已定稿。
            已结算月份在分摊配置里修改参数必须填写修订说明。
          </p>
        </div>
      </section>

      <!-- 按日期趋势 -->
      <section class="uv-panel" aria-label="按日期趋势">
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">
              <ChartColumn class="inline size-3.5" aria-hidden="true" />
              按日期趋势 · {{ month }}
            </h2>
            <p class="uv-panel__subtitle">
              横轴是真实业务日期；没有报工的日子留空，不补 0。图只表达趋势，精确值与缺失原因在同口径数据表里。
            </p>
          </div>
          <div class="uv-actions">
            <Button variant="ghost" size="sm" type="button" @click="shiftMonth(-1)">
              上一月
            </Button>
            <Button variant="ghost" size="sm" type="button" @click="shiftMonth(1)">
              下一月
            </Button>
            <Button variant="outline" size="sm" type="button" @click="goToday">
              回到当前业务日
            </Button>
          </div>
        </div>
        <div class="uv-panel__body">
          <UvStateBlock
            v-if="dailyProjectionRequest.error.value"
            state="error"
            subject="按日期趋势"
            :message="dailyProjectionRequest.error.value.message"
            retryable
            compact
            @retry="dailyProjectionRequest.run"
          />
          <DailyTrendChart
            v-else
            :rows="dailyProjection"
            :period-dates="monthDates"
            :currency="displayCurrency"
            :can-read-cost="canReadCost"
            :can-read-payroll="canReadPayroll"
            :as-of="asOf"
            :coverage="coverageKind"
            :loading="dailyProjectionRequest.loading.value"
          />
        </div>
      </section>

      <!-- 汇总指标与公式 -->
      <section class="uv-panel" aria-label="关键比率与利用率">
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">
              <BadgeCheck class="inline size-3.5" aria-hidden="true" />
              比率与利用率
            </h2>
            <p class="uv-panel__subtitle">
              月合格率、工资占比、结余率都按月分子合计 ÷ 月分母合计计算，不平均每天百分比；
              每个指标旁边直接给出公式。
            </p>
          </div>
        </div>
        <div class="uv-panel__body">
          <dl class="uv-scale">
            <div v-for="item in scaleItems" :key="item.label" class="uv-scale__item">
              <dt class="uv-field__label">{{ item.label }}</dt>
              <dd>
                <span class="uv-scale__value" :class="item.state === 'provisional' ? 'uv-num--provisional' : ''">
                  {{ item.value }}
                </span>
                <span class="uv-scale__formula">{{ item.formula }}</span>
              </dd>
            </div>

            <div class="uv-scale__item">
              <dt class="uv-field__label">机台开机率</dt>
              <dd>
                <span class="uv-scale__value">{{ formatPercent(utilisation.openedRate, 2) }}</span>
                <span class="uv-scale__formula">
                  公式：遥测为「打印中」的机台 {{ utilisation.running }} ÷ 全部机台 {{ utilisation.total }}（机台开机率，不是 OEE）
                </span>
              </dd>
            </div>

            <div class="uv-scale__item">
              <dt class="uv-field__label">时间利用率</dt>
              <dd>
                <span class="uv-scale__value">{{ formatPercent(utilisation.timeRate, 2) }}</span>
                <span class="uv-scale__formula">
                  公式：心跳新鲜的有效机台 {{ utilisation.fresh }} ÷ 非停用机台 {{ utilisation.enabled }}
                  （时间利用率只反映采集心跳覆盖，与机台开机率分开，都不叫 OEE）
                </span>
              </dd>
            </div>

            <div v-if="canReadCost" class="uv-scale__item">
              <dt class="uv-field__label">人均产值</dt>
              <dd>
                <span class="uv-scale__value">
                  {{ headcountMetric.perPersonDay === null ? '暂算' : formatDecimal(headcountMetric.perPersonDay, 2) }}
                </span>
                <span class="uv-scale__formula">
                  口径：分母是<b>人日</b>——本月已确认报工涉及的 {{ headcountMetric.workerDays }} 个人日（日期 × 人员去重）；
                  另一口径 {{ headcountMetric.perPerson === null ? '暂算' : formatDecimal(headcountMetric.perPerson, 2) }} 的分母是去重人数
                  {{ headcountMetric.workerIds }} 人。两个数不可混用。
                </span>
              </dd>
            </div>
          </dl>

          <div v-if="!canReadCost" class="uv-state uv-state--warning" role="alert" style="margin-top: 12px">
            <div class="uv-state__icon uv-state__icon--warning" aria-hidden="true">
              <TriangleAlert class="size-5" />
            </div>
            <p class="uv-state__title">未授权：成本相关比率</p>
            <p class="uv-state__message">
              当前账号没有 uv_printing:cost_read，工资占比、结余率与人均产值不会下发到前端。
              这里不显示数字，也不用「隐藏列」代替权限控制；后端是权威判定。
            </p>
          </div>
        </div>
      </section>

      <!-- 经营结余 -->
      <section class="uv-panel" aria-label="经营结余">
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">
              <Rows3 class="inline size-3.5" aria-hidden="true" />
              经营结余 · {{ viewMode === 'monthly' ? month : scope.business_date }}
            </h2>
            <p class="uv-panel__subtitle">
              经营结余 = 产值 − 员工工资 − 管理人员工资 − 设备投资 − 工具费用 − 房租 − 水电 − 材料
              − 杂费 − 维修 − 夜班补贴 − 油墨领用成本 − 无产值工资 − 加工费
              + 可回收工资 + 可回收油漆金额。旧管理口径，不是法定净利润。
            </p>
          </div>
        </div>
        <div class="uv-panel__body">
          <OperatingWaterfall
            :rows="waterfallRows"
            :currency="displayCurrency"
            :net="monthlyNet"
            :contribution="monthlyContribution"
            :equipment-difference="monthlyEquipmentDifference"
            :warnings="waterfallWarnings"
            :formula-version="OPERATING_RESULT_FORMULA_VERSION"
            :can-read-cost="canReadCost"
            :as-of="asOf"
            :period-label="viewMode === 'monthly' ? month : (scope.business_date ?? '')"
            @drill="(kind: UvDrillKind, ref: string | null, label: string) => openDrill(kind, ref, label)"
          />
        </div>
      </section>

      <!-- 费用构成 -->
      <section class="uv-panel" aria-label="费用构成">
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">
              <Receipt class="inline size-3.5" aria-hidden="true" />
              费用构成 · 归属期 {{ month }}
            </h2>
            <p class="uv-panel__subtitle">
              按金额降序的水平条 + 同口径数据表；不同币种分别列示并标「待核」，不折汇成一个金额。
            </p>
          </div>
        </div>
        <div class="uv-panel__body">
          <UvStateBlock
            v-if="expenseRequest.error.value"
            state="error"
            subject="费用构成"
            :message="expenseRequest.error.value.message"
            retryable
            compact
            @retry="expenseRequest.run"
          />
          <UvStateBlock
            v-else-if="expenseRequest.loading.value && !expenseRequest.settled.value"
            state="loading"
            subject="费用构成"
            compact
          />
          <ExpenseStructureChart
            v-else
            :expenses="expenses"
            :currency="displayCurrency"
            :base="monthAggregate?.output_value?.amount ?? null"
            :can-read-cost="canReadCost"
            :period-label="month"
            :as-of="asOf"
            ready
            @drill="(category: string, label: string) => drillExpenseRow(category as UvExpenseCategory)"
          />
        </div>
      </section>

      <!-- 可核对总表 -->
      <section class="uv-panel" aria-label="可核对总表">
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">
              <CalendarRange class="inline size-3.5" aria-hidden="true" />
              可核对总表 · {{ viewMode === 'monthly' ? '按日期（月报）' : '单日明细' }}
            </h2>
            <p class="uv-panel__subtitle">
              每一行都能下钻到原始记录：业务报工、采集作业、墨水流水、费用记录、工资明细、入库核数、未定价报工。
              缺失与暂算逐行标注，不显示 0。
            </p>
          </div>
          <div class="uv-actions">
            <span v-if="reconciliation" class="uv-field__hint">
              核对：
              {{ reconciliation.qtyMatches ? '数量一致' : '数量与月口径不一致' }} ·
              {{ canReadCost ? (reconciliation.outputMatches ? '产值一致' : '产值与月口径不一致') : '产值未授权' }} ·
              {{ canReadCost ? (reconciliation.netMatches ? '结余一致' : '结余与月口径不一致') : '结余未授权' }}
            </span>
          </div>
        </div>
        <div class="uv-panel__body uv-panel__body--flush">
          <div class="uv-table-scroll" role="region" tabindex="0" aria-label="可核对总表">
            <table class="uv-table" style="min-width: 1180px">
              <caption class="uv-table-caption">
                与页面筛选范围完全一致；{{ viewMode === 'monthly' ? '月报按日列出并给出月度合计' : '日报按业务日列出' }}。
              </caption>
              <thead>
                <tr>
                  <th scope="col">业务日期</th>
                  <th scope="col">班次 / 休息</th>
                  <th scope="col" class="uv-table-cell--right">合格件</th>
                  <th scope="col" class="uv-table-cell--right">报工件</th>
                  <th scope="col" class="uv-table-cell--right">良率</th>
                  <th v-if="canReadCost" scope="col" class="uv-table-cell--right">产值</th>
                  <th v-if="canReadPayroll" scope="col" class="uv-table-cell--right">班组计件工资</th>
                  <th v-if="canReadCost" scope="col" class="uv-table-cell--right">油墨领用成本</th>
                  <th v-if="canReadCost" scope="col" class="uv-table-cell--right">经营结余</th>
                  <th scope="col">口径</th>
                  <th scope="col">下钻</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in dailyRows" :key="row.business_date">
                  <td>
                    <span class="uv-row-primary">{{ row.business_date }}</span>
                    <span class="uv-row-sub">{{ weekdayLabel(row.business_date) }}</span>
                  </td>
                  <td>
                    <span>{{ shiftLabel(scope.shift) }}</span>
                    <span class="uv-row-sub">
                      {{ row.planned_day_off ? '计划休息日' : '计划工作日' }}
                      <template v-if="row.off_plan_production"> · 计划外生产</template>
                    </span>
                  </td>
                  <td class="uv-table-cell--right">
                    <UvNumber :qty="row.reported_qty > 0 ? row.good_qty : null" size="sm" :state="row.reported_qty > 0 ? 'normal' : 'missing'" />
                  </td>
                  <td class="uv-table-cell--right">
                    <UvNumber :qty="row.reported_qty > 0 ? row.reported_qty : null" size="sm" :state="row.reported_qty > 0 ? 'normal' : 'missing'" />
                  </td>
                  <td class="uv-table-cell--right">
                    <UvNumber :percent="row.yield_rate" size="sm" :state="row.yield_rate === null ? 'missing' : row.quality_pending_reports ? 'provisional' : 'normal'" />
                  </td>
                  <td v-if="canReadCost" class="uv-table-cell--right">
                    <UvNumber :money="row.output_value" size="sm" :state="row.output_value === null ? 'unpriced' : row.unpriced_reports ? 'provisional' : 'normal'" />
                  </td>
                  <td v-if="canReadPayroll" class="uv-table-cell--right">
                    <UvNumber :money="row.payroll_amount" size="sm" :state="row.payroll_amount === null ? 'unpriced' : 'normal'" />
                  </td>
                  <td v-if="canReadCost" class="uv-table-cell--right">
                    <UvNumber :money="row.ink_cost" size="sm" />
                  </td>
                  <td v-if="canReadCost" class="uv-table-cell--right">
                    <UvNumber :money="row.operating_result" size="sm" :state="row.operating_result === null ? 'provisional' : 'normal'" />
                  </td>
                  <td>
                    <span v-if="row.unpriced_reports" class="uv-num--unpriced">{{ row.unpriced_reports }} 条未定价</span>
                    <span v-else-if="row.quality_pending_reports" class="uv-num--pending">{{ row.quality_pending_reports }} 条质量未判清</span>
                    <span v-else-if="!row.reported_qty" class="uv-num--placeholder">无已确认报工：留空</span>
                    <span v-else>口径完整</span>
                  </td>
                  <td>
                    <Button variant="ghost" size="xs" type="button" @click="drillDailyRow(row)">
                      查看来源
                      <ArrowRight class="size-3" aria-hidden="true" />
                    </Button>
                  </td>
                </tr>
              </tbody>
              <tfoot>
                <tr>
                  <td>{{ viewMode === 'monthly' ? '月合计（月分子合计 / 月分母合计）' : '当日合计（与月口径分开核对）' }}</td>
                  <td>{{ shiftLabel(scope.shift) }}</td>
                  <td class="uv-table-cell--right">
                    <span class="uv-mono">{{ viewMode === 'monthly' ? (aggregateForTable?.good_qty ?? '—') : (todayProjection?.good_qty ?? '—') }}</span>
                  </td>
                  <td class="uv-table-cell--right">
                    <span class="uv-mono">{{ viewMode === 'monthly' ? (aggregateForTable?.reported_qty ?? '—') : (todayProjection?.reported_qty ?? '—') }}</span>
                  </td>
                  <td class="uv-table-cell--right">
                    <span class="uv-mono">
                      {{ viewMode === 'monthly'
                        ? formatPercent(aggregateForTable?.yield_rate ?? null, 2)
                        : formatPercent(todayProjection?.yield_rate ?? null, 2) }}
                    </span>
                  </td>
                  <td v-if="canReadCost" class="uv-table-cell--right">
                    <UvNumber
                      :money="viewMode === 'monthly' ? (aggregateForTable?.output_value ?? null) : (todayProjection?.output_value ?? null)"
                      size="sm"
                      :state="(viewMode === 'monthly' ? aggregateForTable?.output_value : todayProjection?.output_value) ? 'normal' : 'provisional'"
                    />
                  </td>
                  <td v-if="canReadPayroll" class="uv-table-cell--right">
                    <UvNumber
                      :money="viewMode === 'monthly' ? (aggregateForTable?.payroll_amount ?? null) : (todayProjection?.payroll_amount ?? null)"
                      size="sm"
                      :state="(viewMode === 'monthly' ? aggregateForTable?.payroll_amount : todayProjection?.payroll_amount) ? 'normal' : 'provisional'"
                    />
                  </td>
                  <td v-if="canReadCost" class="uv-table-cell--right">
                    <UvNumber :money="inkIssueCost === null ? null : money(displayCurrency, inkIssueCost)" size="sm" :state="inkIssueCost === null ? 'provisional' : 'normal'" />
                  </td>
                  <td v-if="canReadCost" class="uv-table-cell--right">
                    <UvNumber
                      :money="viewMode === 'monthly'
                        ? (monthlyNet === null ? null : money(displayCurrency, monthlyNet))
                        : (todayProjection?.operating_result ?? null)"
                      size="sm"
                      :state="(viewMode === 'monthly' ? monthlyNet : todayProjection?.operating_result) ? 'normal' : 'provisional'"
                    />
                  </td>
                  <td colspan="2">
                    {{ viewMode === 'monthly'
                      ? '日合计按月分子合计 / 月分母合计，不平均每日比率'
                      : '当日数字来自当日投影，切换到月报查看月度口径' }}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          <!-- 月报补充：月度汇总与费用/分摊结构 -->
          <div v-if="viewMode === 'monthly'" class="uv-panel__body">
            <h3 class="uv-section__title">月度汇总与结构（同口径）</h3>
            <div class="uv-table-scroll" role="region" tabindex="0" aria-label="月度汇总与结构表">
              <table class="uv-table uv-table--dense" style="min-width: 880px">
                <caption class="uv-table-caption">
                  月度汇总行与费用/分摊结构行都来自月报接口；分摊行按工作日集合逐日列出。
                </caption>
                <thead>
                  <tr>
                    <th scope="col">月份</th>
                    <th scope="col" class="uv-table-cell--right">合格件</th>
                    <th scope="col" class="uv-table-cell--right">报工件</th>
                    <th scope="col" class="uv-table-cell--right">月良率</th>
                    <th v-if="canReadCost" scope="col" class="uv-table-cell--right">产值</th>
                    <th v-if="canReadPayroll" scope="col" class="uv-table-cell--right">工资</th>
                    <th v-if="canReadCost" scope="col" class="uv-table-cell--right">工资占比</th>
                    <th v-if="canReadCost" scope="col" class="uv-table-cell--right">经营结余</th>
                    <th v-if="canReadCost" scope="col" class="uv-table-cell--right">结余率</th>
                    <th scope="col">成本覆盖</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in monthlyRows" :key="row.month">
                    <td class="uv-row-primary">{{ row.month }}</td>
                    <td class="uv-table-cell--right"><span class="uv-mono">{{ row.good_qty }}</span></td>
                    <td class="uv-table-cell--right"><span class="uv-mono">{{ row.reported_qty }}</span></td>
                    <td class="uv-table-cell--right">
                      <UvNumber :percent="row.yield_rate" size="sm" :state="row.yield_rate === null ? 'missing' : 'normal'" />
                    </td>
                    <td v-if="canReadCost" class="uv-table-cell--right">
                      <UvNumber :money="row.output_value" size="sm" :state="row.output_value ? 'normal' : 'provisional'" />
                    </td>
                    <td v-if="canReadPayroll" class="uv-table-cell--right">
                      <UvNumber :money="row.payroll_amount" size="sm" :state="row.payroll_amount ? 'normal' : 'provisional'" />
                    </td>
                    <td v-if="canReadCost" class="uv-table-cell--right">
                      <UvNumber :percent="row.payroll_ratio" size="sm" :state="row.payroll_ratio ? 'normal' : 'provisional'" />
                    </td>
                    <td v-if="canReadCost" class="uv-table-cell--right">
                      <UvNumber :money="row.operating_result" size="sm" :state="row.operating_result ? 'normal' : 'provisional'" />
                    </td>
                    <td v-if="canReadCost" class="uv-table-cell--right">
                      <UvNumber :percent="row.result_ratio" size="sm" :state="row.result_ratio ? 'normal' : 'provisional'" />
                    </td>
                    <td><UvStatusPill :status="COVERAGE[row.cost_coverage]" compact /></td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="uv-table-scroll" role="region" tabindex="0" aria-label="月度结构与分摊表" style="margin-top: 10px">
              <table class="uv-table uv-table--dense" style="min-width: 640px">
                <caption class="uv-table-caption">
                  费用构成行与固定费用分摊行；分摊合计必须等于配置额（在分摊配置面板可核对）。
                </caption>
                <thead>
                  <tr>
                    <th scope="col">结构项</th>
                    <th scope="col" class="uv-table-cell--right">金额（{{ displayCurrency }}）</th>
                    <th scope="col">口径 / 下钻</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in monthlyStructureRows" :key="row.key">
                    <td class="uv-row-primary">{{ row.label }}</td>
                    <td class="uv-table-cell--right">
                      <UvNumber
                        v-if="canReadCost"
                        :value="row.value === null ? null : formatDecimal(trimTrailingZeros(row.value), 2)"
                        size="sm"
                        :state="row.value === null ? 'provisional' : 'normal'"
                      />
                      <span v-else class="uv-num--pending">未授权</span>
                    </td>
                    <td>
                      <button
                        v-if="row.drill_kind"
                        type="button"
                        class="uv-chip"
                        @click="openDrill(row.drill_kind!, row.drill_ref, row.label)"
                      >
                        查看来源
                      </button>
                      <span v-else class="uv-num--placeholder">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="uv-field__hint" style="margin-top: 8px">{{ monthlyProjection?.coverage_note }}</p>
          </div>

          <!-- 日报明细：报工与费用 -->
          <div v-else class="uv-panel__body">
            <h3 class="uv-section__title">当日明细（可下钻）</h3>
            <UvStateBlock
              v-if="dailyReportRequest.error.value"
              state="error"
              subject="当日报工明细"
              :message="dailyReportRequest.error.value.message"
              retryable
              compact
              @retry="dailyReportRequest.run"
            />
            <UvStateBlock
              v-else-if="dailyReportRequest.loading.value && !dailyReportRequest.settled.value"
              state="loading"
              subject="当日报工明细"
              compact
            />
            <UvStateBlock
              v-else-if="!dailyReport"
              state="empty"
              subject="当日报工明细"
              :hint="`${scope.business_date} 没有已确认报工；这里不显示 0，也不回落样例数据。`"
              compact
            />
            <template v-else>
              <ul class="uv-report-conclusion__stats">
                <li v-for="metric in dailyReport.metrics" :key="metric.key">
                  {{ metric.label }}
                  <strong>
                    {{ metric.value === null
                      ? '暂算'
                      : metric.unit === '件'
                        ? metric.value
                        : formatDecimal(metric.value, 2) }}
                  </strong>
                  <span class="uv-row-sub">{{ metric.formula }}</span>
                </li>
              </ul>
              <div class="uv-table-scroll" role="region" tabindex="0" aria-label="当日来源行">
                <table class="uv-table uv-table--dense" style="min-width: 620px">
                  <caption class="uv-table-caption">
                    当日各来源的记录条数；点击进入对应原始清单。
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">来源</th>
                      <th scope="col" class="uv-table-cell--right">条数 / 数量</th>
                      <th scope="col">单位</th>
                      <th scope="col">下钻</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in dailyReport.rows" :key="row.key">
                      <td class="uv-row-primary">{{ row.label }}</td>
                      <td class="uv-table-cell--right">
                        <span class="uv-mono">{{ row.value ?? '暂算' }}</span>
                      </td>
                      <td>{{ row.unit }}</td>
                      <td>
                        <button
                          v-if="row.drill_kind"
                          type="button"
                          class="uv-chip"
                          @click="openDrill(row.drill_kind!, row.drill_ref, row.label)"
                        >
                          查看{{ row.label }}
                        </button>
                        <span v-else class="uv-num--placeholder">—</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </div>
        </div>
      </section>

      <!-- 未定价报工与已确认报工 -->
      <section class="uv-panel" aria-label="报工核对">
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">
              <SlidersHorizontal class="inline size-3.5" aria-hidden="true" />
              报工核对 · {{ month }}
            </h2>
            <p class="uv-panel__subtitle">
              未定价报工不计入产值、也不按 0 计入；已确认报工才进入产量与工资口径。作废记录保留并标注。
            </p>
          </div>
          <div class="uv-actions">
            <span class="uv-field__hint">
              已确认 {{ monthReports.filter((report) => report.status === 'confirmed').length }} ·
              未定价 {{ unpricedReports.length }} ·
              共 {{ monthReports.length }} 条
            </span>
          </div>
        </div>
        <div class="uv-panel__body uv-panel__body--flush">
          <UvStateBlock
            v-if="reportRequest.error.value"
            state="error"
            subject="报工列表"
            :message="reportRequest.error.value.message"
            retryable
            compact
            @retry="reportRequest.run"
          />
          <UvStateBlock
            v-else-if="reportRequest.loading.value && !reportRequest.settled.value"
            state="loading"
            subject="报工列表"
            compact
          />
          <UvStateBlock
            v-else-if="!monthReports.length"
            state="empty"
            subject="本月报工"
            hint="该月还没有任何报工记录；这是真实空数据，不是读取失败。"
            compact
          />
          <div v-else class="uv-table-scroll" role="region" tabindex="0" aria-label="报工核对表">
            <table class="uv-table uv-table--dense" style="min-width: 1040px">
              <caption class="uv-table-caption">按业务日期倒序；价格与工资列只在有权限时显示。</caption>
              <thead>
                <tr>
                  <th scope="col">业务日 / 班次</th>
                  <th scope="col">货号 / 品名</th>
                  <th scope="col">机台</th>
                  <th scope="col" class="uv-table-cell--right">报工 / 合格</th>
                  <th scope="col">质量</th>
                  <th scope="col">来源</th>
                  <th v-if="canReadCost" scope="col" class="uv-table-cell--right">产值</th>
                  <th v-if="canReadPayroll" scope="col" class="uv-table-cell--right">班组计件工资</th>
                  <th scope="col">状态</th>
                  <th scope="col">下钻</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="report in monthReports" :key="report.id">
                  <td>
                    <span class="uv-row-primary">{{ report.business_date }}</span>
                    <span class="uv-row-sub">{{ shiftLabel(report.shift) }}</span>
                  </td>
                  <td>
                    <span class="uv-row-primary">{{ report.product_no }} · {{ report.product_name }}</span>
                    <span class="uv-row-sub">{{ report.worker_names.join('、') || '未排班' }}</span>
                  </td>
                  <td>{{ machineLabel(report.machine_id) }}</td>
                  <td class="uv-table-cell--right">
                    <span class="uv-mono">{{ report.reported_qty }} / {{ report.good_qty }}</span>
                    <span class="uv-row-sub">不良 {{ report.defective_qty }} · 待判 {{ report.pending_qty }}</span>
                  </td>
                  <td><UvStatusPill :status="QUALITY_STATUS[report.quality_status]" compact /></td>
                  <td><UvStatusPill :status="SOURCE_KIND[report.source_kind]" compact /></td>
                  <td v-if="canReadCost" class="uv-table-cell--right">
                    <UvNumber
                      :money="report.commercial?.output_value ?? null"
                      size="sm"
                      :state="report.commercial?.pricing_state === 'priced' ? 'normal' : 'unpriced'"
                    />
                  </td>
                  <td v-if="canReadPayroll" class="uv-table-cell--right">
                    <UvNumber
                      :money="report.payroll?.amount ?? null"
                      size="sm"
                      :state="report.payroll?.state === 'unpriced' ? 'unpriced' : report.payroll?.state === 'provisional' ? 'provisional' : 'normal'"
                    />
                  </td>
                  <td><UvStatusPill :status="REPORT_STATUS[report.status]" compact /></td>
                  <td>
                    <Button
                      variant="ghost"
                      size="xs"
                      type="button"
                      @click="openDrill(report.commercial?.pricing_state === 'priced' ? 'reports' : 'unpriced_reports', report.business_date, `业务日 ${report.business_date}`)"
                    >
                      查看同源记录
                    </Button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- 分摊配置（页内，不新开一级菜单） -->
      <MonthlyPolicyPanel
        :month="month"
        :scope="scope"
        :currency="displayCurrency"
        :can-read-cost="canReadCost"
        :can-write-cost="canWriteCost"
        :settled="settled"
        :settled-known="settledKnown"
        @saved="retryAll"
      />
    </template>

    <DrillDownDrawer
      v-if="drill"
      :open="drill !== null"
      :kind="drill.kind"
      :drill-ref="drill.ref"
      :subject="drill.subject"
      :scope="scope"
      :currency="displayCurrency"
      :can-read-cost="canReadCost"
      :can-read-payroll="canReadPayroll"
      :period-label="month"
      @close="drill = null"
    />

    <ExpenseEntryDrawer
      v-if="expenseOpen"
      :open="expenseOpen"
      :scope="scope"
      :currency="displayCurrency"
      :default-period="month"
      :can-write-cost="canWriteCost"
      @close="expenseOpen = false"
      @saved="() => { expenseOpen = false; retryAll() }"
    />
  </div>
</template>

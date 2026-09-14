import type {
  Money,
  UvCoverage,
  UvDailyProjection,
  UvExpense,
  UvMetricValue,
  UvMonthlyPolicy,
  UvReportRow,
} from '../contracts'
import {
  currencyMinorUnits,
  decimalAdd,
  decimalCompare,
  decimalDivide,
  decimalIsZero,
  decimalMultiply,
  decimalRound,
  decimalSum,
  formatScaled,
  money,
} from './decimal'
import { yieldRate } from './quality'

/**
 * 经营口径（UV_PRINT_SHARED_SPEC.md 5.8）。
 *
 * 经营结余 = 产值
 *   − 员工工资 − 管理人员工资 − 设备投资 − 工具费用 − 房租 − 水电
 *   − 材料 − 杂费 − 维修 − 夜班补贴 − 油墨领用成本 − 无产值工资 − 加工费
 *   + 可回收工资 + 可回收油漆金额
 *
 * 这是旧管理口径，不是法定净利润；设备采购整笔扣减属于旧口径，
 * 必须同时给出「排除设备投资的经营贡献」。
 */

export const OPERATING_RESULT_FORMULA_VERSION = 'uv-operating-v1'

export interface OperatingInput {
  currency: string
  outputValue: string | null
  employeeWage: string | null
  managementWage: string | null
  equipment: string | null
  tooling: string | null
  rent: string | null
  utilities: string | null
  material: string | null
  sundry: string | null
  maintenance: string | null
  nightSubsidy: string | null
  inkIssueCost: string | null
  noOutputWage: string | null
  processing: string | null
  recoverableWage: string | null
  recoverablePaint: string | null
}

const DEDUCTION_KEYS: Array<{ key: keyof OperatingInput; label: string }> = [
  { key: 'employeeWage', label: '员工工资' },
  { key: 'managementWage', label: '管理人员工资' },
  { key: 'equipment', label: '设备投资' },
  { key: 'tooling', label: '工具费用' },
  { key: 'rent', label: '房租' },
  { key: 'utilities', label: '水电' },
  { key: 'material', label: '材料' },
  { key: 'sundry', label: '杂费' },
  { key: 'maintenance', label: '维修' },
  { key: 'nightSubsidy', label: '夜班补贴' },
  { key: 'inkIssueCost', label: '油墨领用成本' },
  { key: 'noOutputWage', label: '无产值工资' },
  { key: 'processing', label: '加工费' },
]

const ADDITION_KEYS: Array<{ key: keyof OperatingInput; label: string }> = [
  { key: 'recoverableWage', label: '可回收工资' },
  { key: 'recoverablePaint', label: '可回收油漆金额' },
]

export interface OperatingResult {
  rows: UvReportRow[]
  operatingResult: string | null
  /**
   * 「排除设备投资的经营贡献」。
   *
   * 语义说明：产值缺失（本期存在未定价报工且后端未下发金额）时，
   * `operatingResult` 为 `null`（暂算），而本字段仍会给出「忽略产值、只累计
   * 已填写费用」的算法结果，用于判断费用结构是否完整。调用方必须先看
   * `operatingResult === null`，不能把本字段当作已核定结余展示。
   */
  operatingContribution: string | null
  equipmentExcludedDifference: string | null
  warnings: string[]
}

export function operatingResult(input: OperatingInput): OperatingResult {
  const warnings: string[] = []
  const rows: UvReportRow[] = []
  const outputValue = input.outputValue

  if (outputValue === null) {
    warnings.push('产值不可计算：本期存在未定价报工，结余为暂算')
  }

  rows.push({
    key: 'output_value',
    label: '产值',
    value: outputValue,
    unit: input.currency,
    drill_kind: 'reports',
    drill_ref: null,
    provisional: outputValue === null,
  })

  let net = outputValue ?? '0'
  const equipment = input.equipment
  for (const item of DEDUCTION_KEYS) {
    const value = input[item.key] as string | null
    if (value !== null) net = decimalAdd(net, `-${value}`)
    rows.push({
      key: item.key,
      label: item.label,
      value: value === null ? null : `-${value}`,
      unit: input.currency,
      drill_kind: item.key === 'inkIssueCost' ? 'ink_movements' : item.key === 'employeeWage' ? 'payroll' : 'expenses',
      drill_ref: null,
      provisional: value === null,
    })
  }
  for (const item of ADDITION_KEYS) {
    const value = input[item.key] as string | null
    if (value !== null) net = decimalAdd(net, value)
    rows.push({
      key: item.key,
      label: item.label,
      value: value === null ? null : value,
      unit: input.currency,
      drill_kind: 'expenses',
      drill_ref: null,
      provisional: value === null,
    })
  }

  const missingCost = DEDUCTION_KEYS.some((item) => (input[item.key] as string | null) === null)
  if (missingCost) warnings.push('存在未配置的费用项，结余按已填写项目暂算')

  const contribution = equipment === null ? net : decimalAdd(net, equipment)

  return {
    rows,
    operatingResult: outputValue === null ? null : net,
    operatingContribution: contribution,
    equipmentExcludedDifference: equipment === null ? null : equipment,
    warnings,
  }
}

/**
 * 月合格率、工资占比、结余率按「月分子合计 / 月分母合计」计算，
 * 不平均每天百分比（T34：90/100 + 1/10 → 91/110 ≈ 82.7273%，不是 50%）。
 */
export function ratioOfSums(numerator: number, denominator: number): string | null {
  if (denominator <= 0) return null
  return decimalDivide(String(numerator), String(denominator), 6)
}

export function moneyRatioOfSums(
  numerator: string | null,
  denominator: string | null,
): string | null {
  if (numerator === null || denominator === null || decimalIsZero(denominator)) return null
  return decimalDivide(numerator, denominator, 6)
}

export function monthlyYield(goodQty: number, defectiveQty: number): string | null {
  return ratioOfSums(goodQty, goodQty + defectiveQty)
}

export interface MonthAggregate {
  month: string
  good_qty: number
  defective_qty: number
  reported_qty: number
  yield_rate: string | null
  output_value: Money | null
  payroll_amount: Money | null
  payroll_ratio: string | null
  operating_result: Money | null
  result_ratio: string | null
  cost_coverage: UvCoverage
}

export function aggregateDailyRows(
  currency: string,
  rows: UvDailyProjection[],
  coverage: UvCoverage,
): MonthAggregate | null {
  if (!rows.length) return null
  const month = rows[0]!.business_date.slice(0, 7)
  const goodQty = rows.reduce((total, row) => total + row.good_qty, 0)
  const defectiveQty = rows.reduce((total, row) => total + row.defective_qty, 0)
  const reportedQty = rows.reduce((total, row) => total + row.reported_qty, 0)

  const outputValues = rows.map((row) => row.output_value)
  const payrollValues = rows.map((row) => row.payroll_amount)
  const resultValues = rows.map((row) => row.operating_result)
  const outputComplete = outputValues.every((value) => value !== null && value.currency === currency)
  const payrollComplete = payrollValues.every((value) => value !== null && value.currency === currency)
  const resultComplete = resultValues.every((value) => value !== null && value.currency === currency)

  const outputTotal = outputComplete
    ? money(currency, decimalSum(outputValues.map((value) => value!.amount)))
    : null
  const payrollTotal = payrollComplete
    ? money(currency, decimalSum(payrollValues.map((value) => value!.amount)))
    : null
  const resultTotal = resultComplete
    ? money(currency, decimalSum(resultValues.map((value) => value!.amount)))
    : null

  return {
    month,
    good_qty: goodQty,
    defective_qty: defectiveQty,
    reported_qty: reportedQty,
    yield_rate: monthlyYield(goodQty, defectiveQty),
    output_value: outputTotal,
    payroll_amount: payrollTotal,
    payroll_ratio: moneyRatioOfSums(payrollTotal?.amount ?? null, outputTotal?.amount ?? null),
    operating_result: resultTotal,
    result_ratio: moneyRatioOfSums(resultTotal?.amount ?? null, outputTotal?.amount ?? null),
    cost_coverage: resultComplete ? coverage : 'partial',
  }
}

export function dailyYieldOf(row: UvDailyProjection): string | null {
  return yieldRate({ reported_qty: row.reported_qty, good_qty: row.good_qty, defective_qty: row.defective_qty, pending_qty: 0, semi_finished_qty: 0 })
}

export interface ProrationDay {
  business_date: string
  amount: string
}

/**
 * 月度固定费用按工作日集合分摊，金额舍入余数分配至确定日期，
 * 整月分摊合计必须等于配置额（T33：100.00 分 3 天 → 合计恰好 100.00）。
 */
export function prorateMonthly(
  total: string,
  days: string[],
  currency: string,
  method: UvMonthlyPolicy['allocation_method'] = 'working_days',
): ProrationDay[] {
  if (!days.length) return []
  const minor = currencyMinorUnits(currency)
  const roundedTotal = decimalRound(total, minor)
  const totalMinor = BigInt(roundedTotal.replace('.', '').replace('-', ''))
  const negative = roundedTotal.startsWith('-')
  const base = totalMinor / BigInt(days.length)
  const remainder = Number(totalMinor - base * BigInt(days.length))

  return days.map((businessDate, index) => {
    // 余数从当月第一天开始逐日补一个最小币种单位，顺序稳定可解释。
    const value = index < remainder ? base + 1n : base
    const signed = negative ? -value : value
    return { business_date: businessDate, amount: formatScaled(signed, minor) }
  })
}

export function allocationMethodLabel(method: UvMonthlyPolicy['allocation_method']): string {
  return method === 'working_days' ? '按选择的工作日集合' : '按自然日'
}

export function coverageOf(input: {
  unpricedReports: number
  qualityPendingReports: number
  missingCost: boolean
  periodClosed: boolean
}): UvCoverage {
  if (input.unpricedReports > 0 || input.qualityPendingReports > 0 || input.missingCost) return 'partial'
  return 'complete'
}

export function metric(
  key: string,
  label: string,
  value: string | null,
  options: Partial<Omit<UvMetricValue, 'key' | 'label' | 'value'>> = {},
): UvMetricValue {
  return {
    key,
    label,
    value,
    unit: options.unit ?? '',
    formula: options.formula ?? '',
    sources: options.sources ?? [],
    note: options.note ?? '',
    provisional: options.provisional ?? false,
    unpriced: options.unpriced ?? false,
  }
}

/** 费用构成按金额排序，缺失币种不直接相加。 */
export interface ExpenseStructureRow {
  category: string
  label: string
  amount: Money | null
  share: string | null
  currency: string
}

export function expenseStructure(
  currency: string,
  expenses: UvExpense[],
  labels: Record<string, string>,
  base?: string | null,
): ExpenseStructureRow[] {
  const totals = new Map<string, string>()
  for (const expense of expenses) {
    if (expense.amount.currency !== currency) continue
    totals.set(expense.category, decimalAdd(totals.get(expense.category) ?? '0', expense.amount.amount))
  }
  const rows = [...totals.entries()].map(([category, amount]) => ({
    category,
    label: labels[category] ?? category,
    amount: money(currency, amount),
    share: base && !decimalIsZero(base) ? decimalDivide(amount, base, 6) : null,
    currency,
  }))
  return rows.sort((a, b) => decimalCompare(b.amount?.amount ?? '0', a.amount?.amount ?? '0'))
}

export function addMoney(currency: string, left: Money | null, right: Money | null): Money | null {
  if (!left) return right
  if (!right) return left
  if (left.currency !== right.currency || right.currency !== currency) return null
  return money(currency, decimalAdd(left.amount, right.amount))
}

export function multiplyDecimal(value: string, factor: string): string {
  return decimalMultiply(value, factor)
}

/** 期间完整性提示：未定价 / 未判质量 / 缺成本都进入报表口径说明。 */
export function coverageNotes(input: {
  unpricedReports: number
  qualityPendingReports: number
  missingCostCategories: string[]
  closed: boolean
  asOf: string
}): string[] {
  const notes: string[] = [`数据截止 ${input.asOf}`]
  if (input.unpricedReports > 0) notes.push(`${input.unpricedReports} 条报工没有生效执行价，产值暂算`)
  if (input.qualityPendingReports > 0) {
    notes.push(`${input.qualityPendingReports} 条报工质量未判清，良率分母使用报工数量`)
  }
  if (input.missingCostCategories.length) {
    notes.push(`缺少 ${input.missingCostCategories.join('、')} 配置，结余按已填写项目暂算`)
  }
  if (!input.closed) notes.push('本期未关账，数据会随后续更正变化')
  return notes
}

/** 月参数覆盖检查：分摊合计必须等于配置额，否则不允许保存。 */
export function prorationTotals(
  total: string,
  days: string[],
  currency: string,
  method: UvMonthlyPolicy['allocation_method'],
): { days: ProrationDay[]; total: string; matches: boolean } {
  const rows = prorateMonthly(total, days, currency, method)
  const sum = rows.reduce((acc, row) => decimalAdd(acc, row.amount), '0')
  return { days: rows, total: sum, matches: decimalCompare(sum, decimalRound(total, currencyMinorUnits(currency))) === 0 }
}

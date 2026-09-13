import type { UvPricingInput, UvPricingResult, UvPricingStep, UvWarning } from '../contracts'
import { decimalAdd, decimalCompare, decimalDivide, decimalIsZero, decimalMultiply, decimalRound } from './decimal'

/**
 * 定价测算（UV_PRINT_SHARED_SPEC.md 5.5）。
 *
 *   理论每日板数 = 每日可用工时 / 每板耗时
 *   理论日产能   = 理论每日板数 × 每板件数
 *   直接日成本   = 日人工成本 + 日油墨成本
 *   直接单位成本 = 直接日成本 / 理论日产能
 *   成本加成报价 = 直接单位成本 × (1 + 加成率)
 *   目标毛利报价 = 直接单位成本 / (1 - 目标毛利率)
 *
 * ×1.4 是「成本加成 40%」，不是「毛利率 40%」；两者的对应关系必须同时展示。
 * 耗时为 0 或日产能为 0 时输出不可计算原因，不显示 0 成本报价。
 */

export const UV_PRICING_FORMULA_VERSION = 'uv-pricing-v1'

/** 计价金额默认保留 6 位小数，与契约的 DecimalString 一致。 */
const PRICE_SCALE = 6

export function defaultPricingInput(currency = 'HKD'): UvPricingInput {
  return {
    currency,
    daily_hours: '10',
    board_hours: '0.5',
    pieces_per_board: '20',
    labor_cost_per_day: '200',
    ink_cost_per_day: '80',
    markup_rate: '0.4',
    target_margin_rate: '0.4',
    loss_rate: null,
  }
}

export function computePricing(input: UvPricingInput): UvPricingResult {
  const warnings: UvWarning[] = []
  const steps: UvPricingStep[] = []
  const currency = input.currency || 'HKD'

  const dailyHours = input.daily_hours
  const boardHours = input.board_hours
  const piecesPerBoard = input.pieces_per_board
  const laborCost = input.labor_cost_per_day
  const inkCost = input.ink_cost_per_day

  const boardsPerDay = decimalIsZero(boardHours) ? null : decimalDivide(dailyHours, boardHours, 4)
  steps.push({
    key: 'boards_per_day',
    label: '理论每日板数',
    formula: '每日可用工时 ÷ 每板耗时',
    value: boardsPerDay,
    unit: '板/天',
  })

  const piecesPerDay = boardsPerDay === null ? null : decimalMultiply(boardsPerDay, piecesPerBoard)
  steps.push({
    key: 'pieces_per_day',
    label: '理论日产能',
    formula: '理论每日板数 × 每板件数',
    value: piecesPerDay,
    unit: '件/天',
  })

  const directDailyCost = decimalAdd(laborCost, inkCost)
  steps.push({
    key: 'direct_daily_cost',
    label: '直接日成本',
    formula: '日人工成本 + 日油墨成本',
    value: directDailyCost,
    unit: currency,
  })

  const directUnitCost =
    piecesPerDay === null || decimalIsZero(piecesPerDay)
      ? null
      : decimalDivide(directDailyCost, piecesPerDay, PRICE_SCALE)
  steps.push({
    key: 'direct_unit_cost',
    label: '直接单位成本',
    formula: '直接日成本 ÷ 理论日产能',
    value: directUnitCost,
    unit: `${currency}/件`,
  })

  const markupPrice =
    directUnitCost === null
      ? null
      : decimalMultiply(directUnitCost, decimalAdd('1', input.markup_rate))
  steps.push({
    key: 'markup_price',
    label: '成本加成报价',
    formula: `直接单位成本 × (1 + ${input.markup_rate})`,
    value: markupPrice,
    unit: `${currency}/件`,
  })

  // 成本加成 r 对应的实际毛利率 = r / (1 + r)，用于避免把加成说成毛利率。
  const markupImpliedMargin =
    decimalIsZero(decimalAdd('1', input.markup_rate))
      ? null
      : decimalDivide(input.markup_rate, decimalAdd('1', input.markup_rate), 6)
  steps.push({
    key: 'markup_implied_margin',
    label: '加成对应毛利率',
    formula: '加成率 ÷ (1 + 加成率)',
    value: markupImpliedMargin,
    unit: '',
  })

  const marginDenominator = decimalAdd('1', `-${input.target_margin_rate}`)
  const marginUsable = decimalCompare(marginDenominator, '0') > 0
  const targetMarginPrice =
    directUnitCost === null || !marginUsable
      ? null
      : decimalDivide(directUnitCost, marginDenominator, PRICE_SCALE)
  steps.push({
    key: 'target_margin_price',
    label: '目标毛利报价',
    formula: `直接单位成本 ÷ (1 − ${input.target_margin_rate})`,
    value: targetMarginPrice,
    unit: `${currency}/件`,
  })

  if (input.loss_rate !== null && !decimalIsZero(input.loss_rate)) {
    const lossFactor = decimalAdd('1', `-${input.loss_rate}`)
    const lossAdjusted =
      directUnitCost === null || decimalCompare(lossFactor, '0') <= 0
        ? null
        : decimalDivide(directUnitCost, lossFactor, PRICE_SCALE)
    steps.push({
      key: 'loss_adjusted_cost',
      label: '含损耗单位成本',
      formula: `直接单位成本 ÷ (1 − 损耗率 ${input.loss_rate})`,
      value: lossAdjusted,
      unit: `${currency}/件`,
    })
    warnings.push({
      code: 'loss_included',
      message: '已计入损耗率，但换版、换图、清洗准备时间未计入',
      tone: 'info',
    })
  } else {
    warnings.push({
      code: 'cost_scope',
      message: '成本仅含已填写的人工和油墨，未含损耗、准备时间、维修或折旧',
      tone: 'info',
    })
  }

  const notComputableReason = decimalIsZero(boardHours)
    ? '每板耗时为 0，无法计算理论板数与产能'
    : piecesPerDay === null || decimalIsZero(piecesPerDay)
      ? '理论日产能为 0，无法计算单位成本'
      : null

  let fullBoards: number | null = null
  if (boardsPerDay !== null) {
    const wholeBoards = Math.floor(Number(boardsPerDay))
    fullBoards = Number.isFinite(wholeBoards) ? wholeBoards : null
  }

  if (decimalIsZero(piecesPerBoard)) {
    warnings.push({ code: 'pieces_per_board_zero', message: '每板件数为 0，日产能不可用', tone: 'warning' })
  }
  if (!marginUsable) {
    warnings.push({
      code: 'margin_not_usable',
      message: '目标毛利率不小于 100%，目标毛利报价不可计算',
      tone: 'warning',
    })
  }

  return {
    input,
    steps,
    boards_per_day: boardsPerDay,
    full_boards_per_day: fullBoards,
    pieces_per_day: piecesPerDay,
    direct_unit_cost: directUnitCost,
    markup_price: markupPrice,
    markup_implied_margin: markupImpliedMargin,
    target_margin_price: targetMarginPrice,
    currency,
    formula_version: UV_PRICING_FORMULA_VERSION,
    not_computable_reason: notComputableReason,
    cost_scope: input.loss_rate && !decimalIsZero(input.loss_rate)
      ? '含人工、油墨与已填损耗'
      : '仅含已填写的人工和油墨',
    warnings,
  }
}

export interface PricingSensitivity {
  rate: string
  unit_cost: string | null
  markup_price: string | null
  target_margin_price: string | null
}

/** 滑杆只用于敏感性参考；精确数值仍可键盘输入。 */
export function pricingSensitivity(
  input: UvPricingInput,
  rates: string[] = ['0.1', '0.2', '0.3', '0.4', '0.5'],
): PricingSensitivity[] {
  return rates.map((rate) => {
    const result = computePricing({ ...input, markup_rate: rate })
    return {
      rate,
      unit_cost: result.direct_unit_cost,
      markup_price: result.markup_price,
      target_margin_price: result.target_margin_price,
    }
  })
}

/** 报价金额展示统一走 6 位小数四舍五入，避免出现二进制浮点尾巴。 */
export function roundPrice(value: string | null): string | null {
  return value === null ? null : decimalRound(value, PRICE_SCALE)
}

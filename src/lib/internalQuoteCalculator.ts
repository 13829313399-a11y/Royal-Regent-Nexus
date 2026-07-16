import type {
  InternalQuoteCostLine,
  InternalQuoteDepartment,
  InternalQuoteLineCalculation,
  InternalQuoteSectionCalculation,
  InternalQuoteSectionPayload,
} from '@/types/internalQuote'

const DEFAULT_RMB_HKD = 0.85
const DEFAULT_HKD_USD = 7.8

function numberValue(value: unknown, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback
}

function roundMoney(value: number) {
  return Math.round((value + Number.EPSILON) * 100) / 100
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function normalized(value: unknown) {
  return String(value ?? '').replace(/\s+/g, '').toUpperCase()
}

function lookupMaterialPrice(fields: Record<string, unknown>, snapshot: Record<string, unknown>) {
  const material = normalized(fields.material)
  const grade = normalized(fields.material_grade)
  if (!material || !grade) return 0
  const prices = Array.isArray(snapshot.material_prices) ? snapshot.material_prices : []
  const match = prices.find((item) => {
    const row = recordValue(item)
    return normalized(row.name) === material && normalized(row.model) === grade
  })
  return numberValue(recordValue(match).price_hkd_lb)
}

function lookupMachinePrice(fields: Record<string, unknown>, snapshot: Record<string, unknown>) {
  const target = normalized(fields.machine_model)
  const targetNumber = Number(target.replace(/A/g, ''))
  if (!target) return 0
  const prices = Array.isArray(snapshot.machine_prices) ? snapshot.machine_prices : []
  for (const item of prices) {
    const row = recordValue(item)
    const model = normalized(row.model)
    const range = model.replace(/A/g, '').split('-')
    if (range.length === 2 && Number.isFinite(targetNumber)) {
      if (Number(range[0]) <= targetNumber && targetNumber <= Number(range[1])) {
        return numberValue(row.price_hkd_shift)
      }
    }
    if (model === target) return numberValue(row.price_hkd_shift)
  }
  return 0
}

function genericAmount(row: InternalQuoteCostLine): [number, string] {
  return [numberValue(row.quantity) * numberValue(row.unitPriceHkd), '数量 × HKD单价']
}

function lineAmount(
  department: InternalQuoteDepartment,
  row: InternalQuoteCostLine,
  snapshot: Record<string, unknown>,
  rmbHkd: number,
  electronicSpecialized: boolean,
): [number, string] {
  const fields = row.fields ?? {}
  if (department === 'engineering' && Object.keys(fields).length && fields.mode === 'mold') {
    const amortization = Math.max(numberValue(fields.amortization_qty, 1), 1)
    return [numberValue(fields.mold_price_rmb) / amortization / rmbHkd, '模具RMB总价 ÷ 摊销数量 ÷ RMB/HKD汇率']
  }
  if (department === 'electronic' && electronicSpecialized) {
    return [numberValue(row.quantity) * numberValue(fields.unit_price_rmb) / rmbHkd, '数量 × RMB单价 ÷ RMB/HKD汇率']
  }
  if (department === 'molding' && Object.keys(fields).length) {
    const materialPrice = numberValue(fields.material_price_hkd_lb) || lookupMaterialPrice(fields, snapshot)
    const weight = numberValue(fields.weight_g)
    if (fields.mode === 'blow') {
      return [
        (weight * materialPrice / 454 + numberValue(fields.blow_labor_hkd) + numberValue(fields.flash_hkd))
          * (numberValue(fields.profit_multiplier, 1) || 1),
        '(克重 × HK$/Lb ÷ 454 + 吹气人工 + 水口) × 利润倍数',
      ]
    }
    const lossPct = numberValue(fields.loss_pct, 3)
    const shiftPrice = lookupMachinePrice(fields, snapshot)
    const automaticShot = shiftPrice
      ? shiftPrice / Math.max(numberValue(fields.sets, 1), 1) / Math.max(numberValue(fields.target, 1), 1)
      : 0
    const shotPrice = numberValue(fields.shot_price_hkd) || automaticShot
    return [weight * (1 + lossPct / 100) * materialPrice / 454 + shotPrice, '克重 × (1+损耗%) × HK$/Lb ÷ 454 + 啤价']
  }
  if (department === 'sewing' && Object.keys(fields).length) {
    return [
      numberValue(fields.usage) * numberValue(fields.material_price_hkd) * (numberValue(fields.markup, 1) || 1),
      '用量 × 材料单价 × 加成倍数',
    ]
  }
  if (department === 'assembly' && Object.keys(fields).length && fields.mode === 'process') {
    return [
      numberValue(fields.base_rate_hkd, 310) * numberValue(fields.people_count)
        * numberValue(fields.team_count, 1) / Math.max(numberValue(fields.production_qty, 1), 1),
      '台班基准 × 工序人数 × 组数 ÷ 每组产量',
    ]
  }
  return genericAmount(row)
}

export function calculateInternalQuoteSection(
  department: InternalQuoteDepartment,
  payload: InternalQuoteSectionPayload,
): InternalQuoteSectionCalculation {
  const snapshot = payload.referenceSnapshot ?? {}
  const fx = recordValue(snapshot.fx)
  const rmbHkd = numberValue(fx.rmb_hkd, DEFAULT_RMB_HKD) || DEFAULT_RMB_HKD
  const hkdUsd = numberValue(fx.hkd_usd, DEFAULT_HKD_USD) || DEFAULT_HKD_USD
  const parameters = payload.parameters ?? {}
  const electronicSpecialized = department === 'electronic'
    && (payload.rows.some((row) => Object.keys(row.fields ?? {}).length > 0)
      || Object.values(parameters).some((value) => numberValue(value) > 0))
  const lineBreakdown: InternalQuoteLineCalculation[] = payload.rows.map((row) => {
    const [amount, formula] = lineAmount(department, row, snapshot, rmbHkd, electronicSpecialized)
    return { lineId: row.id, label: row.itemName, formula, amountHkd: roundMoney(amount) }
  })
  const rawSubtotal = lineBreakdown.reduce((total, row) => total + row.amountHkd, 0)
  let subtotal = rawSubtotal
  let lossAmount = 0

  if (electronicSpecialized) {
    const extras = ['bonding_cost_rmb', 'smt_cost_rmb', 'labor_cost_rmb', 'test_repair_rmb', 'packing_shipping_rmb']
      .reduce((total, key) => total + numberValue(parameters[key]), 0)
    const profitPrice = (rawSubtotal * rmbHkd + extras) * (1 + numberValue(parameters.profit_pct) / 100)
    subtotal = (profitPrice + numberValue(parameters.tax_diff_rmb) * 1.1) / rmbHkd
  } else if (payload.rows.every((row) => !Object.keys(row.fields ?? {}).length)) {
    lossAmount = subtotal * numberValue(payload.lossPct) / 100
  } else if (department === 'sewing' && !payload.rows.some((row) => row.itemName.includes('人工'))) {
    subtotal += numberValue(parameters.labor_hkd)
  } else if (department === 'sales') {
    lossAmount = subtotal * numberValue(payload.lossPct) / 100
  }

  const subtotalHkd = roundMoney(subtotal)
  const lossAmountHkd = roundMoney(lossAmount)
  const totalHkd = roundMoney(subtotalHkd + lossAmountHkd)
  return {
    formulaVersion: 'department-formulas-v1',
    subtotalHkd,
    lossAmountHkd,
    totalHkd,
    totalRmb: roundMoney(totalHkd * rmbHkd),
    totalUsd: roundMoney(totalHkd / hkdUsd),
    lineBreakdown,
    warnings: [],
    referenceSnapshot: snapshot,
  }
}

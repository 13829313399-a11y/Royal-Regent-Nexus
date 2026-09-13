import { describe, expect, it } from 'vitest'
import type { UvDailyProjection, UvExpense } from '../contracts'
import {
  OPERATING_RESULT_FORMULA_VERSION,
  addMoney,
  aggregateDailyRows,
  expenseStructure,
  monthlyYield,
  operatingResult,
  prorateMonthly,
  prorationTotals,
  ratioOfSums,
} from '../domain/reporting'
import { formatDecimal, formatPercent } from '../domain/decimal'

/**
 * 经营报表领域测试：只验证共享 reporting.ts 的口径，不重复实现公式。
 *
 * 这些断言保护五件事：
 * 1) 分摊后整月合计必须等于配置额（舍入余数按确定顺序补最小币种单位）；
 * 2) 月比率一律「月分子合计 / 月分母合计」，不平均每天百分比；
 * 3) 经营结余是旧管理口径，设备投资整笔扣减，同时给出排除设备投资的经营贡献；
 * 4) 不同币种不相加，缺成本项进入暂算警告而不是静默当 0；
 * 5) 已有暂算/签约数字一律可核对，因此断言数值本身而不是字符串补零形式。
 *
 * 注意：`domain/decimal.ts` 的 `decimalDivide` 先多算 4 位再按 half-away-from-zero 舍入，
 * 因此 91/110 得到 0.827273（不是截断的 0.827272）。`decimalAdd` 仍保留输入的小数位，
 * 所以金额断言统一比较去掉尾零后的十进制字符串。
 */

const CURRENCY = 'HKD'

function projection(
  businessDate: string,
  input: Partial<UvDailyProjection> = {},
): UvDailyProjection {
  return {
    business_date: businessDate,
    good_qty: 0,
    reported_qty: 0,
    yield_rate: null,
    output_value: null,
    payroll_amount: null,
    ink_cost: null,
    expense_amount: null,
    operating_result: null,
    unpriced_reports: 0,
    quality_pending_reports: 0,
    planned_day_off: false,
    off_plan_production: false,
    ...input,
  }
}

function expenseRecord(
  id: string,
  category: UvExpense['category'],
  currency: string,
  amount: string,
  occurredOn = '2026-09-13',
): UvExpense {
  return {
    id,
    factory_id: 'huakang-a',
    version: 1,
    created_at: '2026-09-13T01:00:00Z',
    updated_at: '2026-09-13T01:00:00Z',
    category,
    occurred_on: occurredOn,
    period: occurredOn.slice(0, 7),
    amount: { currency, amount },
    machine_id: null,
    evidence: 'TEST 凭证',
    source: 'manual',
    note: '',
    reverses_expense_id: null,
  }
}

/** 去掉十进制字符串的尾零，避免把补位形式当成业务差异。 */
function normalized(value: string | null | undefined): string | null {
  return value === null || value === undefined ? null : formatDecimal(value, 6)
}

describe('T33 月度固定费用分摊', () => {
  it('100.00 分到 3 个日期，三份之和恰好是 100.00，且余数补齐', () => {
    const days = ['2026-09-01', '2026-09-02', '2026-09-03']
    const shares = prorateMonthly('100.00', days, CURRENCY, 'working_days')

    expect(shares).toHaveLength(3)
    expect(shares.map((share) => share.amount)).toEqual(['33.34', '33.33', '33.33'])
    expect(shares.reduce((total, share) => total + Number(share.amount), 0)).toBeCloseTo(100, 10)

    const totals = prorationTotals('100.00', days, CURRENCY, 'working_days')
    expect(totals.matches).toBe(true)
    expect(Number(totals.total)).toBeCloseTo(100, 10)
    expect(totals.days.map((day) => day.business_date)).toEqual(days)
  })

  it('工作日集合为空时不分摊，也不把金额摊成 0', () => {
    expect(prorateMonthly('100.00', [], CURRENCY, 'working_days')).toEqual([])
  })

  it('余数补齐顺序稳定：同一输入重复计算结果完全一致', () => {
    const days = [
      '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04',
      '2026-09-05', '2026-09-06', '2026-09-07',
    ]
    const first = prorationTotals('1000.00', days, CURRENCY, 'working_days')
    const second = prorationTotals('1000.00', days, CURRENCY, 'working_days')
    expect(first.days).toEqual(second.days)
    expect(first.matches).toBe(true)
    expect(Number(first.total)).toBeCloseTo(1000, 10)
  })
})

describe('T34 月合格率按分子合计 / 分母合计', () => {
  it('90/100 与 1/10 的月良率是 91/110 ≈ 0.827273，不是 (90% + 10%) / 2', () => {
    const rows = [
      projection('2026-09-01', { good_qty: 90, reported_qty: 100 }),
      projection('2026-09-02', { good_qty: 1, reported_qty: 10 }),
    ]

    // 口径值：91 / 110 = 0.8272727...，与逐日百分比平均 0.5 有本质区别。
    expect(Number(monthlyYield(91, 110))).toBeCloseTo(91 / 110, 5)
    // 六位小数按四舍五入：0.827273（不是截断的 0.827272）。
    expect(monthlyYield(91, 110)).toBe('0.827273')
    expect(formatPercent(monthlyYield(91, 110), 2)).toBe('82.73%')

    const aggregate = aggregateDailyRows(CURRENCY, rows, 'complete')
    expect(aggregate).not.toBeNull()
    expect(aggregate?.good_qty).toBe(91)
    expect(aggregate?.reported_qty).toBe(110)
    expect(aggregate?.yield_rate).toBe('0.827273')
    expect(Number(aggregate?.yield_rate)).toBeCloseTo(91 / 110, 5)
    // 平均每天百分比会得到 0.5，这里必须明确排除该算法。
    expect(Number(aggregate?.yield_rate)).not.toBeCloseTo(0.5, 3)
    expect(Number(ratioOfSums(91, 110))).toBeCloseTo(91 / 110, 5)
  })

  it('分母合计为 0 时比率是 null，不显示 0', () => {
    expect(monthlyYield(0, 0)).toBeNull()
    expect(ratioOfSums(5, 0)).toBeNull()
    expect(aggregateDailyRows(CURRENCY, [], 'no_data')).toBeNull()
  })

  it('工资占比与结余率同样按金额合计相除，任一侧缺失时不给比率', () => {
    const rows = [
      projection('2026-09-01', {
        good_qty: 10,
        reported_qty: 10,
        output_value: { currency: CURRENCY, amount: '100.00' },
        payroll_amount: { currency: CURRENCY, amount: '30.00' },
        operating_result: { currency: CURRENCY, amount: '20.00' },
      }),
      projection('2026-09-02', {
        good_qty: 10,
        reported_qty: 10,
        output_value: { currency: CURRENCY, amount: '300.00' },
        payroll_amount: { currency: CURRENCY, amount: '90.00' },
        operating_result: { currency: CURRENCY, amount: '80.00' },
      }),
    ]

    const aggregate = aggregateDailyRows(CURRENCY, rows, 'complete')
    expect(normalized(aggregate?.output_value?.amount)).toBe('400')
    expect(Number(aggregate?.payroll_ratio)).toBeCloseTo(0.3, 5)
    expect(Number(aggregate?.result_ratio)).toBeCloseTo(0.25, 5)

    // 任一天缺产值合计时不给占比，也不把缺失当 0。
    const incomplete = aggregateDailyRows(CURRENCY, [
      rows[0]!,
      projection('2026-09-03', { good_qty: 5, reported_qty: 5, payroll_amount: { currency: CURRENCY, amount: '10.00' } }),
    ], 'partial')
    expect(incomplete?.output_value).toBeNull()
    expect(incomplete?.payroll_ratio).toBeNull()
    expect(incomplete?.cost_coverage).toBe('partial')
  })
})

describe('经营结余公式（旧管理口径）', () => {
  it('按 产值 − 各项扣减 + 可回收项 得到净结余，并给出排除设备投资的差异', () => {
    const result = operatingResult({
      currency: CURRENCY,
      outputValue: '1000.00',
      employeeWage: '200.00',
      managementWage: '100.00',
      equipment: '300.00',
      tooling: '20.00',
      rent: '50.00',
      utilities: '30.00',
      material: '40.00',
      sundry: '10.00',
      maintenance: '25.00',
      nightSubsidy: '15.00',
      inkIssueCost: '60.00',
      noOutputWage: '5.00',
      processing: '35.00',
      recoverableWage: '20.00',
      recoverablePaint: '15.00',
    })

    // 1000 − (200+100+300+20+50+30+40+10+25+15+60+5+35) + (20+15) = 1000 − 890 + 35
    expect(normalized(result.operatingResult)).toBe('145')
    // 排除设备投资整笔扣减后的经营贡献：145 + 300
    expect(normalized(result.operatingContribution)).toBe('445')
    expect(normalized(result.equipmentExcludedDifference)).toBe('300')
    expect(result.warnings).toEqual([])
    expect(OPERATING_RESULT_FORMULA_VERSION).toBe('uv-operating-v1')
  })

  it('逐项列出产值、13 项扣减与 2 项加回，扣减带负号且可下钻', () => {
    const result = operatingResult({
      currency: CURRENCY,
      outputValue: '100.00',
      employeeWage: '10.00',
      managementWage: null,
      equipment: null,
      tooling: null,
      rent: null,
      utilities: null,
      material: null,
      sundry: null,
      maintenance: null,
      nightSubsidy: null,
      inkIssueCost: null,
      noOutputWage: null,
      processing: null,
      recoverableWage: null,
      recoverablePaint: null,
    })

    expect(result.rows).toHaveLength(16)
    expect(result.rows[0]).toMatchObject({ key: 'output_value', label: '产值', value: '100.00', drill_kind: 'reports' })
    expect(result.rows.find((row) => row.key === 'employeeWage')).toMatchObject({
      label: '员工工资',
      value: '-10.00',
      drill_kind: 'payroll',
    })
    expect(result.rows.find((row) => row.key === 'inkIssueCost')?.drill_kind).toBe('ink_movements')
    expect(result.rows.find((row) => row.key === 'recoverablePaint')).toMatchObject({ label: '可回收油漆金额' })
  })

  it('未填写的扣减项算 0 不改变净额，但必须逐项提示暂算', () => {
    const result = operatingResult({
      currency: CURRENCY,
      outputValue: '500.00',
      employeeWage: '100.00',
      managementWage: null,
      equipment: null,
      tooling: null,
      rent: null,
      utilities: null,
      material: null,
      sundry: null,
      maintenance: null,
      nightSubsidy: null,
      inkIssueCost: null,
      noOutputWage: null,
      processing: null,
      recoverableWage: null,
      recoverablePaint: null,
    })

    expect(normalized(result.operatingResult)).toBe('400')
    expect(result.warnings).toContain('存在未配置的费用项，结余按已填写项目暂算')
    expect(result.rows.filter((row) => row.provisional).length).toBe(14)
  })
})

describe('币种与缺成本', () => {
  it('费用构成按币种分行，不同币种不相加', () => {
    const expenses = [
      expenseRecord('T-EX-1', 'rent', CURRENCY, '3900.00'),
      expenseRecord('T-EX-2', 'utilities', CURRENCY, '1560.00'),
      expenseRecord('T-EX-3', 'rent', 'USD', '200.00'),
      expenseRecord('T-EX-4', 'maintenance', CURRENCY, '920.00'),
    ]

    const labels = { rent: '房租', utilities: '水电', maintenance: '维修' }
    const hkdRows = expenseStructure(CURRENCY, expenses, labels, '10000.00')
    expect(hkdRows.map((row) => row.category)).toEqual(['rent', 'utilities', 'maintenance'])
    expect(hkdRows.map((row) => normalized(row.amount?.amount))).toEqual(['3900', '1560', '920'])
    expect(hkdRows.every((row) => row.currency === CURRENCY)).toBe(true)
    expect(Number(hkdRows[0]?.share)).toBeCloseTo(0.39, 5)

    const usdRows = expenseStructure('USD', expenses, labels)
    expect(usdRows).toHaveLength(1)
    expect(normalized(usdRows[0]?.amount?.amount)).toBe('200')
    // 换币种求构成不会把 HKD 金额带进来。
    expect(usdRows[0]?.category).toBe('rent')

    // 不同币种相加必须返回 null，而不是把 USD 折进 HKD 合计。
    expect(addMoney(CURRENCY, { currency: CURRENCY, amount: '10.00' }, { currency: 'USD', amount: '10.00' })).toBeNull()
    expect(normalized(addMoney(CURRENCY, { currency: CURRENCY, amount: '10.00' }, { currency: CURRENCY, amount: '2.50' })?.amount)).toBe('12.5')
    expect(normalized(addMoney(CURRENCY, null, { currency: CURRENCY, amount: '2.50' })?.amount)).toBe('2.5')
  })

  it('缺成本项进入暂算警告，未定价时结余为 null 而不是 0', () => {
    const missingCost = operatingResult({
      currency: CURRENCY,
      outputValue: '800.00',
      employeeWage: null,
      managementWage: null,
      equipment: '0',
      tooling: null,
      rent: null,
      utilities: null,
      material: null,
      sundry: null,
      maintenance: null,
      nightSubsidy: null,
      inkIssueCost: null,
      noOutputWage: null,
      processing: null,
      recoverableWage: null,
      recoverablePaint: null,
    })

    expect(missingCost.warnings).toContain('存在未配置的费用项，结余按已填写项目暂算')
    expect(missingCost.rows.find((row) => row.key === 'employeeWage')?.provisional).toBe(true)
    expect(missingCost.rows.find((row) => row.key === 'equipment')?.provisional).toBe(false)
    expect(normalized(missingCost.operatingResult)).toBe('800')

    const unpriced = operatingResult({
      currency: CURRENCY,
      outputValue: null,
      employeeWage: '100.00',
      managementWage: null,
      equipment: null,
      tooling: null,
      rent: null,
      utilities: null,
      material: null,
      sundry: null,
      maintenance: null,
      nightSubsidy: null,
      inkIssueCost: null,
      noOutputWage: null,
      processing: null,
      recoverableWage: null,
      recoverablePaint: null,
    })

    expect(unpriced.operatingResult).toBeNull()
    expect(unpriced.warnings).toContain('产值不可计算：本期存在未定价报工，结余为暂算')
    expect(unpriced.rows[0]?.provisional).toBe(true)

    // 产值缺失但费用可算时，净额与「排除设备投资」差额仍分别给出，界面据此标注暂算。
    const unpricedWithEquipment = operatingResult({
      currency: CURRENCY,
      outputValue: null,
      employeeWage: '100.00',
      managementWage: null,
      equipment: '300.00',
      tooling: null,
      rent: null,
      utilities: null,
      material: null,
      sundry: null,
      maintenance: null,
      nightSubsidy: null,
      inkIssueCost: null,
      noOutputWage: null,
      processing: null,
      recoverableWage: null,
      recoverablePaint: null,
    })
    expect(unpricedWithEquipment.operatingResult).toBeNull()
    // 产值缺失时净额按 0 参与扣减：0 − 100 − 300 = −400；排除设备投资 300 后经营贡献 −100。
    // 两个数字都必须显示为暂算，且设备投资整笔扣减的差额 300 是显式的。
    expect(normalized(unpricedWithEquipment.equipmentExcludedDifference)).toBe('300')
    expect(normalized(unpricedWithEquipment.operatingContribution)).toBe('-100')
  })
})

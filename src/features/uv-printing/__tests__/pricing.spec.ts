import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import type { UvPricingInput } from '../contracts'
import {
  UV_PRICING_FORMULA_VERSION,
  computePricing,
  defaultPricingInput,
  pricingSensitivity,
} from '../domain/pricing'
import { decimalToNumber, formatDecimal, formatMoney } from '../domain/decimal'
import { PRICING_STATE } from '../domain/status'
import { UvMemoryStore } from '../preview/memoryStore'
import { DEFAULT_SHIFT_TEMPLATES } from '../domain/businessTime'
import { SAMPLE_BUSINESS_DATE, sampleProducts } from '../preview/fixtures'
import PricingStudio from '../components/PricingStudio.vue'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY, type UvPageContext } from '../composables/uvPageContext'

/**
 * 定价公式域测试（UV_PRINT_SHARED_SPEC.md 5.5）。
 *
 * 这些数字是产品定价页「可解释计算链」的验收基线：
 * 10h ÷ 0.5h = 20 板/天，20 板 × 20 件 = 400 件/天，
 * (200 + 80) ÷ 400 = 0.7 直接单位成本，
 * 成本加成 40% = 0.98，其对应毛利率 28.5714% ≠ 40%，
 * 目标毛利率 40% 报价 = 0.7 ÷ 0.6 ≈ 1.166667。
 */

function specInput(overrides: Partial<UvPricingInput> = {}): UvPricingInput {
  return {
    currency: 'HKD',
    daily_hours: '10',
    board_hours: '0.5',
    pieces_per_board: '20',
    labor_cost_per_day: '200',
    ink_cost_per_day: '80',
    markup_rate: '0.4',
    target_margin_rate: '0.4',
    loss_rate: null,
    ...overrides,
  }
}

function stepValue(result: ReturnType<typeof computePricing>, key: string): string | null {
  return result.steps.find((step) => step.key === key)?.value ?? null
}

describe('UV 定价公式：共享规格示例', () => {
  const result = computePricing(specInput())

  it('每日板数与日产能按 10h / 0.5h / 每板 20 件计算', () => {
    expect(result.not_computable_reason).toBeNull()
    expect(decimalToNumber(result.boards_per_day)).toBe(20)
    expect(formatDecimal(result.boards_per_day, 4)).toBe('20')
    expect(result.full_boards_per_day).toBe(20)
    expect(decimalToNumber(result.pieces_per_day)).toBe(400)
    expect(formatDecimal(result.pieces_per_day, 4)).toBe('400')
  })

  it('直接日成本 280、直接单位成本 0.7', () => {
    expect(formatDecimal(stepValue(result, 'direct_daily_cost'), 2)).toBe('280')
    expect(decimalToNumber(result.direct_unit_cost)).toBeCloseTo(0.7, 6)
    expect(formatDecimal(result.direct_unit_cost, 6)).toBe('0.7')
  })

  it('成本加成 40% 报价 0.98', () => {
    expect(decimalToNumber(result.markup_price)).toBeCloseTo(0.98, 6)
    expect(formatDecimal(result.markup_price, 6)).toBe('0.98')
  })

  it('加成对应毛利率约 28.5714%，不是 40%', () => {
    expect(decimalToNumber(result.markup_implied_margin)).toBeCloseTo(0.285714, 5)
    expect(formatDecimal(stepValue(result, 'markup_implied_margin'), 6)).toBe('0.285714')
    expect(decimalToNumber(result.markup_implied_margin)).toBeLessThan(0.4)
    // 计算链必须显式包含该步骤，用户才不会把「成本加成 40%」读成「毛利率 40%」。
    expect(result.steps.map((step) => step.key)).toContain('markup_implied_margin')
  })

  it('目标毛利率 40% 报价约 1.166667', () => {
    // decimalDivide 先多算 4 位再按 half-away-from-zero 舍入到 6 位，
    // 因此 0.7 ÷ 0.6 = 1.166667（规格示例值），与 0.98 是两个不同口径。
    expect(formatDecimal(result.target_margin_price, 6)).toBe('1.166667')
    expect(decimalToNumber(result.target_margin_price)).toBeCloseTo(1.166667, 6)
    expect(decimalToNumber(result.target_margin_price)).toBeGreaterThan(
      decimalToNumber(result.markup_price),
    )
  })

  it('计算链步骤顺序可解释且带公式与单位', () => {
    expect(result.steps.map((step) => step.key)).toEqual([
      'boards_per_day',
      'pieces_per_day',
      'direct_daily_cost',
      'direct_unit_cost',
      'markup_price',
      'markup_implied_margin',
      'target_margin_price',
    ])
    for (const step of result.steps) {
      expect(step.label.length).toBeGreaterThan(0)
      expect(step.formula.length).toBeGreaterThan(0)
    }
    expect(stepValue(result, 'markup_price')).toBe('0.9800000')
    expect(result.steps.find((step) => step.key === 'markup_price')?.unit).toBe('HKD/件')
    expect(result.formula_version).toBe(UV_PRICING_FORMULA_VERSION)
  })
})

describe('UV 定价公式：不可计算与目标毛利率边界', () => {
  it('每板耗时为 0 时给出原因，且不产出 0 成本报价', () => {
    const result = computePricing(specInput({ board_hours: '0' }))
    expect(result.not_computable_reason).not.toBeNull()
    expect(result.not_computable_reason).toContain('每板耗时')
    expect(result.boards_per_day).toBeNull()
    expect(result.pieces_per_day).toBeNull()
    expect(result.direct_unit_cost).toBeNull()
    expect(result.markup_price).toBeNull()
    expect(result.target_margin_price).toBeNull()
    expect(result.full_boards_per_day).toBeNull()
    // 报价步骤不得输出 '0'：不可计算必须是 null，不能长得像零元报价。
    for (const key of ['direct_unit_cost', 'markup_price', 'target_margin_price']) {
      expect(stepValue(result, key)).toBeNull()
    }
  })

  it('每板件数为 0 时同样不产出报价', () => {
    const result = computePricing(specInput({ pieces_per_board: '0' }))
    expect(result.pieces_per_day).toBe('0.0000')
    expect(result.direct_unit_cost).toBeNull()
    expect(result.markup_price).toBeNull()
    expect(result.not_computable_reason).toContain('日产能')
    expect(result.warnings.map((warning) => warning.code)).toContain('pieces_per_board_zero')
  })

  it('目标毛利率 ≥ 100% 时目标毛利报价为 null 并给出警告', () => {
    for (const target of ['1', '1.2']) {
      const result = computePricing(specInput({ target_margin_rate: target }))
      expect(result.target_margin_price).toBeNull()
      expect(stepValue(result, 'target_margin_price')).toBeNull()
      expect(result.warnings.map((warning) => warning.code)).toContain('margin_not_usable')
      // 目标毛利不可计算不影响成本加成报价仍然可用。
      expect(decimalToNumber(result.markup_price)).toBeCloseTo(0.98, 6)
    }
  })

  it('未填损耗率时口径只声明人工与油墨，绝不写成完整成本', () => {
    const result = computePricing(specInput({ loss_rate: null }))
    expect(result.cost_scope).toBe('仅含已填写的人工和油墨')
    expect(result.cost_scope).not.toContain('完整')
    const scopeWarning = result.warnings.find((warning) => warning.code === 'cost_scope')
    expect(scopeWarning).toBeDefined()
    expect(scopeWarning?.message).toContain('成本仅含已填写的人工和油墨')
    expect(JSON.stringify(result)).not.toContain('完整成本')
    expect(result.warnings.map((warning) => warning.code)).not.toContain('loss_included')
  })

  it('填写损耗率后口径变化，并提示准备时间仍未计入', () => {
    const result = computePricing(specInput({ loss_rate: '0.05' }))
    expect(result.cost_scope).toContain('损耗')
    expect(result.warnings.map((warning) => warning.code)).toContain('loss_included')
    const adjusted = stepValue(result, 'loss_adjusted_cost')
    expect(adjusted).not.toBeNull()
    // 0.7 ÷ 0.95 ≈ 0.736842
    expect(decimalToNumber(adjusted)).toBeCloseTo(0.736842, 5)
  })
})

describe('UV 定价公式：滑杆只做敏感性参考', () => {
  it('pricingSensitivity 不修改输入，也不改变正式报价', () => {
    const input = specInput()
    const before = structuredClone(input)
    const rows = pricingSensitivity(input)
    expect(input).toEqual(before)
    expect(rows.map((row) => row.rate)).toEqual(['0.1', '0.2', '0.3', '0.4', '0.5'])
    expect(decimalToNumber(rows[0]?.markup_price)).toBeCloseTo(0.77, 6)
    expect(decimalToNumber(rows[4]?.markup_price)).toBeCloseTo(1.05, 6)
    // 每一行的单位成本与目标毛利报价只由输入决定，与加成率无关。
    expect(new Set(rows.map((row) => row.unit_cost))).toEqual(new Set(['0.700000']))
    expect(decimalToNumber(computePricing(input).markup_price)).toBeCloseTo(0.98, 6)
  })

  it('defaultPricingInput 使用契约的 Decimal 字符串，不产生二进制浮点尾巴', () => {
    const defaults = defaultPricingInput('CNY')
    expect(defaults.currency).toBe('CNY')
    expect(defaults.loss_rate).toBeNull()
    for (const [key, value] of Object.entries(defaults)) {
      if (key === 'currency' || key === 'loss_rate') continue
      expect(typeof value).toBe('string')
      expect(String(value)).toMatch(/^-?\d+(\.\d+)?$/)
    }
  })

  it('新测算不猜 HKD：必须由用户或现有价规明确选择币种', () => {
    expect(defaultPricingInput().currency).toBe('')
    expect(computePricing(defaultPricingInput()).currency).toBe('')
  })
})

describe('UV 定价数据层：显式零价与缺价必须可区分', () => {
  it('显式零价是已定价且产值为 0，缺价是未定价且产值为 null', async () => {
    const store = new UvMemoryStore()

    // DEMO-P-0005（灯箱片）有一条 unit_price = 0 的显式零价商业执行价。
    const zero = await store.createReport({
      factory_id: 'huakang-a',
      operation_id: 'spec-zero-price',
      expected_version: 0,
      business_date: SAMPLE_BUSINESS_DATE,
      shift: 'day',
      shift_template_version_id: DEFAULT_SHIFT_TEMPLATES.day.versionId,
      machine_id: 'DEMO-M01',
      product_id: 'DEMO-P-0005',
      process_version_id: 'DEMO-PV-0005',
      reported_qty: 10,
      good_qty: 10,
      defective_qty: 0,
      pending_qty: 0,
      semi_finished_qty: 0,
      worker_ids: [],
      notes: '域测试：显式零价与缺价的区别。',
      source_allocations: [],
      evidence_job_ids: [],
    })
    const zeroCommercial = zero.data.entity.commercial
    expect(zeroCommercial?.pricing_state).toBe('priced')
    expect(zeroCommercial?.unit_price).toBe('0.000000')
    expect(zeroCommercial?.output_value).not.toBeNull()
    expect(Number(zeroCommercial?.output_value?.amount)).toBe(0)
    expect(formatMoney(zeroCommercial?.output_value)).toBe('HK$0.00')

    // DEMO-P-0004（按键铭牌）没有任何生效商业执行价。
    const unpricedPage = await store.reports({
      factory_id: 'huakang-a',
      business_date: SAMPLE_BUSINESS_DATE,
      product_id: 'DEMO-P-0004',
    })
    const unpricedCommercial = unpricedPage.data.items[0]?.commercial
    expect(unpricedCommercial?.pricing_state).toBe('unpriced')
    expect(unpricedCommercial?.output_value).toBeNull()
    expect(unpricedCommercial?.unit_price).toBeNull()
    expect(formatMoney(unpricedCommercial?.output_value)).toBe('—')

    // 两个状态在文案与数值上都不同：零价显示 0，缺价显示未定价。
    expect(zeroCommercial?.pricing_state).not.toBe(unpricedCommercial?.pricing_state)
    expect(PRICING_STATE.priced.label).toBe('已定价')
    expect(PRICING_STATE.unpriced.label).toBe('未定价')
  })

  it('保存测算记录公式版本与可计算结果，采用后产出执行价', async () => {
    const store = new UvMemoryStore()
    const saved = await store.savePricingQuote({
      factory_id: 'huakang-a',
      operation_id: 'spec-save-quote',
      expected_version: 0,
      label: '域测试报价',
      product_id: 'DEMO-P-0001',
      input: specInput(),
      note: '',
    })
    expect(saved.data.entity.result.formula_version).toBe(UV_PRICING_FORMULA_VERSION)
    expect(decimalToNumber(saved.data.entity.result.markup_price)).toBeCloseTo(0.98, 6)

    // 同一 operation_id 重放不产生第二条记录（幂等）。
    const replay = await store.savePricingQuote({
      factory_id: 'huakang-a',
      operation_id: 'spec-save-quote',
      expected_version: 0,
      label: '域测试报价',
      product_id: 'DEMO-P-0001',
      input: specInput(),
      note: '',
    })
    expect(replay.data.replayed).toBe(true)

    const adopted = await store.adoptPricingQuote({
      factory_id: 'huakang-a',
      operation_id: 'spec-adopt-quote',
      expected_version: 0,
      quote_id: saved.data.entity.id,
      rate_kind: 'commercial',
      effective_from: '2026-09-14',
    })
    expect(adopted.data.entity.rate_kind).toBe('commercial')
    expect(decimalToNumber(adopted.data.entity.unit_price)).toBeCloseTo(0.98, 6)
    expect(adopted.data.entity.note).toContain(UV_PRICING_FORMULA_VERSION)
  })
})

/* ------------------------------------------------------------------ *
 * 测算台渲染：计算链必须真的把共享公式的每一步显示出来
 * ------------------------------------------------------------------ */

function mountStudio(productIndex: number) {
  const product = sampleProducts[productIndex]!
  const processVersion = product.process_versions[product.process_versions.length - 1]!
  const store = new UvMemoryStore()
  const context = {
    transport: ref(store),
    revision: ref(0),
    markDirty: () => {},
    isPreview: ref(true),
    workspace: {
      scope: { value: { factory_id: 'huakang-a' } },
      business_date: { value: SAMPLE_BUSINESS_DATE },
      permissionDenied: { value: false },
      can: () => true,
    },
  } as unknown as UvPageContext
  const wrapper = mount(PricingStudio, {
    props: {
      product,
      processVersion,
      effectiveRate: null,
      effectiveRateLabel: '',
      quote: null,
      businessDate: SAMPLE_BUSINESS_DATE,
      canReadCost: true,
      canWriteCost: true,
      canPayrollWrite: true,
    },
    global: {
      provide: {
        [UV_TRANSPORT_KEY as symbol]: context.transport,
        [UV_CONTEXT_KEY as symbol]: context,
      },
    },
  })
  return wrapper
}

describe('定价测算台：可解释计算链', () => {
  it('把每一步标签、公式与数值渲染出来，并区分加成与毛利率', async () => {
    const wrapper = mountStudio(0)
    await wrapper.get('#uv-pricing-currency').setValue('HKD')
    const text = wrapper.text()

    for (const label of [
      '理论每日板数',
      '理论日产能',
      '直接日成本',
      '直接单位成本',
      '成本加成报价',
      '加成对应毛利率',
      '目标毛利报价',
    ]) {
      expect(text).toContain(label)
    }
    expect(text).toContain('每日可用工时 ÷ 每板耗时')
    expect(text).toContain('0.98')
    expect(text).toContain('1.166667')
    expect(text).toContain('28.57%')
    expect(text).toContain('不等于加成率本身')
    expect(text).toContain('成本仅含已填写的人工和油墨')
    expect(text).toContain('未定价')
    expect(wrapper.text()).not.toContain('完整成本')
    wrapper.unmount()
  })

  it('工艺未确认每板件数时不猜 1，也不渲染任何价格数字', async () => {
    const wrapper = mountStudio(4)
    await wrapper.get('#uv-pricing-currency').setValue('HKD')
    const text = wrapper.text()

    expect(text).toContain('未确认')
    expect(text).toContain('输入未填齐')
    expect(text).toContain('待填写：每板耗时、每板件数')
    // 光箱片工艺未确认：不能出现按 1 件推算出来的任何报价。
    expect(text).not.toContain('0.98')
    expect(text).not.toContain('成本加成报价')
    wrapper.unmount()
  })
})

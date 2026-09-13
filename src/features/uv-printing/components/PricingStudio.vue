<script setup lang="ts">
import { computed, inject, nextTick, reactive, ref, watch } from 'vue'
import { AlertTriangle, Calculator, Info, SlidersHorizontal } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  BusinessDate,
  UvMutationResult,
  UvPricingInput,
  UvPricingQuote,
  UvPricingQuoteInput,
  UvPricingStep,
  UvProcessVersion,
  UvProduct,
  UvRateKind,
  UvRateVersion,
  UvResponse,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand } from '../composables/useUvRequest'
import {
  decimalDivide,
  decimalIsZero,
  decimalMultiply,
  formatDecimal,
  money,
} from '../domain/decimal'
import {
  UV_PRICING_FORMULA_VERSION,
  computePricing,
  defaultPricingInput,
  pricingSensitivity,
} from '../domain/pricing'
import { RATE_KIND_LABELS } from '../domain/status'
import UvConfirmDialog from './UvConfirmDialog.vue'
import UvFormField from './UvFormField.vue'
import UvNumber from './UvNumber.vue'
import UvStateBlock from './UvStateBlock.vue'
import UvTable from './UvTable.vue'

/**
 * 定价测算台（产品定价页右栏）。
 *
 * - 公式一律来自 `domain/pricing.ts`（computePricing / pricingSensitivity），
 *   组件内不重写任何一条公式，只负责把 `steps` 渲染成可解释的编号计算链；
 * - 「成本加成 40%」与「毛利率 40%」必须同时可见：加成对应毛利率是链上独立一步；
 * - 滑杆只做敏感性参考（pricingSensitivity），移动滑杆不改产品价格、不改输入框；
 * - 「采用为执行价」是独立授权动作：必须已有保存的测算、显式生效起始日、
 *   cost_write（计件工价另需 payroll_write），并经 UvConfirmDialog 列出影响后确认，
 *   永不自动触发；
 * - 保存测算写入 operation_id + expected_version，重试复用同一幂等键；
 * - 输入未填齐时不渲染任何数字，绝不用 0 代替缺失。
 */

const props = withDefaults(defineProps<{
  product: UvProduct | null
  processVersion: UvProcessVersion | null
  /** 当前生效的商业执行价；null 表示未定价（不是 0）。 */
  effectiveRate: UvRateVersion | null
  /** 生效价规来源说明，例如「精确机台覆盖 · M01」。 */
  effectiveRateLabel: string
  /** 该产品已保存的最近一条测算。 */
  quote: UvPricingQuote | null
  businessDate: BusinessDate
  canReadCost: boolean
  canWriteCost: boolean
  canPayrollWrite: boolean
}>(), {
  product: null,
  processVersion: null,
  effectiveRate: null,
  quote: null,
})

const emit = defineEmits<{ saved: [quote: UvPricingQuote]; adopted: [rate: UvRateVersion] }>()

const transportRef = inject(UV_TRANSPORT_KEY)
const context = inject(UV_CONTEXT_KEY)
if (!transportRef || !context) {
  throw new Error('定价测算台必须在 UV 工作区壳内使用。')
}

const baseInput = defaultPricingInput('HKD')
const input = reactive<UvPricingInput>({ ...baseInput })

const quoteLabel = ref('')
const quoteNote = ref('')
const savedQuote = ref<UvPricingQuote | null>(null)
const sensitivityRate = ref('0.4')
const adoptOpen = ref(false)
const adoptKind = ref<UvRateKind>('commercial')
const adoptEffectiveFrom = ref(props.businessDate)
const adoptError = ref('')

const saveCommand = useUvCommand<UvResponse<UvMutationResult<UvPricingQuote>>>()
const adoptCommand = useUvCommand<UvResponse<UvMutationResult<UvRateVersion>>>()

let saveOperation: { id: string; fingerprint: string } | null = null
let adoptOperation: { id: string; fingerprint: string } | null = null

function operationFor(
  current: { id: string; fingerprint: string } | null,
  fingerprint: string,
): { id: string; fingerprint: string } {
  if (current && current.fingerprint === fingerprint) return current
  return { id: newOperationId(), fingerprint }
}

/* ---------------- 产品上下文 → 测算默认值（左右联动） ---------------- */

const contextKey = computed(() =>
  `${props.product?.id ?? ''}|${props.processVersion?.id ?? ''}|${props.effectiveRate?.id ?? ''}`,
)

function boardHoursFromVersion(version: UvProcessVersion | null): string {
  if (!version || version.board_seconds === null || version.board_seconds <= 0) return ''
  return formatDecimal(decimalDivide(String(version.board_seconds), '3600', 6), 6)
}

function applyContext() {
  input.board_hours = boardHoursFromVersion(props.processVersion)
  input.pieces_per_board = props.processVersion?.pieces_per_board === null || props.processVersion === null
    ? ''
    : String(props.processVersion.pieces_per_board)
  input.currency = props.effectiveRate?.currency ?? baseInput.currency
  // 人工与油墨是本次测算的输入假设，切换产品时保留用户已填的假设，不覆盖成样例值。
  quoteLabel.value = props.product
    ? `${props.product.product_no} ${props.product.name} 定价测算`
    : '定价测算'
}

watch(contextKey, () => {
  applyContext()
  savedQuote.value = null
  adoptError.value = ''
}, { immediate: true })

watch(() => props.quote, (quote) => {
  savedQuote.value = quote
})

watch(() => props.businessDate, (date) => {
  adoptEffectiveFrom.value = date
})

/* ---------------- 输入校验 ---------------- */

const REQUIRED_FIELDS: Array<{ key: keyof UvPricingInput; label: string; step: string; min: string }> = [
  { key: 'daily_hours', label: '每日可用工时', step: '0.5', min: '0' },
  { key: 'board_hours', label: '每板耗时', step: '0.05', min: '0' },
  { key: 'pieces_per_board', label: '每板件数', step: '1', min: '0' },
  { key: 'labor_cost_per_day', label: '日人工成本', step: '10', min: '0' },
  { key: 'ink_cost_per_day', label: '日油墨成本', step: '10', min: '0' },
  { key: 'markup_rate', label: '加成率', step: '0.05', min: '0' },
  { key: 'target_margin_rate', label: '目标毛利率', step: '0.05', min: '0' },
]

function rawValue(key: keyof UvPricingInput): string {
  const value = input[key]
  return typeof value === 'string' ? value : ''
}

function isDecimal(value: string): boolean {
  return /^\d+(\.\d+)?$/.test(value.trim())
}

const blankFields = computed(() =>
  REQUIRED_FIELDS.filter((field) => rawValue(field.key).trim() === '').map((field) => field.label),
)

const malformedFields = computed(() =>
  REQUIRED_FIELDS
    .filter((field) => {
      const value = rawValue(field.key).trim()
      return value !== '' && !isDecimal(value)
    })
    .map((field) => field.label),
)

const lossRateError = computed(() => {
  const value = input.loss_rate
  if (value === null || value.trim() === '') return ''
  return isDecimal(value) ? '' : '损耗率必须是非负十进制小数，例如 0.05'
})

/** 输入未填齐时整条链不渲染任何数字：缺失不等于 0。 */
const chainReady = computed(() =>
  blankFields.value.length === 0
  && malformedFields.value.length === 0
  && lossRateError.value === '',
)

const result = computed(() => computePricing({
  ...input,
  loss_rate: input.loss_rate === null || input.loss_rate.trim() === '' ? null : input.loss_rate.trim(),
}))

function stepText(step: UvPricingStep): string {
  if (step.value === null) return ''
  if (step.key === 'markup_implied_margin') {
    return `${formatDecimal(decimalMultiply(step.value, '100'), 4)}%`
  }
  if (step.key === 'pieces_per_day') return formatDecimal(step.value, 2)
  if (step.key === 'boards_per_day') return formatDecimal(step.value, 2)
  if (step.key === 'direct_daily_cost') return formatDecimal(step.value, 2)
  return formatDecimal(step.value, 6)
}

function stepUnit(step: UvPricingStep): string {
  if (step.key === 'markup_implied_margin') return '实际毛利率'
  return step.unit
}

const RESULT_STEPS = ['markup_price', 'target_margin_price']

const markupPrice = computed(() =>
  result.value.markup_price === null ? null : money(result.value.currency, result.value.markup_price),
)

const targetMarginPrice = computed(() =>
  result.value.target_margin_price === null ? null : money(result.value.currency, result.value.target_margin_price),
)

const impliedMarginText = computed(() =>
  result.value.markup_implied_margin === null
    ? ''
    : `${formatDecimal(decimalMultiply(result.value.markup_implied_margin, '100'), 2)}%`,
)

const markupRatePercent = computed(() => `${formatDecimal(decimalMultiply(input.markup_rate || '0', '100'), 2)}%`)

const targetMarginPercent = computed(() =>
  `${formatDecimal(decimalMultiply(input.target_margin_rate || '0', '100'), 2)}%`,
)

const zeroCostWarning = computed(() =>
  chainReady.value && decimalIsZero(input.labor_cost_per_day || '0') && decimalIsZero(input.ink_cost_per_day || '0'),
)

/* ---------------- 生效价规与未定价 ---------------- */

const effectiveRateIsZero = computed(() =>
  props.effectiveRate !== null && decimalIsZero(props.effectiveRate.unit_price),
)

const effectiveRateMoney = computed(() =>
  props.effectiveRate === null ? null : money(props.effectiveRate.currency, props.effectiveRate.unit_price),
)

const activeQuote = computed(() => savedQuote.value ?? props.quote)

const activeQuotePrice = computed(() => {
  const price = activeQuote.value?.result.markup_price
  return price === null || price === undefined
    ? null
    : money(activeQuote.value?.result.currency ?? 'HKD', price)
})

/* ---------------- 敏感性（只做参考） ---------------- */

const sensitivityRows = computed(() => (chainReady.value ? pricingSensitivity(result.value.input) : []))

const sensitivityRateNumber = computed(() => Number(sensitivityRate.value))

function sensitivityPrice(row: { markup_price: string | null }): string {
  return row.markup_price === null ? '' : formatDecimal(row.markup_price, 6)
}

/** 显式动作：把敏感性加成率写入测算输入框。滑杆本身永不改价。 */
function applySensitivityRate() {
  input.markup_rate = formatDecimal(sensitivityRate.value, 4)
}

/* ---------------- 保存测算 ---------------- */

const canSave = computed(() =>
  props.canWriteCost
  && chainReady.value
  && quoteLabel.value.trim().length > 0
  && !saveCommand.pending.value,
)

const saveBlockedReason = computed(() => {
  if (!props.canWriteCost) return '保存测算需要「成本维护权限」，当前账号没有该权限；是否允许写入最终由服务端判定。'
  if (!chainReady.value) return '输入未填齐，暂不能保存：保存会把不可计算的测算写成历史记录。'
  if (!quoteLabel.value.trim()) return '请填写测算名称，便于在测算历史中区分口径。'
  return ''
})

async function saveQuote() {
  if (!canSave.value) return
  const payload: UvPricingQuoteInput = {
    factory_id: context!.workspace.scope.value.factory_id,
    operation_id: '',
    expected_version: 0,
    label: quoteLabel.value.trim(),
    product_id: props.product?.id ?? null,
    input: { ...result.value.input },
    note: quoteNote.value.trim(),
  }
  const fingerprint = JSON.stringify(payload)
  saveOperation = operationFor(saveOperation, fingerprint)
  payload.operation_id = saveOperation.id
  const response = await saveCommand.execute(
    saveOperation.id,
    () => transportRef!.value.savePricingQuote(payload),
  )
  if (!response) return
  saveOperation = null
  savedQuote.value = response.data.entity
  context!.markDirty()
  emit('saved', response.data.entity)
}

/* ---------------- 采用为执行价（独立授权动作） ---------------- */

const adoptKindAllowed = computed(() => adoptKind.value !== 'piece_wage' || props.canPayrollWrite)

const adoptBlockedReason = computed(() => {
  if (!props.canWriteCost) return '采用为执行价需要「成本维护权限」，当前账号没有该权限；是否允许写入最终由服务端判定。'
  if (adoptKind.value === 'piece_wage' && !props.canPayrollWrite) {
    return '把测算采用为计件工价会影响工资口径，需要「计件工资维护权限」；当前账号没有该权限。'
  }
  if (!activeQuote.value) return '请先保存本次测算：采用为执行价只针对已保存、有编号的测算记录，不会自动采用当前预览。'
  if (!adoptEffectiveFrom.value) return '必须显式填写生效起始日，不允许由系统猜测。'
  if (activeQuotePrice.value === null) return '该测算结果不可计算，不能采用为执行价。'
  return ''
})

const canAdopt = computed(() => adoptBlockedReason.value === '' && !adoptCommand.pending.value)

const adoptImpacts = computed(() => {
  const quote = activeQuote.value
  const impacts: string[] = []
  if (!quote) return impacts
  impacts.push(
    `为「${props.product?.product_no ?? '未关联产品'} ${props.product?.name ?? ''}」新增一条${RATE_KIND_LABELS[adoptKind.value]}，单价 ${formatDecimal(quote.result.markup_price, 6)} ${quote.result.currency}。`,
  )
  impacts.push(`生效起始日 ${adoptEffectiveFrom.value}；生效区间左闭右闭，之后的报工按新价规计算。`)
  impacts.push('历史报工与已确认工资不追溯改写；需要更正历史必须走更正流程。')
  impacts.push('同一种价规、同一优先级、同一币种的生效区间不得重叠，重叠时服务端会拒绝，需要改生效日或改优先级。')
  impacts.push(`本次采用来自已保存测算「${quote.label}」（公式版本 ${quote.result.formula_version}），需要你在此明确确认，不会自动执行。`)
  impacts.push('采用会留下审计记录；之后调整价格必须新增价规版本，不能就地覆盖这条生效区间。')
  return impacts
})

function openAdopt() {
  if (!canAdopt.value) return
  adoptError.value = ''
  adoptOpen.value = true
}

async function confirmAdopt() {
  const quote = activeQuote.value
  if (!quote) return
  const payload = {
    factory_id: context!.workspace.scope.value.factory_id,
    operation_id: '',
    expected_version: quote.version,
    quote_id: quote.id,
    rate_kind: adoptKind.value,
    effective_from: adoptEffectiveFrom.value,
  }
  const fingerprint = JSON.stringify(payload)
  adoptOperation = operationFor(adoptOperation, fingerprint)
  payload.operation_id = adoptOperation.id
  const response = await adoptCommand.execute(
    adoptOperation.id,
    () => transportRef!.value.adoptPricingQuote(payload),
  )
  if (!response) {
    adoptError.value = adoptCommand.error.value?.message ?? '采用失败，请稍后重试。'
    adoptOpen.value = false
    await nextTick()
    return
  }
  adoptOperation = null
  adoptOpen.value = false
  context!.markDirty()
  emit('adopted', response.data.entity)
}
</script>

<template>
  <section class="uv-panel uv-studio" aria-labelledby="uv-pricing-studio-title">
    <header class="uv-panel__head">
      <div>
        <h2 id="uv-pricing-studio-title" class="uv-panel__title">定价测算台</h2>
        <p class="uv-panel__subtitle">
          按「每日板数 → 日产能 → 直接单位成本 → 报价」的顺序逐级解释；公式版本 {{ UV_PRICING_FORMULA_VERSION }}。
        </p>
      </div>
      <UvNumber
        v-if="props.effectiveRate && !effectiveRateIsZero"
        :money="effectiveRateMoney"
        size="lg"
        emphasis
        unit="/件"
      />
    </header>

    <div class="uv-panel__body">
      <UvStateBlock
        v-if="!product"
        state="empty"
        subject="产品"
        hint="先在上方产品列表选择一个货号；选中后会自动带出它的工艺版本与生效价规。"
      />

      <template v-else>
        <div class="uv-callout" :class="effectiveRate || !canReadCost ? '' : 'uv-callout--warning'">
          <p>
            <strong>当前生效商业执行价：</strong>
            <template v-if="!canReadCost">
              <span class="uv-num uv-num--pending">无权限查看</span>
              <span class="uv-field__hint">读取价格需要「成本读取权限」，敏感金额不会下发到前端；是否有权限以服务端判定为准。</span>
            </template>
            <template v-else-if="!effectiveRate">
              <span class="uv-num uv-num--unpriced">未定价</span>
              <span class="uv-field__hint">没有生效的商业执行价：未定价不是 0，产值不会被写成零。</span>
            </template>
            <template v-else-if="effectiveRateIsZero">
              <UvNumber :money="effectiveRateMoney" emphasis unit="/件" />
              <span class="uv-form-readonly">显式零价</span>
              <span class="uv-field__hint">这是人为确认过的零价执行，与「没有价规」不同。</span>
            </template>
            <template v-else>
              <UvNumber :money="effectiveRateMoney" emphasis unit="/件" />
              <span class="uv-field__hint">{{ effectiveRateLabel }}</span>
            </template>
          </p>
          <p class="uv-field__hint">
            工艺版本：{{ processVersion ? `${processVersion.version_label}（生效 ${processVersion.effective_from}）` : '未选择' }}
            · 每板件数：{{ processVersion?.pieces_per_board === null || !processVersion ? '未确认' : `${processVersion.pieces_per_board} 件/板` }}
            · 每板耗时：{{ processVersion?.board_seconds === null || !processVersion ? '未提供' : `${processVersion.board_seconds} 秒` }}
          </p>
        </div>

        <div class="uv-quote">
          <form class="uv-form" novalidate @submit.prevent="saveQuote">
            <h3 class="uv-section__title uv-form-field--span-3">
              <span class="uv-section__index" aria-hidden="true">1</span>
              <Calculator class="size-3.5" aria-hidden="true" />
              测算输入
            </h3>

            <UvFormField
              v-for="field in REQUIRED_FIELDS"
              :key="field.key"
              :label="field.key === 'board_hours' ? '每板耗时（小时）' : field.key === 'pieces_per_board' ? '每板件数' : `${field.label}`"
              required
              :field-id="`uv-pricing-${field.key}`"
              :error="malformedFields.includes(field.label) ? '请填写非负十进制数字' : ''"
              :help="field.key === 'board_hours'
                ? '留空表示工艺未提供；留空或填 0 都不会产出 0 成本报价，而是显示不可计算原因。'
                : field.key === 'pieces_per_board'
                  ? '工艺版本未确认时必须手工确认；不会按 1 件猜测。'
                  : field.key === 'markup_rate'
                    ? '0.4 = 成本加成 40%，不等于毛利率 40%，对应毛利率见计算链「加成对应毛利率」。'
                    : field.key === 'target_margin_rate'
                      ? '按「直接单位成本 ÷ (1 − 目标毛利率)」反算；填 1 及以上时目标毛利报价不可计算。'
                      : ''"
            >
              <template #default="{ describedBy, invalid }">
                <input
                  :id="`uv-pricing-${field.key}`"
                  class="uv-input"
                  :class="invalid ? 'uv-input--invalid' : ''"
                  type="number"
                  inputmode="decimal"
                  :min="field.min"
                  :step="field.step"
                  :value="rawValue(field.key)"
                  :aria-describedby="describedBy"
                  :aria-invalid="invalid"
                  @input="input[field.key] = ($event.target as HTMLInputElement).value"
                >
              </template>
            </UvFormField>

            <UvFormField label="币种" required field-id="uv-pricing-currency" help="币种只标注本次测算结果的币种，系统不做汇率折算。">
              <template #default="{ describedBy }">
                <select
                  id="uv-pricing-currency"
                  class="uv-input uv-select"
                  :value="input.currency"
                  :aria-describedby="describedBy"
                  @change="input.currency = ($event.target as HTMLSelectElement).value"
                >
                  <option value="HKD">HKD 港币</option>
                  <option value="CNY">CNY 人民币</option>
                  <option value="USD">USD 美元</option>
                </select>
              </template>
            </UvFormField>

            <UvFormField
              label="损耗率（可选）"
              field-id="uv-pricing-loss"
              :error="lossRateError"
              help="留空表示不计损耗；此时结果会写出口径只含已填写的人工和油墨，不声明为完整口径。"
            >
              <template #default="{ describedBy, invalid }">
                <input
                  id="uv-pricing-loss"
                  class="uv-input"
                  :class="invalid ? 'uv-input--invalid' : ''"
                  type="number"
                  inputmode="decimal"
                  min="0"
                  step="0.01"
                  :value="input.loss_rate ?? ''"
                  :aria-describedby="describedBy"
                  :aria-invalid="invalid"
                  placeholder="例如 0.05"
                  @input="input.loss_rate = ($event.target as HTMLInputElement).value"
                >
              </template>
            </UvFormField>

            <p class="uv-field__hint uv-form-field--span-3">
              日人工成本与日油墨成本是本次测算的输入假设，不代表账面实际成本。
            </p>
          </form>

          <div>
            <h3 class="uv-section__title">
              <span class="uv-section__index" aria-hidden="true">2</span>
              可解释计算链
            </h3>

            <div v-if="!chainReady" class="uv-callout uv-callout--warning" role="status">
              <p><strong>输入未填齐，暂不计算，也不显示任何数字。</strong></p>
              <ul class="uv-list">
                <li v-if="blankFields.length">
                  <span class="uv-list__dot" aria-hidden="true" />
                  <span>待填写：{{ blankFields.join('、') }}</span>
                </li>
                <li v-if="malformedFields.length">
                  <span class="uv-list__dot" aria-hidden="true" />
                  <span>格式有误：{{ malformedFields.join('、') }}</span>
                </li>
                <li v-if="lossRateError">
                  <span class="uv-list__dot" aria-hidden="true" />
                  <span>{{ lossRateError }}</span>
                </li>
                <li v-if="processVersion && processVersion.pieces_per_board === null">
                  <span class="uv-list__dot" aria-hidden="true" />
                  <span>该工艺版本未确认每板件数，未确认不等于 1，请先维护工艺或手工确认。</span>
                </li>
                <li v-if="processVersion && processVersion.board_seconds === null">
                  <span class="uv-list__dot" aria-hidden="true" />
                  <span>该工艺版本未提供每板耗时，请按实测填写。</span>
                </li>
              </ul>
            </div>

            <template v-else>
              <div v-if="result.not_computable_reason" class="uv-callout uv-callout--warning" role="alert">
                <AlertTriangle class="inline size-3.5" aria-hidden="true" />
                <strong>不可计算：</strong>{{ result.not_computable_reason }}。不可计算显示为「不可计算」，不会显示 0 元报价。
              </div>

              <ol class="uv-quote__chain">
                <li
                  v-for="(step, index) in result.steps"
                  :key="step.key"
                  class="uv-quote-step"
                  :class="RESULT_STEPS.includes(step.key) ? 'uv-quote-step--result' : ''"
                >
                  <span class="uv-quote-step__index" aria-hidden="true">{{ index + 1 }}</span>
                  <div>
                    <p class="uv-quote-step__label">{{ step.label }}</p>
                    <p class="uv-quote-step__formula">{{ step.formula }}</p>
                  </div>
                  <p class="uv-quote-step__value">
                    <span v-if="step.value === null" class="uv-num uv-num--pending">不可计算</span>
                    <template v-else>
                      <span class="uv-mono">{{ stepText(step) }}</span>
                      <span v-if="stepUnit(step)" class="uv-num__unit">{{ stepUnit(step) }}</span>
                    </template>
                  </p>
                </li>
              </ol>

              <div class="uv-callout uv-callout--accent">
                <p>
                  <strong>成本加成报价</strong>
                  <UvNumber v-if="markupPrice" :money="markupPrice" emphasis unit="/件" />
                  <span v-else class="uv-num uv-num--pending">不可计算</span>
                  <span class="uv-field__hint">加成率 {{ markupRatePercent }}（加成 {{ formatDecimal(input.markup_rate, 4) }}）</span>
                </p>
                <p>
                  <strong>目标毛利报价</strong>
                  <UvNumber v-if="targetMarginPrice" :money="targetMarginPrice" emphasis unit="/件" />
                  <span v-else class="uv-num uv-num--pending">不可计算</span>
                  <span class="uv-field__hint">目标毛利率 {{ targetMarginPercent }}（{{ formatDecimal(input.target_margin_rate, 4) }}）</span>
                </p>
                <p v-if="impliedMarginText" class="uv-field__hint">
                  成本加成 {{ markupRatePercent }} 对应的实际毛利率约 {{ impliedMarginText }}，不等于加成率本身；
                  两个报价不是同一个口径，不能用加成率代替毛利率。
                </p>
                <p class="uv-field__hint">成本口径：{{ result.cost_scope }}。</p>
              </div>

              <ul v-if="result.warnings.length" class="uv-list">
                <li v-for="warning in result.warnings" :key="warning.code">
                  <span class="uv-list__dot" aria-hidden="true" />
                  <span>{{ warning.message }}</span>
                </li>
              </ul>

              <p v-if="zeroCostWarning" class="uv-callout uv-callout--warning" role="status">
                日人工成本与日油墨成本都是 0，报价只反映已填输入，不代表真实成本。
              </p>
            </template>
          </div>
        </div>

        <div class="uv-section">
          <h3 class="uv-section__title">
            <span class="uv-section__index" aria-hidden="true">3</span>
            <SlidersHorizontal class="size-3.5" aria-hidden="true" />
            加成率敏感性（只做参考，不改动任何价格）
          </h3>

          <div v-if="!chainReady" class="uv-callout">
            输入未填齐，敏感性对比暂不可用。
          </div>

          <template v-else>
            <UvFormField
              label="敏感性加成率（滑杆，仅用于对比）"
              field-id="uv-pricing-sensitivity"
              help="滑杆只高亮对比行，不会写入产品或报价；所有数值仍可在上方输入框用键盘精确输入。"
            >
              <template #default="{ describedBy }">
                <input
                  id="uv-pricing-sensitivity"
                  class="uv-slider"
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  :value="sensitivityRate"
                  :aria-describedby="describedBy"
                  :aria-valuetext="`加成率 ${sensitivityRate}`"
                  @input="sensitivityRate = ($event.target as HTMLInputElement).value"
                >
              </template>
            </UvFormField>

            <UvTable
              :columns="[
                { key: 'rate', label: '加成率', width: 120, align: 'right' },
                { key: 'unit', label: '直接单位成本', width: 160, align: 'right' },
                { key: 'markup', label: '成本加成报价', width: 160, align: 'right' },
                { key: 'margin', label: '目标毛利报价', width: 160, align: 'right' },
                { key: 'note', label: '口径', width: 240 },
              ]"
              :min-width="860"
              dense
              caption="加成率敏感性对比（只读参考）"
              keyboard-hint="滑杆只移动高亮行；价格不会被滑杆改写。"
            >
              <tr
                v-for="row in sensitivityRows"
                :key="row.rate"
                :aria-selected="Number(row.rate) === sensitivityRateNumber"
              >
                <td class="uv-table-cell--right uv-mono">{{ formatDecimal(row.rate, 2) }}</td>
                <td class="uv-table-cell--right">{{ formatDecimal(row.unit_cost, 6) }}</td>
                <td class="uv-table-cell--right">{{ sensitivityPrice(row) || '不可计算' }}</td>
                <td class="uv-table-cell--right">{{ formatDecimal(row.target_margin_price, 6) }}</td>
                <td>{{ Number(row.rate) === sensitivityRateNumber ? '滑杆当前高亮行' : '参考行' }}</td>
              </tr>
            </UvTable>

            <div class="uv-actions">
              <Button variant="outline" size="sm" type="button" @click="applySensitivityRate">
                把加成率 {{ formatDecimal(sensitivityRate, 2) }} 写入测算输入
              </Button>
              <span class="uv-field__hint">只有点击这个按钮才会改动输入框；滑杆本身不改变任何数字。</span>
            </div>
          </template>
        </div>

        <div class="uv-section">
          <h3 class="uv-section__title">
            <span class="uv-section__index" aria-hidden="true">4</span>
            保存测算与采用为执行价
          </h3>

          <div class="uv-form">
            <UvFormField label="测算名称" required field-id="uv-pricing-label" help="名称会出现在测算历史里，说明这是哪一次口径。">
              <template #default="{ describedBy }">
                <input
                  id="uv-pricing-label"
                  v-model="quoteLabel"
                  class="uv-input"
                  type="text"
                  :aria-describedby="describedBy"
                >
              </template>
            </UvFormField>

            <UvFormField label="备注" field-id="uv-pricing-note" :span="2">
              <template #default="{ describedBy }">
                <input
                  id="uv-pricing-note"
                  v-model="quoteNote"
                  class="uv-input"
                  type="text"
                  placeholder="例如客户询价单号、参考的同行报价"
                  :aria-describedby="describedBy"
                >
              </template>
            </UvFormField>
          </div>

          <div class="uv-actions">
            <Button type="button" :disabled="!canSave" :title="saveBlockedReason || undefined" @click="saveQuote">
              {{ saveCommand.pending.value ? '正在保存…' : '保存测算' }}
            </Button>
            <span v-if="saveBlockedReason" class="uv-field__hint">{{ saveBlockedReason }}</span>
            <span v-else class="uv-field__hint">
              保存会写入测算输入、公式版本 {{ UV_PRICING_FORMULA_VERSION }} 与计算结果；重试使用同一幂等键，不会重复入账。
            </span>
          </div>

          <div v-if="saveCommand.error.value" class="uv-callout uv-callout--warning" role="alert">
            <strong>保存失败：</strong>{{ saveCommand.error.value.message }}（输入已保留，可重试）
          </div>

          <div v-if="savedQuote" class="uv-callout" role="status">
            <Info class="inline size-3.5" aria-hidden="true" />
            已保存测算「{{ savedQuote.label }}」，编号 {{ savedQuote.id }}，公式版本 {{ savedQuote.result.formula_version }}。
          </div>

          <div class="uv-section">
            <h4 class="uv-section__title">采用为执行价（独立授权动作）</h4>
            <p class="uv-callout uv-callout--accent">
              「采用为执行价」不会自动发生：必须已有保存的测算、显式填写生效起始日，并在确认框中确认影响后才会写入新的价规版本。
              滑杆、切换产品、保存测算都不会触发它。
            </p>

            <div class="uv-form">
              <UvFormField
                label="生效起始日"
                required
                field-id="uv-pricing-adopt-from"
                help="必填。系统不会猜测生效日，也不会把生效日回填成今天。"
              >
                <template #default="{ describedBy }">
                  <input
                    id="uv-pricing-adopt-from"
                    v-model="adoptEffectiveFrom"
                    class="uv-input"
                    type="date"
                    :aria-describedby="describedBy"
                  >
                </template>
              </UvFormField>

              <UvFormField
                label="采用为"
                field-id="uv-pricing-adopt-kind"
                help="采用为计件工价会影响工资口径，需要额外的计件工资维护权限。"
              >
                <template #default="{ describedBy }">
                  <select
                    id="uv-pricing-adopt-kind"
                    v-model="adoptKind"
                    class="uv-input uv-select"
                    :aria-describedby="describedBy"
                  >
                    <option value="commercial">{{ RATE_KIND_LABELS.commercial }}</option>
                    <option value="piece_wage">{{ RATE_KIND_LABELS.piece_wage }}</option>
                    <option value="area">{{ RATE_KIND_LABELS.area }}</option>
                  </select>
                </template>
              </UvFormField>

              <UvFormField label="待采用的已保存测算" readonly field-id="uv-pricing-adopt-quote">
                <template #default="{ describedBy }">
                  <input
                    id="uv-pricing-adopt-quote"
                    class="uv-input"
                    type="text"
                    readonly
                    :value="activeQuote
                      ? `${activeQuote.label} · ${formatDecimal(activeQuote.result.markup_price, 6)} ${activeQuote.result.currency} · 公式 ${activeQuote.result.formula_version}`
                      : '尚未保存测算'"
                    :aria-describedby="describedBy"
                  >
                </template>
              </UvFormField>
            </div>

            <div class="uv-actions">
              <Button
                variant="secondary"
                type="button"
                :disabled="!canAdopt"
                :title="adoptBlockedReason || undefined"
                @click="openAdopt"
              >
                采用为执行价
              </Button>
              <span v-if="adoptBlockedReason" class="uv-field__hint">{{ adoptBlockedReason }}</span>
            </div>

            <div v-if="adoptError" class="uv-callout uv-callout--warning" role="alert">
              <strong>采用失败：</strong>{{ adoptError }}
            </div>
          </div>
        </div>
      </template>
    </div>

    <UvConfirmDialog
      :open="adoptOpen"
      title="采用为执行价"
      hint="这是一次会影响后续产值与工资的写入，请确认对象、生效日与后果。"
      confirm-label="确认采用为执行价"
      :impacts="adoptImpacts"
      :busy="adoptCommand.pending.value"
      @confirm="confirmAdopt"
      @cancel="adoptOpen = false"
    />
  </section>
</template>

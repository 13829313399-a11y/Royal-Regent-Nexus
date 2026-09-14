<script lang="ts">
import type { DecimalString, UvInkBalance, UvInkSku } from '../contracts'
// 取别名是为了让本文件的两个 script 块不产生同名本地绑定。
import {
  decimalCompare as compareDecimal,
  decimalMultiply as multiplyDecimal,
} from '../domain/decimal'

/** 抽屉可选的 SKU：主数据 + 该 SKU 自己的余额（余额缺失时不显示 0）。 */
export interface InkDrawerSku {
  sku: UvInkSku
  balance: UvInkBalance | null
}

export type InkIssueMode = 'issue' | 'purchase'
export type InkIssueUnit = 'bottle' | 'ml'

/** 抽屉提交的数据；单位换算在前端完成，正式入账仍由后端 Decimal 计算。 */
export interface InkIssueSubmission {
  sku_id: string
  quantity_ml: DecimalString
  bottle_input: DecimalString | null
  occurred_on: string
  machine_id: string | null
  purpose: string
  source_doc: string
  created_by_name: string
  unit_cost: DecimalString | null
  currency: string | null
}

/** 只接受十进制写法，避免把 'abc' 交给 BigInt 解析。 */
export function normalizeInkDecimalInput(value: string): string {
  const trimmed = value.trim()
  if (trimmed === '' || trimmed === '.') return ''
  return /^\d*(\.\d*)?$/.test(trimmed) ? trimmed : ''
}

/**
 * 按出库单位换算 ml：500ml 包装领 2 瓶 = 1000ml，不是 2000ml。
 * 包装容量缺失时返回 0，由调用处显示「包装容量未知」，不假定 1000ml。
 */
export function inkQuantityMl(input: string, unit: InkIssueUnit, packageMl: DecimalString | null): DecimalString {
  const normalized = normalizeInkDecimalInput(input)
  if (normalized === '') return '0'
  if (unit === 'ml') return normalized
  if (!packageMl || compareDecimal(packageMl, '0') <= 0) return '0'
  return multiplyDecimal(normalized, packageMl)
}
</script>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { UvMachine } from '../contracts'
import type { UvRequestError } from '../composables/useUvRequest'
import {
  bottlesFromMl,
  decimalCompare,
  decimalIsZero,
  decimalMultiply,
  formatDecimal,
  formatMoney,
  money,
} from '../domain/decimal'
import { INK_MATERIAL_LABELS } from '../domain/status'
import UvDrawer from './UvDrawer.vue'
import UvField from './UvField.vue'
import UvFormField from './UvFormField.vue'

/**
 * 领用出库 / 采购入库抽屉。
 *
 * 顺序固定：先选 SKU → 再显示当前库存、包装容量、出库单位与换算结果 → 最后选机台与用途。
 *
 * - 双单位：可以按瓶登记，也可以按 ml 登记，换算结果实时可见；
 *   500ml 包装领 2 瓶 = 1000ml，绝不出现「瓶数 × 1000」这类硬编码；
 * - 未知单价不阻断数量操作：出库照常成功，成本显示「待核」，不写成 0；
 * - 库存不足（uv_insufficient_stock）是字段级错误并给出可用 ml，表单内容保留、可重试；
 * - 校验失败与提交失败都不清空表单。
 */

const props = withDefaults(defineProps<{
  open: boolean
  mode: InkIssueMode
  skus: InkDrawerSku[]
  machines: UvMachine[]
  machinesLoading: boolean
  machinesError: string
  canCostRead: boolean
  canWrite: boolean
  pending: boolean
  error: UvRequestError | null
  businessDate: string
  presetSkuId?: string | null
}>(), {
  presetSkuId: null,
})

const emit = defineEmits<{
  close: []
  submit: [payload: InkIssueSubmission]
  retryMachines: []
}>()

const skuId = ref('')
const unit = ref<InkIssueUnit>('bottle')
const amountText = ref('')
const occurredOn = ref(props.businessDate)
const machineId = ref('')
const purpose = ref('')
const sourceDoc = ref('')
const handlerName = ref('')
const unitCostText = ref('')
const currency = ref('')
const showErrors = ref(false)

const isPurchase = computed(() => props.mode === 'purchase')
const title = computed(() => (isPurchase.value ? '采购入库' : '领用出库'))
const subtitle = computed(() =>
  isPurchase.value
    ? '登记采购入库的数量与单价；缺单价时数量照常入库，成本标记为待核。'
    : '登记机台领用数量；先选 SKU 看库存与包装，再填数量与用途。',
)

const selected = computed<InkDrawerSku | null>(
  () => props.skus.find((row) => row.sku.id === skuId.value) ?? null,
)

const packageMl = computed<string | null>(() => {
  const value = selected.value?.sku.package_ml ?? null
  if (!value) return null
  return decimalCompare(value, '0') > 0 ? value : null
})

const availableMl = computed<string | null>(() => selected.value?.balance?.available_ml ?? null)

const quantityMl = computed(() => inkQuantityMl(amountText.value, unit.value, packageMl.value))

const bottleInput = computed<string | null>(() => {
  if (unit.value === 'bottle') return normalizeInkDecimalInput(amountText.value) || null
  if (!packageMl.value) return null
  return bottlesFromMl(quantityMl.value, packageMl.value)
})

/** 换算结果实时可见：两种单位互相折算，避免把「瓶」当成「ml」。 */
const conversionText = computed(() => {
  const raw = normalizeInkDecimalInput(amountText.value)
  if (!selected.value) return '先选择 SKU，再填写数量'
  if (!raw) return `出库单位：${unit.value === 'bottle' ? '瓶' : 'ml'}`
  if (unit.value === 'bottle') {
    return `${raw} 瓶 × ${formatDecimal(packageMl.value, 0)} ml/瓶 = ${formatDecimal(quantityMl.value, 3)} ml`
  }
  const bottles = packageMl.value ? bottlesFromMl(quantityMl.value, packageMl.value) : null
  return bottles
    ? `${formatDecimal(quantityMl.value, 3)} ml ÷ ${formatDecimal(packageMl.value, 0)} ml/瓶 = ${formatDecimal(bottles, 3)} 瓶`
    : `${formatDecimal(quantityMl.value, 3)} ml（包装容量未知，无法折算瓶数）`
})

/** 始终给出一个具体示例，防止把瓶数乘成 1000。 */
const exampleHint = computed(() => {
  if (!packageMl.value) return '包装容量未配置：请按 ml 登记，折算瓶数会显示「包装容量未知」。'
  return `例：${formatDecimal(packageMl.value, 0)}ml 包装领 2 瓶 = ${formatDecimal(decimalMultiply('2', packageMl.value), 0)}ml`
})

const estimatedAmount = computed(() => {
  const sku = selected.value?.sku
  if (!sku?.unit_cost || !sku.currency) return null
  if (decimalIsZero(quantityMl.value)) return null
  return money(sku.currency, decimalMultiply(quantityMl.value, sku.unit_cost))
})

function machineLabel(machine: UvMachine): string {
  return `${machine.code} · ${machine.name}（${INK_MATERIAL_LABELS[machine.ink_material] ?? '材质未标注'}）`
}

const materialMismatch = computed(() => {
  const sku = selected.value?.sku
  const machine = props.machines.find((candidate) => candidate.id === machineId.value)
  if (!sku || !machine || machine.ink_material === sku.material) return ''
  return `提示：机台 ${machine.code} 标注的墨水材质是「${INK_MATERIAL_LABELS[machine.ink_material] ?? '未标注'}」，`
    + `与所选 SKU 的「${INK_MATERIAL_LABELS[sku.material] ?? '未标注'}」不一致，请确认没有拿错墨。`
})

/* ---------------- 校验与错误 ---------------- */

const localErrors = computed<Record<string, string>>(() => {
  const errors: Record<string, string> = {}
  if (!skuId.value) errors.sku_id = '请先选择墨水 SKU'
  const raw = normalizeInkDecimalInput(amountText.value)
  if (amountText.value.trim() !== '' && raw === '') errors.amount = '数量只能是数字，例如 2 或 750.5'
  else if (raw === '') errors.amount = '请填写出库/入库数量'
  else if (decimalCompare(quantityMl.value, '0') <= 0) errors.amount = '数量必须大于 0'
  else if (unit.value === 'bottle' && !packageMl.value) errors.amount = '该 SKU 没有包装容量，请改用 ml 登记'
  if (!purpose.value.trim()) errors.purpose = '请填写用途，例如生产领用、打样、退料'
  if (!handlerName.value.trim()) errors.handler_name = '请填写经手人，会写入流水审计'
  if (isPurchase.value && props.canCostRead && unitCostText.value.trim() && !currency.value.trim()) {
    errors.currency = '填写单价时必须选择币种，否则无法计算金额'
  }
  return errors
})

const serverErrors = computed<Record<string, string>>(() => {
  const error = props.error
  if (!error) return {}
  const mapped: Record<string, string> = {}
  if (error.code === 'uv_insufficient_stock') {
    mapped.amount = availableMl.value === null
      ? error.message
      : `库存不足：可用 ${formatDecimal(availableMl.value, 1)} ml，本次需要 ${formatDecimal(quantityMl.value, 1)} ml。${error.message}`
  }
  for (const [key, message] of Object.entries(error.fields)) {
    if (key === 'quantity_ml') mapped.amount = mapped.amount ?? `服务端校验：${message}`
    else if (key === 'sku_id') mapped.sku_id = `服务端校验：${message}`
    else mapped[key] = `服务端校验：${message}`
  }
  return mapped
})

function fieldError(key: string): string {
  return (showErrors.value ? localErrors.value[key] : '') ?? serverErrors.value[key] ?? ''
}

/** 不在字段级别的错误：用抽屉内的 role="alert" 说明，不能只靠会自动消失的 Toast。 */
const blockingError = computed(() => {
  const error = props.error
  if (!error) return null
  if (error.code === 'uv_insufficient_stock' || error.code === 'uv_invalid_field') return null
  return error
})

const insufficientStock = computed(() => props.error?.code === 'uv_insufficient_stock')

const canSubmit = computed(() => props.canWrite && props.open && !props.pending)
const submitIcon = computed(() => (isPurchase.value ? ArrowDownToLine : ArrowUpFromLine))

const submitLabel = computed(() => {
  if (props.pending) return '正在提交…'
  if (props.error) return '重试提交'
  return isPurchase.value ? '确认入库' : '确认出库'
})

function submit() {
  if (!canSubmit.value) return
  showErrors.value = true
  if (Object.keys(localErrors.value).length) return
  emit('submit', {
    sku_id: skuId.value,
    quantity_ml: quantityMl.value,
    bottle_input: bottleInput.value,
    occurred_on: occurredOn.value || props.businessDate,
    machine_id: machineId.value || null,
    purpose: purpose.value.trim(),
    source_doc: sourceDoc.value.trim(),
    created_by_name: handlerName.value.trim(),
    unit_cost: isPurchase.value && props.canCostRead && unitCostText.value.trim()
      ? normalizeInkDecimalInput(unitCostText.value)
      : null,
    currency: isPurchase.value && props.canCostRead ? (currency.value.trim() || null) : null,
  })
}

function requestClose() {
  if (props.pending) return
  emit('close')
}

/** 每次打开重置草稿；失败重试时不重置，表单内容保留。 */
watch(() => props.open, (open) => {
  if (!open) return
  skuId.value = props.presetSkuId ?? ''
  unit.value = 'bottle'
  amountText.value = ''
  occurredOn.value = props.businessDate
  machineId.value = ''
  purpose.value = isPurchase.value ? '采购入库' : '生产领用'
  sourceDoc.value = ''
  handlerName.value = ''
  unitCostText.value = ''
  currency.value = ''
  showErrors.value = false
})

watch(() => props.presetSkuId, (value) => {
  if (props.open && value) skuId.value = value
})

watch(packageMl, (value) => {
  if (!value) unit.value = 'ml'
})
</script>

<template>
  <UvDrawer
    :open="props.open"
    :title="title"
    :subtitle="subtitle"
    size="lg"
    :busy="props.pending"
    @close="requestClose"
  >
    <div v-if="!props.canWrite" class="uv-callout uv-callout--warning" role="alert">
      <strong>写操作已停用</strong>：当前账号在华康A生产部缺少 <span class="uv-mono">uv_printing:ink_write</span> 权限，
      领用、入库与冲销都不可提交。前端权限只是提示，服务端仍会独立校验并拒绝越权写入。
    </div>

    <div v-if="blockingError" class="uv-callout uv-callout--warning" role="alert">
      <strong>提交失败</strong>：{{ blockingError.message }}
      <br>
      表单内容已保留，可以修改后重试，或先核对库存与权限再提交。
    </div>

    <div v-if="insufficientStock" class="uv-callout uv-callout--warning" role="alert">
      <strong>库存不足，本次没有出库</strong>：可用
      {{ availableMl === null ? '未知' : `${formatDecimal(availableMl, 1)} ml` }}，
      本次需要 {{ formatDecimal(quantityMl, 1) }} ml。请调整数量后重试；库存不会被写成负数。
    </div>

    <section class="uv-section">
      <h3 class="uv-section__title"><span class="uv-section__index">1</span>选择墨水 SKU</h3>
      <div class="uv-form">
        <UvFormField
          label="墨水 SKU"
          required
          field-id="ink-issue-sku"
          :error="fieldError('sku_id')"
          help="同色不同供应商、不同材质是不同 SKU，库存不互相抵扣。"
          :span="2"
        >
          <select
            id="ink-issue-sku"
            v-model="skuId"
            class="uv-input uv-select"
            :class="fieldError('sku_id') ? 'uv-input--invalid' : ''"
            :aria-invalid="Boolean(fieldError('sku_id'))"
            aria-label="墨水 SKU"
          >
            <option value="">请选择供应商 / 材质 / 颜色的具体 SKU</option>
            <option v-for="row in props.skus" :key="row.sku.id" :value="row.sku.id">
              {{ row.sku.supplier }} · {{ INK_MATERIAL_LABELS[row.sku.material] ?? '材质未标注' }} · {{ row.sku.color }}
              （{{ formatDecimal(row.sku.package_ml, 0) }}ml/瓶）
            </option>
          </select>
        </UvFormField>
      </div>
    </section>

    <section v-if="selected" class="uv-section">
      <h3 class="uv-section__title"><span class="uv-section__index">2</span>当前库存、包装容量与换算</h3>
      <dl class="uv-detail-grid">
        <UvField
          label="当前可用库存"
          :value="availableMl === null ? null : `${formatDecimal(availableMl, 1)} ml`"
          missing-label="余额未知"
          hint="按该 SKU 独立计算"
        />
        <UvField
          label="包装容量"
          :value="packageMl ? `${formatDecimal(packageMl, 0)} ml/瓶` : null"
          missing-label="未配置"
          hint="SKU 配置，不假定 1000ml"
        />
        <UvField label="库位" :value="selected.sku.location || null" missing-label="未登记库位" />
        <UvField
          label="成本口径"
          :value="props.canCostRead
            ? (selected.sku.unit_cost ? `${formatDecimal(selected.sku.unit_cost, 4)} ${selected.sku.currency ?? ''}/ml` : '单价缺失，金额待核')
            : null"
          missing-label="未授权"
          :hint="props.canCostRead ? '前端预览，正式入账由后端 Decimal 计算' : '缺少 uv_printing:cost_read，成本不下发前端'"
        />
      </dl>

      <div class="uv-form" style="margin-top: 12px">
        <UvFormField label="出库单位" required field-id="ink-issue-unit" help="按瓶或按 ml 登记都可以，换算结果实时显示。">
          <select id="ink-issue-unit" v-model="unit" class="uv-input uv-select" aria-label="出库单位">
            <option value="bottle" :disabled="!packageMl">
              瓶（{{ packageMl ? `${formatDecimal(packageMl, 0)}ml/瓶` : '包装容量未知' }}）
            </option>
            <option value="ml">ml</option>
          </select>
        </UvFormField>

        <UvFormField
          :label="unit === 'bottle' ? '数量（瓶）' : '数量（ml）'"
          required
          field-id="ink-issue-quantity"
          :error="fieldError('amount')"
          help="填写数量只影响本次登记，不会改写历史流水。"
        >
          <input
            id="ink-issue-quantity"
            v-model="amountText"
            class="uv-input"
            :class="fieldError('amount') ? 'uv-input--invalid' : ''"
            :aria-invalid="Boolean(fieldError('amount'))"
            :aria-describedby="fieldError('amount') ? 'ink-issue-quantity-error' : 'ink-issue-quantity-help'"
            inputmode="decimal"
            autocomplete="off"
            aria-label="出库数量"
            placeholder="例如 2"
          >
        </UvFormField>
      </div>

      <p class="uv-callout uv-callout--accent" role="status" aria-live="polite">
        换算结果：{{ conversionText }}
      </p>
      <p class="uv-form-help">{{ exampleHint }}</p>
      <p v-if="estimatedAmount" class="uv-form-help">
        成本预览：{{ formatMoney(estimatedAmount) }}（数量 × SKU 单价，仅供参考，不作为入账结果）
      </p>
      <p v-else-if="props.canCostRead" class="uv-form-help">
        该 SKU 没有单价：数量照常出库，金额会显示「待核」，不会显示成 0。
      </p>
    </section>

    <section v-if="selected" class="uv-section">
      <h3 class="uv-section__title"><span class="uv-section__index">3</span>机台与用途</h3>

      <div v-if="props.machinesError" class="uv-callout uv-callout--warning" role="alert">
        <strong>机台列表读取失败</strong>：{{ props.machinesError }}
        仍可先登记为「未指定机台」，成本不会归集到具体机台。
        <div class="uv-actions" style="margin-top: 8px">
          <Button variant="outline" size="sm" type="button" @click="emit('retryMachines')">重试读取机台</Button>
        </div>
      </div>

      <div class="uv-form">
        <UvFormField
          label="机台"
          field-id="ink-issue-machine"
          :help="props.machinesLoading ? '正在读取机台列表…' : '留空表示未指定机台，成本不归集到机台。'"
        >
          <select
            id="ink-issue-machine"
            v-model="machineId"
            class="uv-input uv-select"
            :disabled="props.machinesLoading || Boolean(props.machinesError)"
            aria-label="机台"
          >
            <option value="">未指定机台</option>
            <option v-for="machine in props.machines" :key="machine.id" :value="machine.id">
              {{ machineLabel(machine) }}
            </option>
          </select>
        </UvFormField>

        <UvFormField
          label="发生日"
          required
          field-id="ink-issue-date"
          help="业务日期固定 Asia/Shanghai，不随客户端时区改变。"
        >
          <input id="ink-issue-date" v-model="occurredOn" class="uv-input" type="date" aria-label="发生日">
        </UvFormField>

        <UvFormField
          label="用途"
          required
          field-id="ink-issue-purpose"
          :error="fieldError('purpose')"
          help="写清是生产领用、打样还是退料，成本口径按用途区分。"
          :span="2"
        >
          <input
            id="ink-issue-purpose"
            v-model="purpose"
            class="uv-input"
            :class="fieldError('purpose') ? 'uv-input--invalid' : ''"
            :aria-invalid="Boolean(fieldError('purpose'))"
            aria-label="用途"
            placeholder="例如 生产领用 · UV-01 面板外壳 A"
          >
        </UvFormField>

        <UvFormField
          label="来源单号"
          field-id="ink-issue-doc"
          help="领用单 / 送货单号，留空表示没有外部单据。"
        >
          <input
            id="ink-issue-doc"
            v-model="sourceDoc"
            class="uv-input"
            aria-label="来源单号"
            placeholder="例如 DEMO-ISS-7006"
          >
        </UvFormField>

        <UvFormField
          label="经手人"
          required
          field-id="ink-issue-handler"
          :error="fieldError('handler_name')"
          help="写入流水创建人，便于追溯。"
        >
          <input
            id="ink-issue-handler"
            v-model="handlerName"
            class="uv-input"
            :class="fieldError('handler_name') ? 'uv-input--invalid' : ''"
            :aria-invalid="Boolean(fieldError('handler_name'))"
            aria-label="经手人"
            placeholder="填写领用/入库经手人姓名"
          >
        </UvFormField>
      </div>

      <p v-if="materialMismatch" class="uv-callout uv-callout--warning" role="note">
        <AlertTriangle class="inline size-3.5" aria-hidden="true" />
        {{ materialMismatch }}
      </p>

      <div v-if="isPurchase" class="uv-form" style="margin-top: 12px">
        <template v-if="props.canCostRead">
          <UvFormField
            label="入库单价（每 ml）"
            field-id="ink-purchase-cost"
            :error="fieldError('currency')"
            help="留空表示单价待核：数量照常入库，金额显示「待核」而不是 0。"
          >
            <input
              id="ink-purchase-cost"
              v-model="unitCostText"
              class="uv-input"
              inputmode="decimal"
              aria-label="入库单价"
              placeholder="例如 0.3200"
            >
          </UvFormField>

          <UvFormField label="币种" field-id="ink-purchase-currency" help="与单价一起填写；币种不同不能相加。">
            <input id="ink-purchase-currency" v-model="currency" class="uv-input" aria-label="币种" placeholder="例如 HKD">
          </UvFormField>
        </template>
        <p v-else class="uv-readonly-note" role="note">
          未授权：入库单价与金额需要 <span class="uv-mono">uv_printing:cost_read</span>，本次入库会记为成本待核。
        </p>
      </div>
    </section>

    <section v-if="!selected" class="uv-section">
      <p class="uv-callout">
        还没有选择 SKU。选定后会显示该 SKU 自己的可用量、包装容量与换算结果，再填机台与用途。
      </p>
    </section>

    <template #actions>
      <Button variant="outline" size="lg" type="button" :disabled="props.pending" @click="requestClose">
        <X class="size-4" aria-hidden="true" />
        取消
      </Button>
      <Button
        size="lg"
        class="min-h-11 w-full sm:w-auto"
        type="button"
        :disabled="!canSubmit"
        :title="props.canWrite ? '' : '缺少 uv_printing:ink_write 权限'"
        @click="submit"
      >
        <component :is="submitIcon" class="size-4" aria-hidden="true" />
        {{ submitLabel }}
      </Button>
    </template>
  </UvDrawer>
</template>

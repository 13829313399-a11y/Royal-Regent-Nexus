<script setup lang="ts">
import { computed, inject, reactive, watch } from 'vue'
import { Info } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  BusinessDate,
  UvMachine,
  UvMutationResult,
  UvProcessVersion,
  UvProduct,
  UvRateKind,
  UvRateVersion,
  UvRateVersionInput,
  UvResponse,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand } from '../composables/useUvRequest'
import { decimalCompare, money } from '../domain/decimal'
import { RATE_KIND_LABELS } from '../domain/status'
import UvDrawer from './UvDrawer.vue'
import UvFormField from './UvFormField.vue'
import UvNumber from './UvNumber.vue'

/**
 * 价规版本维护抽屉（商业执行价 / 计件工价 / 面积费率）。
 *
 * - 三种价规共用一条记录结构，但语义严格分开：计件工价与商业执行价不互相回退；
 * - 优先级：同一种价规内，精确机台覆盖 > 价组覆盖 > 标准价；
 *   同优先级同币种生效区间不得重叠，是否重叠最终由服务端判定；
 * - 服务端 409/422 区间重叠错误落到「生效起始日」字段，而不是只弹通用错误；
 * - 单价允许显式 0：0 是「零价执行」，与「没有价规」完全不同，不能用留空代替；
 * - 写入携带 operation_id 与 expected_version，成功后通知工作区刷新。
 */

const props = withDefaults(defineProps<{
  open: boolean
  /** 传入原记录为编辑，传 null 为新建。 */
  rate: UvRateVersion | null
  product: UvProduct
  processVersions: UvProcessVersion[]
  machines: UvMachine[]
  businessDate: BusinessDate
  defaultKind: UvRateKind
  canWriteCost: boolean
  canPayrollWrite: boolean
  /** 页面统一维护的优先级与回退口径说明。 */
  priorityNote: string
}>(), {
  rate: null,
})

const emit = defineEmits<{ close: []; saved: [rate: UvRateVersion] }>()

const transportRef = inject(UV_TRANSPORT_KEY)
const context = inject(UV_CONTEXT_KEY)
if (!transportRef || !context) {
  throw new Error('价规维护抽屉必须在 UV 工作区壳内使用。')
}

const CURRENCY_OPTIONS = ['HKD', 'CNY', 'USD']
const RATE_KINDS: UvRateKind[] = ['commercial', 'piece_wage', 'area']

interface RateForm {
  rate_kind: UvRateKind
  process_version_id: string
  machine_id: string
  price_group: string
  currency: string
  unit_price: string
  effective_from: string
  effective_to: string
  note: string
}

const form = reactive<RateForm>({
  rate_kind: 'commercial',
  process_version_id: '',
  machine_id: '',
  price_group: '',
  currency: 'HKD',
  unit_price: '',
  effective_from: props.businessDate,
  effective_to: '',
  note: '',
})

const fieldErrors = reactive<Record<string, string>>({})
const command = useUvCommand<UvResponse<UvMutationResult<UvRateVersion>>>()
const editing = computed(() => props.rate !== null)

let operationId: string | null = null
let operationFingerprint = ''

/** 同一份内容的重试复用同一幂等键；表单改动后重新生成，避免误命中「内容不一致」冲突。 */
function operationFor(fingerprint: string): string {
  if (!operationId || operationFingerprint !== fingerprint) {
    operationId = newOperationId()
    operationFingerprint = fingerprint
  }
  return operationId
}

function clearErrors() {
  for (const key of Object.keys(fieldErrors)) delete fieldErrors[key]
}

function reset() {
  clearErrors()
  command.clearError()
  operationId = null
  operationFingerprint = ''
  const rate = props.rate
  if (rate) {
    form.rate_kind = rate.rate_kind
    form.process_version_id = rate.process_version_id ?? ''
    form.machine_id = rate.machine_id ?? ''
    form.price_group = rate.price_group ?? ''
    form.currency = rate.currency
    form.unit_price = rate.unit_price
    form.effective_from = rate.effective_from
    form.effective_to = rate.effective_to ?? ''
    form.note = rate.note
    return
  }
  const active = props.processVersions.find((version) => version.is_active) ?? props.processVersions[0]
  form.rate_kind = props.defaultKind
  form.process_version_id = active?.id ?? ''
  form.machine_id = ''
  form.price_group = ''
  form.currency = 'HKD'
  form.unit_price = ''
  form.effective_from = props.businessDate
  form.effective_to = ''
  form.note = ''
}

watch(() => props.open, (open) => {
  if (open) reset()
})

const kindHelp = computed(() => {
  if (editing.value) return '编辑只改单价与生效区间；类型与作用域要改请新建一条，保留历史版本。'
  if (form.rate_kind === 'piece_wage') return '计件工价只用于工资；缺失时工资显示未定价，不会回退到商业执行价。'
  if (form.rate_kind === 'area') return '面积费率按 cm² 计，作为独立参考产值，不与按件产值相加。'
  return '商业执行单价用于对外产值；缺失时产值显示未定价，不显示 0。'
})

const priceHelp = computed(() => `${
  form.rate_kind === 'area' ? '按每 cm² 计的费率。' : '按件计的单价。'
}显式零价请填 0：0 记为「零价执行」，与「没有价规（未定价）」不同。`)

const permissionLabel = computed(() =>
  form.rate_kind === 'piece_wage' ? '计件工资维护权限' : '成本维护权限',
)

const allowed = computed(() =>
  form.rate_kind === 'piece_wage' ? props.canPayrollWrite : props.canWriteCost,
)

/** 无权限时按钮停用，并说明原因与后端权威性。 */
const blockedReason = computed(() => (allowed.value
  ? ''
  : `${RATE_KIND_LABELS[form.rate_kind]}属于敏感金额，保存需要「${permissionLabel.value}」。当前账号没有该权限，保存已停用；是否允许写入最终由服务端判定。`))

const priorityLabel = computed(() => {
  if (form.machine_id) return '精确机台覆盖（优先于价组覆盖与标准价）'
  if (form.price_group.trim()) return '价组覆盖（优先于标准价）'
  return '标准价（同种价规内的最低优先级）'
})

function isDecimal(value: string): boolean {
  return /^-?\d+(\.\d+)?$/.test(value.trim())
}

const pricePreview = computed(() =>
  isDecimal(form.unit_price) ? money(form.currency, form.unit_price.trim()) : null,
)

const isZeroPrice = computed(() =>
  isDecimal(form.unit_price) && decimalCompare(form.unit_price.trim(), '0') === 0,
)

function validate(): boolean {
  clearErrors()
  const price = form.unit_price.trim()
  if (!price) {
    fieldErrors.unit_price = '请填写单价；显式零价请填写 0，留空不等于零价'
  } else if (!isDecimal(price)) {
    fieldErrors.unit_price = '请填写十进制数字，不要带千分位或单位'
  } else if (decimalCompare(price, '0') < 0) {
    fieldErrors.unit_price = '单价不能为负数'
  }
  if (!form.currency) fieldErrors.currency = '请选择币种'
  if (!form.effective_from) {
    fieldErrors.effective_from = '必须指定生效起始日，生效区间是必填口径'
  }
  if (form.effective_to && form.effective_from && form.effective_to < form.effective_from) {
    fieldErrors.effective_to = '生效结束日不能早于生效起始日'
  }
  return Object.keys(fieldErrors).length === 0
}

/**
 * 区间重叠错误来自服务端（409/422）。契约字段里带 effective_from 时直接落到该字段；
 * 只有通用消息时，只要语义是生效区间冲突也落到「生效起始日」。
 */
const overlapOnEffectiveFrom = computed(() => {
  const error = command.error.value
  if (!error) return ''
  if (error.fields.effective_from) return error.fields.effective_from
  const conflict = error.status === 409 || error.status === 422
  if (conflict && /重叠|区间|生效起始日/.test(error.message)) return error.message
  return ''
})

const effectiveFromError = computed(() => fieldErrors.effective_from || overlapOnEffectiveFrom.value)

const generalError = computed(() => {
  const error = command.error.value
  if (!error) return ''
  const handledAsField = Boolean(error.fields.effective_from || overlapOnEffectiveFrom.value)
  return handledAsField ? '' : error.message
})

const generalFields = computed(() =>
  Object.entries(command.error.value?.fields ?? {}).filter(([key]) => key !== 'effective_from'),
)

function fieldError(key: string): string {
  return fieldErrors[key] ?? command.error.value?.fields[key] ?? ''
}

async function submit() {
  if (!allowed.value) return
  if (!validate()) return
  const input: UvRateVersionInput = {
    factory_id: context!.workspace.scope.value.factory_id,
    operation_id: '',
    expected_version: props.rate?.version ?? 0,
    id: props.rate?.id,
    rate_kind: form.rate_kind,
    product_id: props.product.id,
    // 编辑不改作用域：改作用域等于改写历史生效口径，必须新建一条价规。
    process_version_id: editing.value
      ? props.rate?.process_version_id ?? null
      : form.process_version_id || null,
    machine_id: editing.value ? props.rate?.machine_id ?? null : form.machine_id || null,
    price_group: editing.value
      ? props.rate?.price_group ?? null
      : form.machine_id
        ? null
        : form.price_group.trim() || null,
    currency: form.currency,
    unit_price: form.unit_price.trim(),
    effective_from: form.effective_from,
    effective_to: form.effective_to || null,
    note: form.note.trim(),
  }
  const id = operationFor(JSON.stringify(input))
  input.operation_id = id
  const result = await command.execute(id, () => transportRef!.value.saveRateVersion(input))
  if (!result) return
  operationId = null
  operationFingerprint = ''
  context!.markDirty()
  emit('saved', result.data.entity)
  emit('close')
}
</script>

<template>
  <UvDrawer
    :open="open"
    :title="editing ? `编辑${RATE_KIND_LABELS[form.rate_kind]}` : `新增${RATE_KIND_LABELS[form.rate_kind]}`"
    :subtitle="`${product.product_no} · ${product.name}`"
    size="lg"
    :busy="command.pending.value"
    close-hint="按 Esc 取消编辑"
    @close="emit('close')"
  >
    <p class="uv-callout uv-callout--accent">
      <Info class="inline size-3.5" aria-hidden="true" />
      {{ priorityNote }}
    </p>

    <div v-if="blockedReason" class="uv-callout uv-callout--warning" role="alert">
      {{ blockedReason }}
    </div>

    <div v-if="generalError" class="uv-callout uv-callout--warning" role="alert">
      <strong>保存失败：</strong>{{ generalError }}
      <ul v-if="generalFields.length" class="uv-list">
        <li v-for="[key, message] in generalFields" :key="key">
          <span class="uv-list__dot" aria-hidden="true" />
          <span>{{ key }}：{{ message }}</span>
        </li>
      </ul>
      <p class="uv-form-help">表单内容已保留，可直接修改后重试；相同内容重试使用同一幂等键，不会重复入账。</p>
    </div>

    <form class="uv-form" novalidate @submit.prevent="submit">
      <UvFormField label="价规类型" required field-id="uv-rate-kind" :help="kindHelp">
        <template #default="{ describedBy }">
          <select
            id="uv-rate-kind"
            v-model="form.rate_kind"
            class="uv-input uv-select"
            :disabled="editing"
            :aria-describedby="describedBy"
          >
            <option v-for="kind in RATE_KINDS" :key="kind" :value="kind">
              {{ RATE_KIND_LABELS[kind] }}
            </option>
          </select>
        </template>
      </UvFormField>

      <UvFormField
        label="适用产品"
        readonly
        field-id="uv-rate-product"
        help="货号是精确匹配值（保留前导零）；同名不同货号是两条独立价规，不做品名模糊匹配。"
      >
        <template #default="{ describedBy }">
          <input
            id="uv-rate-product"
            class="uv-input"
            type="text"
            readonly
            :value="`${product.product_no} · ${product.name}`"
            :aria-describedby="describedBy"
          >
        </template>
      </UvFormField>

      <UvFormField
        label="工艺版本"
        field-id="uv-rate-version"
        help="选择具体版本只覆盖该版本；留空表示该产品所有工艺版本共用这一条价规。"
      >
        <template #default="{ describedBy }">
          <select
            id="uv-rate-version"
            v-model="form.process_version_id"
            class="uv-input uv-select"
            :disabled="editing"
            :aria-describedby="describedBy"
          >
            <option value="">适用于该产品全部工艺版本</option>
            <option v-for="version in processVersions" :key="version.id" :value="version.id">
              {{ version.version_label }} · 生效 {{ version.effective_from }}{{ version.is_active ? '（当前版本）' : '' }}
            </option>
          </select>
        </template>
      </UvFormField>

      <UvFormField
        label="机台覆盖"
        field-id="uv-rate-machine"
        help="指定机台即成「精确机台覆盖」，优先于价组覆盖与标准价；选定机台后价组不再参与。"
      >
        <template #default="{ describedBy }">
          <select
            id="uv-rate-machine"
            v-model="form.machine_id"
            class="uv-input uv-select"
            :disabled="editing"
            :aria-describedby="describedBy"
          >
            <option value="">无机台覆盖（标准价或价组价）</option>
            <option v-for="machine in machines" :key="machine.id" :value="machine.id">
              {{ machine.code }} · {{ machine.name }}
            </option>
          </select>
        </template>
      </UvFormField>

      <UvFormField
        label="价组"
        field-id="uv-rate-group"
        :readonly="Boolean(form.machine_id)"
        :error="fieldError('price_group')"
        help="不指定机台时可填价组，作为「价组覆盖」；留空即标准价。"
      >
        <template #default="{ describedBy, invalid }">
          <input
            id="uv-rate-group"
            v-model="form.price_group"
            class="uv-input"
            :class="invalid ? 'uv-input--invalid' : ''"
            type="text"
            :disabled="Boolean(form.machine_id) || editing"
            placeholder="例如 A组 / 一号线"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
          >
        </template>
      </UvFormField>

      <UvFormField
        label="币种"
        required
        field-id="uv-rate-currency"
        :error="fieldError('currency')"
        help="币种是价规的一部分：缺港币价不会回退到人民币价，系统不做汇率折算。"
      >
        <template #default="{ describedBy, invalid }">
          <select
            id="uv-rate-currency"
            v-model="form.currency"
            class="uv-input uv-select"
            :class="invalid ? 'uv-input--invalid' : ''"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
          >
            <option v-for="currency in CURRENCY_OPTIONS" :key="currency" :value="currency">
              {{ currency }}
            </option>
          </select>
        </template>
      </UvFormField>

      <UvFormField
        label="单价"
        required
        field-id="uv-rate-price"
        :error="fieldError('unit_price')"
        :help="priceHelp"
      >
        <template #default="{ describedBy, invalid }">
          <input
            id="uv-rate-price"
            v-model="form.unit_price"
            class="uv-input"
            :class="invalid ? 'uv-input--invalid' : ''"
            type="number"
            inputmode="decimal"
            step="0.000001"
            min="0"
            placeholder="例如 1.000000"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
          >
        </template>
      </UvFormField>

      <UvFormField
        label="单价预览"
        readonly
        field-id="uv-rate-preview"
        help="预览按最小币种单位显示；正式入账金额由服务端按十进制计算。"
      >
        <template #default="{ describedBy }">
          <div id="uv-rate-preview" class="flex items-center gap-2" :aria-describedby="describedBy">
            <UvNumber v-if="pricePreview" :money="pricePreview" size="md" align="left" />
            <UvNumber v-else state="missing" size="md" align="left" />
            <span v-if="isZeroPrice" class="uv-form-readonly">显式零价</span>
          </div>
        </template>
      </UvFormField>

      <UvFormField
        label="生效起始日"
        required
        field-id="uv-rate-from"
        :error="effectiveFromError"
        help="同一价规类型、同一优先级、同一币种下生效区间不得重叠（含边界）。"
      >
        <template #default="{ describedBy, invalid }">
          <input
            id="uv-rate-from"
            v-model="form.effective_from"
            class="uv-input"
            :class="invalid ? 'uv-input--invalid' : ''"
            type="date"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
          >
        </template>
      </UvFormField>

      <UvFormField
        label="生效结束日"
        field-id="uv-rate-to"
        :error="fieldError('effective_to')"
        help="留空表示长期有效，直到被新的生效区间替代。"
      >
        <template #default="{ describedBy, invalid }">
          <input
            id="uv-rate-to"
            v-model="form.effective_to"
            class="uv-input"
            :class="invalid ? 'uv-input--invalid' : ''"
            type="date"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
          >
        </template>
      </UvFormField>

      <UvFormField
        label="本条约定的优先级"
        readonly
        field-id="uv-rate-priority"
        :span="2"
        :help="priorityNote"
      >
        <template #default="{ describedBy }">
          <input
            id="uv-rate-priority"
            class="uv-input"
            type="text"
            readonly
            :value="priorityLabel"
            :aria-describedby="describedBy"
          >
        </template>
      </UvFormField>

      <UvFormField label="备注" field-id="uv-rate-note" :span="3">
        <template #default="{ describedBy }">
          <textarea
            id="uv-rate-note"
            v-model="form.note"
            class="uv-input uv-textarea"
            rows="2"
            placeholder="说明这次调价的依据，例如客户确认的报价单号"
            :aria-describedby="describedBy"
          />
        </template>
      </UvFormField>
    </form>

    <template #actions>
      <Button variant="outline" type="button" :disabled="command.pending.value" @click="emit('close')">
        取消
      </Button>
      <Button
        type="button"
        :disabled="!allowed || command.pending.value"
        :title="blockedReason || undefined"
        @click="submit"
      >
        {{ command.pending.value ? '正在保存…' : editing ? '保存价规' : '新增价规' }}
      </Button>
    </template>
  </UvDrawer>
</template>

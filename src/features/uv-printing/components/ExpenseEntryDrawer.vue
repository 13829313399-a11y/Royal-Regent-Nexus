<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { TriangleAlert } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { UvExpenseCategory, UvMachine, UvMutationResult, UvExpense, UvScope } from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand, useUvRequest } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import { monthOf } from '../domain/businessTime'
import { currencyMinorUnits, decimalRound } from '../domain/decimal'
import { EXPENSE_CATEGORY_LABELS } from '../domain/status'
import { readAllPages } from '../transport/pagination'
import UvDrawer from './UvDrawer.vue'
import UvFormField from './UvFormField.vue'

/**
 * 费用录入抽屉。
 *
 * - 字段：类别 / 发生日 / 归属期 / 金额 / 币种 / 机台（可选）/ 凭证 / 备注；
 * - 归属期可以与发生日不同（例如 9 月缴纳 10 月房租），分摊按归属期；
 * - **去重口径必须写在界面上**：采购油墨、油墨出库与人工录入「油墨费用」按来源去重，
 *   菜品类既有流水又有手工录入时必须选择一种口径，不能重复计入结余；
 * - 写入需要 uv_printing:cost_write，携带 operation_id 幂等键，成功后刷新页面数据。
 */

const props = withDefaults(defineProps<{
  open: boolean
  scope: UvScope
  currency: string
  /** 默认归属期，通常来自页面当前月份。 */
  defaultPeriod: string
  canWriteCost: boolean
}>(), {})

const emit = defineEmits<{ close: []; saved: [] }>()

const ctx = inject(UV_CONTEXT_KEY)!
const transport = inject(UV_TRANSPORT_KEY)!
const toast = useUvToast()
const command = useUvCommand<UvMutationResult<UvExpense>>()

const machineRequest = useUvRequest<{ items: UvMachine[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.machines(nextScope, nextSignal), props.scope, signal).then((response) => response.data),
  { watchSource: () => [props.open, ctx.revision.value] },
)

const category = ref<UvExpenseCategory>('material')
const occurredOn = ref(props.scope.business_date ?? '')
const period = ref(props.defaultPeriod)
const amount = ref('')
const currency = ref(props.currency)
const machineId = ref('')
const evidence = ref('')
const note = ref('')
const errors = ref<Record<string, string>>({})

const CATEGORY_ORDER: UvExpenseCategory[] = [
  'material', 'tooling', 'sundry', 'maintenance', 'processing', 'night_subsidy',
  'rent', 'utilities', 'management_wage', 'equipment', 'ink', 'recoverable_wage', 'recoverable_paint',
]

/** 已经由墨水流水入账的类别：手工录入必须选择口径，不能重复计入。 */
const INK_SOURCED: UvExpenseCategory[] = ['ink']

watch(() => props.open, (open) => {
  if (!open) return
  category.value = 'material'
  occurredOn.value = props.scope.business_date ?? ''
  period.value = props.defaultPeriod || monthOf(props.scope.business_date ?? '')
  amount.value = ''
  currency.value = props.currency
  machineId.value = ''
  evidence.value = ''
  note.value = ''
  errors.value = {}
  command.clearError()
})

const isInkCategory = computed(() => INK_SOURCED.includes(category.value))
const machines = computed(() => machineRequest.data.value?.items ?? [])
const categoryHint = computed(() => {
  if (isInkCategory.value) {
    return '「油墨」类别用于确实无法通过墨水流水入账的零星费用；采购入库与领用出库已在墨水账本记成本，这里再录一次就会重复计入结余。'
  }
  if (category.value === 'equipment') {
    return '设备投资按整笔扣减计入旧管理口径结余，因此报表结果不得标成经营毛利，并会同时显示「排除设备投资的经营贡献」。'
  }
  if (category.value === 'recoverable_wage' || category.value === 'recoverable_paint') {
    return '可回收项在结余中作为加项；它是经营调整项，不等同员工实际扣薪或客户退款。'
  }
  return '费用发生在哪一天填「发生日」，计入哪一期填「归属期」；跨月缴纳时两者可以不同。'
})

function validate(): boolean {
  const next: Record<string, string> = {}
  if (!occurredOn.value) next.occurred_on = '必须填写发生日，报表按发生日进入筛选范围'
  if (!/^\d{4}-\d{2}$/.test(period.value)) next.period = '归属期格式必须是 YYYY-MM，分摊按归属期'
  if (!/^\d+(\.\d+)?$/.test(amount.value.trim())) next.amount = '金额必须是数字，最多到最小币种单位'
  else if (Number(amount.value) <= 0) next.amount = '金额必须大于 0；本期不发生的费用请直接不录'
  if (!currency.value.trim()) next.currency = '必须选择币种，不同币种不会相加'
  if (isInkCategory.value && !note.value.trim()) {
    next.note = '油墨费用必须写清来源与去重口径，说明为何不在墨水流水中体现'
  }
  errors.value = next
  return Object.keys(next).length === 0
}

async function submit() {
  if (!props.canWriteCost) {
    toast.push({
      message: '没有费用写入权限',
      detail: '需要 uv_printing:cost_write；后端是权威判定，这里不做「隐藏按钮」式权限控制。',
      tone: 'red',
      retryable: false,
    })
    return
  }
  if (!validate()) {
    toast.push({ message: '费用录入未通过校验', detail: '按字段提示修正后再提交。', tone: 'red', retryable: false })
    return
  }

  const operationId = newOperationId()
  const result = await command.execute(operationId, () => transport.value.createExpense({
    factory_id: props.scope.factory_id,
    operation_id: operationId,
    expected_version: 0,
    category: category.value,
    occurred_on: occurredOn.value,
    period: period.value,
    currency: currency.value.trim().toUpperCase(),
    amount: decimalRound(amount.value.trim(), currencyMinorUnits(currency.value.trim().toUpperCase())),
    machine_id: machineId.value || null,
    evidence: evidence.value,
    note: note.value,
  }).then((response) => response.data))

  if (!result) {
    toast.push({
      message: '费用保存失败',
      detail: command.error.value?.message ?? '提交没有返回结果，表单内容已保留，可重试。',
      tone: 'red',
      retryable: true,
    })
    return
  }

  toast.push({
    message: `${EXPENSE_CATEGORY_LABELS[category.value]}费用已保存`,
    detail: `发生日 ${occurredOn.value} · 归属期 ${period.value} · 记录 ${result.entity.id}${result.replayed ? '（幂等重放，未重复入账）' : ''}`,
    tone: 'green',
    retryable: false,
  })
  ctx.markDirty()
  emit('saved')
}

const busy = computed(() => command.pending.value)
</script>

<template>
  <UvDrawer
    :open="open"
    title="费用录入"
    subtitle="发生日进入报表筛选范围，归属期决定分摊与月度归集；两者可以不同。"
    size="md"
    :busy="busy"
    @close="emit('close')"
  >
    <div class="uv-form">
      <UvFormField field-id="uv-expense-category" label="费用类别" required :span="2">
        <template #default="{ describedBy }">
          <select
            id="uv-expense-category"
            v-model="category"
            class="uv-input uv-select"
            :aria-describedby="describedBy"
          >
            <option v-for="key in CATEGORY_ORDER" :key="key" :value="key">
              {{ EXPENSE_CATEGORY_LABELS[key] }}
            </option>
          </select>
        </template>
      </UvFormField>

      <UvFormField field-id="uv-expense-occurred" label="发生日" required :error="errors.occurred_on">
        <template #default="{ describedBy, invalid }">
          <input
            id="uv-expense-occurred"
            v-model="occurredOn"
            class="uv-input"
            :class="invalid ? 'uv-input--invalid' : ''"
            type="date"
            :aria-describedby="describedBy"
          >
        </template>
      </UvFormField>

      <UvFormField
        field-id="uv-expense-period"
        label="归属期"
        required
        :error="errors.period"
        help="YYYY-MM；月度分摊与月报按归属期归集。"
      >
        <template #default="{ describedBy, invalid }">
          <input
            id="uv-expense-period"
            v-model="period"
            class="uv-input"
            :class="invalid ? 'uv-input--invalid' : ''"
            type="month"
            :aria-describedby="describedBy"
          >
        </template>
      </UvFormField>

      <UvFormField field-id="uv-expense-amount" label="金额" required :error="errors.amount">
        <template #default="{ describedBy, invalid }">
          <input
            id="uv-expense-amount"
            v-model="amount"
            class="uv-input"
            :class="invalid ? 'uv-input--invalid' : ''"
            type="text"
            inputmode="decimal"
            placeholder="例如 1200.00"
            :aria-describedby="describedBy"
          >
        </template>
      </UvFormField>

      <UvFormField field-id="uv-expense-currency" label="币种" required :error="errors.currency">
        <template #default="{ describedBy }">
          <select
            id="uv-expense-currency"
            v-model="currency"
            class="uv-input"
            :aria-describedby="describedBy"
          >
            <option value="">请选择币种</option>
            <option value="CNY">CNY 人民币</option>
            <option value="HKD">HKD 港币</option>
            <option value="USD">USD 美元</option>
            <option value="JPY">JPY 日元</option>
            <option value="EUR">EUR 欧元</option>
            <option value="GBP">GBP 英镑</option>
          </select>
        </template>
      </UvFormField>

      <UvFormField
        field-id="uv-expense-machine"
        label="机台（可选）"
        help="只有确实归属单台机台的费用才选机台；公共费用留空。"
        :span="2"
      >
        <template #default="{ describedBy }">
          <select
            id="uv-expense-machine"
            v-model="machineId"
            class="uv-input uv-select"
            :aria-describedby="describedBy"
          >
            <option value="">全厂共用（不指定机台）</option>
            <option v-for="machine in machines" :key="machine.id" :value="machine.id">
              {{ machine.code }} · {{ machine.name }}
            </option>
          </select>
        </template>
      </UvFormField>

      <UvFormField
        field-id="uv-expense-evidence"
        label="凭证"
        help="发票号、合同号或送货单号；没有凭证的费用仍需写明来源。"
        :span="3"
      >
        <template #default="{ describedBy }">
          <input
            id="uv-expense-evidence"
            v-model="evidence"
            class="uv-input"
            type="text"
            placeholder="例如 发票 DEMO-2026-0901"
            :aria-describedby="describedBy"
          >
        </template>
      </UvFormField>

      <UvFormField
        field-id="uv-expense-note"
        label="备注"
        :error="errors.note"
        :help="categoryHint"
        :span="3"
      >
        <template #default="{ describedBy, invalid }">
          <textarea
            id="uv-expense-note"
            v-model="note"
            class="uv-input uv-textarea"
            :class="invalid ? 'uv-input--invalid' : ''"
            :aria-describedby="describedBy"
            placeholder="说明业务原因、去重口径与归属判断依据"
          />
        </template>
      </UvFormField>
    </div>

    <div class="uv-callout uv-callout--warning" style="margin-top: 12px">
      <p>
        <TriangleAlert class="inline size-3.5" aria-hidden="true" />
        <strong>去重口径（必须选择一种，不能重复计入）</strong>
      </p>
      <ul class="uv-list" style="margin-top: 6px">
        <li><span class="uv-list__dot" aria-hidden="true" /><span>采购油墨：在墨水账本「采购入库」记成本，结余的油墨领用成本按出库流水计算，不再另录「油墨」费用。</span></li>
        <li><span class="uv-list__dot" aria-hidden="true" /><span>油墨出库：按领用流水金额进入油墨领用成本，缺单价时显示「成本待核」而不是 0。</span></li>
        <li><span class="uv-list__dot" aria-hidden="true" /><span>人工录入「油墨费用」：仅用于无法通过流水入账的零星用量，必须在备注里写明为何不在墨水账本体现。</span></li>
        <li><span class="uv-list__dot" aria-hidden="true" /><span>同一笔支出已在上游模块入账时，本模块只做引用，不重复录入；确需冲销请用冲销而不是再录一笔。</span></li>
      </ul>
    </div>

    <div v-if="command.error.value" class="uv-state uv-state--error" role="alert" style="margin-top: 10px">
      <div class="uv-state__icon uv-state__icon--error" aria-hidden="true">
        <TriangleAlert class="size-5" />
      </div>
      <p class="uv-state__title">提交失败：{{ command.error.value.message }}</p>
      <p class="uv-state__hint">表单内容已保留；使用同一 operation_id 重试不会重复入账。</p>
    </div>

    <template #actions>
      <Button variant="outline" type="button" :disabled="busy" @click="emit('close')">取消</Button>
      <Button type="button" :disabled="busy || !canWriteCost" @click="submit">
        {{ busy ? '正在提交…' : '保存费用' }}
      </Button>
    </template>
  </UvDrawer>
</template>

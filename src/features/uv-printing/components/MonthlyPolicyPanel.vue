<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { Ban, CalendarDays, RefreshCw, Save, TriangleAlert } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { BusinessDate, UvMonthlyPolicy, UvMutationResult, UvScope } from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand, useUvRequest } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import { daysInMonth, monthOf, weekdayLabel } from '../domain/businessTime'
import { decimalCompare, decimalRound, currencyMinorUnits, formatMoney, trimTrailingZeros } from '../domain/decimal'
import { allocationMethodLabel, prorationTotals } from '../domain/reporting'
import UvConfirmDialog from './UvConfirmDialog.vue'
import UvFormField from './UvFormField.vue'
import UvStateBlock from './UvStateBlock.vue'
import UvStatusPill from './UvStatusPill.vue'

/**
 * 分摊配置面板（经营报表页内，不新开一级菜单）。
 *
 * - 工作日集合必须由用户明确选择，不采用 26/26/21 之类的默认值当制度；
 * - 房租 / 水电 / 管理人员工资整月金额按所选方法分摊；
 * - 实时预览必须证明 **整月分摊合计等于配置额**（舍入余数按确定日期分配），
 *   不等于配置额时不允许保存；
 * - 保存需要 uv_printing:cost_write 与 operation_id；已结算月份修改参数必须填写修订说明。
 */

const props = withDefaults(defineProps<{
  month: string
  scope: UvScope
  currency: string
  canReadCost: boolean
  canWriteCost: boolean
  /** 该月是否已经结算（关账）；已结算时修改参数必须填写修订说明。 */
  settled: boolean
  /** 已结算状态未知时显式说明，不假装知道。 */
  settledKnown: boolean
}>(), {})

const emit = defineEmits<{ saved: []; dirty: [] }>()

const ctx = inject(UV_CONTEXT_KEY)!
const transport = inject(UV_TRANSPORT_KEY)!
const toast = useUvToast()
const command = useUvCommand<UvMutationResult<UvMonthlyPolicy>>()

const policyRequest = useUvRequest<UvMonthlyPolicy | null>(
  (signal) => transport.value.monthlyPolicy(props.month, props.scope, signal).then((response) => response.data),
  { watchSource: () => [props.month, props.scope.business_date, ctx.revision.value] },
)

const policy = computed(() => policyRequest.data.value)
const days = computed(() => daysInMonth(props.month))

/* ---------------- 表单草稿 ---------------- */

const workingDays = ref<BusinessDate[]>([])
const allocationMethod = ref<UvMonthlyPolicy['allocation_method']>('working_days')
const rent = ref('')
const utilities = ref('')
const managementWage = ref('')
const note = ref('')
const revisionNote = ref('')
const policyVersion = ref(0)
const confirmOpen = ref(false)
const fieldErrors = ref<Record<string, string>>({})

function amountOf(policyValue: UvMonthlyPolicy | null, key: 'rent' | 'utilities' | 'management_wage'): string {
  const value = policyValue?.[key]
  if (!value || value.currency !== props.currency) return ''
  return trimTrailingZeros(value.amount)
}

function syncFromPolicy(value: UvMonthlyPolicy | null) {
  workingDays.value = value ? [...value.working_days].sort() : []
  allocationMethod.value = value?.allocation_method ?? 'working_days'
  rent.value = amountOf(value, 'rent')
  utilities.value = amountOf(value, 'utilities')
  managementWage.value = amountOf(value, 'management_wage')
  note.value = value?.note ?? ''
  policyVersion.value = value?.version ?? 0
  revisionNote.value = ''
  fieldErrors.value = {}
}

watch(policy, (value) => syncFromPolicy(value ?? null), { immediate: true })

const changed = computed(() => {
  const current = policy.value
  if (!current) return true
  return (
    workingDays.value.join(',') !== [...current.working_days].sort().join(',')
    || allocationMethod.value !== current.allocation_method
    || rent.value !== amountOf(current, 'rent')
    || utilities.value !== amountOf(current, 'utilities')
    || managementWage.value !== amountOf(current, 'management_wage')
    || note.value !== current.note
  )
})

const requiresRevisionNote = computed(() => {
  // 已关账标记未知时，只要该月已有配置版本且内容有变化，就要求填写修订说明。
  const settled = props.settledKnown ? props.settled : policyVersion.value > 0
  return settled && changed.value
})

/* ---------------- 分摊预览 ---------------- */

interface AllocationPreview {
  key: 'rent' | 'utilities' | 'management_wage'
  label: string
  amount: string
  total: string
  matches: boolean
  days: Array<{ business_date: string; amount: string }>
  remainderDays: string[]
}

function buildPreview(key: AllocationPreview['key'], label: string, amount: string): AllocationPreview | null {
  if (!amount.trim() || Number(amount) <= 0) return null
  const total = decimalRound(amount, currencyMinorUnits(props.currency))
  const result = prorationTotals(total, workingDays.value, props.currency, allocationMethod.value)
  const base = result.days.length ? result.days[0]!.amount : '0'
  return {
    key,
    label,
    amount: total,
    total: result.total,
    matches: result.matches,
    days: result.days,
    remainderDays: result.days.filter((day) => day.amount !== base).map((day) => day.business_date),
  }
}

const previews = computed<AllocationPreview[]>(() =>
  [
    buildPreview('rent', '房租', rent.value),
    buildPreview('utilities', '水电', utilities.value),
    buildPreview('management_wage', '管理人员工资', managementWage.value),
  ].filter((item): item is AllocationPreview => item !== null),
)

const allMatch = computed(() => previews.value.every((item) => item.matches))
const perDayTotals = computed(() => {
  const map = new Map<string, string>()
  for (const preview of previews.value) {
    for (const day of preview.days) {
      const existing = map.get(day.business_date) ?? '0'
      map.set(day.business_date, String(Number(existing) + Number(day.amount)))
    }
  }
  return [...map.entries()]
    .sort((left, right) => left[0].localeCompare(right[0]))
    .map(([businessDate, amount]) => ({ business_date: businessDate, amount }))
})

/* ---------------- 校验与保存 ---------------- */

function validate(): boolean {
  const errors: Record<string, string> = {}
  if (!props.currency) errors.currency = '请先在经营报表顶部选择币种，系统不会猜测默认币种'
  if (!workingDays.value.length) errors.working_days = '工作日集合不能为空，否则分摊合计无法等于配置额'
  for (const preview of previews.value) {
    if (!preview.matches) {
      errors[preview.key] = `${preview.label} 分摊合计 ${preview.total} 与配置额 ${preview.amount} 不一致，不允许保存`
    }
  }
  if (requiresRevisionNote.value && !revisionNote.value.trim()) {
    errors.revision = '该月已结算，修改分摊参数必须填写修订说明'
  }
  fieldErrors.value = errors
  return Object.keys(errors).length === 0
}

function toggleDay(day: BusinessDate) {
  const next = new Set(workingDays.value)
  if (next.has(day)) next.delete(day)
  else next.add(day)
  workingDays.value = [...next].sort()
  emit('dirty')
}

function selectWeekdaysOnly() {
  workingDays.value = days.value.filter((day) => weekdayLabel(day) !== '周日')
  emit('dirty')
}

function clearDays() {
  workingDays.value = []
  emit('dirty')
}

function submit() {
  if (!props.canWriteCost) {
    toast.push({
      message: '没有分摊配置写入权限',
      detail: '需要 uv_printing:cost_write；后端是权威判定，这里不做「隐藏按钮」式权限控制。',
      tone: 'red',
      retryable: false,
    })
    return
  }
  if (!validate()) {
    toast.push({ message: '分摊参数未通过校验', detail: '按字段提示修正后再保存。', tone: 'red', retryable: false })
    return
  }
  if (requiresRevisionNote.value) {
    confirmOpen.value = true
    return
  }
  void save()
}

async function save() {
  confirmOpen.value = false
  const money = (value: string) => (value.trim() && Number(value) > 0
    ? { currency: props.currency, amount: decimalRound(value, currencyMinorUnits(props.currency)) }
    : null)

  // operation_id 必须在发起时确定一次，重试沿用同一个键才不会重复入账。
  const operationId = newOperationId()
  const result = await command.execute(operationId, () => transport.value.saveMonthlyPolicy({
    factory_id: props.scope.factory_id,
    operation_id: operationId,
    expected_version: policyVersion.value,
    month: props.month,
    working_days: [...workingDays.value].sort(),
    allocation_method: allocationMethod.value,
    rent: money(rent.value),
    utilities: money(utilities.value),
    management_wage: money(managementWage.value),
    note: revisionNote.value.trim()
      ? `${note.value}${note.value ? '；' : ''}修订说明：${revisionNote.value.trim()}`
      : note.value,
  }).then((response) => response.data))

  if (!result) {
    const error = command.error.value
    toast.push({
      message: '分摊配置保存失败',
      detail: error?.message ?? '提交没有返回结果，表单内容已保留，可重试。',
      tone: 'red',
      retryable: true,
    })
    return
  }

  toast.push({
    message: result.entity.month ? `${result.entity.month} 分摊配置已保存` : '分摊配置已保存',
    detail: `工作日 ${result.entity.working_days.length} 天 · ${allocationMethodLabel(result.entity.allocation_method)} · 版本 ${result.entity.version}${result.replayed ? '（幂等重放）' : ''}`,
    tone: 'green',
    retryable: false,
  })
  ctx.markDirty()
  emit('saved')
  await policyRequest.run()
}

const settlementsNote = computed(() => {
  if (!props.settledKnown) {
    return '关账状态未由接口下发：保存已结算月份的参数时请主动填写修订说明，并确认该月报工不会因此被追溯重算。'
  }
  return props.settled
    ? '该月已结算：修改分摊参数会写入修订说明，已结算月份的报表金额不会自动重算。'
    : '该月未结算：参数修改会立即影响本月暂算结果，最终以关账结果为准。'
})

const previewToleranceOk = computed(() => allMatch.value)

/** 确认框里的原因需要写回 ref，模板里直接赋值只会改到解包后的值。 */
function confirmSettledRevision(reason: string) {
  revisionNote.value = reason
  void save()
}
</script>

<template>
  <section class="uv-panel" aria-label="分摊配置">
    <div class="uv-panel__head">
      <div>
        <h2 class="uv-panel__title">分摊配置 · {{ month }}</h2>
        <p class="uv-panel__subtitle">
          房租、水电与管理人员工资是整月固定费用，按所选工作日集合（或自然日）分摊到每一天；
          整月分摊合计必须等于配置额，舍入余数按确定日期补最小币种单位。
        </p>
      </div>
      <div class="uv-actions">
        <UvStatusPill
          v-if="policy"
          :status="{ label: `已配置 · 版本 ${policy.version}`, tone: 'green' }"
          compact
        />
        <UvStatusPill v-else :status="{ label: '尚未配置', tone: 'amber' }" compact />
      </div>
    </div>

    <div class="uv-panel__body">
      <p v-if="fieldErrors.currency" class="uv-field__error">{{ fieldErrors.currency }}</p>
      <div v-if="!canReadCost" class="uv-state uv-state--warning" role="alert">
        <div class="uv-state__icon uv-state__icon--warning" aria-hidden="true">
          <Ban class="size-5" />
        </div>
        <p class="uv-state__title">未授权：分摊金额</p>
        <p class="uv-state__message">
          当前账号没有 uv_printing:cost_read，房租、水电与管理工资金额不会下发到前端。
          这里不显示金额，也不用隐藏字段代替权限控制；后端是权威判定。
        </p>
      </div>

      <UvStateBlock
        v-else-if="policyRequest.error.value"
        state="error"
        subject="分摊配置"
        :message="policyRequest.error.value.message"
        :detail="`${month} · ${policyRequest.error.value.code}`"
        retryable
        @retry="policyRequest.run"
      />

      <UvStateBlock
        v-else-if="policyRequest.loading.value && !policyRequest.settled.value"
        state="loading"
        subject="分摊配置"
        compact
      />

      <template v-else>
        <p v-if="!policy" class="uv-callout uv-callout--warning">
          {{ month }} 还没有分摊配置：房租、水电与管理人员工资未分摊，本月结余按已填写项目暂算。
          工作日集合由你明确选择，系统不会套用默认天数作为制度。
        </p>

        <div class="uv-form">
          <UvFormField
            field-id="uv-policy-working-days"
            label="工作日集合"
            required
            :error="fieldErrors.working_days"
            :help="`已选 ${workingDays.length} / ${days.length} 天；周日默认不选，但可以手动勾选计划外生产日。`"
            :span="3"
          >
            <template #default>
              <div class="uv-policy-day" role="group" aria-label="选择该月的工作日">
                <label
                  v-for="day in days"
                  :key="day"
                  class="uv-check"
                  :class="workingDays.includes(day) ? 'uv-check--on' : ''"
                >
                  <input
                    type="checkbox"
                    :checked="workingDays.includes(day)"
                    :disabled="!canWriteCost"
                    @change="toggleDay(day)"
                  >
                  <span>{{ day.slice(8) }} {{ weekdayLabel(day) }}</span>
                </label>
              </div>
              <div class="uv-actions" style="margin-top: 8px">
                <Button variant="outline" size="sm" type="button" :disabled="!canWriteCost" @click="selectWeekdaysOnly">
                  <CalendarDays class="size-3.5" aria-hidden="true" />
                  选择周一至周六
                </Button>
                <Button variant="ghost" size="sm" type="button" :disabled="!canWriteCost" @click="clearDays">
                  清空
                </Button>
              </div>
            </template>
          </UvFormField>

          <UvFormField
            field-id="uv-policy-method"
            label="分摊方法"
            help="按选择的工作日集合：只在勾选日期分摊；按自然日：整月每一天等分。"
          >
            <template #default="{ describedBy }">
              <select
                id="uv-policy-method"
                v-model="allocationMethod"
                class="uv-input uv-select"
                :disabled="!canWriteCost"
                :aria-describedby="describedBy"
                @change="emit('dirty')"
              >
                <option value="working_days">按选择的工作日集合</option>
                <option value="calendar_days">按自然日</option>
              </select>
            </template>
          </UvFormField>

          <UvFormField
            field-id="uv-policy-rent"
            label="房租（整月）"
            :error="fieldErrors.rent"
            :help="`单位为 ${currency}；留空表示本期不配置，不会被当作 0 计入结余。`"
          >
            <template #default="{ describedBy, invalid }">
              <input
                id="uv-policy-rent"
                v-model="rent"
                class="uv-input"
                :class="invalid ? 'uv-input--invalid' : ''"
                type="text"
                inputmode="decimal"
                :disabled="!canWriteCost"
                :aria-describedby="describedBy"
                placeholder="例如 3900"
                @input="emit('dirty')"
              >
            </template>
          </UvFormField>

          <UvFormField
            field-id="uv-policy-utilities"
            label="水电（整月）"
            :error="fieldErrors.utilities"
            :help="`单位为 ${currency}；与房租分别配置，各自校验分摊合计。`"
          >
            <template #default="{ describedBy, invalid }">
              <input
                id="uv-policy-utilities"
                v-model="utilities"
                class="uv-input"
                :class="invalid ? 'uv-input--invalid' : ''"
                type="text"
                inputmode="decimal"
                :disabled="!canWriteCost"
                :aria-describedby="describedBy"
                placeholder="例如 1560"
                @input="emit('dirty')"
              >
            </template>
          </UvFormField>

          <UvFormField
            field-id="uv-policy-management"
            label="管理人员工资（整月）"
            :error="fieldErrors.management_wage"
            :help="`单位为 ${currency}；这是管理人员工资，与现场员工计件工资分开。`"
          >
            <template #default="{ describedBy, invalid }">
              <input
                id="uv-policy-management"
                v-model="managementWage"
                class="uv-input"
                :class="invalid ? 'uv-input--invalid' : ''"
                type="text"
                inputmode="decimal"
                :disabled="!canWriteCost"
                :aria-describedby="describedBy"
                placeholder="例如 4200"
                @input="emit('dirty')"
              >
            </template>
          </UvFormField>

          <UvFormField field-id="uv-policy-note" label="参数说明" :span="3">
            <template #default="{ describedBy }">
              <textarea
                id="uv-policy-note"
                v-model="note"
                class="uv-input uv-textarea"
                :disabled="!canWriteCost"
                :aria-describedby="describedBy"
                placeholder="说明工作日集合与金额来源，例如排班表版本或租赁合同"
                @input="emit('dirty')"
              />
            </template>
          </UvFormField>

          <UvFormField
            v-if="requiresRevisionNote"
            field-id="uv-policy-revision"
            label="修订说明"
            required
            :error="fieldErrors.revision"
            :help="settlementsNote"
            :span="3"
          >
            <template #default="{ describedBy, invalid }">
              <textarea
                id="uv-policy-revision"
                v-model="revisionNote"
                class="uv-input uv-textarea"
                :class="invalid ? 'uv-input--invalid' : ''"
                :aria-describedby="describedBy"
                placeholder="说明为什么在已结算月份修改分摊参数，以及是否需要重出报表"
              />
            </template>
          </UvFormField>
        </div>

        <div class="uv-section">
          <h3 class="uv-section__title">分摊预览（必须证明合计等于配置额）</h3>

          <div v-if="!previews.length" class="uv-callout">
            还没有填写整月金额：填写房租、水电或管理人员工资后，这里会逐日列出分摊额与合计。
          </div>

          <div v-else class="uv-policy-preview">
            <article v-for="preview in previews" :key="preview.key" class="uv-drill-item">
              <div class="uv-drill-item__head">
                <span class="uv-drill-item__title">{{ preview.label }}</span>
                <span class="uv-actions">
                  <UvStatusPill
                    :status="preview.matches
                      ? { label: `合计 ${preview.total} = 配置额`, tone: 'green' }
                      : { label: `合计 ${preview.total} ≠ 配置额 ${preview.amount}`, tone: 'red' }"
                    compact
                  />
                </span>
              </div>
              <div class="uv-drill-meta">
                <span>配置额 <strong>{{ formatMoney({ currency, amount: preview.amount }) }}</strong></span>
                <span>分摊天数 <strong>{{ preview.days.length }}</strong> 天</span>
                <span>每份基准 <strong>{{ preview.days.length ? formatMoney({ currency, amount: preview.days[0]!.amount }) : '—' }}</strong></span>
                <span>余数补齐日
                  <strong>{{ preview.remainderDays.length ? preview.remainderDays.join('、') : '无需补齐' }}</strong>
                </span>
              </div>
              <div class="uv-policy-day">
                <span v-for="item in preview.days" :key="item.business_date">
                  {{ item.business_date.slice(8) }} {{ item.amount }}
                </span>
              </div>
            </article>

            <div class="uv-callout" :class="previewToleranceOk ? 'uv-callout--accent' : 'uv-callout--warning'">
              <p>
                <strong>{{ previewToleranceOk ? '校验通过' : '校验未通过' }}</strong>
                ：{{ allocationMethodLabel(allocationMethod) }}，共 {{ workingDays.length }} 个分摊日；
                每项分摊合计必须等于配置额，否则保存会被拒绝。
              </p>
              <p v-if="perDayTotals.length" style="margin-top: 6px">
                每日固定费用合计：{{ perDayTotals.map((item) => `${item.business_date} ${item.amount}`).join(' · ') }}
              </p>
            </div>
          </div>
        </div>

        <div class="uv-actions uv-actions--end uv-policy-actions" style="margin-top: 14px">
          <span v-if="!canWriteCost" class="uv-readonly-note">
            只读：没有 uv_printing:cost_write，无法保存分摊配置
          </span>
          <span v-else-if="changed && requiresRevisionNote" class="uv-field__hint">
            有未保存的修改：该月已有配置版本，保存需要修订说明
          </span>
          <span v-else-if="changed" class="uv-field__hint">有未保存的修改</span>
          <span v-else class="uv-field__hint">当前内容与已保存版本一致</span>
          <Button
            variant="outline"
            size="sm"
            type="button"
            :disabled="policyRequest.loading.value"
            @click="policyRequest.run"
          >
            <RefreshCw class="size-3.5" aria-hidden="true" />
            重新读取
          </Button>
          <Button
            type="button"
            size="sm"
            :disabled="!canWriteCost || command.pending.value"
            @click="submit"
          >
            <Save class="size-3.5" aria-hidden="true" />
            {{ command.pending.value ? '正在保存…' : '保存分摊配置' }}
          </Button>
        </div>

        <div v-if="command.error.value" class="uv-state uv-state--error" role="alert" style="margin-top: 10px">
          <div class="uv-state__icon uv-state__icon--error" aria-hidden="true">
            <TriangleAlert class="size-5" />
          </div>
          <p class="uv-state__title">保存失败：{{ command.error.value.message }}</p>
          <p class="uv-state__hint">表单内容已保留，可以修正后重试；同一 operation_id 重试不会重复入账。</p>
        </div>

        <p class="uv-section" style="margin-top: 14px">{{ settlementsNote }}</p>

        <div v-if="previews.some((preview) => decimalCompare(preview.total, preview.amount) !== 0)" class="uv-callout uv-callout--warning">
          分摊合计与配置额不一致时不允许保存；请检查工作日集合是否为空，或改用自然日分摊。
        </div>
      </template>
    </div>

    <UvConfirmDialog
      :open="confirmOpen"
      :title="`修订 ${month} 分摊参数`"
      :impacts="[
        `该月已结算（版本 ${policyVersion}）：修改工作日集合或金额会写入修订说明，并保留原版本记录`,
        '已结算月份的报表金额不会自动重算，需要另行重出报表',
        '本次保存使用 operation_id 幂等键，重复提交不会产生第二份配置',
      ]"
      confirm-label="确认修订并保存"
      require-reason
      reason-label="修订说明"
      reason-placeholder="说明修改原因与是否需要重出报表"
      :busy="command.pending.value"
      @confirm="confirmSettledRevision"
      @cancel="confirmOpen = false"
    />
  </section>
</template>

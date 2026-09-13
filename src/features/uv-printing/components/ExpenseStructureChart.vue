<script setup lang="ts">
import { computed } from 'vue'
import { Ban } from '@lucide/vue'
import type { UvExpense } from '../contracts'
import {
  decimalAdd,
  decimalCompare,
  decimalIsZero,
  decimalToNumber,
  formatDecimal,
  formatMoney,
  trimTrailingZeros,
} from '../domain/decimal'
import { expenseStructure } from '../domain/reporting'
import { EXPENSE_CATEGORY_LABELS } from '../domain/status'
import UvNumber from './UvNumber.vue'

/**
 * 费用构成：按金额排序的水平条 + **同口径数据表**。
 *
 * - 只用一维水平条（`.uv-bars` / `.uv-bar-row*`），不用 3D 饼图，也不用无依据的双轴；
 * - 条长只表达相对量级，金额、占比、来源与缺失说明全部落在同口径数据表里，
 *   不存在「只有 tooltip 才有」的信息；
 * - **不同币种不折成一个金额**：构成按币种分别计算，其他币种单列并标「待核」；
 * - 缺成本的项显示「待核」，不显示 0。
 */

const props = withDefaults(defineProps<{
  /** 与页面筛选范围完全一致的原始费用记录。 */
  expenses: UvExpense[]
  /** 当前展示币种；构成只在这个币种内计算。 */
  currency: string
  /** 占比分母（通常为同期产值）；缺失时不给占比。 */
  base: string | null
  /** 只有具备成本权限时才渲染金额。 */
  canReadCost: boolean
  /** 期间标签，例如 2026-09 或 2026-09-13。 */
  periodLabel: string
  /** 数据截止时间。 */
  asOf: string
  /** 加载/错误/空状态由外层 UvStateBlock 承担，这里只决定是否渲染。 */
  ready: boolean
}>(), {})

const emit = defineEmits<{ drill: [category: string, label: string] }>()

/** 当前币种的构成（同口径数据表的唯一数据源）。 */
const rows = computed(() =>
  expenseStructure(props.currency, props.expenses, EXPENSE_CATEGORY_LABELS, props.base),
)

const maxAmount = computed(() =>
  Math.max(1, ...rows.value.map((row) => Math.abs(decimalToNumber(row.amount?.amount ?? '0')))),
)

/** 其他币种合计：只列金额，不折汇、不与本币相加。 */
const otherCurrencies = computed(() => {
  const totals = new Map<string, string>()
  for (const expense of props.expenses) {
    if (expense.amount.currency === props.currency) continue
    totals.set(
      expense.amount.currency,
      decimalAdd(totals.get(expense.amount.currency) ?? '0', expense.amount.amount),
    )
  }
  return [...totals.entries()]
    .map(([currency, amount]) => ({
      currency,
      amount,
      recordCount: props.expenses.filter((expense) => expense.amount.currency === currency).length,
    }))
    .sort((left, right) => decimalCompare(right.amount, left.amount))
})

const currencyTotal = computed(() =>
  rows.value.reduce((total, row) => decimalAdd(total, row.amount?.amount ?? '0'), '0'),
)

const pendingCostCount = computed(() =>
  rows.value.filter((row) => row.amount === null || decimalIsZero(row.amount.amount)).length,
)

const explanation = computed(() => {
  const notes = [
    `口径：按「费用归属期 = ${props.periodLabel}」且「发生日在本页筛选范围内」的费用记录，按类别合计后按金额降序。`,
    `单位：${props.currency}；占比 = 该类别金额 ÷ 同期产值（${props.base === null ? '产值未定价，本次不给占比' : formatMoney({ currency: props.currency, amount: props.base })}）。`,
    '缺失说明：未配置或无发生额的类别不会出现在本表，也不会被当作 0 计入结余；油墨领用成本来自墨水出库流水，不重复计入人工录入的「油墨」费用。',
  ]
  if (otherCurrencies.value.length) {
    notes.push(
      `其他币种（${otherCurrencies.value.map((item) => item.currency).join('、')}）不折算、不与 ${props.currency} 相加，单独列示并标「待核」。`,
    )
  }
  notes.push(`数据截止 ${props.asOf || '—'}。`)
  return notes
})
</script>

<template>
  <div>
    <div v-if="!canReadCost" class="uv-state uv-state--warning" role="alert">
      <div class="uv-state__icon uv-state__icon--warning" aria-hidden="true">
        <Ban class="size-5" />
      </div>
      <p class="uv-state__title">未授权：费用构成金额</p>
      <p class="uv-state__message">
        当前账号没有 uv_printing:cost_read，费用金额不会下发到前端。
        这里不显示金额，也不用「隐藏列」代替权限控制；后端是权威判定。
      </p>
    </div>

    <template v-else-if="ready">
      <div v-if="!rows.length" class="uv-callout uv-callout--warning">
        当前范围内没有 {{ currency }} 的费用记录。这是真实空数据，不是读取失败，也不会按 0 计入结余。
      </div>

      <template v-else>
        <div
          class="uv-bars"
          role="img"
          :aria-label="`费用构成（${currency}）：${rows.map((row) => `${row.label} ${formatMoney(row.amount)}`).join('；')}`"
        >
          <div v-for="row in rows" :key="row.category" class="uv-bar-row">
            <button
              type="button"
              class="uv-bar-row__label uv-row-button"
              :title="`下钻：${row.label} 的费用记录`"
              @click="emit('drill', row.category, row.label)"
            >
              {{ row.label }}
            </button>
            <span class="uv-bar-row__track" aria-hidden="true">
              <span
                class="uv-bar-row__fill"
                :style="{ width: `${Math.min(100, (Math.abs(decimalToNumber(row.amount?.amount ?? '0')) / maxAmount) * 100)}%` }"
              />
            </span>
            <span class="uv-bar-row__value">
              <UvNumber :money="row.amount" size="sm" :state="row.amount === null ? 'pending' : 'normal'" />
            </span>
          </div>
        </div>

        <div class="uv-trend-table__head" style="margin-top: 14px">
          <h3 class="uv-section__title">同口径数据表</h3>
          <span class="uv-field__hint">
            合计 {{ formatMoney({ currency, amount: currencyTotal }) }} · 类别 {{ rows.length }} 项
          </span>
        </div>

        <div class="uv-table-scroll" role="region" tabindex="0" aria-label="费用构成同口径数据表">
          <table class="uv-table uv-table--dense" style="min-width: 660px">
            <caption class="uv-table-caption">
              与上方条形同一批数据、同一币种、同一筛选；占比分母为同期产值。
            </caption>
            <thead>
              <tr>
                <th scope="col">费用类别</th>
                <th scope="col" class="uv-table-cell--right">金额（{{ currency }}）</th>
                <th scope="col" class="uv-table-cell--right">占产值</th>
                <th scope="col">单位与期间</th>
                <th scope="col">来源下钻</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="`t-${row.category}`">
                <td class="uv-row-primary">{{ row.label }}</td>
                <td class="uv-table-cell--right">
                  <UvNumber :money="row.amount" size="sm" :state="row.amount === null ? 'pending' : 'normal'" />
                </td>
                <td class="uv-table-cell--right">
                  <UvNumber
                    :percent="row.share"
                    size="sm"
                    :state="row.share === null ? 'missing' : 'normal'"
                  />
                </td>
                <td>
                  <span>{{ currency }} · 归属期 {{ periodLabel }}</span>
                  <span class="uv-row-sub">数据截止 {{ asOf || '—' }}</span>
                </td>
                <td>
                  <button
                    type="button"
                    class="uv-chip"
                    @click="emit('drill', row.category, row.label)"
                  >
                    查看费用记录
                  </button>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td>{{ currency }} 合计</td>
                <td class="uv-table-cell--right">
                  <span class="uv-mono">{{ formatDecimal(trimTrailingZeros(currencyTotal), 2) }}</span>
                </td>
                <td colspan="3">
                  {{ pendingCostCount ? `${pendingCostCount} 项金额待核，未计入合计` : '全部类别均有明确金额' }}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div v-if="otherCurrencies.length" class="uv-callout uv-callout--warning" style="margin-top: 10px">
          <p><strong>其他币种不并入合计</strong>（不做汇率折算，也不与 {{ currency }} 相加）：</p>
          <ul class="uv-policy-scale">
            <li v-for="item in otherCurrencies" :key="item.currency">
              <span>{{ item.currency }} · {{ item.recordCount }} 条</span>
              <strong>{{ formatMoney({ currency: item.currency, amount: item.amount }) }} · 待核</strong>
            </li>
          </ul>
        </div>

        <ul class="uv-list" style="margin-top: 10px">
          <li v-for="note in explanation" :key="note">
            <span class="uv-list__dot" aria-hidden="true" />
            <span>{{ note }}</span>
          </li>
        </ul>
      </template>
    </template>
  </div>
</template>

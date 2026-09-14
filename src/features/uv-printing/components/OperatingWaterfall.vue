<script setup lang="ts">
import { computed } from 'vue'
import { Ban } from '@lucide/vue'
import type { UvDrillKind, UvReportRow } from '../contracts'
import { decimalCompare, decimalToNumber, formatDecimal, formatMoney, trimTrailingZeros } from '../domain/decimal'
import { DRILL_KIND_LABELS } from '../domain/status'
import UvNumber from './UvNumber.vue'

/**
 * 经营结余瀑布（简洁分项条 + 分项表）。
 *
 * - 口径固定为旧管理口径：产值 − 员工工资 − 管理人员工资 − 设备投资 − 工具费用 − 房租 − 水电
 *   − 材料 − 杂费 − 维修 − 夜班补贴 − 油墨领用成本 − 无产值工资 − 加工费 + 可回收工资 + 可回收油漆金额；
 * - 明确写出「不是法定净利润」；设备采购整笔扣减属于旧口径，**不得标成经营毛利**；
 *   因此同时给出「排除设备投资的经营贡献」并把差额写成可核对的一行；
 * - 条长只表达相对量级，精确值、口径与缺失原因都在数字与分项表里，不做「只在 tooltip 里」的信息；
 * - 缺失项用斜纹条 + 「暂算」，显式 0 用实心 0，两者外观必须区分。
 */

const props = withDefaults(defineProps<{
  rows: UvReportRow[]
  currency: string
  /** operatingResult(...).operatingResult；null 表示产值不可计算，结余暂算。 */
  net: string | null
  /** operatingResult(...).operatingContribution；排除设备投资后的经营贡献。 */
  contribution: string | null
  /** operatingResult(...).equipmentExcludedDifference；设备投资整笔扣减的差额。 */
  equipmentDifference: string | null
  warnings: string[]
  formulaVersion: string
  /** 只有具备成本权限时才渲染金额。 */
  canReadCost: boolean
  /** 数据截止时间。 */
  asOf: string
  periodLabel: string
}>(), {})

const emit = defineEmits<{ drill: [kind: UvDrillKind, ref: string | null, label: string] }>()

/** 条长基准：产值与所有扣减项绝对值的最大值。 */
const scale = computed(() => {
  const values = props.rows
    .map((row) => Math.abs(decimalToNumber(row.value ?? '0')))
    .filter((value) => Number.isFinite(value))
  return Math.max(1, ...values)
})

interface BarRow {
  row: UvReportRow
  label: string
  display: string
  /** 条长百分比。 */
  width: number
  missing: boolean
  kind: 'in' | 'out'
}

const bars = computed<BarRow[]>(() =>
  props.rows.map((row) => {
    const missing = row.value === null
    const magnitude = Math.abs(decimalToNumber(row.value ?? '0'))
    const isAddition = row.value !== null && !row.value.startsWith('-')
    return {
      row,
      label: row.label,
      display: missing ? '暂算' : formatDecimal(trimTrailingZeros(row.value!), 2),
      width: missing ? 100 : Math.min(100, (magnitude / scale.value) * 100),
      missing,
      kind: row.key === 'output_value' || isAddition ? 'in' : 'out',
    }
  }),
)

const netDisplay = computed(() =>
  props.net === null ? '暂算' : formatMoney({ currency: props.currency, amount: props.net }),
)
const contributionDisplay = computed(() =>
  props.contribution === null ? '暂算' : formatMoney({ currency: props.currency, amount: props.contribution }),
)
const differenceDisplay = computed(() =>
  props.equipmentDifference === null ? '—' : formatMoney({ currency: props.currency, amount: props.equipmentDifference }),
)

const contributionIsHigher = computed(() => {
  if (props.net === null || props.contribution === null) return false
  return decimalCompare(props.contribution, props.net) > 0
})

const provisionalCount = computed(() => props.rows.filter((row) => row.provisional).length)
const missingLabels = computed(() => props.rows.filter((row) => row.value === null).map((row) => row.label))

/** 分项表合计行：只作展示核对，不参与任何回写。 */
const tableRows = computed(() => bars.value)
const closingNote = computed(() => {
  const notes = [
    '本表是旧管理口径，不是法定净利润，也不等于税务口径利润。',
    '设备采购按整笔扣减计入，因此不得把这里的结果标成经营毛利；应同时看「排除设备投资的经营贡献」。',
    `数据截止 ${props.asOf || '—'} · 口径版本 ${props.formulaVersion}。`,
  ]
  if (provisionalCount.value) {
    notes.push(`有 ${provisionalCount.value} 项未配置或不可计算（${missingLabels.value.join('、')}），相关金额按暂算处理而不是 0。`)
  }
  return notes
})
</script>

<template>
  <div>
    <div v-if="!canReadCost" class="uv-state uv-state--warning" role="alert">
      <div class="uv-state__icon uv-state__icon--warning" aria-hidden="true">
        <Ban class="size-5" />
      </div>
      <p class="uv-state__title">未授权：经营结余与费用金额</p>
      <p class="uv-state__message">
        当前账号在华康A生产部没有 uv_printing:cost_read，服务端不会下发产值、费用与结余金额。
        这里既不显示数字，也不把「隐藏的列」当作权限控制；后端判定才是权威。
      </p>
      <p class="uv-state__hint">需要查看金额请联系部门主管开通成本读取权限后重新进入本页。</p>
    </div>

    <template v-else>
      <ul class="uv-report-conclusion__stats">
        <li>期间 <strong>{{ periodLabel }}</strong></li>
        <li>参与计算的金额均为 <strong>{{ currency }}</strong>，其他币种不并入</li>
        <li>暂算项 <strong>{{ provisionalCount }}</strong> / {{ rows.length }}</li>
      </ul>

      <div class="uv-waterfall">
        <div
          v-for="bar in tableRows"
          :key="bar.row.key"
          class="uv-waterfall__row"
        >
          <span class="uv-waterfall__label">
            <button
              v-if="bar.row.drill_kind"
              type="button"
              class="uv-row-button"
              :title="`下钻：${DRILL_KIND_LABELS[bar.row.drill_kind]} · ${bar.label}`"
              @click="emit('drill', bar.row.drill_kind, bar.row.drill_ref, bar.label)"
            >
              {{ bar.label }}
            </button>
            <template v-else>{{ bar.label }}</template>
          </span>
          <span class="uv-waterfall__track" aria-hidden="true">
            <span
              class="uv-waterfall__fill"
              :class="bar.missing ? 'uv-waterfall__fill--missing' : bar.kind === 'in' ? 'uv-waterfall__fill--in' : 'uv-waterfall__fill--out'"
              :style="{ width: `${bar.width}%` }"
            />
          </span>
          <span class="uv-waterfall__value">
            <UvNumber
              v-if="bar.row.value !== null"
              :value="bar.display"
              size="sm"
              :unit="currency"
              :state="bar.row.provisional ? 'provisional' : 'normal'"
            />
            <UvNumber v-else :value="null" state="provisional" size="sm" />
          </span>
        </div>

        <div class="uv-waterfall__row uv-waterfall__row--total">
          <span class="uv-waterfall__label">经营结余</span>
          <span class="uv-field__hint">
            产值 − 全部扣减 + 可回收项；旧管理口径，不是法定净利润
          </span>
          <span class="uv-waterfall__value">
            <UvNumber
              v-if="net !== null"
              :value="netDisplay"
              size="md"
              emphasis
              :state="provisionalCount ? 'provisional' : 'normal'"
            />
            <UvNumber v-else :value="null" state="provisional" size="md" emphasis />
          </span>
        </div>

        <div class="uv-waterfall__row uv-waterfall__row--total">
          <span class="uv-waterfall__label">排除设备投资的经营贡献</span>
          <span class="uv-field__hint">
            = 经营结余 + 设备投资整笔扣减 {{ differenceDisplay }}
            <template v-if="contributionIsHigher">（设备投资已加回，因此高于经营结余）</template>
          </span>
          <span class="uv-waterfall__value">
            <UvNumber
              v-if="contribution !== null"
              :value="contributionDisplay"
              size="md"
              emphasis
              :state="provisionalCount ? 'provisional' : 'normal'"
            />
            <UvNumber v-else :value="null" state="provisional" size="md" emphasis />
          </span>
        </div>
      </div>

      <div class="uv-callout" style="margin-top: 12px">
        <p v-for="note in closingNote" :key="note">{{ note }}</p>
      </div>

      <ul v-if="warnings.length" class="uv-list" style="margin-top: 8px">
        <li v-for="warning in warnings" :key="warning">
          <span class="uv-list__dot" aria-hidden="true" />
          <span>{{ warning }}</span>
        </li>
      </ul>

      <details class="uv-section" open>
        <summary class="uv-section__title">分项表（与上方条同一口径，可逐项下钻）</summary>
        <div class="uv-table-scroll" role="region" tabindex="0" aria-label="经营结余分项表">
          <table class="uv-table uv-table--dense" style="min-width: 560px">
            <caption class="uv-table-caption">
              逐项列出扣减与加回；「暂算」表示该项未配置或不可计算，绝不当成 0。
            </caption>
            <thead>
              <tr>
                <th scope="col">项目</th>
                <th scope="col" class="uv-table-cell--right">金额（{{ currency }}）</th>
                <th scope="col">口径</th>
                <th scope="col">来源下钻</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="bar in tableRows" :key="`row-${bar.row.key}`">
                <td class="uv-row-primary">{{ bar.label }}</td>
                <td class="uv-table-cell--right">
                  <UvNumber
                    v-if="bar.row.value !== null"
                    :value="bar.display"
                    size="sm"
                    :state="bar.row.provisional ? 'provisional' : 'normal'"
                  />
                  <UvNumber v-else :value="null" state="provisional" size="sm" />
                </td>
                <td>
                  <span v-if="bar.missing" class="uv-num--pending">未配置口径：暂算，不是 0</span>
                  <span v-else>{{ bar.kind === 'in' ? '计入（加项）' : '扣减（减项）' }}</span>
                </td>
                <td>
                  <button
                    v-if="bar.row.drill_kind"
                    type="button"
                    class="uv-chip"
                    @click="emit('drill', bar.row.drill_kind, bar.row.drill_ref, bar.label)"
                  >
                    查看{{ DRILL_KIND_LABELS[bar.row.drill_kind] }}
                  </button>
                  <span v-else class="uv-num--placeholder">—</span>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td>经营结余（旧管理口径）</td>
                <td class="uv-table-cell--right">
                  <span class="uv-mono">
                    {{ net === null ? '暂算' : formatDecimal(trimTrailingZeros(net), 2) }}
                  </span>
                </td>
                <td colspan="2">产值 − 扣减合计 + 可回收合计</td>
              </tr>
              <tr>
                <td>排除设备投资的经营贡献</td>
                <td class="uv-table-cell--right">
                  <span class="uv-mono">
                    {{ contribution === null ? '暂算' : formatDecimal(trimTrailingZeros(contribution), 2) }}
                  </span>
                </td>
                <td colspan="2">设备投资整笔扣减已加回，差额 {{ differenceDisplay }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </details>
    </template>
  </div>
</template>

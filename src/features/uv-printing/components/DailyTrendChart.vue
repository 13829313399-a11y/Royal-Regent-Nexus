<script setup lang="ts">
import { computed } from 'vue'
import { TriangleAlert } from '@lucide/vue'
import type { UvDailyProjection } from '../contracts'
import { decimalToNumber, formatMoney, formatPercent, trimTrailingZeros } from '../domain/decimal'
import { weekdayLabel } from '../domain/businessTime'
import { COVERAGE } from '../domain/status'
import UvNumber from './UvNumber.vue'
import UvStatusPill from './UvStatusPill.vue'

/**
 * 按日期趋势：真实时间轴上的合格件柱与月内良率折线，配同口径数据表。
 *
 * - 横轴按业务日期等距铺满所选期间，日期缺席就留空，**不补 0、不连线**；
 *   相邻有效点之间用 `.uv-trend__gap` 表示「这几天没有已确认报工」；
 * - 良率与产量同一张图只共用横轴，不引入第二条数值轴；
 * - 图只承担趋势，精确值、口径与缺失原因都在右侧同口径数据表里，不做「只在 tooltip 里」的信息；
 * - 图表提供 role="img" + aria-label 摘要，并提供相邻数据表。
 */

const props = withDefaults(defineProps<{
  rows: UvDailyProjection[]
  /** 期间内的全部业务日期，决定横轴刻度；缺失日期留空。 */
  periodDates: string[]
  currency: string
  /** 只有具备成本权限时才画金额序列。 */
  canReadCost: boolean
  /** 只有具备工资权限时才展示个人/班组工资列。 */
  canReadPayroll: boolean
  /** 数据截止时间，来自 coverageNotes。 */
  asOf: string
  coverage?: 'complete' | 'partial' | 'no_data'
  loading?: boolean
}>(), {
  coverage: 'complete',
  loading: false,
})

const CHARTS = { width: 720, height: 168, left: 46, right: 18, top: 14, bottom: 30 }

const observed = computed(() => {
  const byDate = new Map(props.rows.map((row) => [row.business_date, row]))
  return props.periodDates.map((date, index) => ({
    date,
    index,
    row: byDate.get(date) ?? null,
  }))
})

/** 有已确认报工或任何金额的日期才算「有数据」；其余按缺口处理。 */
const points = computed(() =>
  observed.value.map((entry) => {
    const row = entry.row
    const hasData = Boolean(row) && (row!.reported_qty > 0 || row!.good_qty > 0 || row!.unpriced_reports > 0)
    return {
      ...entry,
      hasData,
      good: row?.good_qty ?? 0,
      reported: row?.reported_qty ?? 0,
      yieldRate: row?.yield_rate ?? null,
      unpriced: row?.unpriced_reports ?? 0,
      qualityPending: row?.quality_pending_reports ?? 0,
      output: row?.output_value ?? null,
      payroll: row?.payroll_amount ?? null,
      inkCost: row?.ink_cost ?? null,
      operating: row?.operating_result ?? null,
      plannedDayOff: row?.planned_day_off ?? false,
      offPlanProduction: row?.off_plan_production ?? false,
    }
  }),
)

const hasAnyData = computed(() => points.value.some((point) => point.hasData))
const maxGood = computed(() => Math.max(1, ...points.value.map((point) => point.good)))
const step = computed(() =>
  points.value.length > 1
    ? (CHARTS.width - CHARTS.left - CHARTS.right) / (points.value.length - 1)
    : 0,
)

function xOf(index: number): number {
  return CHARTS.left + step.value * index
}

function yOf(rate: string | null): number | null {
  if (rate === null) return null
  const value = Math.min(1, Math.max(0, decimalToNumber(rate)))
  const usable = CHARTS.height - CHARTS.top - CHARTS.bottom
  return CHARTS.top + usable * (1 - value)
}

const barWidth = computed(() => Math.max(3, Math.min(14, step.value * 0.44)))

const bars = computed(() =>
  points.value
    .filter((point) => point.hasData && point.good > 0)
    .map((point) => {
      const usable = CHARTS.height - CHARTS.top - CHARTS.bottom
      const height = Math.max(2, (point.good / maxGood.value) * usable)
      return {
        date: point.date,
        x: xOf(point.index) - barWidth.value / 2,
        y: CHARTS.height - CHARTS.bottom - height,
        width: barWidth.value,
        height,
        good: point.good,
      }
    }),
)

/** 相邻有效点之间的真实缺口段，虚线表达「这几天无数据」。 */
const gaps = computed(() => {
  const valid = points.value.filter((point) => point.hasData && yOf(point.yieldRate) !== null)
  const segments: Array<{ key: string; x1: number; y1: number; x2: number; y2: number; days: number }> = []
  for (let index = 1; index < valid.length; index += 1) {
    const previous = valid[index - 1]!
    const current = valid[index]!
    if (current.index - previous.index <= 1) continue
    segments.push({
      key: `${previous.date}~${current.date}`,
      x1: xOf(previous.index),
      y1: yOf(previous.yieldRate)!,
      x2: xOf(current.index),
      y2: yOf(current.yieldRate)!,
      days: current.index - previous.index - 1,
    })
  }
  return segments
})

const yieldSegments = computed(() => {
  const valid = points.value.filter((point) => point.hasData && yOf(point.yieldRate) !== null)
  const segments: string[] = []
  let current: string[] = []
  for (let index = 0; index < valid.length; index += 1) {
    const point = valid[index]!
    const previous = valid[index - 1]
    if (previous && point.index - previous.index > 1) {
      if (current.length > 1) segments.push(current.join(' '))
      current = []
    }
    current.push(`${xOf(point.index)},${yOf(point.yieldRate)}`)
  }
  if (current.length > 1) segments.push(current.join(' '))
  return segments
})

const axisTicks = computed(() => {
  if (!points.value.length) return []
  const ticks: Array<{ key: string; x: number; label: string }> = []
  const stride = points.value.length > 16 ? 4 : points.value.length > 8 ? 3 : 2
  points.value.forEach((point, index) => {
    if (index % stride !== 0 && index !== points.value.length - 1) return
    ticks.push({ key: point.date, x: xOf(index), label: point.date.slice(8) })
  })
  return ticks
})

const yieldGridlines = computed(() =>
  [0, 0.5, 1].map((value) => {
    const usable = CHARTS.height - CHARTS.top - CHARTS.bottom
    return {
      value,
      y: CHARTS.top + usable * (1 - value),
      label: formatPercent(trimTrailingZeros(String(value)), 0),
    }
  }),
)

const missingDates = computed(() => points.value.filter((point) => !point.hasData).map((point) => point.date))

const chartSummary = computed(() => {
  if (!hasAnyData.value) {
    return `所选期间 ${props.periodDates[0] ?? ''} 至 ${props.periodDates[props.periodDates.length - 1] ?? ''} 没有已确认报工，趋势图不画任何点，也不补 0。`
  }
  const valid = points.value.filter((point) => point.hasData)
  const peak = valid.reduce((best, point) => (point.good > best.good ? point : best), valid[0]!)
  return [
    `按日期趋势：${valid[0]!.date} 至 ${valid[valid.length - 1]!.date} 共 ${valid.length} 天有数据`,
    `合格件峰值 ${peak.good} 件（${peak.date}）`,
    missingDates.value.length ? `${missingDates.value.length} 天没有报工，图中留空不补 0` : '期间内每天都有数据',
    props.canReadCost ? '柱为日合格件，折线为当日良率' : '无成本权限，仅展示数量与良率',
  ].join('；')
})

const coverageView = computed(() => COVERAGE[props.coverage])

function qualityNote(point: { unpriced: number; qualityPending: number }): string {
  const notes: string[] = []
  if (point.unpriced > 0) notes.push(`${point.unpriced} 条未定价`)
  if (point.qualityPending > 0) notes.push(`${point.qualityPending} 条质量未判清`)
  return notes.length ? notes.join(' · ') : '口径完整'
}
</script>

<template>
  <div class="uv-trend-block">
    <div class="uv-trend-chart">
      <svg
        v-if="hasAnyData"
        class="uv-trend"
        :viewBox="`0 0 ${CHARTS.width} ${CHARTS.height}`"
        role="img"
        :aria-label="chartSummary"
        preserveAspectRatio="none"
      >
        <line
          v-for="gridline in yieldGridlines"
          :key="gridline.value"
          class="uv-trend__axis"
          :x1="CHARTS.left"
          :x2="CHARTS.width - CHARTS.right"
          :y1="gridline.y"
          :y2="gridline.y"
        />
        <text
          v-for="gridline in yieldGridlines"
          :key="`label-${gridline.value}`"
          class="uv-trend__label"
          :x="CHARTS.left - 6"
          :y="gridline.y + 3"
          text-anchor="end"
        >
          {{ gridline.label }}
        </text>

        <rect
          v-for="bar in bars"
          :key="`bar-${bar.date}`"
          class="uv-trend__bar"
          :x="bar.x"
          :y="bar.y"
          :width="bar.width"
          :height="bar.height"
        >
          <title>{{ bar.date }} 合格 {{ bar.good }} 件</title>
        </rect>

        <line
          v-for="gap in gaps"
          :key="`gap-${gap.key}`"
          class="uv-trend__gap"
          :x1="gap.x1"
          :y1="gap.y1"
          :x2="gap.x2"
          :y2="gap.y2"
        >
          <title>缺口 {{ gap.days }} 天没有已确认报工，不补 0</title>
        </line>

        <polyline
          v-for="(segment, index) in yieldSegments"
          :key="`seg-${index}`"
          class="uv-trend__line"
          :points="segment"
        />

        <text
          v-for="tick in axisTicks"
          :key="`tick-${tick.key}`"
          class="uv-trend__label"
          :x="tick.x"
          :y="CHARTS.height - 10"
          text-anchor="middle"
        >
          {{ tick.label }}
        </text>
      </svg>

      <p v-else class="uv-callout uv-callout--warning">
        <TriangleAlert class="inline size-3.5" aria-hidden="true" />
        所选期间没有已确认报工，趋势图不画点、不补 0，也不回落样例数据。
      </p>

      <p class="uv-trend-caption">
        <span
          class="uv-split-legend"
          aria-hidden="true"
        >
          <span><i class="uv-trend-legend__bar" />日合格件（件）</span>
          <span><i class="uv-trend-legend__line" />日良率（%）</span>
          <span><i class="uv-trend-legend__gap" />缺口：无报工，不补 0</span>
        </span>
        <span class="uv-field__hint">{{ chartSummary }}</span>
      </p>
    </div>

    <div class="uv-trend-table">
      <div class="uv-trend-table__head">
        <h3 class="uv-section__title">同口径数据表</h3>
        <UvStatusPill :status="coverageView" compact />
      </div>
      <div class="uv-table-scroll" role="region" tabindex="0" aria-label="按日期趋势同口径数据表">
        <table class="uv-table uv-table--dense" style="min-width: 620px">
          <caption class="uv-table-caption">
            与左侧趋势图同一批数据、同一期间、同一筛选；缺失日期保留行并标注原因。
          </caption>
          <thead>
            <tr>
              <th scope="col">业务日期</th>
              <th scope="col" class="uv-table-cell--right">合格件</th>
              <th scope="col" class="uv-table-cell--right">报工件</th>
              <th scope="col" class="uv-table-cell--right">日良率</th>
              <th v-if="canReadCost" scope="col" class="uv-table-cell--right">产值</th>
              <th v-if="canReadPayroll" scope="col" class="uv-table-cell--right">班组计件工资</th>
              <th scope="col">口径</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="point in points" :key="point.date">
              <td>
                <span class="uv-row-primary">{{ point.date }}</span>
                <span class="uv-row-sub">
                  {{ weekdayLabel(point.date) }}
                  <template v-if="point.plannedDayOff"> · 计划休息日</template>
                  <template v-if="point.offPlanProduction"> · 计划外生产</template>
                </span>
              </td>
              <td class="uv-table-cell--right">
                <UvNumber v-if="point.hasData" :qty="point.good" size="sm" />
                <span v-else class="uv-num--placeholder">—</span>
              </td>
              <td class="uv-table-cell--right">
                <UvNumber v-if="point.hasData" :qty="point.reported" size="sm" />
                <span v-else class="uv-num--placeholder">—</span>
              </td>
              <td class="uv-table-cell--right">
                <UvNumber :percent="point.yieldRate" size="sm" :state="point.yieldRate === null ? 'missing' : 'normal'" />
              </td>
              <td v-if="canReadCost" class="uv-table-cell--right">
                <UvNumber :money="point.output" size="sm" :state="point.output === null ? 'provisional' : 'normal'" />
              </td>
              <td v-if="canReadPayroll" class="uv-table-cell--right">
                <UvNumber :money="point.payroll" size="sm" :state="point.payroll === null ? 'provisional' : 'normal'" />
              </td>
              <td>
                <span v-if="!point.hasData" class="uv-num--pending">无已确认报工：留空，不补 0</span>
                <span v-else>{{ qualityNote(point) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="uv-field__hint">
        日良率 = 当日合格 ÷ (当日合格 + 当日不良)；月良率不是这些日百分比的平均值。
        数据截止 {{ asOf || '—' }}。
      </p>
    </div>
  </div>
</template>

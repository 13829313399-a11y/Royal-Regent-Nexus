<script setup lang="ts">
import { computed } from 'vue'
import type { Money } from '../contracts'
import { formatDecimal, formatMoney, formatPercent, formatQty } from '../domain/decimal'

/**
 * 数字与金额的统一展示。
 *
 * - 金额等宽数字右对齐；
 * - 未定价显示「未定价」，缺失显示「—」，显式 0 显示 0，三者必须可区分；
 * - 暂算数字带口径后缀，不能与已核定数字长得一样。
 */

const props = withDefaults(defineProps<{
  /** 已格式化的文本；为空时按 state 输出占位。 */
  value?: string | number | null
  money?: Money | null
  percent?: string | null
  qty?: number | null
  decimal?: string | null
  decimalScale?: number
  unit?: string
  align?: 'left' | 'right'
  /** 数据状态：正常 / 未定价 / 待核 / 暂算 / 缺失。 */
  state?: 'normal' | 'unpriced' | 'pending' | 'provisional' | 'missing' | 'zero'
  size?: 'sm' | 'md' | 'lg'
  emphasis?: boolean
}>(), {
  value: undefined,
  money: undefined,
  percent: undefined,
  qty: undefined,
  decimal: undefined,
  decimalScale: 2,
  unit: '',
  align: 'right',
  state: 'normal',
  size: 'md',
  emphasis: false,
})

const stateLabel = computed(() => {
  switch (props.state) {
    case 'unpriced': return '未定价'
    case 'pending': return '待核'
    case 'provisional': return '暂算'
    case 'missing': return '—'
    default: return ''
  }
})

const text = computed(() => {
  if (props.money !== undefined) return formatMoney(props.money)
  if (props.percent !== undefined) return props.percent === null ? '' : formatPercent(props.percent)
  if (props.qty !== undefined) return props.qty === null ? '' : formatQty(props.qty)
  if (props.decimal !== undefined) return formatDecimal(props.decimal, props.decimalScale)
  if (props.value === null || props.value === undefined || props.value === '') return ''
  return String(props.value)
})

const isPlaceholder = computed(() => text.value === '' || text.value === '—')
</script>

<template>
  <span
    class="uv-num"
    :class="[
      `uv-num--${size}`,
      `uv-num--${align}`,
      emphasis ? 'uv-num--emphasis' : '',
      state !== 'normal' ? `uv-num--${state}` : '',
      isPlaceholder ? 'uv-num--placeholder' : '',
    ]"
  >
    <template v-if="stateLabel">{{ stateLabel }}</template>
    <template v-else>{{ text }}</template>
    <span v-if="unit && !stateLabel" class="uv-num__unit">{{ unit }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Archive, CircleCheck, CircleDot, CirclePause, CircleX, Clock, LoaderCircle, TriangleAlert } from '@lucide/vue'
import type { Component } from 'vue'
import { statusName } from '../../workspace'

/* 状态胶囊标签：把接口状态映射为文字 + 双色调微徽章。
   口径保持“文字优先、颜色辅助”：任何状态都必须能只读文字区分，
   圆点、图标与色调只补充语义，不单独承担状态表达。 */
const tones = {
  /* 进行中、已执行：品牌青绿 */
  active: { className: 'spray-pill info', icon: null },
  /* 完成、已核、合格：绿色 */
  success: { className: 'spray-pill success', icon: CircleCheck },
  /* 待开工、已排、已预留：信息蓝 */
  info: { className: 'spray-pill', icon: CircleDot },
  /* 待判、返工、暂算、未定价、待映射：需要关注 */
  warn: { className: 'spray-pill warn', icon: TriangleAlert },
  /* 取消、拒收、报废、错误 */
  danger: { className: 'spray-pill error', icon: CircleX },
  /* 暂停 */
  paused: { className: 'spray-pill warn', icon: CirclePause },
  /* 归档、只读、结案 */
  neutral: { className: 'spray-pill muted', icon: Archive },
  /* 待人工判断的暂态 */
  pending: { className: 'spray-pill muted', icon: Clock },
} as const

const byStatus: Record<string, keyof typeof tones> = {
  running: 'active',
  active: 'active',
  completed: 'success',
  confirmed: 'success',
  verified: 'success',
  closed: 'neutral',
  archived: 'neutral',
  cancelled: 'danger',
  corrected: 'info',
  planned: 'info',
  ready: 'info',
  route: 'info',
  shipped: 'success',
  finished: 'success',
  preview: 'pending',
  provisional: 'warn',
  unpriced: 'warn',
  held: 'warn',
  rework: 'warn',
  'receipt-held': 'warn',
  'return-held': 'warn',
  scrap: 'danger',
  rejected: 'danger',
}

const props = withDefaults(defineProps<{
  status: unknown
  /* 覆盖展示文字；默认使用业务中文状态名，不直接暴露枚举。 */
  label?: string
  /* 显式指定色调，用于业务语义强于状态枚举的场景（例如工资已核）。 */
  tone?: keyof typeof tones
  /* 进行中/读取中显示旋转指示，替代静态圆点。 */
  spinning?: boolean
  /* 呼吸点：只用于真实实时状态。 */
  live?: boolean
}>(), { spinning: false, live: false })

const resolvedTone = computed(() => props.tone ?? byStatus[String(props.status ?? '')] ?? 'info')
const preset = computed(() => tones[resolvedTone.value])
const text = computed(() => props.label ?? statusName(props.status))
const leadingIcon = computed<Component | null>(() => (props.spinning ? LoaderCircle : preset.value.icon))
</script>

<template>
  <span class="spray-status-pill" :class="preset.className">
    <component :is="leadingIcon" v-if="leadingIcon" :size="13" :class="{ 'spray-spin': spinning }" aria-hidden="true" />
    <span v-else class="spray-dot" :class="{ pulse: live }" aria-hidden="true" />
    <span>{{ text }}</span>
  </span>
</template>

<script setup lang="ts">
import { Boxes, ClipboardCheck, FileStack, Package, TriangleAlert } from '@lucide/vue'
import type { Component } from 'vue'
import type { Metric, Tone } from '@/data/enterpriseMock'

withDefaults(defineProps<{
  metric: Metric
  /** 仅用于级联入场的先后次序，不参与业务语义。 */
  index?: number
}>(), {
  index: 0,
})

/**
 * 业务图标按标签映射；未覆盖的标签统一回退到中性的单据图标，
 * 不建立额外的图标配置系统，也不改动共享 Metric 类型与示例数据。
 */
const labelIcons: Record<string, Component> = {
  待处理审批: ClipboardCheck,
  今日生产单: FileStack,
  'QA 异常': TriangleAlert,
  库存预警: Boxes,
}

const toneIcons: Record<Tone, Component> = {
  teal: ClipboardCheck,
  blue: FileStack,
  amber: TriangleAlert,
  red: Boxes,
  slate: Package,
  green: Package,
}

function resolveIcon(metric: Metric): Component {
  const byLabel = labelIcons[metric.label] ?? labelIcons[metric.label.replace(/\s+/g, '')]
  return byLabel ?? toneIcons[metric.tone] ?? Package
}
</script>

<template>
  <article
    class="dashboard-metric enterprise-panel"
    :data-tone="metric.tone"
    :style="{ '--metric-index': index }"
  >
    <div class="relative z-[1] flex items-start justify-between gap-4">
      <div class="min-w-0">
        <p class="dashboard-metric__label">{{ metric.label }}</p>
        <p class="dashboard-metric__value">{{ metric.value }}</p>
        <p class="dashboard-metric__detail">{{ metric.detail }}</p>
      </div>
      <span class="dashboard-metric__icon" data-metric-icon aria-hidden="true">
        <component :is="resolveIcon(metric)" class="size-[19px]" :stroke-width="1.9" />
      </span>
    </div>
  </article>
</template>

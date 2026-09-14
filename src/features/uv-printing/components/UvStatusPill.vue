<script setup lang="ts">
import StatusPill from '@/components/common/StatusPill.vue'
import type { StatusView } from '../domain/status'

/**
 * 业务状态胶囊：状态一律用业务语言输出，不直接展示枚举。
 * 复用宿主 StatusPill 的六种色调，同时包含文字与圆点，
 * 颜色不是唯一状态信号。
 */
withDefaults(defineProps<{
  status: StatusView
  compact?: boolean
  /** 追加口径说明，例如「只读」「暂算」。 */
  suffix?: string
}>(), {
  compact: false,
  suffix: '',
})
</script>

<template>
  <span class="uv-status" :class="compact ? 'uv-status--compact' : ''">
    <StatusPill :label="suffix ? `${status.label} · ${suffix}` : status.label" :tone="status.tone" :compact="compact" />
  </span>
</template>

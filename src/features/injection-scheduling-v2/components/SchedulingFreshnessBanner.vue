<script setup lang="ts">
import { computed } from 'vue'
import { AlertOctagon, RefreshCw } from '@lucide/vue'
import type { SchedulingSyncHealth } from '../types'

const props = defineProps<{
  syncHealth: SchedulingSyncHealth
  sourceMode: 'live' | 'fallback'
  sourceMessage: string
  lastSyncedAt: string
  refreshing: boolean
}>()
const emit = defineEmits<{ retry: [] }>()

const title = computed(() => {
  if (props.syncHealth === 'stale') return '数据已过期'
  if (props.syncHealth === 'demo-readonly') return '只读演示'
  if (props.syncHealth === 'error') return '正式数据未加载'
  return props.sourceMode === 'fallback' ? '正在重试正式数据' : '正在重新同步'
})
const summary = computed(() => {
  if (props.syncHealth === 'stale') {
    return props.lastSyncedAt
      ? `当前展示 ${props.lastSyncedAt} 的最近正式数据。`
      : '当前继续展示最近一次成功取得的正式数据。'
  }
  if (props.syncHealth === 'refreshing') {
    if (props.sourceMode === 'fallback') return '当前仍为只读演示数据，正式数据返回前不会开放正式操作。'
    if (props.lastSyncedAt) return `当前仍展示 ${props.lastSyncedAt} 的最近正式数据。`
    return '正在取得正式排产数据。'
  }
  return props.sourceMessage
})
const detail = computed(() => ['stale', 'refreshing'].includes(props.syncHealth) ? props.sourceMessage : '')
const canRetry = computed(() => ['stale', 'demo-readonly', 'error'].includes(props.syncHealth))
</script>

<template>
  <div v-if="syncHealth !== 'live'" class="freshness-banner" :class="syncHealth" role="status" aria-live="polite">
    <AlertOctagon :size="16" aria-hidden="true" />
    <div class="freshness-copy">
      <strong>{{ title }}</strong>
      <span>{{ summary }}</span>
      <small v-if="detail">{{ detail }}</small>
    </div>
    <button v-if="canRetry" type="button" :disabled="refreshing" @click="emit('retry')">
      <RefreshCw :size="14" :class="{ spinning: refreshing }" />
      {{ refreshing ? '同步中' : '重新同步' }}
    </button>
  </div>
</template>

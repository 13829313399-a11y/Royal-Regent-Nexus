<script setup lang="ts">
import { AlertCircle, CheckCircle2, LoaderCircle } from '@lucide/vue'
import type { AIToolActivityItem } from './types'

defineProps<{
  items: AIToolActivityItem[]
}>()
</script>

<template>
  <ul
    v-if="items.length"
    class="mx-4 space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs text-slate-600 sm:mx-5"
    aria-label="AI 工具执行状态"
  >
    <li v-for="item in items" :key="item.id" class="flex items-center gap-2">
      <LoaderCircle v-if="item.status === 'running'" class="size-3.5 animate-spin" aria-hidden="true" />
      <CheckCircle2 v-else-if="item.status === 'complete'" class="size-3.5 text-emerald-600" aria-hidden="true" />
      <AlertCircle v-else class="size-3.5 text-rose-600" aria-hidden="true" />
      <span>{{ item.label }}</span>
      <span class="sr-only">
        {{ item.status === 'running' ? '进行中' : item.status === 'complete' ? '已完成' : '失败' }}
      </span>
    </li>
  </ul>
</template>

<style scoped>
@media (prefers-reduced-motion: reduce) {
  .animate-spin { animation: none; }
}
</style>

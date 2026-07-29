<script setup lang="ts">
import { AlertTriangle, Clock3 } from '@lucide/vue'
import type { ChangeoverCost } from '@/types/injectionScheduling'

defineProps<{ changeover: ChangeoverCost }>()
</script>

<template>
  <span
    class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[8px] font-black"
    :class="changeover.status === 'missing-rule' ? 'bg-violet-50 text-violet-700' : changeover.totalHours > 1 ? 'bg-amber-50 text-amber-700' : 'bg-teal-50 text-teal-700'"
    :title="changeover.reason"
  >
    <AlertTriangle v-if="changeover.status === 'missing-rule'" class="size-2.5" aria-hidden="true" />
    <Clock3 v-else class="size-2.5" aria-hidden="true" />
    {{ changeover.status === 'missing-rule' ? '缺规则' : `${changeover.totalHours.toFixed(1)}h` }}
  </span>
</template>

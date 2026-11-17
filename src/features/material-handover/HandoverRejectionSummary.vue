<script setup lang="ts">
import StatusPill from '@/components/common/StatusPill.vue'
import type { HandoverRejectionSummary } from '@/api/materialHandover'

defineProps<{ summary: HandoverRejectionSummary }>()

const labels = { PENDING_REDELIVERY: '待补送', RESOLVED: '差异已处理' }
</script>

<template>
  <span class="inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-600">
    <StatusPill compact class="rounded-md" :label="summary.status ? labels[summary.status] : '全拒收'"
      :tone="summary.status === 'RESOLVED' ? 'slate' : 'amber'" />
    <span>拒收 {{ summary.rejected_quantity }} {{ summary.unit }} · 本项实收 0 {{ summary.unit }}</span>
  </span>
</template>

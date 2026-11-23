<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ rows: { unit: string; inbound: number; remaining: number }[] }>()
const totals = computed(() => {
  const units = new Map<string, { inbound: number; remaining: number }>()
  for (const row of props.rows) {
    const sum = units.get(row.unit) ?? { inbound: 0, remaining: 0 }
    sum.inbound += Math.round(row.inbound * 10_000)
    sum.remaining += Math.round(row.remaining * 10_000)
    units.set(row.unit, sum)
  }
  return [...units]
})
const format = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 })
</script>

<template>
  <dl class="grid grid-cols-2 gap-2 text-xs text-slate-700" aria-live="polite">
    <div class="min-w-0">
      <dt>本批有效入库</dt>
      <dd class="font-bold tabular-nums [overflow-wrap:anywhere]">{{ totals.map(([unit, sum]) => format.format(sum.inbound / 10_000) + ' ' + unit).join(' · ') || '—' }}</dd>
    </div>
    <div class="min-w-0">
      <dt>原单继续待收</dt>
      <dd class="font-bold tabular-nums [overflow-wrap:anywhere]">{{ totals.map(([unit, sum]) => format.format(sum.remaining / 10_000) + ' ' + unit).join(' · ') || '—' }}</dd>
    </div>
  </dl>
</template>

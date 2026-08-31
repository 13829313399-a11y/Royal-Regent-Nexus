<script setup lang="ts">
import { computed } from 'vue'
import type { InjectionScheduleKpis } from '@/types/injectionScheduling'

const props = defineProps<{ kpis?: InjectionScheduleKpis }>()

const cards = computed(() => [
  { label: '当前订单', value: props.kpis?.active_order_count ?? 0, tone: 'text-slate-950' },
  { label: '已排订单', value: props.kpis?.scheduled_order_count ?? 0, tone: 'text-teal-700' },
  { label: '待排订单', value: props.kpis?.unscheduled_order_count ?? 0, tone: 'text-amber-700' },
  { label: '生产中', value: props.kpis?.in_production_order_count ?? 0, tone: 'text-blue-700' },
  { label: '已逾期', value: props.kpis?.overdue_order_count ?? 0, tone: 'text-red-700' },
])
</script>

<template>
  <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="注塑排产关键指标">
    <article
      v-for="card in cards"
      :key="card.label"
      class="rounded-xl border border-slate-200/80 bg-white/90 px-4 py-3 shadow-sm"
    >
      <p class="text-xs font-medium text-slate-500">{{ card.label }}</p>
      <p class="mt-1 text-2xl font-bold tabular-nums" :class="card.tone">{{ card.value }}</p>
    </article>
  </section>
</template>

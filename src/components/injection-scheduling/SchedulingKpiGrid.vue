<script setup lang="ts">
import { Activity, CalendarClock, CircleGauge, Layers3, TriangleAlert, Warehouse } from '@lucide/vue'
import type { SchedulingKpi } from '@/types/injectionScheduling'

defineProps<{ kpis: SchedulingKpi[] }>()

const icons = [CircleGauge, Activity, Layers3, Warehouse, TriangleAlert, CalendarClock]
</script>

<template>
  <section class="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6" aria-label="排产关键指标">
    <article
      v-for="(kpi, index) in kpis"
      :key="kpi.label"
      class="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_8px_24px_-22px_rgba(15,23,42,.45)]"
    >
      <div class="flex items-start justify-between gap-3">
        <p class="text-xs font-semibold text-slate-500">{{ kpi.label }}</p>
        <component
          :is="icons[index]"
          class="size-4"
          :class="{
            'text-teal-600': kpi.tone === 'teal',
            'text-amber-600': kpi.tone === 'amber',
            'text-red-600': kpi.tone === 'red',
            'text-slate-400': kpi.tone === 'default',
          }"
          aria-hidden="true"
        />
      </div>
      <strong
        class="mt-3 block text-[26px] leading-none tracking-tight"
        :class="{
          'text-teal-700': kpi.tone === 'teal',
          'text-amber-600': kpi.tone === 'amber',
          'text-red-600': kpi.tone === 'red',
          'text-slate-950': kpi.tone === 'default',
        }"
      >{{ kpi.value }}</strong>
      <p class="mt-2 text-[11px] text-slate-500">{{ kpi.detail }}</p>
    </article>
  </section>
</template>

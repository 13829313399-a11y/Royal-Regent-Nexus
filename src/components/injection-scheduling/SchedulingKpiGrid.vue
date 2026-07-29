<script setup lang="ts">
import { Activity, CalendarClock, CircleGauge, Layers3, RefreshCcw, TriangleAlert } from '@lucide/vue'
import type { SchedulingKpi } from '@/types/injectionScheduling'

defineProps<{ kpis: SchedulingKpi[] }>()
const emit = defineEmits<{ activate: [action: NonNullable<SchedulingKpi['action']>] }>()

const icons = [CircleGauge, Activity, Layers3, TriangleAlert, RefreshCcw, CalendarClock]
</script>

<template>
  <section class="grid h-[58px] grid-cols-3 gap-2 xl:grid-cols-6" aria-label="排产关键指标">
    <button
      v-for="(kpi, index) in kpis"
      :key="kpi.label"
      type="button"
      class="relative flex min-w-0 items-center gap-2 overflow-hidden rounded-xl border border-slate-200 bg-white px-3 text-left shadow-[0_8px_22px_-22px_rgba(15,23,42,.6)]"
      :class="kpi.action ? 'cursor-pointer hover:border-teal-300' : 'cursor-default'"
      @click="kpi.action && emit('activate', kpi.action)"
    >
      <span
        class="grid size-8 shrink-0 place-items-center rounded-lg"
        :class="{
          'bg-teal-50 text-teal-700': kpi.tone === 'teal',
          'bg-amber-50 text-amber-700': kpi.tone === 'amber',
          'bg-red-50 text-red-700': kpi.tone === 'red',
          'bg-violet-50 text-violet-700': kpi.tone === 'violet',
          'bg-slate-100 text-slate-500': kpi.tone === 'default',
        }"
      >
        <component :is="icons[index]" class="size-3.5" aria-hidden="true" />
      </span>
      <div class="min-w-0">
        <p class="truncate text-[8px] font-bold text-slate-400">{{ kpi.label }}</p>
        <div class="mt-0.5 flex items-baseline gap-1.5">
          <strong
            class="truncate text-[16px] leading-none"
            :class="{
              'text-teal-700': kpi.tone === 'teal',
              'text-amber-700': kpi.tone === 'amber',
              'text-red-700': kpi.tone === 'red',
              'text-violet-700': kpi.tone === 'violet',
              'text-slate-900': kpi.tone === 'default',
            }"
          >{{ kpi.value }}</strong>
          <span class="hidden truncate text-[8px] text-slate-400 min-[1500px]:inline">{{ kpi.detail }}</span>
        </div>
      </div>
      <i
        class="absolute inset-x-0 bottom-0 h-0.5"
        :class="{
          'bg-teal-500': kpi.tone === 'teal',
          'bg-amber-500': kpi.tone === 'amber',
          'bg-red-500': kpi.tone === 'red',
          'bg-violet-500': kpi.tone === 'violet',
          'bg-slate-300': kpi.tone === 'default',
        }"
      />
    </button>
  </section>
</template>

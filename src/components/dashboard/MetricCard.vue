<script setup lang="ts">
import { Circle, Square, Triangle } from '@lucide/vue'
import type { Metric, Tone } from '@/data/enterpriseMock'

defineProps<{
  metric: Metric
}>()

const toneClasses: Record<Tone, { iconBg: string; iconText: string }> = {
  teal: { iconBg: 'bg-teal-50', iconText: 'text-teal-700' },
  blue: { iconBg: 'bg-blue-50', iconText: 'text-blue-600' },
  amber: { iconBg: 'bg-amber-50', iconText: 'text-amber-700' },
  red: { iconBg: 'bg-red-50', iconText: 'text-red-700' },
  slate: { iconBg: 'bg-slate-100', iconText: 'text-slate-700' },
  green: { iconBg: 'bg-emerald-50', iconText: 'text-emerald-700' },
}
</script>

<template>
  <article class="enterprise-panel interactive-surface group relative overflow-hidden rounded-xl p-5 sm:p-6">
    <span class="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-teal-500/55 to-transparent" aria-hidden="true" />
    <div class="flex items-start justify-between gap-4">
      <div>
        <p class="text-sm font-medium text-slate-600">{{ metric.label }}</p>
        <p class="mt-3 text-3xl font-semibold tabular-nums tracking-[-0.035em] text-slate-950">{{ metric.value }}</p>
        <p class="mt-2 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
      </div>
      <span
        class="flex size-10 items-center justify-center rounded-xl ring-1 ring-inset ring-white/75 transition-transform duration-200 group-hover:scale-105"
        :class="toneClasses[metric.tone].iconBg"
      >
        <Circle
          v-if="metric.tone === 'teal' || metric.tone === 'red' || metric.tone === 'green'"
          class="size-4 fill-current"
          :class="toneClasses[metric.tone].iconText"
          aria-hidden="true"
        />
        <Square
          v-else-if="metric.tone === 'blue'"
          class="size-4 fill-current"
          :class="toneClasses[metric.tone].iconText"
          aria-hidden="true"
        />
        <Triangle
          v-else
          class="size-5 fill-current"
          :class="toneClasses[metric.tone].iconText"
          aria-hidden="true"
        />
      </span>
    </div>
  </article>
</template>

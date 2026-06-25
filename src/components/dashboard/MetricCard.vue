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
  <article class="rounded-lg border border-slate-200 bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
    <div class="flex items-start justify-between gap-4">
      <div>
        <p class="text-sm text-slate-600">{{ metric.label }}</p>
        <p class="mt-4 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
        <p class="mt-2 text-xs text-slate-500">{{ metric.detail }}</p>
      </div>
      <span
        class="flex size-10 items-center justify-center rounded-xl"
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

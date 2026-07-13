<script setup lang="ts">
import { computed } from 'vue'
import type { Tone } from '@/data/enterpriseMock'

const props = withDefaults(defineProps<{
  value: number
  tone?: Tone
  label?: string
}>(), {
  tone: 'teal',
  label: '',
})

const width = computed(() => `${Math.max(0, Math.min(100, props.value))}%`)

const toneClasses: Record<Tone, string> = {
  teal: 'bg-gradient-to-r from-teal-700 to-teal-500',
  blue: 'bg-gradient-to-r from-blue-700 to-blue-500',
  amber: 'bg-gradient-to-r from-amber-600 to-amber-400',
  red: 'bg-gradient-to-r from-red-700 to-red-500',
  slate: 'bg-gradient-to-r from-slate-700 to-slate-500',
  green: 'bg-gradient-to-r from-emerald-700 to-emerald-500',
}
</script>

<template>
  <div class="space-y-1.5">
    <div v-if="label" class="flex items-center justify-between text-xs text-slate-500">
      <span>{{ label }}</span>
      <span>{{ value }}%</span>
    </div>
    <div
      class="h-1.5 overflow-hidden rounded-full bg-slate-100 ring-1 ring-inset ring-slate-200/70"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="Math.max(0, Math.min(100, value))"
      :aria-label="label || '进度'"
    >
      <div
        class="h-full rounded-full shadow-[0_0_8px_rgba(13,148,136,0.15)] transition-[width] duration-500 ease-out"
        :class="toneClasses[tone]"
        :style="{ width }"
      />
    </div>
  </div>
</template>

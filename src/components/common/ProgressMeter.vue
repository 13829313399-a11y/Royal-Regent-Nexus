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
  teal: 'bg-teal-700',
  blue: 'bg-blue-600',
  amber: 'bg-amber-600',
  red: 'bg-red-700',
  slate: 'bg-slate-600',
  green: 'bg-emerald-700',
}
</script>

<template>
  <div class="space-y-1.5">
    <div v-if="label" class="flex items-center justify-between text-xs text-slate-500">
      <span>{{ label }}</span>
      <span>{{ value }}%</span>
    </div>
    <div class="h-2 overflow-hidden rounded-full bg-slate-200">
      <div class="h-full rounded-full transition-all" :class="toneClasses[tone]" :style="{ width }" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Tone } from '@/data/enterpriseMock'

const props = withDefaults(defineProps<{
  label: string
  tone?: Tone
  compact?: boolean
}>(), {
  tone: 'slate',
  compact: false,
})

const toneClasses: Record<Tone, string> = {
  teal: 'bg-teal-50 text-teal-700 ring-teal-100',
  blue: 'bg-blue-50 text-blue-700 ring-blue-100',
  amber: 'bg-amber-50 text-amber-700 ring-amber-100',
  red: 'bg-red-50 text-red-700 ring-red-100',
  slate: 'bg-slate-100 text-slate-700 ring-slate-200',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
}

const classes = computed(() => [
  toneClasses[props.tone],
  props.compact ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs',
])
</script>

<template>
  <span
    class="inline-flex items-center rounded-full font-semibold leading-none ring-1 ring-inset"
    :class="classes"
  >
    {{ label }}
  </span>
</template>

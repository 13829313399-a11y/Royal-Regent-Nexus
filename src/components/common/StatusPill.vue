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

const toneClasses: Record<Tone, { surface: string; dot: string }> = {
  teal: { surface: 'bg-teal-50/90 text-teal-700 ring-teal-200/70', dot: 'bg-teal-600' },
  blue: { surface: 'bg-blue-50/90 text-blue-700 ring-blue-200/70', dot: 'bg-blue-600' },
  amber: { surface: 'bg-amber-50/90 text-amber-700 ring-amber-200/70', dot: 'bg-amber-500' },
  red: { surface: 'bg-red-50/90 text-red-700 ring-red-200/70', dot: 'bg-red-600' },
  slate: { surface: 'bg-slate-100/90 text-slate-700 ring-slate-200', dot: 'bg-slate-500' },
  green: { surface: 'bg-emerald-50/90 text-emerald-700 ring-emerald-200/70', dot: 'bg-emerald-600' },
}

const classes = computed(() => [
  toneClasses[props.tone].surface,
  props.compact ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs',
])
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full font-semibold leading-none ring-1 ring-inset"
    :class="classes"
  >
    <span class="size-1.5 shrink-0 rounded-full" :class="toneClasses[tone].dot" aria-hidden="true" />
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { DropdownMenuItem } from 'reka-ui'

withDefaults(defineProps<{ disabled?: boolean; tone?: 'neutral' | 'teal' | 'blue' | 'amber' | 'correction' | 'danger' }>(), { tone: 'neutral' })
const emit = defineEmits<{ select: [event: Event] }>()
const tones = {
  neutral: 'text-slate-700 data-[highlighted]:bg-slate-50',
  teal: 'text-teal-700 data-[highlighted]:bg-teal-50',
  blue: 'text-blue-700 data-[highlighted]:bg-blue-50',
  amber: 'text-amber-700 data-[highlighted]:bg-amber-50',
  correction: 'text-amber-800 data-[highlighted]:bg-amber-50',
  danger: 'text-red-700 data-[highlighted]:bg-red-50',
}
</script>

<template>
  <DropdownMenuItem as-child :disabled="disabled" @select="emit('select', $event)">
    <button type="button" :disabled="disabled" :class="tones[tone]" class="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-[10px] font-semibold outline-none data-[disabled]:pointer-events-none data-[disabled]:cursor-not-allowed data-[disabled]:text-slate-400 data-[disabled]:opacity-40">
      <slot />
    </button>
  </DropdownMenuItem>
</template>

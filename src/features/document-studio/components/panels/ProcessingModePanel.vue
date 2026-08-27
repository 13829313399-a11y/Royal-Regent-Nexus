<script setup lang="ts">
import type { DocumentProcessingMode, DocumentToolCapability } from '@/api/tools'

const props = defineProps<{
  modelValue: DocumentProcessingMode
  capability: DocumentToolCapability | null
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [mode: DocumentProcessingMode] }>()
</script>

<template>
  <div>
    <p class="text-xs font-semibold text-slate-700">处理模式</p>
    <div class="mt-2 grid grid-cols-2 gap-2">
      <button
        v-for="mode in (['AUTO', 'LOCAL'] as const)"
        :key="mode"
        type="button"
        class="rounded-lg border px-2 py-2 text-xs font-semibold"
        :class="modelValue === mode ? 'border-teal-400 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'"
        :disabled="disabled || !props.capability?.modes[mode].available"
        :title="props.capability?.modes[mode].reason"
        @click="emit('update:modelValue', mode)"
      >
        {{ mode === 'AUTO' ? '自动' : '仅本地' }}
      </button>
    </div>
    <p v-if="props.capability?.modes[modelValue].reason" class="mt-2 text-xs leading-5 text-amber-700">
      {{ props.capability.modes[modelValue].reason }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Boxes, ShieldCheck } from '@lucide/vue'
import type {
  AIContextOption,
  AIConversationContextBinding,
} from '@/api/aiConversations'
import { contextDisplayLabel } from '../conversation/conversationContext'

const props = defineProps<{
  modelValue: AIConversationContextBinding | null
  options: readonly AIContextOption[]
  disabled?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  change: [option: AIContextOption | null]
}>()

const selectedValue = computed(() => props.modelValue?.module_id ?? '')

function selectContext(event: Event) {
  const moduleId = (event.target as HTMLSelectElement).value
  emit('change', props.options.find((option) => option.module_id === moduleId) ?? null)
}
</script>

<template>
<label class="inline-flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm">
  <Boxes class="size-3.5 shrink-0 text-sky-700" aria-hidden="true" />
  <span class="sr-only">当前业务上下文</span>
  <select
    class="min-w-0 max-w-40 bg-transparent font-semibold outline-none disabled:cursor-not-allowed disabled:opacity-60"
    :value="selectedValue"
    :disabled="disabled || loading"
    aria-label="切换会话业务上下文"
    @change="selectContext"
  >
    <option value="">无业务上下文</option>
    <option v-for="option in options" :key="option.module_id" :value="option.module_id">
      {{ option.display_label }}
    </option>
  </select>
  <ShieldCheck
    v-if="modelValue"
    class="size-3.5 shrink-0 text-emerald-600"
    aria-label="服务端已重新验证"
  />
  <span v-else class="hidden text-slate-400 sm:inline">
    {{ contextDisplayLabel(null) }}
  </span>
</label>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { X } from '@lucide/vue'
withDefaults(defineProps<{ title: string; description?: string; busy?: boolean; disabled?: boolean; submitDisabled?: boolean; closeLabel?: string; backLabel?: string; submitLabel: string }>(), { backLabel: '返回', closeLabel: '关闭订单表单' })
const emit = defineEmits<{ submit: []; close: [] }>()
const form = ref<HTMLFormElement>()
defineExpose({ focusField: (label: string) => form.value?.querySelector<HTMLElement>(`[aria-label="${label}"]`)?.focus() })
</script>
<template>
  <form ref="form" class="carton-editor-form max-h-[92dvh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white shadow-2xl" aria-label="订单表单" @submit.prevent="!busy && !submitDisabled && emit('submit')">
    <div class="flex shrink-0 items-start justify-between border-b border-slate-200 px-5 py-4"><div><h2 class="text-base font-bold text-slate-950">{{ title }}</h2><p v-if="description" class="mt-1 text-xs text-slate-500">{{ description }}</p></div><button type="button" :disabled="busy" :aria-label="closeLabel" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 disabled:opacity-40" @click="emit('close')"><X class="size-4" /></button></div>
    <fieldset :disabled="busy || disabled" class="min-w-0 space-y-5 p-5"><slot /></fieldset>
    <div class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-4"><div class="min-w-0 flex-1"><slot name="feedback" /></div><div class="flex gap-2"><button type="button" :disabled="busy" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-xs font-bold text-slate-600 disabled:opacity-40" @click="emit('close')">{{ backLabel }}</button><button type="submit" :disabled="busy || submitDisabled" class="h-9 rounded-lg bg-teal-700 px-4 text-xs font-bold text-white disabled:opacity-40">{{ busy ? '正在保存…' : submitLabel }}</button></div></div>
  </form>
</template>

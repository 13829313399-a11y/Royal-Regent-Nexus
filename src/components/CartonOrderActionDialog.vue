<script setup lang="ts">
import { DialogRoot, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { X } from '@lucide/vue'
const props = withDefaults(defineProps<{ title: string; description: string; busy?: boolean; disabled?: boolean; danger?: boolean; submitLabel: string; submitAria?: string; closeLabel?: string; backLabel?: string; reasonLabel?: string; reasonAria?: string; reasonMax?: number; error?: string; teleport?: boolean }>(), { closeLabel: '关闭操作窗口', backLabel: '返回', reasonMax: 500 })
const reason = defineModel<string>('reason', { default: '' })
const emit = defineEmits<{ submit: []; close: [] }>()
function submit() { if (!props.busy && !props.disabled && (!props.reasonLabel || reason.value.trim().length >= 4)) emit('submit') }
</script>
<template>
  <DialogRoot :open="true" @update:open="value => { if (!value && !busy) emit('close') }">
    <Teleport to="body" :disabled="!teleport">
    <DialogOverlay class="fixed inset-0 z-[80] bg-slate-950/45" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[81] flex max-h-[88dvh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" @interact-outside="event => { if (busy) event.preventDefault() }" @escape-key-down="event => { if (busy) event.preventDefault() }">
      <form class="flex min-h-0 flex-col" @submit.prevent="submit">
        <div class="flex shrink-0 items-start justify-between border-b border-slate-200 px-5 py-4"><div><DialogTitle class="text-base font-bold text-slate-950">{{ title }}</DialogTitle><DialogDescription class="mt-1 text-xs leading-5 text-slate-500">{{ description }}</DialogDescription></div><button type="button" :disabled="busy" :aria-label="closeLabel" class="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-slate-100" @click="emit('close')"><X class="size-4" /></button></div>
        <fieldset :disabled="busy" class="min-h-0 space-y-4 overflow-y-auto p-5"><slot /><label v-if="reasonLabel" class="block space-y-1.5 text-xs font-bold text-slate-600">{{ reasonLabel }} *<textarea v-model="reason" :aria-label="reasonAria || reasonLabel" rows="3" required minlength="4" :maxlength="reasonMax" class="w-full rounded-lg border border-slate-200 px-3 py-2 font-normal" /></label><p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p></fieldset>
        <div class="flex shrink-0 justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" :disabled="busy" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-xs font-bold text-slate-600 disabled:opacity-40" @click="emit('close')">{{ backLabel }}</button><button type="submit" @click.prevent="submit" :aria-label="submitAria" :disabled="busy || disabled || (!!reasonLabel && reason.trim().length < 4)" class="h-9 rounded-lg px-4 text-xs font-bold text-white disabled:opacity-40" :class="danger ? 'bg-red-600' : 'bg-teal-700'">{{ busy ? '正在处理…' : submitLabel }}</button></div>
      </form>
    </DialogContent>
    </Teleport>
  </DialogRoot>
</template>

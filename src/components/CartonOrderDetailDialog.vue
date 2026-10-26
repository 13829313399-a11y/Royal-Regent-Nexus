<script setup lang="ts">
import { DialogRoot, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { X } from '@lucide/vue'
defineOptions({ inheritAttrs: false })
withDefaults(defineProps<{ title: string; pinned?: boolean; description?: string; closeLabel?: string; busy?: boolean; hideFooter?: boolean; form?: boolean; compact?: boolean; narrow?: boolean }>(), { pinned: true, closeLabel: '关闭订单明细' })
const emit = defineEmits<{ close: []; closeAutoFocus: [event: Event] }>()
</script>
<template>
  <DialogRoot :open="true" :modal="pinned" @update:open="value => { if (!value && pinned && !busy) emit('close') }">
    <div v-bind="$attrs" class="fixed inset-0 z-[62] flex items-center justify-center p-4" :class="pinned ? 'pointer-events-auto bg-slate-950/45' : 'pointer-events-none bg-slate-950/25'" @click.self="pinned && !busy && emit('close')">
      <DialogContent :aria-modal="pinned ? true : undefined" :aria-label="form ? title : undefined" :inert="pinned ? undefined : true" :class="[narrow ? 'max-w-lg' : compact ? 'max-w-2xl' : 'max-w-5xl', { 'pointer-events-none': !pinned }]" class="flex max-h-[88dvh] w-full flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" @open-auto-focus="event => { if (!pinned) event.preventDefault() }" @close-auto-focus="event => { if (!pinned) event.preventDefault(); emit('closeAutoFocus', event) }" @interact-outside="event => { if (!pinned || busy) event.preventDefault() }" @escape-key-down="event => { if (busy) event.preventDefault() }">
        <div :class="form ? 'sr-only' : ''" class="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 px-5 py-4"><div class="min-w-0"><DialogTitle class="break-words text-lg font-bold text-slate-950">{{ title }}</DialogTitle><DialogDescription class="mt-1 text-xs text-teal-700">{{ description || (pinned ? '已固定显示 · 查看纸品、交付和箱唛资料' : '悬停预览 · 单击明细可固定查看') }}</DialogDescription></div><button v-if="pinned && !form" type="button" :aria-label="closeLabel" :disabled="busy" class="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-slate-100 disabled:opacity-40" @click="emit('close')"><X class="size-4" /></button></div>
        <div class="min-h-0 overflow-y-auto" :class="form ? 'carton-embedded-form' : 'space-y-4 p-5'"><slot /></div>
        <div v-if="pinned && !hideFooter" class="flex shrink-0 justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4"><button type="button" :disabled="busy" class="h-9 rounded-lg border border-slate-200 bg-white px-4 text-xs font-bold text-slate-600 disabled:opacity-40" @click="emit('close')">关闭</button><slot name="footer" /></div>
      </DialogContent>
    </div>
  </DialogRoot>
</template>

<style scoped>
.carton-embedded-form :deep(.carton-editor-form) { max-height:none; overflow:visible; }
</style>

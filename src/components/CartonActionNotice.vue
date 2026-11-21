<script setup lang="ts">
import { AlertCircle, CheckCircle2, X } from '@lucide/vue'

defineProps<{ message: string; tone?: 'error' | 'warning' | 'success' }>()
defineEmits<{ dismiss: [] }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="message" data-testid="carton-action-notice" :role="tone === 'success' ? 'status' : 'alert'" :aria-live="tone === 'success' ? 'polite' : 'assertive'"
      class="pointer-events-auto fixed right-4 top-4 z-[200] flex max-h-[45vh] w-[calc(100%-2rem)] max-w-lg items-start gap-3 overflow-auto rounded-xl border p-4 shadow-xl"
      :class="tone === 'success' ? 'border-emerald-300 bg-emerald-50 text-emerald-900' : tone === 'warning' ? 'border-amber-300 bg-amber-50 text-amber-900' : 'border-red-300 bg-red-50 text-red-900'">
      <CheckCircle2 v-if="tone === 'success'" class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <AlertCircle v-else class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <p class="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm leading-6">{{ message }}</p>
      <button type="button" aria-label="关闭操作提醒" class="shrink-0 rounded p-1 hover:bg-white/70" @click="$emit('dismiss')"><X class="size-4" /></button>
    </div>
  </Teleport>
</template>

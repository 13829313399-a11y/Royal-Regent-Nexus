<script setup lang="ts">
import { AlertCircle, X } from '@lucide/vue'

defineProps<{ message: string; tone?: 'error' | 'warning' }>()
defineEmits<{ dismiss: [] }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="message" data-testid="carton-action-notice" role="alert" aria-live="assertive"
      class="pointer-events-auto fixed right-4 top-4 z-[200] flex max-h-[45vh] w-[calc(100%-2rem)] max-w-lg items-start gap-3 overflow-auto rounded-xl border p-4 shadow-xl"
      :class="tone === 'warning' ? 'border-amber-300 bg-amber-50 text-amber-900' : 'border-red-300 bg-red-50 text-red-900'">
      <AlertCircle class="mt-0.5 size-5 shrink-0" />
      <p class="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm leading-6">{{ message }}</p>
      <button type="button" aria-label="关闭操作提醒" class="shrink-0 rounded p-1 hover:bg-white/70" @click="$emit('dismiss')"><X class="size-4" /></button>
    </div>
  </Teleport>
</template>

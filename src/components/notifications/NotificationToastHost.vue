<script setup lang="ts">
import { BellRing, ExternalLink, X } from '@lucide/vue'
import type { NotificationToastEntry } from '@/composables/useNotificationCenter'

defineProps<{
  entry: NotificationToastEntry
  queuedCount: number
  formatTime: (value: string) => string
}>()

const emit = defineEmits<{
  activate: [entry: NotificationToastEntry]
  dismiss: []
  pause: []
  resume: []
}>()
</script>

<template>
  <div
    class="fixed inset-x-3 top-20 z-[80] mx-auto w-auto max-w-[390px] overflow-hidden rounded-[14px] border border-slate-200 bg-white shadow-[0_18px_50px_-24px_rgba(15,23,42,0.42)] sm:left-auto sm:right-6 sm:mx-0 sm:w-[390px]"
    role="status"
    aria-live="polite"
    @mouseenter="emit('pause')"
    @mouseleave="emit('resume')"
    @focusin="emit('pause')"
    @focusout="emit('resume')"
  >
    <div class="h-1 bg-teal-700" />
    <div class="flex items-start gap-3 p-4">
      <div class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-teal-50 text-teal-700">
        <BellRing class="size-4" aria-hidden="true" />
      </div>

      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2 text-[11px] font-semibold">
          <span class="text-teal-700">{{ entry.categoryLabel }}</span>
          <span class="text-slate-300" aria-hidden="true">·</span>
          <time class="text-slate-500">{{ formatTime(entry.createdAt) }}</time>
        </div>
        <p class="mt-1 text-sm font-bold leading-5 text-slate-950">{{ entry.title }}</p>
        <p class="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">{{ entry.summary }}</p>
        <p v-if="entry.contextLabel" class="mt-1.5 truncate text-[11px] text-slate-500">
          {{ entry.contextLabel }}
        </p>

        <div class="mt-3 flex items-center justify-between gap-3">
          <span v-if="queuedCount" class="text-[11px] text-slate-500">
            后续还有 {{ queuedCount }} 条
          </span>
          <span v-else />

          <RouterLink
            v-if="entry.route"
            :to="entry.route"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-900 px-3 text-xs font-semibold text-white transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
            @click="emit('activate', entry)"
          >
            查看详情
            <ExternalLink class="size-3.5" aria-hidden="true" />
          </RouterLink>
          <button
            v-else
            type="button"
            class="inline-flex h-8 items-center rounded-lg bg-slate-900 px-3 text-xs font-semibold text-white transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
            @click="emit('activate', entry)"
          >
            打开通知中心
          </button>
        </div>
      </div>

      <button
        type="button"
        class="flex size-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
        aria-label="关闭消息提醒"
        @click="emit('dismiss')"
      >
        <X class="size-4" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

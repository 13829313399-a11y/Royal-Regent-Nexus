<script setup lang="ts">
import { computed } from 'vue'
import { Database, TimerOff } from '@lucide/vue'
import type { AIConversationMode } from '@/api/aiConversations'

const props = defineProps<{
  mode: AIConversationMode
}>()

const isPersistent = computed(() => props.mode === 'PERSISTENT')
</script>

<template>
  <span
    data-conversation-retention
    class="inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[11px] font-semibold"
    :class="isPersistent
      ? 'border-sky-200 bg-sky-50 text-sky-800'
      : 'border-amber-200 bg-amber-50 text-amber-800'"
    :title="isPersistent
      ? '持久会话的正文与安全摘要最多保留 30 天。'
      : '临时会话只保留必要元数据，不保存用户或助手正文。'"
  >
    <Database v-if="isPersistent" class="size-3" aria-hidden="true" />
    <TimerOff v-else class="size-3" aria-hidden="true" />
    {{ isPersistent ? '持久 · 30 天' : '临时 · 不存正文' }}
  </span>
</template>

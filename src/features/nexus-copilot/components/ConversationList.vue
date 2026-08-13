<script setup lang="ts">
import { MessageSquarePlus, Plus, Trash2 } from '@lucide/vue'
import type { AIConversationListItem, AIConversationMode } from '@/api/aiConversations'
import ConversationRetentionBadge from './ConversationRetentionBadge.vue'

defineProps<{
  items: readonly AIConversationListItem[]
  activeId: string | null
  loading: boolean
  hasMore: boolean
}>()

const emit = defineEmits<{
  select: [conversationId: string]
  create: [mode: AIConversationMode]
  delete: [conversationId: string]
  loadMore: []
}>()

function activityTime(item: AIConversationListItem) {
  const value = item.last_message_at ?? item.updated_at
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function requestDelete(item: AIConversationListItem) {
  const approved = window.confirm(
    `删除“${item.title || '未命名会话'}”？\n\n对话正文和摘要将不可恢复；已产生的 Action 审计记录不会被删除。`,
  )
  if (approved) emit('delete', item.id)
}
</script>

<template>
  <aside class="flex min-h-0 flex-col border-r border-slate-200 bg-white" aria-label="AI 会话列表">
    <div class="border-b border-slate-200 p-3">
      <div class="grid grid-cols-2 gap-2">
        <button
          type="button"
          class="inline-flex items-center justify-center gap-1.5 rounded-xl bg-slate-950 px-3 py-2 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
          @click="emit('create', 'PERSISTENT')"
        >
          <MessageSquarePlus class="size-3.5" aria-hidden="true" />
          持久会话
        </button>
        <button
          type="button"
          class="inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-amber-300 hover:bg-amber-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600"
          @click="emit('create', 'TEMPORARY')"
        >
          <Plus class="size-3.5" aria-hidden="true" />
          临时会话
        </button>
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto p-2">
      <p v-if="loading && !items.length" class="px-3 py-8 text-center text-xs text-slate-500" role="status">
        正在加载会话…
      </p>
      <div v-else-if="!items.length" class="px-4 py-10 text-center">
        <p class="text-sm font-semibold text-slate-700">还没有会话</p>
        <p class="mt-1 text-xs leading-5 text-slate-500">创建持久会话用于跨页面继续，或使用不保存正文的临时会话。</p>
      </div>
      <ul v-else class="space-y-1">
        <li v-for="item in items" :key="item.id" class="group relative">
          <button
            type="button"
            class="w-full rounded-xl border px-3 py-3 pr-10 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
            :class="activeId === item.id
              ? 'border-sky-300 bg-sky-50'
              : 'border-transparent hover:border-slate-200 hover:bg-slate-50'"
            :aria-current="activeId === item.id ? 'true' : undefined"
            @click="emit('select', item.id)"
          >
            <span class="block truncate text-sm font-semibold text-slate-900">{{ item.title || '未命名会话' }}</span>
            <span class="mt-1.5 flex flex-wrap items-center gap-2">
              <ConversationRetentionBadge :mode="item.mode" />
              <span class="text-[11px] text-slate-500">{{ activityTime(item) }}</span>
            </span>
          </button>
          <button
            type="button"
            class="absolute right-2 top-2 flex size-8 items-center justify-center rounded-lg text-slate-400 opacity-70 hover:bg-rose-50 hover:text-rose-700 focus:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rose-600 group-hover:opacity-100"
            :aria-label="`删除会话：${item.title || '未命名会话'}`"
            @click.stop="requestDelete(item)"
          >
            <Trash2 class="size-3.5" aria-hidden="true" />
          </button>
        </li>
      </ul>
      <button
        v-if="hasMore"
        type="button"
        class="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-50"
        :disabled="loading"
        @click="emit('loadMore')"
      >
        {{ loading ? '正在加载…' : '加载更多会话' }}
      </button>
    </div>
  </aside>
</template>

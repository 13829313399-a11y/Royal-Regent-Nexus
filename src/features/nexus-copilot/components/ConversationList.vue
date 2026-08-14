<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Archive,
  ArchiveRestore,
  MessageSquarePlus,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
} from '@lucide/vue'
import type { AIConversationListItem, AIConversationMode } from '@/api/aiConversations'
import { contextDisplayLabel } from '../conversation/conversationContext'
import type { ConversationRuntimeStatus } from '../conversation/conversationRuntimeStatus'
import ConversationRetentionBadge from './ConversationRetentionBadge.vue'

const props = withDefaults(defineProps<{
  items: readonly AIConversationListItem[]
  activeId: string | null
  loading: boolean
  hasMore: boolean
  managementEnabled?: boolean
  runtimeStatuses?: Readonly<Record<string, ConversationRuntimeStatus>>
}>(), { managementEnabled: true, runtimeStatuses: () => ({}) })

const emit = defineEmits<{
  select: [conversationId: string]
  create: [mode: AIConversationMode]
  delete: [conversationId: string]
  rename: [conversationId: string, title: string]
  pin: [conversationId: string, pinned: boolean]
  archive: [conversationId: string, archived: boolean]
  loadMore: []
}>()

const search = ref('')

const factoryLabels: Record<string, string> = {
  'huakang-a': '华康 A', 'huakang-b': '华康 B', 'huakang-c': '华康 C',
  'huakang-d': '华康 D', huadeng: '华登', huaxing: '华兴',
}

function factoryLabel(factoryId: string) {
  return factoryLabels[factoryId] ?? factoryId
}

function activityDate(item: AIConversationListItem) {
  return new Date(item.last_message_at ?? item.updated_at)
}

function activityTime(item: AIConversationListItem) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(activityDate(item))
}

const filteredItems = computed(() => {
  const query = search.value.trim().toLocaleLowerCase('zh-CN')
  if (!query) return [...props.items]
  return props.items.filter((item) => [
    item.title,
    item.factory_scope,
    factoryLabel(item.factory_scope),
    contextDisplayLabel(item.context_binding?.module_id),
    props.runtimeStatuses[item.id]?.taskLabel ?? '',
    props.runtimeStatuses[item.id]?.actionLabel ?? '',
  ].some((value) => value.toLocaleLowerCase('zh-CN').includes(query)))
})

const groupedItems = computed(() => {
  const now = new Date()
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const recentBoundary = startToday - (7 * 24 * 60 * 60 * 1000)
  const groups = [
    { id: 'pinned', label: '已固定', items: [] as AIConversationListItem[] },
    { id: 'today', label: '今天', items: [] as AIConversationListItem[] },
    { id: 'recent', label: '最近 7 天', items: [] as AIConversationListItem[] },
    { id: 'older', label: '更早', items: [] as AIConversationListItem[] },
    { id: 'archived', label: '已归档', items: [] as AIConversationListItem[] },
  ]
  filteredItems.value
    .sort((left, right) => activityDate(right).getTime() - activityDate(left).getTime())
    .forEach((item) => {
      if (item.archived_at) groups[4]!.items.push(item)
      else if (item.pinned_at) groups[0]!.items.push(item)
      else if (activityDate(item).getTime() >= startToday) groups[1]!.items.push(item)
      else if (activityDate(item).getTime() >= recentBoundary) groups[2]!.items.push(item)
      else groups[3]!.items.push(item)
    })
  return groups.filter((group) => group.items.length)
})

function requestDelete(item: AIConversationListItem) {
  const approved = window.confirm(
    `删除“${item.title || '未命名会话'}”？\n\n对话正文和摘要将不可恢复；已产生的 Action 审计记录不会被删除。`,
  )
  if (approved) emit('delete', item.id)
}

function requestRename(item: AIConversationListItem) {
  const title = window.prompt('重命名会话', item.title)?.trim()
  if (title && title !== item.title) emit('rename', item.id, title.slice(0, 160))
}
</script>

<template>
  <aside class="flex min-h-0 flex-col border-r border-slate-200 bg-white" aria-label="AI 会话列表">
    <div class="space-y-2 border-b border-slate-200 p-3">
      <button
        type="button"
        class="inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-slate-950 px-3 py-2.5 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
        @click="emit('create', 'PERSISTENT')"
      >
        <MessageSquarePlus class="size-3.5" aria-hidden="true" />
        新建会话
      </button>
      <button
        type="button"
        class="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-amber-300 hover:bg-amber-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600"
        @click="emit('create', 'TEMPORARY')"
      >
        <Plus class="size-3.5" aria-hidden="true" />
        临时会话
      </button>
      <label class="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-2 focus-within:border-sky-400 focus-within:ring-2 focus-within:ring-sky-100">
        <Search class="size-3.5 text-slate-400" aria-hidden="true" />
        <span class="sr-only">搜索会话</span>
        <input
          v-model="search"
          type="search"
          class="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-400"
          placeholder="搜索标题、上下文或厂区"
        >
      </label>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto p-2">
      <p v-if="loading && !items.length" class="px-3 py-8 text-center text-xs text-slate-500" role="status">
        正在加载会话…
      </p>
      <div v-else-if="!groupedItems.length" class="px-4 py-10 text-center">
        <p class="text-sm font-semibold text-slate-700">{{ search ? '没有匹配会话' : '还没有会话' }}</p>
        <p class="mt-1 text-xs leading-5 text-slate-500">持久会话可跨页面继续；临时会话不保存正文。</p>
      </div>
      <section v-for="group in groupedItems" v-else :key="group.id" class="mb-4">
        <h2 class="px-2 pb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
          {{ group.label }}
        </h2>
        <ul class="space-y-1">
          <li v-for="item in group.items" :key="item.id" class="group relative">
            <button
              type="button"
              class="w-full rounded-xl border px-3 py-3 pr-24 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
              :class="activeId === item.id
                ? 'border-sky-300 bg-sky-50'
                : 'border-transparent hover:border-slate-200 hover:bg-slate-50'"
              :aria-current="activeId === item.id ? 'true' : undefined"
              @click="emit('select', item.id)"
            >
              <span class="block truncate text-sm font-semibold text-slate-900">{{ item.title || '未命名会话' }}</span>
              <span class="mt-1 block truncate text-[11px] text-slate-500">
                {{ contextDisplayLabel(item.context_binding?.module_id) }} · {{ factoryLabel(item.factory_scope) }}
              </span>
              <span class="mt-1.5 flex flex-wrap items-center gap-2">
                <ConversationRetentionBadge :mode="item.mode" />
                <span
                  v-if="runtimeStatuses[item.id]?.taskState"
                  class="rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-700 ring-1 ring-inset ring-violet-200"
                  data-conversation-task-status
                >
                  {{ runtimeStatuses[item.id]!.taskLabel }}<template v-if="runtimeStatuses[item.id]!.taskCount > 1"> · {{ runtimeStatuses[item.id]!.taskCount }}</template>
                </span>
                <span
                  v-if="runtimeStatuses[item.id]?.actionState"
                  class="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800 ring-1 ring-inset ring-amber-200"
                  data-conversation-action-status
                >
                  {{ runtimeStatuses[item.id]!.actionLabel }}<template v-if="runtimeStatuses[item.id]!.actionCount > 1"> · {{ runtimeStatuses[item.id]!.actionCount }}</template>
                </span>
                <span class="text-[11px] text-slate-500">{{ activityTime(item) }}</span>
              </span>
            </button>
            <div class="absolute right-2 top-2 flex items-center rounded-lg bg-white/90 opacity-0 shadow-sm transition group-hover:opacity-100 group-focus-within:opacity-100">
              <button v-if="managementEnabled" type="button" class="icon-action" :aria-label="`${item.pinned_at ? '取消固定' : '固定'}会话：${item.title}`" @click.stop="emit('pin', item.id, !item.pinned_at)">
                <PinOff v-if="item.pinned_at" class="size-3.5" aria-hidden="true" />
                <Pin v-else class="size-3.5" aria-hidden="true" />
              </button>
              <button v-if="managementEnabled" type="button" class="icon-action" :aria-label="`重命名会话：${item.title}`" @click.stop="requestRename(item)">
                <Pencil class="size-3.5" aria-hidden="true" />
              </button>
              <button v-if="managementEnabled" type="button" class="icon-action" :aria-label="`${item.archived_at ? '恢复' : '归档'}会话：${item.title}`" @click.stop="emit('archive', item.id, !item.archived_at)">
                <ArchiveRestore v-if="item.archived_at" class="size-3.5" aria-hidden="true" />
                <Archive v-else class="size-3.5" aria-hidden="true" />
              </button>
              <button type="button" class="icon-action hover:text-rose-700" :aria-label="`删除会话：${item.title || '未命名会话'}`" @click.stop="requestDelete(item)">
                <Trash2 class="size-3.5" aria-hidden="true" />
              </button>
            </div>
          </li>
        </ul>
      </section>
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

<style scoped>
.icon-action {
  display: inline-flex;
  width: 1.75rem;
  height: 1.75rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  color: rgb(100 116 139);
}

.icon-action:hover {
  background: rgb(241 245 249);
  color: rgb(15 23 42);
}

.icon-action:focus-visible {
  outline: 2px solid rgb(2 132 199);
  outline-offset: 1px;
}
</style>

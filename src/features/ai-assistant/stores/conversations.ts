import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  appendAIConversationMessage,
  createAIConversation,
  deleteAIConversation,
  getAIConversation,
  listAIConversations,
} from '@/api/aiConversations'
import type {
  AIConversationDetail,
  AIConversationListItem,
  AIConversationMode,
} from '@/api/aiConversations'

export const useAIConversationsStore = defineStore('aiConversations', () => {
  const items = ref<AIConversationListItem[]>([])
  const active = ref<AIConversationDetail | null>(null)
  const nextCursor = ref<string | null>(null)
  const loading = ref(false)
  const error = ref('')
  const evidenceAccessChanged = ref(false)

  const activeId = computed(() => active.value?.id ?? null)

  async function loadList(reset = true) {
    loading.value = true
    error.value = ''
    try {
      const page = await listAIConversations(reset ? undefined : nextCursor.value ?? undefined)
      items.value = reset
        ? page.items
        : [...items.value, ...page.items].filter(
            (item, index, all) => all.findIndex((candidate) => candidate.id === item.id) === index,
          )
      nextCursor.value = page.next_cursor
    } catch {
      error.value = '会话列表暂时无法加载，请稍后重试。'
      throw new Error(error.value)
    } finally {
      loading.value = false
    }
  }

  async function create(input: {
    mode: AIConversationMode
    factoryScope: string
    title?: string
  }) {
    error.value = ''
    const created = await createAIConversation(input)
    items.value = [created, ...items.value.filter((item) => item.id !== created.id)]
    return created
  }

  async function open(conversationId: string) {
    loading.value = true
    error.value = ''
    try {
      const previousEvidenceCount = active.value?.id === conversationId
        ? active.value.messages.reduce((total, message) => total + message.evidence.length, 0)
        : 0
      const next = await getAIConversation(conversationId)
      const nextEvidenceCount = next.messages.reduce(
        (total, message) => total + message.evidence.length,
        0,
      )
      evidenceAccessChanged.value = previousEvidenceCount > 0 && nextEvidenceCount === 0
      active.value = next
      const listItem: AIConversationListItem = {
        id: next.id,
        mode: next.mode,
        status: next.status,
        title: next.title,
        factory_scope: next.factory_scope,
        revision: next.revision,
        created_at: next.created_at,
        updated_at: next.updated_at,
        expires_at: next.expires_at,
        message_count: next.message_count,
        last_message_at: next.last_message_at,
      }
      items.value = [listItem, ...items.value.filter((item) => item.id !== next.id)]
      return active.value
    } catch {
      active.value = null
      evidenceAccessChanged.value = true
      error.value = '会话暂时无法读取，可能已删除或权限已变化。'
      throw new Error(error.value)
    } finally {
      loading.value = false
    }
  }

  async function loadOlderMessages() {
    const current = active.value
    if (!current?.next_message_cursor) return
    loading.value = true
    error.value = ''
    try {
      const page = await getAIConversation(current.id, {
        messageCursor: current.next_message_cursor,
      })
      if (active.value?.id !== current.id) return
      const known = new Set(active.value.messages.map((message) => message.id))
      active.value.messages = [
        ...page.messages.filter((message) => !known.has(message.id)),
        ...active.value.messages,
      ]
      active.value.next_message_cursor = page.next_message_cursor
    } catch {
      error.value = '更早的会话记录暂时无法加载。'
      throw new Error(error.value)
    } finally {
      loading.value = false
    }
  }

  async function appendUserMessage(input: {
    text: string
    idempotencyKey: string
  }) {
    if (!active.value) throw new Error('请先选择会话。')
    const message = await appendAIConversationMessage({
      conversationId: active.value.id,
      text: input.text,
      idempotencyKey: input.idempotencyKey,
      expectedRevision: active.value.revision,
    })
    if (message.persisted) active.value.messages.push(message)
    active.value.revision += 1
    active.value.message_count += message.persisted ? 1 : 0
    return message
  }

  async function remove(conversationId: string) {
    await deleteAIConversation(conversationId)
    items.value = items.value.filter((item) => item.id !== conversationId)
    if (active.value?.id === conversationId) active.value = null
  }

  function reset() {
    items.value = []
    active.value = null
    nextCursor.value = null
    loading.value = false
    error.value = ''
    evidenceAccessChanged.value = false
  }

  return {
    items,
    active,
    activeId,
    nextCursor,
    loading,
    error,
    evidenceAccessChanged,
    loadList,
    create,
    open,
    loadOlderMessages,
    appendUserMessage,
    remove,
    reset,
  }
})

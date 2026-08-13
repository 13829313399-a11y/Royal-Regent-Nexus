import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getAIConversation: vi.fn(),
  listAIConversations: vi.fn(),
}))

vi.mock('@/api/aiConversations', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/aiConversations')>(),
  getAIConversation: apiMocks.getAIConversation,
  listAIConversations: apiMocks.listAIConversations,
}))

import { useAIAssistantStore } from '@/features/ai-assistant/store'
import { useAIConversationsStore } from '@/features/ai-assistant/stores/conversations'

const conversationId = 'aicv-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
const base = {
  id: conversationId,
  mode: 'PERSISTENT' as const,
  status: 'ACTIVE' as const,
  title: '权限恢复测试',
  factory_scope: 'huaxing',
  revision: 2,
  created_at: '2026-08-12T08:00:00+08:00',
  updated_at: '2026-08-12T08:01:00+08:00',
  expires_at: null,
  message_count: 1,
  last_message_at: '2026-08-12T08:01:00+08:00',
}

const message = {
  id: 'aimsg-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
  conversation_id: conversationId,
  role: 'ASSISTANT' as const,
  kind: 'TEXT' as const,
  text: '只对当前权限可见',
  authority: 'CONVERSATIONAL_ONLY' as const,
  requires_tool_refresh: true as const,
  persisted: true,
  truncated: false,
  skill_id: '',
  skill_version: '',
  skill_hash: '',
  prompt_version: '',
  prompt_hash: '',
  provider_profile: '',
  provider_model_alias: '',
  usage: {},
  evidence: [{ evidence_id: 'ev:1234567890abcdef' }],
  created_at: '2026-08-12T08:01:00+08:00',
  expires_at: '2026-09-11T08:01:00+08:00',
}

beforeEach(() => {
  setActivePinia(createPinia())
  Object.values(apiMocks).forEach((mock) => mock.mockReset())
})

describe('NIF-06 conversation recovery boundaries', () => {
  it('drops previously visible evidence when current authorization no longer returns it', async () => {
    apiMocks.getAIConversation
      .mockResolvedValueOnce({ ...base, messages: [message], summary: null, next_message_cursor: null })
      .mockResolvedValueOnce({ ...base, messages: [], summary: null, next_message_cursor: null })
    const store = useAIConversationsStore()

    await store.open(conversationId)
    expect(store.active?.messages[0]?.evidence).toHaveLength(1)
    await store.open(conversationId)

    expect(store.active?.messages).toEqual([])
    expect(store.evidenceAccessChanged).toBe(true)
  })

  it('paginates conversation metadata without duplicating overlapping records', async () => {
    apiMocks.listAIConversations
      .mockResolvedValueOnce({ items: [base], next_cursor: 'next-page' })
      .mockResolvedValueOnce({ items: [base], next_cursor: null })
    const store = useAIConversationsStore()

    await store.loadList(true)
    await store.loadList(false)

    expect(store.items).toHaveLength(1)
    expect(apiMocks.listAIConversations).toHaveBeenLastCalledWith('next-page')
  })

  it('keeps persistent Drawer state on close but clears temporary bodies and binding', () => {
    const store = useAIAssistantStore()
    store.bindConversation(conversationId, 'PERSISTENT', [message])
    store.closeDrawer()
    expect(store.activeConversationId).toBe(conversationId)
    expect(store.messages).toHaveLength(1)

    store.bindConversation('aicv-cccccccccccccccccccccccccccccccc', 'TEMPORARY')
    store.messages.push({
      id: 'local-temp',
      role: 'user',
      text: '临时正文',
      status: 'complete',
      createdAt: '2026-08-12T08:02:00+08:00',
    })
    store.closeDrawer()

    expect(store.activeConversationId).toBeNull()
    expect(store.messages).toEqual([])
  })
})

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  appendAIConversationMessage: vi.fn(),
  createAIConversation: vi.fn(),
  deleteAIConversation: vi.fn(),
  getAIConversation: vi.fn(),
  listAIConversations: vi.fn(),
  listAIContextOptions: vi.fn(),
  setAIConversationContext: vi.fn(),
  updateAIConversation: vi.fn(),
}))

vi.mock('@/api/aiConversations', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/aiConversations')>(),
  ...apiMocks,
}))

import {
  parseAIConversationDetail,
  parseAIConversationListPage,
} from '@/api/aiConversations'
import { useAIConversationsStore } from '../stores/conversations'

const listItem = {
  id: 'aicv-11111111111111111111111111111111',
  mode: 'PERSISTENT' as const,
  status: 'ACTIVE' as const,
  title: 'NIF-05 会话',
  factory_scope: 'huaxing',
  revision: 1,
  created_at: '2026-08-12T08:00:00+08:00',
  updated_at: '2026-08-12T08:00:00+08:00',
  expires_at: null,
  message_count: 0,
  last_message_at: null,
  pinned_at: null,
  archived_at: null,
  context_binding: null,
}

const detail = {
  ...listItem,
  messages: [],
  summary: null,
  next_message_cursor: null,
}

beforeEach(() => {
  setActivePinia(createPinia())
  Object.values(apiMocks).forEach((mock) => mock.mockReset())
})

describe('NIF-05 conversation client contract', () => {
  it('accepts the closed v1 resource and rejects unknown additive fields', () => {
    expect(parseAIConversationListPage({ items: [listItem], next_cursor: null })).toEqual({
      items: [listItem],
      next_cursor: null,
    })
    expect(parseAIConversationDetail(detail).id).toBe(listItem.id)
    expect(() => parseAIConversationListPage({
      items: [{ ...listItem, leaked_body: 'must fail closed' }],
      next_cursor: null,
    })).toThrow(/unknown field/)
  })

  it('keeps server conversations in memory and never adds temporary bodies', async () => {
    apiMocks.listAIConversations.mockResolvedValue({ items: [listItem], next_cursor: null })
    apiMocks.getAIConversation.mockResolvedValue({ ...detail })
    apiMocks.appendAIConversationMessage.mockResolvedValue({
      id: 'aimsg-22222222222222222222222222222222',
      conversation_id: listItem.id,
      role: 'USER',
      kind: 'TEXT',
      text: 'temporary text',
      authority: 'CONVERSATIONAL_ONLY',
      requires_tool_refresh: true,
      persisted: false,
      truncated: false,
      skill_id: '',
      skill_version: '',
      skill_hash: '',
      prompt_version: '',
      prompt_hash: '',
      provider_profile: '',
      provider_model_alias: '',
      usage: {},
      evidence: [],
      created_at: '2026-08-12T08:01:00+08:00',
      expires_at: '2026-09-11T08:00:00+08:00',
    })
    const store = useAIConversationsStore()

    await store.loadList()
    await store.open(listItem.id)
    await store.appendUserMessage({
      text: 'temporary text',
      idempotencyKey: 'web-temporary-message-1',
    })

    expect(store.items).toHaveLength(1)
    expect(store.active?.messages).toEqual([])
    expect(store.active?.revision).toBe(2)
    expect(store.active?.message_count).toBe(0)
  })

  it('removes deleted conversation metadata from the local store', async () => {
    apiMocks.listAIConversations.mockResolvedValue({ items: [listItem], next_cursor: null })
    apiMocks.getAIConversation.mockResolvedValue({ ...detail })
    apiMocks.deleteAIConversation.mockResolvedValue(undefined)
    const store = useAIConversationsStore()
    await store.loadList()
    await store.open(listItem.id)

    await store.remove(listItem.id)

    expect(apiMocks.deleteAIConversation).toHaveBeenCalledWith(listItem.id)
    expect(store.items).toEqual([])
    expect(store.active).toBeNull()
  })

  it('keeps context and management metadata revisioned in the server store', async () => {
    apiMocks.listAIConversations.mockResolvedValue({ items: [listItem], next_cursor: null })
    apiMocks.getAIConversation.mockResolvedValue({ ...detail })
    apiMocks.setAIConversationContext.mockResolvedValue({
      factory_scope: 'huaxing',
      module_id: 'injection-scheduling',
      route_name: 'injection-scheduling-v2',
      path: '/modules/production/injection-scheduling',
      context_version: 1,
      selected_entity_type: '',
      selected_entity_id: '',
      selected_entity_revision: null,
      updated_at: '2026-08-12T08:02:00+08:00',
    })
    const store = useAIConversationsStore()
    await store.loadList()
    await store.open(listItem.id)
    await store.setContext({
      route_name: 'injection-scheduling-v2',
      path: '/modules/production/injection-scheduling',
      factory_id: 'huaxing',
      module_id: 'injection-scheduling',
      selected_entity: null,
    })
    apiMocks.updateAIConversation.mockResolvedValue({
      ...store.items[0],
      title: '已固定会话',
      revision: 3,
      pinned_at: '2026-08-12T08:03:00+08:00',
    })
    await store.updateMetadata(listItem.id, { title: '已固定会话', pinned: true })

    expect(apiMocks.setAIConversationContext).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: listItem.id,
      expectedRevision: 1,
    }))
    expect(apiMocks.updateAIConversation).toHaveBeenCalledWith(expect.objectContaining({
      conversationId: listItem.id,
      expectedRevision: 2,
      pinned: true,
    }))
    expect(store.active?.title).toBe('已固定会话')
    expect(store.active?.pinned_at).not.toBeNull()
  })
})

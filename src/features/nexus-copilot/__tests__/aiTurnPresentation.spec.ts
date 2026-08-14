import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ streamAIResponse: vi.fn() }))

vi.mock('@/api/ai', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/ai')>(),
  streamAIResponse: apiMocks.streamAIResponse,
}))

import { useAIAssistantStore } from '@/features/ai-assistant/store'
import type { AIStreamEnvelope } from '@/features/ai-assistant/types'

function event(requestId: string, sequence: number, type: string, payload: Record<string, unknown> = {}): AIStreamEnvelope {
  return { schema_version: '1', request_id: requestId, sequence, type, timestamp: '2026-08-14T00:00:00Z', payload }
}

describe('turn-level AI presentation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMocks.streamAIResponse.mockReset()
  })

  it('keeps tool activity, result and source bound to each of two turns', async () => {
    let call = 0
    apiMocks.streamAIResponse.mockImplementation(async (options) => {
      call += 1
      const requestId = `request-${call}`
      options.onEvent(event(requestId, 1, 'tool.started', { tool_call_id: `call-${call}`, tool_name: 'identity.current_user' }))
      options.onEvent(event(requestId, 2, 'tool.completed', {
        tool_call_id: `call-${call}`,
        tool_name: 'identity.current_user',
        result: {
          ok: true,
          data: { source_type: 'MODEL_INFERENCE', title: `结果 ${call}`, summary: `摘要 ${call}` },
        },
      }))
      options.onEvent(event(requestId, 3, 'message.delta', { delta: `回答 ${call}` }))
      const terminal = event(requestId, 4, 'response.completed')
      options.onEvent(terminal)
      return terminal
    })
    const store = useAIAssistantStore()
    store.capabilities = {
      enabled: true,
      available: true,
      provider: 'fake',
      model: 'fake',
      streaming: true,
      vision_enabled: false,
      conversation_persistence: false,
      tool_groups: ['identity'],
      pilot_access: { granted: true, status: 'GRANTED', read_only: true },
    }

    await store.sendMessage('第一问', null)
    await store.sendMessage('第二问', null)

    expect(store.turns).toHaveLength(2)
    expect(store.turns[0]).toMatchObject({ requestId: 'request-1', status: 'complete' })
    expect(store.turns[0]?.businessResults[0]?.summary).toBe('摘要 1')
    expect(store.turns[1]?.businessResults[0]?.summary).toBe('摘要 2')
    expect(store.turns[0]?.activities[0]).toMatchObject({ id: 'call-1', status: 'complete' })
    expect(store.turns[1]?.activities[0]).toMatchObject({ id: 'call-2', status: 'complete' })
    expect(store.businessResults[0]?.summary).toBe('摘要 2')
  })

  it('rebuilds historical turns with reauthorization evidence and no result snapshot', () => {
    const store = useAIAssistantStore()
    store.bindConversation('aicv-11111111111111111111111111111111', 'PERSISTENT', [
      {
        id: 'aimsg-11111111111111111111111111111111',
        conversation_id: 'aicv-11111111111111111111111111111111',
        role: 'USER',
        kind: 'TEXT',
        text: '历史问题',
        authority: 'CONVERSATIONAL_ONLY',
        requires_tool_refresh: true,
        persisted: true,
        truncated: false,
        skill_id: '', skill_version: '', skill_hash: '', prompt_version: '', prompt_hash: '',
        provider_profile: '', provider_model_alias: '', usage: {}, evidence: [],
        created_at: '2026-08-14T00:00:00Z', expires_at: null,
      },
      {
        id: 'aimsg-22222222222222222222222222222222',
        conversation_id: 'aicv-11111111111111111111111111111111',
        role: 'ASSISTANT',
        kind: 'TEXT',
        text: '历史回答',
        authority: 'CONVERSATIONAL_ONLY',
        requires_tool_refresh: true,
        persisted: true,
        truncated: false,
        skill_id: '', skill_version: '', skill_hash: '', prompt_version: '', prompt_hash: '',
        provider_profile: '', provider_model_alias: '', usage: {},
        evidence: [{
          evidence_id: 'ev:1234567890abcdef', source_level: 'FORMAL_DOMAIN_SERVICE',
          source_name: 'molding_sample.list_summaries', factory_id: 'huaxing',
          as_of: '2026-08-14T00:00:00Z', entity_type: null, entity_id: null,
          entity_revision: null, content_hash: `sha256:${'a'.repeat(64)}`, truncated: false,
          cursor: null, access_policy: 'REAUTHORIZE_ON_OPEN',
        }],
        created_at: '2026-08-14T00:00:01Z', expires_at: null,
      },
    ])
    expect(store.turns).toHaveLength(1)
    expect(store.turns[0]).toMatchObject({ historical: true, requiresRefresh: true })
    expect(store.turns[0]?.evidence[0]?.sourceName).toBe('molding_sample.list_summaries')
    expect(store.turns[0]?.businessResults).toEqual([])
  })
})

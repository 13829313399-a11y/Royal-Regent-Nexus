import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getAICapabilities: vi.fn(),
  streamAIResponse: vi.fn(),
}))

vi.mock('@/api/ai', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/ai')>(),
  getAICapabilities: apiMocks.getAICapabilities,
  streamAIResponse: apiMocks.streamAIResponse,
}))

import { useAIAssistantStore } from '../store'
import type { AICapabilities, AIStreamEnvelope } from '../types'

const capabilities: AICapabilities = {
  enabled: true,
  available: true,
  provider: 'fake',
  model: 'fake-model',
  streaming: true,
  vision_enabled: false,
  conversation_persistence: false,
  tool_groups: ['identity'],
  pilot_access: {
    granted: true,
    status: 'GRANTED',
    read_only: false,
    max_tool_risk_level: 'PREVIEW_WITH_AUDIT',
  },
}

function event(
  sequence: number,
  type: string,
  payload: Record<string, unknown> = {},
): AIStreamEnvelope {
  return {
    schema_version: '1',
    request_id: 'web-legacy-contract',
    sequence,
    type,
    timestamp: `2026-08-12T00:00:0${sequence}Z`,
    payload,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  apiMocks.getAICapabilities.mockReset()
  apiMocks.streamAIResponse.mockReset()
})

describe('AI v1 compatibility contract', () => {
  it('ignores unknown additive events and unregistered result schemas', async () => {
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'future.progress', {
        delta: '未知事件内容不能进入现有消息',
        result: {
          schema_version: 'future-result-v9',
          result_type: 'future.unregistered',
          opaque: 'untrusted',
        },
      }))
      options.onEvent(event(2, 'message.delta', {
        delta: '兼容文本',
        source: 'MODEL_INFERENCE',
      }))
      options.onEvent(event(3, 'message.completed', {
        delta_count: 1,
        output_chars: 4,
        tool_count: 0,
        source: 'MODEL_INFERENCE',
      }))
      const terminal = event(4, 'response.completed', {
        usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
        tool_count: 0,
        tool_rounds: 0,
        source: 'MODEL_INFERENCE',
      })
      options.onEvent(terminal)
      return terminal
    })
    const store = useAIAssistantStore()
    store.capabilities = capabilities

    await expect(store.sendMessage('测试兼容合同', null)).resolves.toBe(true)

    expect(store.messages.at(-1)).toMatchObject({
      role: 'assistant',
      text: '兼容文本',
      status: 'complete',
    })
    expect(store.activities).toEqual([])
    expect(store.businessResults).toEqual([])
    expect(store.sources).toHaveLength(1)
    expect(store.sources[0]?.level).toBe('MODEL_INFERENCE')
  })
})

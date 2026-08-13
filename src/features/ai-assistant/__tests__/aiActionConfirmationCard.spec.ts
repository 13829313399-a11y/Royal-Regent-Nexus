import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getAICapabilities: vi.fn(),
  streamAIResponse: vi.fn(),
  confirmAIAction: vi.fn(),
  cancelAIAction: vi.fn(),
  executeAIAction: vi.fn(),
}))

vi.mock('@/api/ai', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/ai')>(),
  getAICapabilities: apiMocks.getAICapabilities,
  streamAIResponse: apiMocks.streamAIResponse,
}))

vi.mock('@/api/aiActions', () => ({
  confirmAIAction: apiMocks.confirmAIAction,
  cancelAIAction: apiMocks.cancelAIAction,
  executeAIAction: apiMocks.executeAIAction,
  newAIActionExecutionRequestId: () => 'web-ai-action-test-1',
}))

import AiBusinessResultCard from '../AiBusinessResultCard.vue'
import { useAIAssistantStore } from '../store'
import type { AIActionConfirmation, AIStreamEnvelope } from '../types'

function event(sequence: number, type: string, payload: Record<string, unknown>): AIStreamEnvelope {
  return {
    schema_version: '1',
    request_id: 'action-confirmation-card',
    sequence,
    type,
    timestamp: `2026-08-12T01:00:0${sequence}Z`,
    payload,
  }
}

function confirmationData(reviewRequiredCount = 0) {
  return {
    schema_version: 'ai-action-confirmation-v1',
    result_type: 'ai.action_confirmation',
    source_type: 'FORMAL',
    confirmation_id: 'aic-confirmation-1',
    tool_name: 'injection_scheduling.apply_preview_run',
    risk_level: 'CONSEQUENTIAL_WRITE',
    factory_id: 'huaxing',
    entity_type: 'auto_schedule_run',
    entity_id: 'isrun-ai-1',
    entity_revision: 1,
    args_hash: 'a'.repeat(64),
    expires_at: '2026-08-12T09:10:00+08:00',
    status: 'PENDING',
    created_at: '2026-08-12T09:00:00+08:00',
    confirmed_at: '',
    executed_at: '',
    failure_code: '',
    action_summary: {
      action_type: 'APPLY_INJECTION_AUTO_SCHEDULE_RUN',
      run_id: 'isrun-ai-1',
      plan_id: 'draft-plan-1',
      plan_revision: 7,
      rule_revision: 3,
      assignment_count: 16,
      review_required_count: reviewRequiredCount,
      effect_label: '应用到 DRAFT，不会发布生产',
      requires_override_reason: reviewRequiredCount > 0,
    },
  }
}

function usableStore() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useAIAssistantStore(pinia)
  store.capabilities = {
    enabled: true,
    available: true,
    provider: 'test',
    model: 'test',
    streaming: true,
    vision_enabled: false,
    conversation_persistence: false,
    tool_groups: ['injection_scheduling'],
    pilot_access: {
      granted: true,
      status: 'GRANTED',
      read_only: false,
      max_tool_risk_level: 'PREVIEW_WITH_AUDIT',
    },
  }
  return store
}

async function loadConfirmation(reviewRequiredCount = 0) {
  const store = usableStore()
  apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
    options.onEvent(event(1, 'message.delta', { delta: '模型声称已发布。' }))
    options.onEvent(event(2, 'tool.completed', {
      tool_call_id: 'propose-apply-1',
      tool_name: 'injection_scheduling.propose_apply',
      status: 'completed',
      result: {
        ok: true,
        tool_name: 'injection_scheduling.propose_apply',
        data: confirmationData(reviewRequiredCount),
        error: null,
        metadata: {},
      },
    }))
    options.onEvent(event(3, 'response.completed', {}))
    return event(3, 'response.completed', {})
  })
  await store.sendMessage('准备应用候选方案', null)
  const wrapper = mount(AiBusinessResultCard, {
    props: { results: store.businessResults, sources: store.sources },
  })
  return { store, wrapper }
}

beforeEach(() => {
  Object.values(apiMocks).forEach((mock) => mock.mockReset())
})

describe('AI controlled action confirmation card', () => {
  it('requires an explicit click and reports DRAFT rather than publish', async () => {
    const { store, wrapper } = await loadConfirmation()
    const parsed = store.businessResults[0].actionConfirmation!
    apiMocks.confirmAIAction.mockResolvedValue({ ...parsed, status: 'CONFIRMED' })
    apiMocks.executeAIAction.mockResolvedValue({
      confirmation: { ...parsed, status: 'EXECUTED' },
      result: {
        outcome_label: '已应用到 DRAFT，尚未发布生产',
      },
    })

    const card = wrapper.get('[data-ai-action-confirmation]')
    expect(card.text()).toContain('待确认的正式操作')
    expect(card.text()).toContain('应用到 DRAFT，不会发布生产')
    expect(card.text()).not.toContain('模型声称已发布')
    expect(apiMocks.confirmAIAction).not.toHaveBeenCalled()
    expect(apiMocks.executeAIAction).not.toHaveBeenCalled()

    await card.get('button').trigger('click')
    await flushPromises()

    expect(apiMocks.confirmAIAction).toHaveBeenCalledTimes(1)
    expect(apiMocks.executeAIAction).toHaveBeenCalledTimes(1)
    expect(card.text()).toContain('已应用到 DRAFT，尚未发布生产')
    expect(card.text()).toContain('不会 Publish 或 Rollback')
  })

  it('requires the human to type an override reason for review-required assignments', async () => {
    const { store, wrapper } = await loadConfirmation(2)
    const parsed = store.businessResults[0].actionConfirmation!
    apiMocks.confirmAIAction.mockResolvedValue({ ...parsed, status: 'CONFIRMED' })
    apiMocks.executeAIAction.mockResolvedValue({
      confirmation: { ...parsed, status: 'EXECUTED' },
      result: { outcome_label: '已应用到 DRAFT，尚未发布生产' },
    })
    const card = wrapper.get('[data-ai-action-confirmation]')

    await card.get('button').trigger('click')
    expect(card.text()).toContain('请由你本人填写覆盖原因')
    expect(apiMocks.confirmAIAction).not.toHaveBeenCalled()

    await card.get('textarea').setValue('已逐项核对待复核安排')
    await card.get('button').trigger('click')
    await flushPromises()
    expect(apiMocks.executeAIAction).toHaveBeenCalledWith(
      expect.any(Object),
      '已逐项核对待复核安排',
      'web-ai-action-test-1',
    )
  })

  it('reuses the execution request id when a confirmed action is retried', async () => {
    const { store, wrapper } = await loadConfirmation()
    const parsed = store.businessResults[0].actionConfirmation!
    apiMocks.confirmAIAction.mockResolvedValue({ ...parsed, status: 'CONFIRMED' })
    apiMocks.executeAIAction
      .mockRejectedValueOnce(new Error('network interrupted'))
      .mockResolvedValueOnce({
        confirmation: { ...parsed, status: 'EXECUTED' },
        result: { outcome_label: '已应用到 DRAFT，尚未发布生产' },
      })
    const card = wrapper.get('[data-ai-action-confirmation]')

    await card.get('button').trigger('click')
    await flushPromises()
    expect(apiMocks.confirmAIAction).toHaveBeenCalledTimes(1)
    expect(card.text()).toContain('重试执行到 DRAFT')

    await card.get('button').trigger('click')
    await flushPromises()
    expect(apiMocks.confirmAIAction).toHaveBeenCalledTimes(1)
    expect(apiMocks.executeAIAction).toHaveBeenCalledTimes(2)
    expect(apiMocks.executeAIAction.mock.calls[0]?.[2]).toBe('web-ai-action-test-1')
    expect(apiMocks.executeAIAction.mock.calls[1]?.[2]).toBe('web-ai-action-test-1')
    expect(card.text()).toContain('已应用到 DRAFT，尚未发布生产')
  })

  it('cancels a pending action without calling execute', async () => {
    const { store, wrapper } = await loadConfirmation()
    const parsed = store.businessResults[0].actionConfirmation as AIActionConfirmation
    apiMocks.cancelAIAction.mockResolvedValue({ ...parsed, status: 'CANCELLED' })
    const buttons = wrapper.findAll('[data-ai-action-confirmation] button')

    await buttons[1].trigger('click')
    await flushPromises()
    expect(apiMocks.cancelAIAction).toHaveBeenCalledTimes(1)
    expect(apiMocks.executeAIAction).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('操作已取消，未修改计划草案')
  })

  it('fails closed when the tool result contains hidden canonical action data', async () => {
    const unsafe = {
      ...confirmationData(),
      normalized_action_json: '{"secret":"must-not-render"}',
    }
    const store = usableStore()
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'tool.completed', {
        tool_call_id: 'unsafe-confirmation',
        tool_name: 'injection_scheduling.propose_apply',
        status: 'completed',
        result: {
          ok: true,
          tool_name: 'injection_scheduling.propose_apply',
          data: unsafe,
          error: null,
          metadata: {},
        },
      }))
      options.onEvent(event(2, 'response.completed', {}))
      return event(2, 'response.completed', {})
    })
    await store.sendMessage('准备应用', null)
    expect(store.businessResults).toEqual([])
  })
})

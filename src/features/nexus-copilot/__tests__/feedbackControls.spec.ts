import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const feedbackMocks = vi.hoisted(() => ({
  submitAIFeedback: vi.fn(),
}))

vi.mock('@/api/aiFeedback', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/aiFeedback')>(),
  ...feedbackMocks,
}))

import FeedbackControls from '../components/FeedbackControls.vue'

function response() {
  return {
    schema_version: 'ai-feedback-v1' as const,
    id: 'aifb-00000000000000000000000000000000',
    target_type: 'RESPONSE' as const,
    target_id: 'request-feedback-0001',
    rating: 'HELPFUL' as const,
    issue_category: 'NONE' as const,
    status: 'SUBMITTED' as const,
    auto_applied_to_prompt_or_knowledge: false as const,
  }
}

function render() {
  return mount(FeedbackControls, {
    props: {
      factoryId: 'huaxing',
      targetType: 'RESPONSE',
      targetId: 'request-feedback-0001',
    },
    global: {
      stubs: {
        ThumbsUp: true,
        ThumbsDown: true,
      },
    },
  })
}

beforeEach(() => {
  feedbackMocks.submitAIFeedback.mockReset()
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'feedback-uuid-0001') })
})

describe('NIF-17 feedback controls', () => {
  it('submits helpful feedback with a stable idempotency key', async () => {
    feedbackMocks.submitAIFeedback.mockResolvedValue(response())
    const wrapper = render()

    await wrapper.get('button[aria-label="回答有帮助"]').trigger('click')
    await flushPromises()

    expect(feedbackMocks.submitAIFeedback).toHaveBeenCalledWith({
      factoryId: 'huaxing',
      targetType: 'RESPONSE',
      targetId: 'request-feedback-0001',
      rating: 'HELPFUL',
      issueCategory: 'NONE',
      comment: '',
      idempotencyKey: 'feedback-feedback-uuid-0001',
    })
    expect(wrapper.text()).toContain('只进入人工审核')
    expect(wrapper.text()).toContain('不会自动修改 Prompt 或知识')
  })

  it('collects a category and optional correction without auto-applying it', async () => {
    feedbackMocks.submitAIFeedback.mockResolvedValue({
      ...response(),
      rating: 'NOT_HELPFUL',
      issue_category: 'WRONG_ARGUMENTS',
    })
    const wrapper = render()

    await wrapper.get('button[aria-label="回答没有帮助"]').trigger('click')
    await wrapper.get('select').setValue('WRONG_ARGUMENTS')
    await wrapper.get('textarea').setValue('厂区和日期范围需要纠正')
    const submit = wrapper.findAll('button').find((button) => button.text() === '提交反馈')
    expect(submit).toBeDefined()
    await submit!.trigger('click')
    await flushPromises()

    expect(feedbackMocks.submitAIFeedback).toHaveBeenCalledWith(expect.objectContaining({
      rating: 'NOT_HELPFUL',
      issueCategory: 'WRONG_ARGUMENTS',
      comment: '厂区和日期范围需要纠正',
    }))
    expect(wrapper.text()).toContain('不会自动修改 Prompt 或知识')
  })

  it('shows a recoverable error and reuses the same request key on retry', async () => {
    feedbackMocks.submitAIFeedback
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(response())
    const wrapper = render()

    await wrapper.get('button[aria-label="回答有帮助"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('反馈暂未保存')
    await wrapper.get('button[aria-label="回答有帮助"]').trigger('click')
    await flushPromises()

    expect(feedbackMocks.submitAIFeedback).toHaveBeenCalledTimes(2)
    expect(feedbackMocks.submitAIFeedback.mock.calls[0]?.[0].idempotencyKey).toBe(
      feedbackMocks.submitAIFeedback.mock.calls[1]?.[0].idempotencyKey,
    )
  })
})

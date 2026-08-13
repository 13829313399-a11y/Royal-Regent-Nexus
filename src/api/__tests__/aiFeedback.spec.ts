import { describe, expect, it, vi } from 'vitest'

const httpMocks = vi.hoisted(() => ({
  post: vi.fn(),
}))

vi.mock('@/lib/http', () => ({
  http: httpMocks,
}))

import { submitAIFeedback } from '@/api/aiFeedback'

describe('AI feedback API', () => {
  it('maps client fields to the strict metadata-only v1 contract', async () => {
    const data = {
      schema_version: 'ai-feedback-v1' as const,
      id: 'aifb-00000000000000000000000000000000',
      target_type: 'MESSAGE' as const,
      target_id: 'aimsg-00000000000000000000000000000000',
      rating: 'NOT_HELPFUL' as const,
      issue_category: 'UNSUPPORTED_CLAIM' as const,
      status: 'SUBMITTED' as const,
      auto_applied_to_prompt_or_knowledge: false as const,
    }
    httpMocks.post.mockResolvedValue({ data })

    await expect(submitAIFeedback({
      factoryId: 'huaxing',
      targetType: 'MESSAGE',
      targetId: data.target_id,
      rating: 'NOT_HELPFUL',
      issueCategory: 'UNSUPPORTED_CLAIM',
      comment: '结论没有对应证据',
      idempotencyKey: 'feedback-request-0001',
    })).resolves.toEqual(data)
    expect(httpMocks.post).toHaveBeenCalledWith('/ai/feedback', {
      factory_id: 'huaxing',
      target_type: 'MESSAGE',
      target_id: data.target_id,
      rating: 'NOT_HELPFUL',
      issue_category: 'UNSUPPORTED_CLAIM',
      comment: '结论没有对应证据',
      idempotency_key: 'feedback-request-0001',
    })
  })
})

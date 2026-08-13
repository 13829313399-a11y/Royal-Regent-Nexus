import { http } from '@/lib/http'

export type AIFeedbackRating = 'HELPFUL' | 'NOT_HELPFUL'
export type AIFeedbackIssueCategory =
  | 'NONE'
  | 'INCORRECT'
  | 'MISSING_CONTEXT'
  | 'WRONG_TOOL'
  | 'WRONG_ARGUMENTS'
  | 'UNSUPPORTED_CLAIM'
  | 'PERMISSION'
  | 'PREVIEW_MISLABEL'
  | 'UNSAFE'
  | 'OTHER'

export interface AIFeedbackData {
  schema_version: 'ai-feedback-v1'
  id: string
  target_type: 'RESPONSE' | 'MESSAGE' | 'TASK' | 'ACTION'
  target_id: string
  rating: AIFeedbackRating
  issue_category: AIFeedbackIssueCategory
  status: 'SUBMITTED' | 'TRIAGED' | 'EVAL_CANDIDATE' | 'DISMISSED'
  auto_applied_to_prompt_or_knowledge: false
}

export async function submitAIFeedback(input: {
  factoryId: string
  targetType: 'RESPONSE' | 'MESSAGE' | 'TASK' | 'ACTION'
  targetId: string
  rating: AIFeedbackRating
  issueCategory: AIFeedbackIssueCategory
  comment: string
  idempotencyKey: string
}) {
  const { data } = await http.post<AIFeedbackData>('/ai/feedback', {
    factory_id: input.factoryId,
    target_type: input.targetType,
    target_id: input.targetId,
    rating: input.rating,
    issue_category: input.issueCategory,
    comment: input.comment,
    idempotency_key: input.idempotencyKey,
  })
  return data
}

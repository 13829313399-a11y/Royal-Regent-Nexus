import type { AsyncFeedback, AsyncFeedbackPhase, AsyncFeedbackTone, AsyncOperation } from '../types'

export function createAsyncFeedback(
  operation: AsyncOperation,
  phase: AsyncFeedbackPhase,
  tone: AsyncFeedbackTone,
  message: string,
): AsyncFeedback {
  return { operation, phase, tone, message, occurredAt: new Date().toISOString() }
}

export function shouldShowFeedbackToast(feedback: AsyncFeedback | null, hasRevisionConflict: boolean) {
  if (!feedback?.message || feedback.phase === 'idle' || feedback.phase === 'pending') return false
  if (hasRevisionConflict) return false
  if (feedback.operation === 'initial-load' || feedback.operation === 'poll' || feedback.operation === 'auto-generate') return false
  if (feedback.phase === 'failed' && ['refresh', 'publish', 'auto-apply'].includes(feedback.operation)) return false
  return true
}

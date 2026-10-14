import { createRandomUuid } from '@/lib/randomUuid'

export interface OrderSubmission {
  requestId: string
  payloadFingerprint: string
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => [key, canonical(item)]))
  }
  return value
}

/** Until success or explicit discard, changed retries must never silently create a second order. */
export function orderSubmissionFor(payload: object, previous: OrderSubmission | null): OrderSubmission {
  const payloadFingerprint = JSON.stringify(canonical(payload))
  return previous?.payloadFingerprint === payloadFingerprint ? previous
    : { requestId: previous?.requestId ?? createRandomUuid(), payloadFingerprint }
}

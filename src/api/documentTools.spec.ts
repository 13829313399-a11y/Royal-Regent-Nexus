import { afterEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/lib/http'
import { documentTools } from './documentTools'

vi.mock('@/lib/http', () => ({ http: { post: vi.fn() } }))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('document tool requests on HTTP origins', () => {
  it('creates distinct conversion and package request IDs without randomUUID', async () => {
    const getRandomValues = crypto.getRandomValues.bind(crypto)
    vi.stubGlobal('crypto', { getRandomValues })
    vi.mocked(http.post).mockResolvedValue({ data: { job_id: 'job' } })

    await documentTools.create('source', 'word_to_pdf', { ai_mode: 'off' }, 'batch')
    await documentTools.create('source', 'word_to_pdf', { ai_mode: 'off' }, 'batch')
    await documentTools.package(['artifact'])

    const payloads = vi.mocked(http.post).mock.calls.map(([, payload]) => payload)
    const ids = payloads.map(payload => (payload as { client_request_id: string }).client_request_id)
    expect(new Set(ids).size).toBe(3)
    for (const id of ids) expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(payloads[0]).toMatchObject({ source_id: 'source', operation: 'word_to_pdf', batch_id: 'batch' })
    expect(payloads[2]).toMatchObject({ artifact_ids: ['artifact'] })
  })
})

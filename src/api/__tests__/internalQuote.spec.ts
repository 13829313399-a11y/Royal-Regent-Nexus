import { describe, expect, it, vi } from 'vitest'
import { createInternalQuoteApi, type InternalQuoteHttpClient } from '@/api/internalQuote'

function client() {
  return {
    get: vi.fn(async () => ({ data: [] })),
    post: vi.fn(async () => ({ data: { id: 'created' } })),
    put: vi.fn(async () => ({ data: { id: 'updated' } })),
  } satisfies InternalQuoteHttpClient
}

describe('internal quote API adapter', () => {
  it('requests expanded factory list and scoped business-owner choices', async () => {
    const http = client()
    const api = createInternalQuoteApi(http)

    await api.list('huaxing', { status: 'drafting', keyword: 'IQ-HX' })
    await api.listBusinessOwners('huaxing')

    expect(http.get).toHaveBeenNthCalledWith(1, '/internal-quotes', {
      params: {
        factory_id: 'huaxing',
        include_sections: true,
        status: 'drafting',
        keyword: 'IQ-HX',
      },
    })
    expect(http.get).toHaveBeenNthCalledWith(2, '/internal-quotes/business-owners', {
      params: { factory_id: 'huaxing' },
    })
  })

  it('uses the canonical create, clone and detail-enrichment endpoints', async () => {
    const http = client()
    const api = createInternalQuoteApi(http)
    const createPayload = {
      factory_id: 'huaxing', workshop_code: 'huaxing-workshop', workshop_name: '华兴',
      quote_no: 'IQ-1', product_name: '产品', customer: 'Disney', qty: 1000,
      version_label: 'V1', initiator_department: 'engineering' as const,
      business_owner_id: 'owner-1', business_owner_name: '负责人', target_date: '', remark: '',
    }

    await api.create(createPayload)
    await api.clone('quote-1', {
      quote_no: 'IQ-2', version_label: 'V2', business_owner_id: 'owner-1',
      business_owner_name: '负责人', target_date: '', remark: '',
    })
    await api.get('quote-1')
    await api.getTimeline('quote-1')
    await api.getReferenceSnapshot('quote-1')
    await api.getSummary('quote-1')
    await api.listAttachments('quote-1')
    await api.listExports('quote-1')

    expect(http.post).toHaveBeenNthCalledWith(1, '/internal-quotes', createPayload)
    expect(http.post).toHaveBeenNthCalledWith(2, '/internal-quotes/quote-1/clone', expect.objectContaining({ quote_no: 'IQ-2' }))
    expect(http.get.mock.calls.map(([url]) => url)).toEqual([
      '/internal-quotes/quote-1',
      '/internal-quotes/quote-1/timeline',
      '/internal-quotes/quote-1/reference-snapshot',
      '/internal-quotes/quote-1/summary',
      '/internal-quotes/quote-1/attachments',
      '/internal-quotes/quote-1/exports',
    ])
  })

  it('uses revision-safe section, file and final-release endpoints', async () => {
    const http = client()
    const api = createInternalQuoteApi(http)
    const file = new File(['xlsx'], '工程.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })

    await api.saveSection('quote-1', 'engineering', 4, { molds: [] }, '修正')
    await api.submitSection('quote-1', 'engineering', 5)
    await api.reviewSection('quote-1', 'engineering', 6, 'reject', '资料不全')
    await api.requestSectionNa('quote-1', 'engineering', 7, '无需工程')
    await api.reopenSection('quote-1', 'engineering', 8, '成本变化')
    await api.previewImport('quote-1', 'mold', file)
    await api.confirmImport('quote-1', 'batch-1', 9, 'replace')
    await api.uploadAttachment('quote-1', 'engineering', file)
    await api.submitFinal('quote-1', 3)
    await api.reviewFinal('quote-1', 4, 'approve')
    await api.createExport('quote-1')

    expect(http.put).toHaveBeenCalledWith('/internal-quotes/quote-1/sections/engineering', { revision: 4, payload: { molds: [] }, reason: '修正' })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/sections/engineering/submit', { revision: 5 })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/sections/engineering/review', { revision: 6, decision: 'reject', reason: '资料不全' })
    const formCalls = http.post.mock.calls.filter(([, data]) => data instanceof FormData)
    expect(formCalls).toHaveLength(2)
    expect((formCalls[0][1] as FormData).get('file')).toBe(file)
    expect((formCalls[1][1] as FormData).get('department')).toBe('engineering')
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/final-submit', { revision: 3 })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/final-review', { revision: 4, decision: 'approve', reason: '' })
  })
})

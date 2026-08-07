import { describe, expect, it, vi } from 'vitest'
import { createInternalQuoteApi, type InternalQuoteHttpClient } from '@/api/internalQuote'
import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

function client() {
  return {
    get: vi.fn(async () => ({ data: [] })),
    post: vi.fn(async () => ({ data: { id: 'created' } })),
    patch: vi.fn(async () => ({ data: { id: 'patched' } })),
    put: vi.fn(async () => ({ data: { id: 'updated' } })),
    delete: vi.fn(async () => ({ data: undefined })),
  } satisfies InternalQuoteHttpClient
}

describe('internal quote API adapter', () => {
  it('requests expanded factory list and scoped business-owner choices', async () => {
    const http = client()
    const api = createInternalQuoteApi(http)

    await api.list('huaxing', { status: 'drafting', keyword: 'IQ-HX', customer: 'Disney', page: 2, pageSize: 10 })
    await api.getDashboard('huaxing', 'month')
    await api.listBusinessOwners('huaxing')

    expect(http.get).toHaveBeenNthCalledWith(1, '/internal-quotes', {
      params: {
        factory_id: 'huaxing',
        include_sections: true,
        page: 2,
        page_size: 10,
        status: 'drafting',
        keyword: 'IQ-HX',
        customer: 'Disney',
      },
    })
    expect(http.get).toHaveBeenNthCalledWith(2, '/internal-quotes/dashboard', {
      params: { factory_id: 'huaxing', period: 'month' },
    })
    expect(http.get).toHaveBeenNthCalledWith(3, '/internal-quotes/business-owners', {
      params: { factory_id: 'huaxing' },
    })
  })

  it('maps UI status names to backend workflow statuses', async () => {
    const http = client()
    const api = createInternalQuoteApi(http)

    await api.list('huaxing', { status: 'pending_review' })
    await api.list('huaxing', { status: 'fully_approved' })
    await api.list('huaxing', { status: 'final_pending' })
    await api.list('huaxing', { status: 'released' })

    expect(http.get.mock.calls.map(([, config]) => config?.params.status)).toEqual([
      'section_reviewing',
      'ready_for_final_review',
      'final_reviewing',
      'fully_approved',
    ])
  })

  it('uses the canonical create, clone and detail-enrichment endpoints', async () => {
    const http = client()
    const api = createInternalQuoteApi(http)
    const createPayload = {
      factory_id: 'huaxing', workshop_code: 'huaxing-workshop', workshop_name: '华兴',
      quote_no: 'IQ-1', product_name: '产品', customer: 'Disney', qty: 1000,
      version_label: 'V1', initiator_department: 'engineering' as const,
      business_owner_id: 'owner-1', business_owner_name: '负责人', target_customer_price: 'USD 3.50', target_date: '', remark: '',
      participating_sections: ['sales', 'engineering', 'electronic', 'assembly'] as InternalQuoteSectionCode[],
    }

    await api.create(createPayload)
    await api.clone('quote-1', {
      quote_no: 'IQ-2', version_label: 'V2', business_owner_id: 'owner-1',
      business_owner_name: '负责人', target_customer_price: 'USD 3.50', target_date: '', remark: '',
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
    await api.previewSection('quote-1', 'engineering', 4, { molds: [{ item: '主模' }] })
    await api.submitSection('quote-1', 'engineering', 5)
    await api.reviewSection('quote-1', 'engineering', 6, 'reject', '资料不全')
    await api.requestSectionNa('quote-1', 'engineering', 7, '无需工程')
    await api.reopenSection('quote-1', 'engineering', 8, '成本变化')
    await api.addParticipation('quote-1', 3, ['painting', 'sewing'])
    await api.removeParticipation('quote-1', 4, ['painting'])
    await api.updateReferenceFx('quote-1', 3, '0.9', '7.9')
    await api.previewImport('quote-1', 'mold', file)
    await api.downloadImportTemplate('quote-1', 'mold')
    await api.confirmImport('quote-1', 'batch-1', 9)
    await api.uploadAttachment('quote-1', 'engineering', file)
    await api.deleteImportAttachment('quote-1', 'attachment-1', 10)
    await api.submitFinal('quote-1', 3)
    await api.reviewFinal('quote-1', 4, 'approve')
    await api.createExport('quote-1')
    await api.downloadEngineeringWorkbook('quote-1')

    expect(http.put).toHaveBeenCalledWith('/internal-quotes/quote-1/sections/engineering', { revision: 4, payload: { molds: [] }, reason: '修正' })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/sections/engineering/preview', { revision: 4, payload: { molds: [{ item: '主模' }] } })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/sections/engineering/submit', { revision: 5 })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/sections/engineering/review', { revision: 6, decision: 'reject', reason: '资料不全' })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/participation', { revision: 3, add_sections: ['painting', 'sewing'] })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/participation/remove', { revision: 4, remove_sections: ['painting'] })
    expect(http.put).toHaveBeenCalledWith('/internal-quotes/quote-1/reference-snapshot/fx', { revision: 3, rmb_hkd: '0.9', hkd_usd: '7.9' })
    expect(http.get).toHaveBeenCalledWith('/internal-quotes/quote-1/imports/mold/template', {
      responseType: 'blob',
      timeout: 60_000,
    })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/imports/batch-1/confirm', { revision: 9 })
    expect(http.delete).toHaveBeenCalledWith('/internal-quotes/quote-1/attachments/attachment-1', {
      params: { revision: 10 },
    })
    const formCalls = http.post.mock.calls.filter(([, data]) => data instanceof FormData)
    expect(formCalls).toHaveLength(2)
    expect((formCalls[0][1] as FormData).get('file')).toBe(file)
    expect((formCalls[1][1] as FormData).get('department')).toBe('engineering')
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/final-submit', { revision: 3 })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/final-review', { revision: 4, decision: 'approve', reason: '' })
    expect(http.post).toHaveBeenCalledWith(
      '/internal-quotes/quote-1/engineering-data/export',
      undefined,
      { responseType: 'blob' },
    )
  })

  it('uses the factory-scoped pricing-baseline read and revision-safe update endpoints', async () => {
    const http = client()
    const api = createInternalQuoteApi(http)
    const payload = {
      revision: 3,
      workshop_name: '华兴',
      material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '8.50' }],
      machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '940' }],
      freight_routes: [
        { route_key: 'hk40', route_name: 'HK 40 柜', capacity_key: 'cap_40' as const, freight_hkd: '8000', lifting_hkd: '1200' },
      ],
    }

    await api.getPricingBaseline('huaxing', 'huaxing-workshop')
    await api.updatePricingBaseline('huaxing', 'huaxing-workshop', payload)

    expect(http.get).toHaveBeenCalledWith('/internal-quotes/pricing-baseline', {
      params: { factory_id: 'huaxing', workshop_code: 'huaxing-workshop' },
    })
    expect(http.put).toHaveBeenCalledWith('/internal-quotes/pricing-baseline', payload, {
      params: { factory_id: 'huaxing', workshop_code: 'huaxing-workshop' },
    })
  })

  it('uses revision-safe header update and archive endpoints', async () => {
    const http = client()
    const api = createInternalQuoteApi(http)
    const payload = {
      revision: 4,
      product_name: '新产品名',
      customer: 'Disney',
      qty: 1200,
      business_owner_id: 'owner-1',
      business_owner_name: '负责人',
      target_customer_price: 'USD 3.50',
      target_date: '2026-08-01',
      remark: '更新资料',
    }

    await api.updateHeader('quote-1', payload)
    await api.archiveQuote('quote-1', 5, '项目取消')

    expect(http.patch).toHaveBeenCalledWith('/internal-quotes/quote-1', payload)
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/quote-1/archive', {
      revision: 5,
      reason: '项目取消',
    })
  })

  it('uses factory-scoped and revision-safe customer maintenance endpoints', async () => {
    const http = client()
    const api = createInternalQuoteApi(http)

    await api.listCustomers('huaxing')
    await api.createCustomer('huaxing', 'Disney')
    await api.updateCustomer('customer-1', 'Disney Consumer', 2)
    await api.deleteCustomer('customer-1', 3)

    expect(http.get).toHaveBeenCalledWith('/internal-quotes/customers', {
      params: { factory_id: 'huaxing' },
    })
    expect(http.post).toHaveBeenCalledWith('/internal-quotes/customers', { name: 'Disney' }, {
      params: { factory_id: 'huaxing' },
    })
    expect(http.put).toHaveBeenCalledWith('/internal-quotes/customers/customer-1', {
      name: 'Disney Consumer', revision: 2,
    })
    expect(http.delete).toHaveBeenCalledWith('/internal-quotes/customers/customer-1', {
      params: { revision: 3 },
    })
  })
})

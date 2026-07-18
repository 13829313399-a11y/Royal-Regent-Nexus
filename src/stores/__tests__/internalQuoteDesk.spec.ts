import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApiInternalQuote, ApiInternalQuoteSection } from '@/api/internalQuote'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

const apiMock = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  create: vi.fn(),
  clone: vi.fn(),
  addParticipation: vi.fn(),
  listBusinessOwners: vi.fn(),
  getPricingBaseline: vi.fn(),
  updatePricingBaseline: vi.fn(),
  getTimeline: vi.fn(),
  getReferenceSnapshot: vi.fn(),
  getSummary: vi.fn(),
  listAttachments: vi.fn(),
  listExports: vi.fn(),
  saveSection: vi.fn(),
  submitSection: vi.fn(),
  reviewSection: vi.fn(),
  requestSectionNa: vi.fn(),
  reopenSection: vi.fn(),
  syncReferenceSnapshot: vi.fn(),
  updateReferenceFx: vi.fn(),
  previewImport: vi.fn(),
  confirmImport: vi.fn(),
  uploadAttachment: vi.fn(),
  downloadAttachment: vi.fn(),
  createExport: vi.fn(),
  downloadExport: vi.fn(),
  submitFinal: vi.fn(),
  reviewFinal: vi.fn(),
  listVersionCandidates: vi.fn(),
  compareVersion: vi.fn(),
}))

vi.mock('@/api/internalQuote', () => ({ internalQuoteApi: apiMock }))

const sectionCodes = ['sales', 'engineering', 'electronic', 'molding', 'painting', 'slush', 'sewing', 'assembly']

function section(code: string, index: number): ApiInternalQuoteSection {
  return {
    id: `quote-1-${code}`,
    department: code,
    department_name: `${code}-name`,
    status: index === 0 ? 'approved' : 'draft',
    payload: { source: 'backend' },
    calculation: {
      totals: { total_hkd: index === 0 ? '12.5000' : '0.0000' },
      line_breakdown: index === 0 ? [{ kind: 'tax', item: '后端行', amount_hkd: '12.5000' }] : [],
      warnings: [],
    },
    calculation_status: index === 0 ? 'valid' : 'pending',
    calculation_hash: '',
    calculation_formula_version: 'rr2-2026-v1',
    calculation_reference_snapshot_id: 'REF-1',
    calculated_at: '2026-07-16 10:00',
    dependency_hash: '',
    dependency_status: 'current',
    revision: index === 0 ? 4 : 1,
    is_required: true,
    filled_by: '经办人',
    filled_at: '',
    submitted_by: index === 0 ? '提交人' : '',
    submitted_by_id: index === 0 ? 'submitter' : '',
    submitted_at: '',
    reviewed_by: index === 0 ? '审核人' : '',
    reviewed_at: '',
    review_comment: '',
    updated_at: '2026-07-16 10:00',
  }
}

function quote(overrides: Partial<ApiInternalQuote> = {}): ApiInternalQuote {
  return {
    id: 'quote-1',
    factory_id: 'huaxing',
    workshop_code: 'huaxing-workshop',
    workshop_name: '华兴',
    quote_no: 'IQ-HX-REAL-001',
    product_name: '真实接口产品',
    customer: 'Disney',
    qty: 1000,
    version_label: 'V1',
    status: 'section_reviewing',
    initiator_department: 'engineering',
    business_owner_id: 'owner-1',
    business_owner_name: '业务负责人',
    target_date: '2026-08-31',
    remark: '',
    module_version: 'p4',
    reference_snapshot_id: 'REF-1',
    formula_version: 'rr2-2026-v1',
    header_revision: 2,
    cloned_from_quote_id: '',
    archived_by: '',
    archived_at: '',
    archive_reason: '',
    final_release_status: '',
    final_submission_revision: 0,
    final_submission_manifest: {},
    final_submitted_by: '',
    final_submitted_by_name: '',
    final_submitted_at: '',
    final_reviewed_by: '',
    final_reviewed_by_name: '',
    final_reviewed_at: '',
    final_review_comment: '',
    final_release_revision: 0,
    final_release_invalidated_at: '',
    final_release_invalidation_reason: '',
    created_by: 'engineer-1',
    created_by_name: '工程经办',
    created_at: '2026-07-16 09:00',
    updated_at: '2026-07-16 10:00',
    sections: sectionCodes.map(section),
    ...overrides,
  }
}

describe('internal quote desk real API state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMock.list.mockResolvedValue([quote()])
    apiMock.listBusinessOwners.mockResolvedValue([{ id: 'owner-1', username: 'owner', display_name: '业务负责人' }])
    apiMock.getPricingBaseline.mockResolvedValue({
      factory_id: 'huaxing', workshop_code: 'huaxing-workshop', workshop_name: '华兴', revision: 0,
      source_type: 'default', updated_by: '', updated_by_name: '', updated_at: '',
      material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '8.50' }],
      machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '940' }],
    })
    apiMock.updatePricingBaseline.mockResolvedValue({
      factory_id: 'huaxing', workshop_code: 'huaxing-workshop', workshop_name: '华兴', revision: 1,
      source_type: 'custom', updated_by: 'supervisor', updated_by_name: '业务主管', updated_at: '2026-07-18 14:00',
      material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '9.25' }],
      machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '999' }],
    })
    apiMock.get.mockResolvedValue(quote())
    apiMock.getTimeline.mockResolvedValue({
      business_events: [{ id: 'audit-1', department: 'sales', actor_id: 'u1', actor_name: '业务经办', action: 'create', detail: '', old_revision: null, new_revision: 1, reason: '', created_at: '2026-07-16 09:00' }],
      view_records: [{ id: 'view-1', department: '', actor_id: 'u2', actor_name: '浏览人', action: 'view', detail: 'Chrome', old_revision: null, new_revision: null, reason: '', created_at: '2026-07-16 10:00' }],
    })
    apiMock.getReferenceSnapshot.mockResolvedValue({ snapshot: { fx: { rmb_hkd: '0.86', hkd_usd: '7.81', rmb_usd: '7.76' } } })
    apiMock.getSummary.mockResolvedValue({ factory_price_hkd: '88.8000' })
    apiMock.listAttachments.mockResolvedValue([{ id: 'attachment-1', quote_id: 'quote-1', department: 'sales', file_name: '核价依据.xlsx', content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', size_bytes: 128, sha256: 'attachment-sha', uploaded_by: 'u1', uploaded_by_name: '业务经办', uploaded_at: '2026-07-16 10:30' }])
    apiMock.listExports.mockResolvedValue([{ id: 'export-1', file_name: '最终放行.xlsx', template_version: 'internal-quote-p4-v1', release_stage: 'p4_final_approved', exported_by: 'u3', exported_by_name: '终审主管', exported_at: '2026-07-16 11:00', sha256: 'abc', status: 'current' }])
    apiMock.create.mockResolvedValue(quote({ id: 'created-1', quote_no: 'IQ-CREATED' }))
    apiMock.clone.mockResolvedValue(quote({ id: 'clone-1', quote_no: 'IQ-CLONE', status: 'drafting', sections: sectionCodes.map((code, index) => ({ ...section(code, index), status: 'draft', revision: 1 })) }))
    apiMock.saveSection.mockResolvedValue({ ...section('engineering', 1), revision: 2, payload: { molds: [{ item: '模具A' }] } })
    apiMock.addParticipation.mockResolvedValue(quote())
    apiMock.updateReferenceFx.mockResolvedValue(quote({ header_revision: 3, reference_snapshot_id: 'REF-2' }))
  })

  it('loads the factory list with real section progress and owner choices', async () => {
    const store = useInternalQuoteDeskStore()
    await Promise.all([store.loadQuotes('huaxing'), store.loadBusinessOwners('huaxing')])

    expect(apiMock.list).toHaveBeenCalledWith('huaxing')
    expect(store.quotes[0].sections).toHaveLength(8)
    expect(store.quotes[0].sections[0].lines[0]).toMatchObject({ item: '后端行', amountHkd: 12.5 })
    expect(store.businessOwners).toEqual([{ id: 'owner-1', username: 'owner', displayName: '业务负责人' }])
  })

  it('enriches detail with authoritative summary, snapshot, timeline, attachments and exports', async () => {
    const store = useInternalQuoteDeskStore()
    const loaded = await store.loadQuote('quote-1')

    expect(loaded?.factoryPriceHkd).toBe(88.8)
    expect(loaded?.fxRmbHkd).toBe(0.86)
    expect(loaded?.sections[0].attachments[0]).toMatchObject({ id: 'attachment-1', fileName: '核价依据.xlsx', sha256: 'attachment-sha' })
    expect(loaded?.exports[0]).toMatchObject({ id: 'export-1', status: 'current' })
    expect(loaded?.activities.map((item) => item.action)).toEqual(['create'])
    expect(loaded?.viewRecords.map((item) => item.viewer)).toEqual(['浏览人'])
  })

  it('creates and clones with a stable business-owner identity', async () => {
    const store = useInternalQuoteDeskStore()
    const payload = {
      quoteNo: 'IQ-CREATED', productName: '产品', customer: 'Disney', versionLabel: 'V1',
      initiatorDepartment: 'engineering' as const, businessOwnerId: 'owner-1', businessOwner: '业务负责人',
      targetCustomerPrice: 'USD 3.50', quantity: 1000, targetDate: '2026-08-31', remark: '',
      participatingSections: ['sales', 'engineering', 'electronic', 'assembly'] as InternalQuoteSectionCode[],
    }
    const created = await store.createQuote(payload)
    const cloned = await store.cloneQuote(created.id, { ...payload, quoteNo: 'IQ-CLONE' })

    expect(apiMock.create.mock.calls[0][0]).toMatchObject({ factory_id: 'huaxing', business_owner_id: 'owner-1', target_customer_price: 'USD 3.50', participating_sections: ['sales', 'engineering', 'electronic', 'assembly'] })
    expect(apiMock.clone).toHaveBeenCalledWith('created-1', expect.objectContaining({ quote_no: 'IQ-CLONE', business_owner_name: '业务负责人', target_customer_price: 'USD 3.50', participating_sections: ['sales', 'engineering', 'electronic', 'assembly'] }))
    expect(cloned.id).toBe('clone-1')
  })

  it('loads and saves the pricing baseline with its optimistic revision', async () => {
    const store = useInternalQuoteDeskStore()
    const loaded = await store.loadPricingBaseline('huaxing', 'huaxing-workshop')
    const payload = {
      revision: loaded?.revision ?? 0,
      workshop_name: '华兴',
      material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '9.25' }],
      machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '999' }],
    }
    const saved = await store.updatePricingBaseline('huaxing', 'huaxing-workshop', payload)

    expect(apiMock.getPricingBaseline).toHaveBeenCalledWith('huaxing', 'huaxing-workshop')
    expect(apiMock.updatePricingBaseline).toHaveBeenCalledWith('huaxing', 'huaxing-workshop', payload)
    expect(saved.revision).toBe(1)
    expect(store.pricingBaseline?.material_prices[0].price_hkd_lb).toBe('9.25')
  })

  it('writes section payloads through the revision-safe API and keeps comments server-only', async () => {
    const store = useInternalQuoteDeskStore()
    await store.saveSection('quote-1', 'engineering', 1, { molds: [{ item: '模具A' }] }, '修正模具')
    await store.addParticipation('quote-1', 2, ['painting'])

    expect(store.sectionEditingEnabled).toBe(true)
    expect(apiMock.saveSection).toHaveBeenCalledWith('quote-1', 'engineering', 1, { molds: [{ item: '模具A' }] }, '修正模具')
    expect(apiMock.addParticipation).toHaveBeenCalledWith('quote-1', 2, ['painting'])
    expect(apiMock.get).toHaveBeenCalledWith('quote-1')
    expect(() => store.addComment('quote-1', '本地评论')).toThrow('尚未提供协作评论接口')
  })

  it('updates quote-scoped FX through the optimistic header revision and reloads the snapshot', async () => {
    const store = useInternalQuoteDeskStore()
    await store.updateReferenceFx('quote-1', 2, '0.9', '7.9')

    expect(apiMock.updateReferenceFx).toHaveBeenCalledWith('quote-1', 2, '0.9', '7.9')
    expect(apiMock.get).toHaveBeenCalledWith('quote-1')
    expect(apiMock.getReferenceSnapshot).toHaveBeenCalledWith('quote-1')
  })
})

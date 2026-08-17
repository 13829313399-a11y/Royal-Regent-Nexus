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
  removeParticipation: vi.fn(),
  updateHeader: vi.fn(),
  archiveQuote: vi.fn(),
  listBusinessOwners: vi.fn(),
  listCustomers: vi.fn(),
  createCustomer: vi.fn(),
  updateCustomer: vi.fn(),
  deleteCustomer: vi.fn(),
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
  updateReferenceMaterials: vi.fn(),
  previewImport: vi.fn(),
  confirmImport: vi.fn(),
  uploadAttachment: vi.fn(),
  downloadAttachment: vi.fn(),
  createExport: vi.fn(),
  downloadExport: vi.fn(),
  downloadEngineeringWorkbook: vi.fn(),
  submitFinal: vi.fn(),
  reviewFinal: vi.fn(),
  listVersionCandidates: vi.fn(),
  compareVersion: vi.fn(),
}))

vi.mock('@/api/internalQuote', () => ({ internalQuoteApi: apiMock }))

const sectionCodes = ['sales', 'engineering', 'electronic', 'molding', 'painting', 'slush', 'sewing', 'hair', 'assembly']

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

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('internal quote desk real API state', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    apiMock.list.mockResolvedValue([quote()])
    apiMock.listBusinessOwners.mockResolvedValue([{ id: 'owner-1', username: 'owner', display_name: '业务负责人' }])
    apiMock.listCustomers.mockResolvedValue([{
      id: 'customer-1', factory_id: 'huaxing', name: 'Disney', revision: 1,
      created_by: 'system', created_by_name: '系统迁移', created_at: '2026-07-21 10:00:00',
      updated_by: 'system', updated_by_name: '系统迁移', updated_at: '2026-07-21 10:00:00',
    }])
    apiMock.createCustomer.mockResolvedValue({
      id: 'customer-2', factory_id: 'huaxing', name: 'BuzzBee', revision: 1,
      created_by: 'supervisor', created_by_name: '业务主管', created_at: '2026-07-21 11:00:00',
      updated_by: 'supervisor', updated_by_name: '业务主管', updated_at: '2026-07-21 11:00:00',
    })
    apiMock.updateCustomer.mockResolvedValue({
      id: 'customer-2', factory_id: 'huaxing', name: 'BuzzBee Toys', revision: 2,
      created_by: 'supervisor', created_by_name: '业务主管', created_at: '2026-07-21 11:00:00',
      updated_by: 'supervisor', updated_by_name: '业务主管', updated_at: '2026-07-21 11:10:00',
    })
    apiMock.deleteCustomer.mockResolvedValue(undefined)
    apiMock.getPricingBaseline.mockResolvedValue({
      factory_id: 'huaxing', workshop_code: 'huaxing-workshop', workshop_name: '华兴', revision: 0,
      source_type: 'default', updated_by: '', updated_by_name: '', updated_at: '',
      material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '8.50' }],
      machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '940' }],
      freight_routes: [{ route_key: 'hk40', route_name: 'HK 40 柜', capacity_key: 'cap_40', freight_hkd: '8000', lifting_hkd: '0' }],
    })
    apiMock.updatePricingBaseline.mockResolvedValue({
      factory_id: 'huaxing', workshop_code: 'huaxing-workshop', workshop_name: '华兴', revision: 1,
      source_type: 'custom', updated_by: 'supervisor', updated_by_name: '业务主管', updated_at: '2026-07-18 14:00',
      material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '9.25' }],
      machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '999' }],
      freight_routes: [{ route_key: 'hk40', route_name: '香港 40 柜', capacity_key: 'cap_40', freight_hkd: '8200', lifting_hkd: '1200' }],
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
    apiMock.removeParticipation.mockResolvedValue(quote())
    apiMock.updateReferenceFx.mockResolvedValue(quote({ header_revision: 3, reference_snapshot_id: 'REF-2' }))
  })

  it('loads the factory list with real section progress and owner choices', async () => {
    const store = useInternalQuoteDeskStore()
    await Promise.all([store.loadQuotes('huaxing'), store.loadBusinessOwners('huaxing')])

    expect(apiMock.list).toHaveBeenCalledWith('huaxing')
    expect(store.quotes[0].sections.map((item) => item.code)).toEqual([
      'engineering', 'molding', 'assembly', 'painting', 'electronic', 'slush', 'sewing', 'hair', 'sales',
    ])
    expect(store.quotes[0].sections.find((item) => item.code === 'sales')?.lines[0]).toMatchObject({ item: '后端行', amountHkd: 12.5 })
    expect(store.businessOwners).toEqual([{ id: 'owner-1', username: 'owner', displayName: '业务负责人' }])
  })

  it('keeps only the requested quote page and exposes server pagination metadata', async () => {
    apiMock.list.mockResolvedValue({
      items: [quote({ id: 'page-2', quote_no: 'IQ-PAGE-2', customer: 'Disney' })],
      total: 14,
      page: 2,
      page_size: 10,
      total_pages: 2,
      customers: ['Disney', 'BuzzBee'],
    })
    const store = useInternalQuoteDeskStore()

    await store.loadQuotes('huaxing', { page: 2, pageSize: 10, customer: 'Disney' })

    expect(apiMock.list).toHaveBeenCalledWith('huaxing', { page: 2, pageSize: 10, customer: 'Disney' })
    expect(store.quotes.map((item) => item.id)).toEqual(['page-2'])
    expect(store.quoteListTotal).toBe(14)
    expect(store.quoteListPage).toBe(2)
    expect(store.quoteListPageSize).toBe(10)
    expect(store.quoteListTotalPages).toBe(2)
    expect(store.quoteListCustomers).toEqual(['Disney', 'BuzzBee'])
  })

  it('paginates a legacy unpaged array response instead of locking the list to one page', async () => {
    const legacyRows = Array.from({ length: 14 }, (_, index) => quote({
      id: `legacy-${index + 1}`,
      quote_no: `IQ-LEGACY-${index + 1}`,
      customer: index % 2 ? 'Disney' : 'BuzzBee',
    }))
    apiMock.list.mockResolvedValue(legacyRows)
    const store = useInternalQuoteDeskStore()

    await store.loadQuotes('huaxing', { page: 1, pageSize: 10 })
    expect(store.quotes).toHaveLength(10)
    expect(store.quoteListTotal).toBe(14)
    expect(store.quoteListPage).toBe(1)
    expect(store.quoteListTotalPages).toBe(2)

    await store.loadQuotes('huaxing', { page: 2, pageSize: 10 })
    expect(store.quotes.map((item) => item.id)).toEqual(['legacy-11', 'legacy-12', 'legacy-13', 'legacy-14'])
    expect(store.quoteListPage).toBe(2)
    expect(store.quoteListTotalPages).toBe(2)
  })

  it('enriches detail with authoritative summary, snapshot, timeline, attachments and exports', async () => {
    const store = useInternalQuoteDeskStore()
    const loaded = await store.loadQuote('quote-1')

    expect(loaded?.factoryPriceHkd).toBe(88.8)
    expect(loaded?.fxRmbHkd).toBe(0.86)
    expect(loaded?.sections.find((item) => item.code === 'sales')?.attachments[0]).toMatchObject({ id: 'attachment-1', fileName: '核价依据.xlsx', sha256: 'attachment-sha' })
    expect(loaded?.exports[0]).toMatchObject({ id: 'export-1', status: 'current' })
    expect(loaded?.activities.map((item) => item.action)).toEqual(['create'])
    expect(loaded?.viewRecords.map((item) => item.viewer)).toEqual(['浏览人'])
    expect(loaded?.rr2CostSummary.t1.map((item) => item.label)).toEqual(['货价', '进口料', '国内料', '吹气', '搪胶', '车发', '车衣', '五金', '电子', '马达', '吸塑', '胶袋'])
    expect(loaded?.rr2CostSummary.t2.map((item) => item.label)).toEqual(['彩盒/内咭', '未减税前码数', '减税后码数', '电池', '利宝', '电镀', '其他外购', '纸箱', '运费', '吊柜费', '杂项'])
    expect(loaded?.rr2CostSummary.t3.map((item) => item.label)).toEqual(['啤工', '喷油工', '油漆', '装配工', '不含人工成本', '人工比例', '毛利', '毛利率', '利润', '利润率', '总成本'])
    expect(loaded?.rr2CostSummary.t4.map((item) => item.label)).toEqual(['含税13%类成本', '人工类13%', '纸箱类', '含税1%', '搪胶类3%', '车发类13%', '车衣类13%', '吸塑类6%', '运费类9%', '含税13%类'])
    expect(loaded?.rr2CostSummary.t4.map((item) => item.ratePercent)).toEqual([null, null, null, .99, 3, 11.5, 11.5, 6, 8.26, 11.5])
  })

  it('does not publish a detail view when the authoritative summary fails', async () => {
    apiMock.getSummary.mockRejectedValueOnce(new Error('汇总服务不可用'))
    const store = useInternalQuoteDeskStore()

    const loaded = await store.loadQuote('quote-1')

    expect(loaded).toBeUndefined()
    expect(store.getQuoteById('quote-1')).toBeUndefined()
    expect(store.errorMessage).toContain('报价权威汇总读取不完整')
    expect(store.errorMessage).toContain('汇总服务不可用')
  })

  it('keeps the detail usable but reports optional attachment degradation', async () => {
    apiMock.listAttachments.mockRejectedValueOnce(new Error('附件服务超时'))
    const store = useInternalQuoteDeskStore()

    const loaded = await store.loadQuote('quote-1')

    expect(loaded?.factoryPriceHkd).toBe(88.8)
    expect(store.errorMessage).toContain('附件读取失败')
    expect(store.errorMessage).toContain('附件服务超时')
  })

  it('ignores an older detail response after navigating to another quote', async () => {
    const first = deferred<ApiInternalQuote>()
    apiMock.get.mockImplementation((quoteId: string) => (
      quoteId === 'quote-old'
        ? first.promise
        : Promise.resolve(quote({ id: 'quote-new', quote_no: 'IQ-NEW' }))
    ))
    const store = useInternalQuoteDeskStore()

    const oldRequest = store.loadQuote('quote-old')
    const fresh = await store.loadQuote('quote-new')
    first.resolve(quote({ id: 'quote-old', quote_no: 'IQ-OLD' }))
    const stale = await oldRequest

    expect(fresh?.id).toBe('quote-new')
    expect(stale).toBeUndefined()
    expect(store.getQuoteById('quote-new')?.quoteNo).toBe('IQ-NEW')
    expect(store.getQuoteById('quote-old')).toBeUndefined()
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

    expect(apiMock.create.mock.calls[0][0]).toMatchObject({ factory_id: 'huaxing', business_owner_id: 'owner-1', target_customer_price: 'USD 3.50', participating_sections: ['engineering', 'assembly', 'electronic', 'sales'], workflow_mode: 'whole_quote_review' })
    expect(apiMock.clone).toHaveBeenCalledWith('created-1', expect.objectContaining({ quote_no: 'IQ-CLONE', business_owner_name: '业务负责人', target_customer_price: 'USD 3.50', participating_sections: ['engineering', 'assembly', 'electronic', 'sales'], workflow_mode: 'whole_quote_review' }))
    expect(cloned.id).toBe('clone-1')
  })

  it('uploads create-time product documents to their assigned departments', async () => {
    const store = useInternalQuoteDeskStore()
    const engineeringFile = new File(['PK-engineering'], '模具映射.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const salesFile = new File(['%PDF-sales'], '客户资料.pdf', { type: 'application/pdf' })

    await store.createQuote({
      quoteNo: 'IQ-CREATED-DOCS', productName: '产品', customer: 'Disney', versionLabel: 'V1',
      initiatorDepartment: 'engineering', businessOwnerId: 'owner-1', businessOwner: '业务负责人',
      targetCustomerPrice: 'USD 3.50', quantity: 1000, targetDate: '2026-08-31', remark: '',
      participatingSections: ['sales', 'engineering', 'electronic', 'assembly'],
      products: [{
        productName: '产品', quantity: 1000, regionCode: '', imageFile: null,
        documentFiles: [
          { file: engineeringFile, department: 'engineering' },
          { file: salesFile, department: 'sales' },
        ],
      }],
    })

    expect(apiMock.uploadAttachment).toHaveBeenNthCalledWith(1, 'created-1', 'engineering', engineeringFile)
    expect(apiMock.uploadAttachment).toHaveBeenNthCalledWith(2, 'created-1', 'sales', salesFile)
  })

  it('loads and saves the pricing baseline with its optimistic revision', async () => {
    const store = useInternalQuoteDeskStore()
    const loaded = await store.loadPricingBaseline('huaxing', 'huaxing-workshop')
    const payload = {
      revision: loaded?.revision ?? 0,
      workshop_name: '华兴',
      material_prices: [{ material: 'ABS', grade: '750SW', price_hkd_lb: '9.25' }],
      machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '999' }],
      freight_routes: [{ route_key: 'hk40', route_name: '香港 40 柜', capacity_key: 'cap_40' as const, freight_hkd: '8200', lifting_hkd: '1200' }],
    }
    const saved = await store.updatePricingBaseline('huaxing', 'huaxing-workshop', payload)

    expect(apiMock.getPricingBaseline).toHaveBeenCalledWith('huaxing', 'huaxing-workshop')
    expect(apiMock.updatePricingBaseline).toHaveBeenCalledWith('huaxing', 'huaxing-workshop', payload)
    expect(saved.revision).toBe(1)
    expect(store.pricingBaseline?.material_prices[0].price_hkd_lb).toBe('9.25')
  })

  it('keeps factory customers revision-safe across create, rename and delete', async () => {
    const store = useInternalQuoteDeskStore()
    await store.loadCustomers('huaxing')
    const created = await store.createCustomer('huaxing', 'BuzzBee')
    const updated = await store.updateCustomer('huaxing', created!.id, 'BuzzBee Toys', created!.revision)
    await store.deleteCustomer('huaxing', updated!.id, updated!.revision)

    expect(apiMock.listCustomers).toHaveBeenCalledWith('huaxing')
    expect(apiMock.createCustomer).toHaveBeenCalledWith('huaxing', 'BuzzBee')
    expect(apiMock.updateCustomer).toHaveBeenCalledWith('customer-2', 'BuzzBee Toys', 1)
    expect(apiMock.deleteCustomer).toHaveBeenCalledWith('customer-2', 2)
    expect(store.factoryCustomers.map((item) => item.name)).toEqual(['Disney'])
  })

  it('writes section payloads through the revision-safe API and keeps comments server-only', async () => {
    const store = useInternalQuoteDeskStore()
    await store.saveSection('quote-1', 'engineering', 1, { molds: [{ item: '模具A' }] }, '修正模具')
    await store.addParticipation('quote-1', 2, ['painting'])
    await store.removeParticipation('quote-1', 3, ['painting'])

    expect(store.sectionEditingEnabled).toBe(true)
    expect(apiMock.saveSection).toHaveBeenCalledWith('quote-1', 'engineering', 1, { molds: [{ item: '模具A' }] }, '修正模具')
    expect(apiMock.addParticipation).toHaveBeenCalledWith('quote-1', 2, ['painting'])
    expect(apiMock.removeParticipation).toHaveBeenCalledWith('quote-1', 3, ['painting'])
    expect(apiMock.get).toHaveBeenCalledWith('quote-1')
    expect(() => store.addComment('quote-1', '本地评论')).toThrow('尚未提供协作评论接口')
  })

  it('keeps the saved miscellaneous ratio and selected markup tier after the authoritative refresh', async () => {
    const salesPayload = {
      shipping: {
        markup_x: 1.15,
        markup_tiers: [
          { moq: 3000, markup_x: 1.25 },
          { moq: 5000, markup_x: 1.20 },
          { moq: 10000, markup_x: 1.15 },
        ],
        selected_markup_moq: 10000,
        misc_ratio: .035,
      },
    }
    apiMock.saveSection.mockResolvedValue({
      ...section('sales', 0),
      revision: 5,
      payload: salesPayload,
    })
    const store = useInternalQuoteDeskStore()

    await store.saveSection('quote-1', 'sales', 4, salesPayload, '保存分段码数与杂项')

    const saved = store.getQuoteById('quote-1')!
    expect(saved.rr2CostSummary.shippingPricing.miscRatio).toBe(.035)
    expect(saved.rr2CostSummary.shippingPricing.activeMarkupMoq).toBe(10000)
    expect(saved.rr2CostSummary.shippingPricing.markup).toBe(1.15)
    expect(saved.rr2CostSummary.shippingPricing.markupTiers.map((tier) => tier.isActive)).toEqual([false, false, true])
  })

  it('does not report a mutation as complete when the authoritative refresh fails', async () => {
    apiMock.get.mockRejectedValueOnce(new Error('详情读取失败'))
    const store = useInternalQuoteDeskStore()

    await expect(store.saveSection('quote-1', 'engineering', 1, { molds: [] }))
      .rejects.toThrow('操作已在服务端成功，但页面未能读取最新报价')
    expect(apiMock.saveSection).toHaveBeenCalledTimes(1)
    expect(store.errorMessage).toContain('详情读取失败')
  })

  it('updates quote-scoped FX through the optimistic header revision and reloads the snapshot', async () => {
    const store = useInternalQuoteDeskStore()
    await store.updateReferenceFx('quote-1', 2, '0.9', '7.9')

    expect(apiMock.updateReferenceFx).toHaveBeenCalledWith('quote-1', 2, '0.9', '7.9')
    expect(apiMock.get).toHaveBeenCalledWith('quote-1')
    expect(apiMock.getReferenceSnapshot).toHaveBeenCalledWith('quote-1')
  })
})

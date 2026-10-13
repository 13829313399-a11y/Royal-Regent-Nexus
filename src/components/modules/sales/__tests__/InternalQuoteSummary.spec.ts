import { mount } from '@vue/test-utils'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InternalQuoteSummary from '@/components/modules/sales/internal-quote/InternalQuoteSummary.vue'

const mocks = vi.hoisted(() => {
  const quoteStore: Record<string, any> = {
    currentQuote: undefined,
    placeholderQuote: undefined,
    batchProductsByQuoteId: {},
    versionCandidates: {},
    errorMessage: '',
    conflictMessage: '',
    submitting: false,
    getQuoteById: vi.fn(() => quoteStore.currentQuote),
    loadQuote: vi.fn(async () => quoteStore.currentQuote),
    loadBatchProducts: vi.fn(async () => []),
    loadVersionCandidates: vi.fn(async () => []),
    saveSection: vi.fn(async () => ({})),
    refreshAfterMutation: vi.fn(async () => undefined),
    submitFinal: vi.fn(),
    reviewFinal: vi.fn(),
    compareVersion: vi.fn(),
  }
  return {
    route: { params: { quoteId: 'quote-1' } },
    router: { push: vi.fn(), replace: vi.fn() },
    quoteStore,
    authStore: {
      editable: true,
      currentUser: { id: 'user-1', profile: { primary_factory_id: 'huaxing' } },
      can: vi.fn((permission: string) => (
        permission === 'internal_quote:read'
        || (mocks.authStore.editable && ['internal_quote:sales_edit', 'internal_quote:engineering_edit'].includes(permission))
      )),
      canAny: vi.fn(() => false),
    },
    appStore: {
      activeFactory: { id: 'huaxing' },
      activeProductionFactory: { id: 'huaxing' },
    },
  }
})

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => mocks.router,
}))

vi.mock('@/stores/internalQuoteDesk', () => ({
  useInternalQuoteDeskStore: () => mocks.quoteStore,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => mocks.authStore,
}))

vi.mock('@/stores/app', () => ({
  useAppStore: () => mocks.appStore,
}))

function quoteFixture(regionCode: '' | 'mainland' | 'indonesia', salesStatus = 'draft') {
  const salesSection = {
    code: 'sales',
    label: '业务部',
    owner: '业务部',
    status: salesStatus,
    isRequired: true,
    revision: 7,
    totalHkd: 2,
    updatedAt: '2026-08-20 09:00:00',
    formulaHint: '',
    dependencies: [],
    warnings: [],
    lines: [],
    attachments: [],
    payload: {
      paper_price_factor: 3.2,
      packaging_materials: [{ item: '彩盒', quantity: 2, unit_price_rmb: 1 }],
      cartons: [{ item: '主纸箱', length_in: 10, width_in: 8, height_in: 6, qty_per_carton: 12, flat_cards: [] }],
      indonesia_freight_hkd: 1.25,
    },
    calculation: {},
    calculationStatus: 'valid',
    dependencyStatus: 'current',
    filledAt: '2026-08-20 09:00:00',
  }
  return {
    id: 'quote-1',
    quoteNo: 'IQ-001',
    productName: regionCode === 'indonesia' ? '产品—印尼价' : '产品—大陆价',
    quoteType: regionCode ? 'multi_region' : 'single',
    batchId: 'batch-1',
    batchQuoteNo: 'IQ-001',
    batchPosition: 1,
    batchSize: 1,
    baselineQuoteId: 'quote-1',
    regionCode,
    customer: '客户',
    versionLabel: 'V1.0',
    factoryId: 'huaxing',
    factoryName: '华兴',
    workshopCode: 'huaxing',
    workshopName: '华兴',
    initiatorDepartment: 'sales-business',
    createdById: 'user-1',
    initiatorName: '业务员',
    businessOwnerId: 'owner-1',
    businessOwner: '审核人',
    targetCustomerPrice: '无',
    quantity: 10000,
    targetDate: '2026-08-30',
    remark: '',
    createdAt: '2026-08-20 08:00:00',
    updatedAt: '2026-08-20 09:00:00',
    status: salesStatus === 'approved' ? 'final_pending' : 'drafting',
    fxRmbHkd: 0.85,
    fxHkdUsd: 7.8,
    fxRmbUsd: 7.75,
    referenceSnapshotId: 'ref-1',
    referenceSnapshot: {},
    formulaVersion: 'rr2-2026-v1',
    moduleVersion: 'v3',
    headerRevision: 3,
    finalReleaseStatus: '',
    factoryPriceHkd: 16,
    summaryComponents: { packaging_material_hkd: 2, indonesia_freight_hkd: 1.25 },
    summaryWarnings: [],
    shippingScenarios: [],
    rr2CostSummary: {
      currency: 'HKD',
      indonesiaFreightHkd: 1.25,
      t1: [
        { key: 'base_price', label: '货价', value: 16, display: true },
        { key: 'material', label: '料价', value: 3.75, display: true },
        { key: 'imp_mat', label: '进口料', value: 1.25, display: false },
        { key: 'dom_mat', label: '国内料', value: 2.5, display: false },
        { key: 'blow', label: '吹气', value: 0.5, display: true },
      ],
      t2: [{ key: 'misc', label: '杂项', value: 0.32 }],
      t3: [{ key: 'total_cost', label: '总成本', value: 14 }],
      t4: [],
      rmbPurchaseCostHkd: 2,
      totalDeductionHkd: 0,
      afterDeductionCostHkd: 14,
      shippingPricing: {
        enabled: false,
        freightEnabled: false,
        liftingEnabled: false,
        freightSharePercent: 48,
        liftSharePercent: 52,
        markup: 1.2,
        activeMarkupMoq: 10000,
        markupTiers: [],
        miscRatio: 0.02,
        settlement: 0.98,
        factoryPriceHkd: 16,
        additionalTaxHkd: 0,
        shippingFloorHkd: 16,
        hkdUsd: 7.8,
        moldAmortizationUsd: 0,
        rows: [],
      },
    },
    sections: [salesSection],
    activities: [],
    comments: [],
    viewRecords: [],
    exports: [],
  }
}

function mountSummary() {
  return mount(InternalQuoteSummary, {
    global: {
      stubs: {
        InternalQuoteOutputTable: { name: 'InternalQuoteOutputTable', props: ['quoteId', 'collaborationRoute'], emits: ['saved', 'dirty'], template: '<div data-testid=output-table />' },
        RouterLink: { props: ['to'], template: '<a><slot /></a>' },
      },
    },
  })
}

describe('InternalQuoteSummary output table entry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.authStore.editable = true
    mocks.quoteStore.currentQuote = quoteFixture('indonesia')
    mocks.quoteStore.placeholderQuote = mocks.quoteStore.currentQuote
  })

  it('replaces redundant distributions and tax panels with the current quotation output table', async () => {
    const wrapper = mountSummary()
    await flushPromises()
    const table = wrapper.findComponent({ name: 'InternalQuoteOutputTable' })
    expect(wrapper.find('[data-testid="output-table"]').exists()).toBe(true)
    expect(table.props('quoteId')).toBe('quote-1')
    expect(table.props('collaborationRoute')).toContain('/quote-1/collaboration')
    expect(wrapper.find('.quote-cost-overview').exists()).toBe(false)
    expect(wrapper.find('.quote-tax-summary-panel').exists()).toBe(false)
    expect(wrapper.find('.quote-logistics-panel').exists()).toBe(false)
  })

  it('refreshes the original quotation and readiness after table saves', async () => {
    const wrapper = mountSummary()
    wrapper.findComponent({ name: 'InternalQuoteOutputTable' }).vm.$emit('saved')
    await flushPromises()
    expect(mocks.quoteStore.refreshAfterMutation).toHaveBeenCalledWith('quote-1')
  })
})

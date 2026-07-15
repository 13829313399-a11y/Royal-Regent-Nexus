import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { InternalQuoteDetail, InternalQuoteSummary } from '@/types/internalQuote'
import { useAuthStore } from '@/stores/auth'
import InternalQuotePanel from '../InternalQuotePanel.vue'

const internalQuoteApiMock = vi.hoisted(() => ({
  listWorkshops: vi.fn(),
  listQuotes: vi.fn(),
  getQuote: vi.fn(),
  listImports: vi.fn(),
  listAttachments: vi.fn(),
  listExports: vi.fn(),
}))

vi.mock('@/api/internalQuote', () => ({
  internalQuoteApi: internalQuoteApiMock,
}))

const summary: InternalQuoteSummary = {
  id: 'quote-1',
  factoryId: 'huaxing',
  workshopCode: 'huaxing-workshop',
  workshopName: '华兴',
  quoteNo: 'Q-ADMIN-001',
  productName: '管理员报价容错测试',
  customer: '测试客户',
  qty: 1000,
  versionLabel: 'V1',
  status: 'drafting',
  approvedCount: 0,
  totalSections: 8,
  totalHkd: 20,
  createdBy: 'user-admin',
  createdByName: '系统管理员',
  createdAt: '2026-07-16 10:00:00',
  updatedAt: '2026-07-16 10:00:00',
}

const detail: InternalQuoteDetail = {
  ...summary,
  sections: [
    {
      id: 'section-sales',
      quoteId: summary.id,
      department: 'sales',
      departmentName: '业务部',
      status: 'draft',
      payload: {
        currency: 'HKD',
        lossPct: 0,
        parameters: {},
        referenceSnapshot: { version: 'rr2-2026-v1', fx: { rmb_hkd: 0.85, hkd_usd: 7.8 } },
        rows: [
          {
            id: 'line-1',
            category: '业务费用',
            itemName: '运输费',
            specification: '标准',
            quantity: 1,
            unitPriceHkd: 20,
            amountHkd: 20,
            note: '',
            fields: {},
          },
        ],
      },
      calculation: {
        formulaVersion: 'department-formulas-v1',
        subtotalHkd: 20,
        lossAmountHkd: 0,
        totalHkd: 20,
        totalRmb: 17,
        totalUsd: 2.56,
        lineBreakdown: [{ lineId: 'line-1', label: '运输费', formula: '1 × 20', amountHkd: 20 }],
        warnings: [],
        referenceSnapshot: {},
      },
      revision: 1,
      filledBy: '',
      filledAt: '',
      submittedBy: '',
      submittedAt: '',
      reviewedBy: '',
      reviewedAt: '',
      reviewComment: '',
      updatedAt: '2026-07-16 10:00:00',
    },
  ],
  auditLogs: [],
}

function seedLegacyAdmin() {
  const permissions = [
    'internal_pricing:read',
    'internal_pricing:create',
    'internal_pricing:edit',
    'internal_pricing:review',
    'internal_pricing:export',
  ]
  useAuthStore().applySession({
    id: 'user-admin',
    username: 'admin',
    display_name: '系统管理员',
    roles: ['系统管理员'],
    permissions,
    grants: [{
      role_id: 'admin',
      role_code: 'admin',
      role_name: '系统管理员',
      factory_id: '*',
      department: 'system',
      permissions: [],
      data_scope: 'all',
    }],
    factory_scopes: ['*'],
    department_scopes: ['system'],
    authz_mode: 'legacy',
    force_password_change: false,
  })
}

describe('InternalQuotePanel', () => {
  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    vi.clearAllMocks()
    internalQuoteApiMock.listWorkshops.mockResolvedValue([{ code: 'huaxing-workshop', name: '华兴' }])
    internalQuoteApiMock.listQuotes.mockResolvedValue([summary])
    internalQuoteApiMock.getQuote.mockResolvedValue(detail)
    internalQuoteApiMock.listImports.mockResolvedValue([])
    internalQuoteApiMock.listAttachments.mockResolvedValue([])
    internalQuoteApiMock.listExports.mockRejectedValue(new Error('无授权范围内操作权限'))
  })

  it('keeps a draft quote visible and editable when export history cannot be loaded', async () => {
    seedLegacyAdmin()
    const wrapper = mount(InternalQuotePanel)

    await flushPromises()

    expect(internalQuoteApiMock.listExports).toHaveBeenCalledWith(summary.id)
    expect(wrapper.text()).toContain('Q-ADMIN-001 · 管理员报价容错测试')
    expect(wrapper.text()).toContain('报价详情已加载，但受控导出历史读取失败')
    expect(wrapper.get('input[aria-label="成本项目"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('保存草稿')
    expect(wrapper.text()).toContain('提交审核')

    wrapper.unmount()
  })
})

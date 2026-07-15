import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))

vi.mock('@/lib/http', () => ({ http: httpMock }))

import { internalQuoteApi } from '@/api/internalQuote'

const summary = {
  id: 'IQD-001',
  factory_id: 'huaxing',
  workshop_code: 'huaxing-workshop',
  workshop_name: '华兴',
  quote_no: '47765A',
  product_name: '测试产品',
  customer: 'Target',
  qty: 10000,
  version_label: 'V1',
  status: 'drafting',
  approved_count: 0,
  total_sections: 8,
  total_hkd: 21,
  created_by: 'user-sales',
  created_by_name: '业务员',
  created_at: '2026-07-15 18:00:00',
  updated_at: '2026-07-15 18:00:00',
} as const

const detail = {
  ...summary,
  sections: [
    {
      id: 'IQS-001',
      quote_id: summary.id,
      department: 'sales',
      department_name: '业务部',
      status: 'draft',
      payload: {
        currency: 'HKD',
        loss_pct: 5,
        rows: [
          {
            id: 'line-1',
            category: '业务费用',
            item_name: '运输及杂项',
            specification: '标准',
            quantity: 2,
            unit_price_hkd: 10,
            amount_hkd: 20,
            note: '',
          },
        ],
      },
      calculation: { subtotal_hkd: 20, loss_amount_hkd: 1, total_hkd: 21 },
      revision: 2,
      filled_by: '业务员',
      filled_at: '2026-07-15 18:01:00',
      submitted_by: '',
      submitted_at: '',
      reviewed_by: '',
      reviewed_at: '',
      review_comment: '',
      updated_at: '2026-07-15 18:01:00',
    },
  ],
  audit_logs: [],
} as const

describe('internalQuoteApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('keeps workshop filters in the list contract and maps quote summaries', async () => {
    httpMock.get.mockResolvedValueOnce({ data: [summary] })

    const result = await internalQuoteApi.listQuotes('huaxing', {
      workshopCode: 'huaxing-workshop',
      status: 'drafting',
      keyword: '47765A',
    })

    expect(httpMock.get).toHaveBeenCalledWith('/internal-quotes', {
      params: {
        factory_id: 'huaxing',
        workshop_code: 'huaxing-workshop',
        status_filter: 'drafting',
        keyword: '47765A',
      },
    })
    expect(result[0]).toMatchObject({
      factoryId: 'huaxing',
      workshopCode: 'huaxing-workshop',
      workshopName: '华兴',
      totalSections: 8,
      totalHkd: 21,
    })
  })

  it('maps editable cost rows to the backend snapshot contract', async () => {
    httpMock.put.mockResolvedValueOnce({ data: detail })

    const result = await internalQuoteApi.updateSection(
      summary.id,
      'sales',
      1,
      {
        currency: 'HKD',
        lossPct: 5,
        parameters: { freight_hkd: 0 },
        referenceSnapshot: { version: 'rr2-2026-v1' },
        rows: [
          {
            id: 'line-1',
            category: '业务费用',
            itemName: '运输及杂项',
            specification: '标准',
            quantity: 2,
            unitPriceHkd: 10,
            amountHkd: 999,
            note: '',
            fields: {},
          },
        ],
      },
      true,
    )

    expect(httpMock.put).toHaveBeenCalledWith('/internal-quotes/IQD-001/sections/sales', {
      revision: 1,
      submit: true,
      payload: {
        currency: 'HKD',
        loss_pct: 5,
        parameters: { freight_hkd: 0 },
        reference_snapshot: { version: 'rr2-2026-v1' },
        rows: [
          {
            id: 'line-1',
            category: '业务费用',
            item_name: '运输及杂项',
            specification: '标准',
            quantity: 2,
            unit_price_hkd: 10,
            amount_hkd: 999,
            note: '',
            fields: {},
          },
        ],
      },
    })
    expect(result.sections[0]).toMatchObject({
      departmentName: '业务部',
      revision: 2,
      payload: { lossPct: 5 },
      calculation: { totalHkd: 21 },
    })
    expect(result.sections[0].payload.rows[0]).toMatchObject({
      itemName: '运输及杂项',
      unitPriceHkd: 10,
      amountHkd: 20,
    })
  })

  it('uploads a workbook for preview and confirms the selected merge mode', async () => {
    httpMock.post.mockResolvedValueOnce({
      data: {
        batch_id: 'IQI-001',
        quote_id: summary.id,
        import_type: 'electronic',
        target_department: 'electronic',
        source_file_name: '电子报价.xlsx',
        source_sha256: 'abc123',
        sheet_name: '电子报价',
        header_row: 2,
        rows: [{
          id: 'import-1', category: '电子料', item_name: 'IC', specification: 'A1', quantity: 2,
          unit_price_hkd: 0, amount_hkd: 0, note: '', fields: { unit_price_rmb: 10 },
        }],
        parameters: { bonding_cost_rmb: 1.5 },
        warnings: [],
        status: 'previewed',
        created_by_name: '业务员',
        created_at: '2026-07-16 09:00:00',
        confirmed_by_name: '',
        confirmed_at: '',
      },
    })
    const file = new File(['xlsx'], '电子报价.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    const preview = await internalQuoteApi.previewImport(summary.id, 'electronic', file)

    expect(httpMock.post).toHaveBeenCalledWith(
      '/internal-quotes/IQD-001/imports/electronic/preview',
      expect.any(FormData),
    )
    expect(preview).toMatchObject({
      batchId: 'IQI-001',
      targetDepartment: 'electronic',
      sourceFileName: '电子报价.xlsx',
      rows: [{ itemName: 'IC', fields: { unit_price_rmb: 10 } }],
      parameters: { bonding_cost_rmb: 1.5 },
    })

    httpMock.post.mockResolvedValueOnce({ data: detail })
    await internalQuoteApi.confirmImport(summary.id, preview.batchId, 1, 'replace')
    expect(httpMock.post).toHaveBeenLastCalledWith(
      '/internal-quotes/IQD-001/imports/IQI-001/confirm',
      { revision: 1, mode: 'replace' },
    )
  })

  it('maps attachment and retained export metadata', async () => {
    httpMock.get
      .mockResolvedValueOnce({
        data: [{
          id: 'IQA-001', quote_id: summary.id, department: 'electronic', file_name: 'reference.pdf',
          content_type: 'application/pdf', size_bytes: 1024, sha256: 'attachment-hash',
          uploaded_by_name: '业务员', uploaded_at: '2026-07-16 09:10:00',
        }],
      })
      .mockResolvedValueOnce({
        data: [{
          id: 'IQE-001', quote_id: summary.id, file_name: '内部报价.xlsx',
          content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          size_bytes: 2048, sha256: 'export-hash', section_revisions: { sales: 2 }, status: 'current',
          exported_by_name: '主管', exported_at: '2026-07-16 09:20:00', superseded_at: '',
        }],
      })

    const attachments = await internalQuoteApi.listAttachments(summary.id)
    const exports = await internalQuoteApi.listExports(summary.id)

    expect(attachments[0]).toMatchObject({
      quoteId: summary.id,
      department: 'electronic',
      fileName: 'reference.pdf',
      sizeBytes: 1024,
    })
    expect(exports[0]).toMatchObject({
      quoteId: summary.id,
      fileName: '内部报价.xlsx',
      sectionRevisions: { sales: 2 },
      status: 'current',
    })
  })
})

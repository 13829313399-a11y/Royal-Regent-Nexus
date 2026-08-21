import { describe, expect, it, vi } from 'vitest'
import {
  QC_SCHEDULE_IMPORT_MAX_FILE_BYTES,
  QC_SCHEDULE_IMPORT_MAX_FILE_MEGABYTES,
  createQcInspectionApi,
  validateQcScheduleImportFile,
} from '@/api/qcInspection'

describe('QC inspection API', () => {
  it('uses the 35 MB schedule import limit required by QC', () => {
    expect(QC_SCHEDULE_IMPORT_MAX_FILE_MEGABYTES).toBe(35)
    expect(QC_SCHEDULE_IMPORT_MAX_FILE_BYTES).toBe(35 * 1024 * 1024)
    expect(validateQcScheduleImportFile({ size: QC_SCHEDULE_IMPORT_MAX_FILE_BYTES })).toBe('')
    expect(validateQcScheduleImportFile({ size: QC_SCHEDULE_IMPORT_MAX_FILE_BYTES + 1 }))
      .toBe('排期文件不能超过 35 MB')
  })

  it('loads a factory-scoped weekly workspace', async () => {
    const get = vi.fn().mockResolvedValue({
      data: {
        factory_id: 'huaxing',
        week: '2026-W33',
        summary: { total_orders: 0, pending_orders: 0, completed_orders: 0, problem_orders: 0 },
        orders: [],
        problems: [],
        imports: [],
        reports: [],
      },
    })
    const api = createQcInspectionApi({ get, post: vi.fn(), patch: vi.fn() })

    const workspace = await api.getWorkspace('huaxing', '2026-W33')

    expect(workspace.factory_id).toBe('huaxing')
    expect(get).toHaveBeenCalledWith('/qc-inspections/workspace', {
      params: { factory_id: 'huaxing', week: '2026-W33' },
    })
  })

  it('uploads schedule input with explicit factory, week and request identity', async () => {
    const post = vi.fn().mockResolvedValue({
      data: { id: 'batch-1', factory_id: 'huaxing', week_key: '2026-W33', rows: [] },
    })
    const api = createQcInspectionApi({ get: vi.fn(), post, patch: vi.fn() })
    const file = new File(['xlsx'], '2026-W33.xlsx')

    await api.previewScheduleImport(file, 'huaxing', '2026-W33')

    const payload = post.mock.calls[0]![1] as FormData
    expect(post.mock.calls[0]![0]).toBe('/qc-inspections/schedule-imports/preview')
    expect(payload.get('file')).toBe(file)
    expect(payload.get('factory_id')).toBe('huaxing')
    expect(payload.get('week_key')).toBe('2026-W33')
    expect(String(payload.get('request_id'))).toBeTruthy()
  })

  it('confirms a revision-bound schedule batch with explicit row decisions', async () => {
    const post = vi.fn().mockResolvedValue({ data: { id: 'batch-1', rows: [] } })
    const api = createQcInspectionApi({ get: vi.fn(), post, patch: vi.fn() })

    await api.confirmScheduleImport('batch-1', 'huaxing', 3, [
      { row_id: 'row-1', action: 'UPDATE', target_order_id: 'order-1' },
      { row_id: 'row-2', action: 'SKIP' },
    ])

    expect(post.mock.calls[0]![0]).toBe('/qc-inspections/schedule-imports/batch-1/confirm')
    expect(post.mock.calls[0]![1]).toEqual(expect.objectContaining({
      factory_id: 'huaxing',
      expected_revision: 3,
      decisions: [
        { row_id: 'row-1', action: 'UPDATE', target_order_id: 'order-1' },
        { row_id: 'row-2', action: 'SKIP' },
      ],
    }))
  })

  it('adds request identity to manual order and revision-bound result updates', async () => {
    const post = vi.fn().mockResolvedValue({ data: { id: 'order-1' } })
    const patch = vi.fn().mockResolvedValue({ data: { id: 'order-1', revision: 2 } })
    const api = createQcInspectionApi({ get: vi.fn(), post, patch })

    await api.createOrder({
      factory_id: 'huaxing',
      week_key: '2026-W33',
      customer_name: 'Customer',
      sales_contract_no: 'SC-1',
      customer_po_no: '00123',
      customer_item_no: 'ITEM-1',
      product_name: 'Product',
      quantity: 100,
      packing: '12 pcs',
      carton_count: '9',
      production_department: '装配一部',
      export_country_code: 'US',
      shipment_date: '2026-08-20',
      planned_inspection_date: '2026-08-18',
    })
    await api.updateOrder('order-1', {
      factory_id: 'huaxing',
      expected_revision: 1,
      reason: '填写实际验货结果',
      actual_inspection_date: '2026-08-18',
      inspection_result: 'PASS',
      report_status: '有',
      manual_has_problem: true,
    })

    expect(post.mock.calls[0]![1]).toEqual(expect.objectContaining({
      customer_po_no: '00123',
      week_key: '2026-W33',
      packing: '12 pcs',
      carton_count: '9',
      production_department: '装配一部',
      request_id: expect.any(String),
    }))
    expect(patch.mock.calls[0]![1]).toEqual(expect.objectContaining({
      factory_id: 'huaxing',
      expected_revision: 1,
      manual_has_problem: true,
      report_status: '有',
      request_id: expect.any(String),
    }))
  })

  it('loads order detail with an explicit factory scope', async () => {
    const get = vi.fn().mockResolvedValue({ data: { id: 'order-1', factory_id: 'huaxing' } })
    const api = createQcInspectionApi({ get, post: vi.fn(), patch: vi.fn() })

    await api.getOrder('order-1', 'huaxing')

    expect(get).toHaveBeenCalledWith('/qc-inspections/orders/order-1', {
      params: { factory_id: 'huaxing' },
    })
  })

  it('unwraps list envelopes and requests report downloads as blobs', async () => {
    const blob = new Blob(['xlsx'])
    const get = vi.fn()
      .mockResolvedValueOnce({ data: { factory_id: 'huaxing', week: '2026-W33', total: 1, items: [{ id: 'order-1' }] } })
      .mockResolvedValueOnce({ data: blob, headers: { 'content-disposition': "attachment; filename*=UTF-8''QC_%E6%8A%A5%E8%A1%A8.xlsx" } })
    const api = createQcInspectionApi({ get, post: vi.fn(), patch: vi.fn() })

    const orders = await api.listOrders('huaxing', '2026-W33')
    const result = await api.downloadReport('report-1', 'fallback.xlsx', 'huaxing')

    expect(orders).toEqual([{ id: 'order-1' }])
    expect(result.blob).toBe(blob)
    expect(result.fileName).toBe('QC_报表.xlsx')
    expect(get.mock.calls[1]).toEqual([
      '/qc-inspections/reports/report-1/download',
      expect.objectContaining({ responseType: 'blob', params: { factory_id: 'huaxing' } }),
    ])
  })

  it('binds rename uploads to stable file ids and explicit JPG sequence metadata', async () => {
    const post = vi.fn().mockResolvedValue({
      data: { id: 'rename-1', factory_id: 'huaxing', revision: 1, groups: [] },
    })
    const api = createQcInspectionApi({ get: vi.fn(), post, patch: vi.fn() })
    const pdf = new File(['pdf'], 'report.pdf', { type: 'application/pdf' })
    const jpg = new File(['jpg'], 'photo.jpg', { type: 'image/jpeg' })

    await api.previewRenameBatch(
      [{ fileId: 'group-1-pdf', file: pdf }, { fileId: 'group-1-jpg-1', file: jpg }],
      [{
        group_id: 'group-1',
        is_caixing: false,
        export_country: 'US',
        item_number: 'ITEM-1',
        customer_po_no: '00123',
        actual_inspection_date: '2026-08-18',
        files: [
          { file_id: 'group-1-pdf', source_file_name: 'report.pdf' },
          { file_id: 'group-1-jpg-1', source_file_name: 'photo.jpg', sequence: 1 },
        ],
      }],
      'huaxing',
    )

    const payload = post.mock.calls[0]![1] as FormData
    expect(payload.getAll('files')).toEqual([pdf, jpg])
    expect(payload.getAll('file_ids')).toEqual(['group-1-pdf', 'group-1-jpg-1'])
    expect(JSON.parse(String(payload.get('metadata_json')))).toEqual(expect.objectContaining({
      factory_id: 'huaxing',
      groups: [expect.objectContaining({
        group_id: 'group-1',
        files: [
          { file_id: 'group-1-pdf', source_file_name: 'report.pdf' },
          { file_id: 'group-1-jpg-1', source_file_name: 'photo.jpg', sequence: 1 },
        ],
      })],
      request_id: expect.any(String),
    }))
  })
})

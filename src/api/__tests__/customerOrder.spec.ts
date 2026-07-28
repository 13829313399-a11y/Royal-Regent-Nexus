import { describe, expect, it, vi } from 'vitest'
import { createCustomerOrderApi } from '@/api/customerOrder'


describe('customer order api', () => {
  it('uploads both source files for preview and returns the mapped batch', async () => {
    const post = vi.fn().mockResolvedValue({
      data: { preview_schema_version: 'customer-order-buzzbee-preview-v1', rows: [] },
    })
    const api = createCustomerOrderApi({ post })
    const po = new File(['po'], 'PO.xls')
    const schedule = new File(['schedule'], '2026年 BUZZ BEE 生产排期表.xls.xlsx')

    const result = await api.previewBuzzbee(po, schedule, '2026-07-27', 'huaxing')

    expect(result.preview_schema_version).toBe('customer-order-buzzbee-preview-v1')
    expect(post).toHaveBeenCalledWith(
      '/customer-orders/buzzbee/preview',
      expect.any(FormData),
      expect.objectContaining({ timeout: 60_000 }),
    )
    const payload = post.mock.calls[0]![1] as FormData
    expect(payload.get('factory_id')).toBe('huaxing')
    expect(payload.get('received_date')).toBe('2026-07-27')
    expect(payload.get('po_file')).toBe(po)
    expect(payload.get('schedule_file')).toBe(schedule)
  })

  it('confirms export and decodes the UTF-8 download filename', async () => {
    const blob = new Blob(['xlsx'])
    const post = vi.fn().mockResolvedValue({
      data: blob,
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''BuzzBee_%E5%B7%B2%E5%A1%AB%E6%8E%92%E6%9C%9F.xlsx",
      },
    })
    const api = createCustomerOrderApi({ post })

    const result = await api.exportBuzzbee(
      new File(['po'], 'PO.xlsx'),
      new File(['schedule'], 'schedule.xlsx'),
      '2026-07-27',
      'fallback.xlsx',
      'huaxing',
      ['row-1|missing_unit_price|unit_price_hkd'],
    )

    expect(result.blob).toBe(blob)
    expect(result.fileName).toBe('BuzzBee_已填排期.xlsx')
    const payload = post.mock.calls[0]![1] as FormData
    expect(payload.get('confirmed')).toBe('true')
    expect(payload.get('skipped_issue_keys')).toBe(
      '["row-1|missing_unit_price|unit_price_hkd"]',
    )
    expect(post.mock.calls[0]![2]).toEqual(expect.objectContaining({
      responseType: 'blob',
      timeout: 120_000,
    }))
  })

  it('uploads multiple PO files and exports one schedule with the original filename', async () => {
    const blob = new Blob(['batch-xlsx'])
    const post = vi.fn()
      .mockResolvedValueOnce({
        data: {
          preview_schema_version: 'customer-order-buzzbee-preview-v1',
          po_file_count: 2,
          rows: [],
        },
      })
      .mockResolvedValueOnce({
        data: blob,
        headers: {
          'content-disposition': "attachment; filename*=UTF-8''2026%E5%B9%B4%20BUZZ%20BEE%20%E7%94%9F%E4%BA%A7%E6%8E%92%E6%9C%9F%E8%A1%A8.xls.xlsx",
        },
      })
    const api = createCustomerOrderApi({ post })
    const poFiles = [
      new File(['po-1'], 'PO-1.xls'),
      new File(['po-2'], 'PO-2.xlsx'),
    ]
    const schedule = new File(['schedule'], '2026年 BUZZ BEE 生产排期表.xls.xlsx')

    const preview = await api.previewBuzzbeeBatch(
      poFiles,
      schedule,
      '2026-07-27',
      'huaxing',
    )
    expect(preview.po_file_count).toBe(2)
    const previewPayload = post.mock.calls[0]![1] as FormData
    expect(previewPayload.getAll('po_files')).toEqual(poFiles)
    expect(post.mock.calls[0]![0]).toBe('/customer-orders/buzzbee/preview-batch')

    const exported = await api.exportBuzzbeeBatch(
      poFiles,
      schedule,
      '2026-07-27',
      schedule.name,
      'huaxing',
      [],
    )
    expect(exported.blob).toBe(blob)
    expect(exported.fileName).toBe(schedule.name)
    const exportPayload = post.mock.calls[1]![1] as FormData
    expect(exportPayload.getAll('po_files')).toEqual(poFiles)
    expect(exportPayload.get('confirmed')).toBe('true')
    expect(post.mock.calls[1]![0]).toBe('/customer-orders/buzzbee/export-batch')
    expect(post.mock.calls[1]![2]).toEqual(expect.objectContaining({
      responseType: 'blob',
      timeout: 180_000,
    }))
  })
})

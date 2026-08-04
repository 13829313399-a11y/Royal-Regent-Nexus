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
      'preview-fingerprint-1',
      '测试阶段已核对单价留空',
    )

    expect(result.blob).toBe(blob)
    expect(result.fileName).toBe('BuzzBee_已填排期.xlsx')
    const payload = post.mock.calls[0]![1] as FormData
    expect(payload.get('confirmed')).toBe('true')
    expect(payload.get('skipped_issue_keys')).toBe(
      '["row-1|missing_unit_price|unit_price_hkd"]',
    )
    expect(payload.get('preview_fingerprint')).toBe('preview-fingerprint-1')
    expect(payload.get('confirmation_reason')).toBe('测试阶段已核对单价留空')
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

  it('routes Dickie PDF batches through the customer-specific preview and export endpoints', async () => {
    const blob = new Blob(['dickie-xlsx'])
    const post = vi.fn()
      .mockResolvedValueOnce({
        data: {
          preview_schema_version: 'customer-order-dickie-preview-v1',
          customer_code: 'dickie',
          po_file_count: 2,
          rows: [],
        },
      })
      .mockResolvedValueOnce({
        data: blob,
        headers: {
          'content-disposition': "attachment; filename*=UTF-8''2026%E5%B9%B4.Dickie%20%E7%94%9F%E4%BA%A7%E6%83%85%E5%86%B5.xlsx",
        },
      })
    const api = createCustomerOrderApi({ post })
    const poFiles = [
      new File(['%PDF-1'], 'SC700142026-1200.pdf', { type: 'application/pdf' }),
      new File(['%PDF-2'], 'SC700143686-2000.pdf', { type: 'application/pdf' }),
    ]
    const schedule = new File(['schedule'], '2026年.Dickie 生产情况.xlsx')

    const preview = await api.previewDickieBatch(
      poFiles,
      schedule,
      '2026-07-29',
      'huaxing',
    )
    expect(preview.customer_code).toBe('dickie')
    expect(post.mock.calls[0]![0]).toBe('/customer-orders/dickie/preview-batch')
    expect((post.mock.calls[0]![1] as FormData).getAll('po_files')).toEqual(poFiles)
    expect(post.mock.calls[0]![2]).toEqual(expect.objectContaining({ timeout: 180_000 }))

    const exported = await api.exportDickieBatch(
      poFiles,
      schedule,
      '2026-07-29',
      schedule.name,
      'huaxing',
      [],
    )
    expect(exported.blob).toBe(blob)
    expect(exported.fileName).toBe(schedule.name)
    expect(post.mock.calls[1]![0]).toBe('/customer-orders/dickie/export-batch')
    expect(post.mock.calls[1]![2]).toEqual(expect.objectContaining({
      responseType: 'blob',
      timeout: 240_000,
    }))
  })

  it('routes Caixing Playmates PDF batches and preserves the schedule filename and encryption state', async () => {
    const blob = new Blob(['caixing-xlsx'])
    const post = vi.fn()
      .mockResolvedValueOnce({
        data: {
          preview_schema_version: 'customer-order-caixing-preview-v1',
          customer_code: 'caixing',
          po_file_count: 2,
          rows: [],
        },
      })
      .mockResolvedValueOnce({
        data: blob,
        headers: {
          'content-disposition': "attachment; filename*=UTF-8''2026%E5%B9%B4%E5%BD%A9%E6%98%9F%E6%8E%92%E6%9C%9F.xlsx",
          'x-workbook-password-required': 'false',
        },
      })
    const api = createCustomerOrderApi({ post })
    const poFiles = [
      new File(['%PDF-1'], '1931815.pdf', { type: 'application/pdf' }),
      new File(['%PDF-2'], '1931878.pdf', { type: 'application/pdf' }),
    ]
    const schedule = new File(['schedule'], '2026年彩星排期.xlsx')

    const preview = await api.previewCaixingBatch(
      poFiles,
      schedule,
      '2026-07-29',
      'huaxing',
    )
    expect(preview.customer_code).toBe('caixing')
    expect(post.mock.calls[0]![0]).toBe('/customer-orders/caixing/preview-batch')
    expect((post.mock.calls[0]![1] as FormData).getAll('po_files')).toEqual(poFiles)

    const exported = await api.exportCaixingBatch(
      poFiles,
      schedule,
      '2026-07-29',
      schedule.name,
      'huaxing',
      [],
    )
    expect(exported.blob).toBe(blob)
    expect(exported.fileName).toBe(schedule.name)
    expect(exported.passwordRequired).toBe(false)
    expect(post.mock.calls[1]![0]).toBe('/customer-orders/caixing/export-batch')
    expect(post.mock.calls[1]![2]).toEqual(expect.objectContaining({
      responseType: 'blob',
      timeout: 240_000,
    }))
  })

  it('surfaces the backend detail when a blob export fails', async () => {
    const error = Object.assign(new Error('Request failed with status code 409'), {
      isAxiosError: true,
      response: {
        data: new Blob([
          JSON.stringify({ detail: '当前环境未启用测试阶段重复订单确认' }),
        ], { type: 'application/json' }),
      },
    })
    const post = vi.fn().mockRejectedValue(error)
    const api = createCustomerOrderApi({ post })

    await expect(api.exportBuzzbeeBatch(
      [new File(['po'], 'PO.xlsx')],
      new File(['schedule'], 'schedule.xlsx'),
      '2026-08-04',
      'schedule.xlsx',
      'huaxing',
      ['row-1|duplicate_reference|reference_no'],
    )).rejects.toThrow('当前环境未启用测试阶段重复订单确认')
  })

  it('routes all six Huaxing mapped customers through the shared batch contract', async () => {
    const customers = ['edu', '360', 'yinhui', 'seasons', 'maxx', 'shushupapa'] as const
    for (const customer of customers) {
      const blob = new Blob([customer])
      const post = vi.fn()
        .mockResolvedValueOnce({
          data: {
            preview_schema_version: 'customer-order-huaxing-mapped-preview-v1',
            customer_code: customer,
            po_file_count: 1,
            rows: [],
          },
        })
        .mockResolvedValueOnce({
          data: blob,
          headers: {
            'content-disposition': `attachment; filename*=UTF-8''${customer}%E6%96%B0%E5%8D%95.xlsx`,
            'x-workbook-password-required': 'false',
          },
        })
      const api = createCustomerOrderApi({ post })
      const poFiles = [new File(['po'], `${customer}.xlsx`)]
      const schedule = new File(['schedule'], `${customer}排期.xlsx`)

      const preview = await api.previewHuaxingMappedBatch(
        customer,
        poFiles,
        schedule,
        '2026-08-03',
      )
      const exported = await api.exportHuaxingMappedBatch(
        customer,
        poFiles,
        schedule,
        '2026-08-03',
        `${customer}新单.xlsx`,
      )

      expect(preview.customer_code).toBe(customer)
      expect(post.mock.calls[0]![0]).toBe(`/customer-orders/${customer}/preview-batch`)
      expect(post.mock.calls[0]![2]).toEqual(expect.objectContaining({ timeout: 240_000 }))
      expect(post.mock.calls[1]![0]).toBe(`/customer-orders/${customer}/export-batch`)
      expect(post.mock.calls[1]![2]).toEqual(expect.objectContaining({
        responseType: 'blob',
        timeout: 300_000,
      }))
      expect(exported.passwordRequired).toBe(false)
    }
  })

  it('routes all five Huadeng mapped customers with the Huadeng factory contract', async () => {
    const customers = ['casdon', 'jakks', 'simba', 'spin', 'spin-master'] as const
    for (const customer of customers) {
      const blob = new Blob([customer])
      const post = vi.fn()
        .mockResolvedValueOnce({
          data: {
            preview_schema_version: 'customer-order-huadeng-mapped-preview-v1',
            customer_code: customer,
            factory_id: 'huadeng',
            po_file_count: 1,
            rows: [],
          },
        })
        .mockResolvedValueOnce({
          data: blob,
          headers: {
            'content-disposition': `attachment; filename*=UTF-8''${customer}%E6%96%B0%E5%8D%95.xlsx`,
            'x-workbook-password-required': 'false',
          },
        })
      const api = createCustomerOrderApi({ post })
      const poFiles = [new File(['po'], `${customer}.xlsx`)]
      const schedule = new File(['schedule'], `${customer}排期.xlsx`)

      const preview = await api.previewMappedBatch(
        customer,
        poFiles,
        schedule,
        '2026-08-03',
        'huadeng',
      )
      const exported = await api.exportMappedBatch(
        customer,
        poFiles,
        schedule,
        '2026-08-03',
        `${customer}新单.xlsx`,
        'huadeng',
      )

      expect(preview.customer_code).toBe(customer)
      expect(preview.factory_id).toBe('huadeng')
      expect(post.mock.calls[0]![0]).toBe(`/customer-orders/${customer}/preview-batch`)
      expect((post.mock.calls[0]![1] as FormData).get('factory_id')).toBe('huadeng')
      expect(post.mock.calls[1]![0]).toBe(`/customer-orders/${customer}/export-batch`)
      expect(exported.passwordRequired).toBe(false)
    }
  })
})

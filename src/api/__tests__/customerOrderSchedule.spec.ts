import { describe, expect, it, vi } from 'vitest'
import { createCustomerOrderScheduleApi } from '@/api/customerOrderSchedule'

const organizeReport = {
  as_of_date: '2026-10-16', warning_count: 5, warnings: ['ITEM表第 8 行日期缺失', '接单表第 9 行日期冲突', '正单评审表第 10 行日期无效'],
  sheets: { ITEM表: { moved_to_completed: 7, moved_to_pending: 1 }, 接单表: { moved_to_completed: 7, moved_to_pending: 1 }, 正单评审表: { moved_to_completed: 6, moved_to_pending: 2 } },
}

describe('customer order schedule api', () => {
  it('requests factory-scoped customers and all three independently paged sections', async () => {
    const get = vi.fn()
      .mockResolvedValueOnce({ data: { factory_id: 'huaxing', items: [{ code: 'buzzbee', name: 'BuzzBee' }] } })
      .mockResolvedValueOnce({ data: { factory_id: 'huaxing', customer_code: 'buzzbee' } })
    const api = createCustomerOrderScheduleApi({ get })

    await api.customers('huaxing')
    await api.get('huaxing', {
      customerCode: 'buzzbee', q: 'PO 0007', dateFrom: '2026-10-01', dateTo: '2026-10-31',
      unshippedPage: 2, shippedPage: 3, cancelledPage: 4,
    })

    expect(get).toHaveBeenNthCalledWith(1, '/customer-order-ledger/schedule/customers?factory_id=huaxing')
    expect(get).toHaveBeenNthCalledWith(2, expect.stringContaining('/customer-order-ledger/schedule?'))
    const url = get.mock.calls[1]![0] as string
    expect(url).toContain('factory_id=huaxing')
    expect(url).toContain('customer_code=buzzbee')
    expect(url).toContain('q=PO+0007')
    expect(url).toContain('date_from=2026-10-01')
    expect(url).toContain('date_to=2026-10-31')
    expect(url).toContain('unshipped_page=2')
    expect(url).toContain('shipped_page=3')
    expect(url).toContain('cancelled_page=4')
    expect(url).toContain('page_size=50')
    expect(url).toContain('inspection_pending_page=1')
    expect(url).toContain('completed_page=1')
  })

  it('pages inspection groups separately from shipment groups for Huakang A 360', async () => {
    const get = vi.fn().mockResolvedValue({ data: {} })
    await createCustomerOrderScheduleApi({ get }).get('huakang-a', {
      customerCode: '360', inspectionPendingPage: 2, completedPage: 3, shippedPage: 4,
    })
    const url = new URL(get.mock.calls[0]![0], 'https://example.test')
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      factory_id: 'huakang-a', customer_code: '360', inspection_pending_page: '2', completed_page: '3', shipped_page: '4',
    })
  })

  it('uploads only the chosen workbook and downloads its server-provided UTF-8 name', async () => {
    const file = new File(['workbook'], '360 原排期.xlsx')
    const blob = new Blob(['output'])
    const post = vi.fn().mockResolvedValue({ data: blob, headers: { 'content-disposition': "attachment; filename*=UTF-8''360_%E5%B7%B2%E6%95%B4%E7%90%86.xlsx" } })
    const response = await createCustomerOrderScheduleApi({ get: vi.fn(), post }).organize360('huakang-a', file)
    expect(post).toHaveBeenCalledWith('/customer-order-ledger/schedule/organize-360?factory_id=huakang-a', expect.any(FormData), expect.objectContaining({ responseType: 'blob', timeout: 300_000 }))
    const form = post.mock.calls[0]![1] as FormData
    expect([...form.keys()]).toEqual(['schedule_file'])
    expect(form.get('schedule_file')).toBe(file)
    expect(response).toEqual({ blob, fileName: '360_已整理.xlsx' })
  })

  it('keeps download errors available for the shared permission and validation messages', async () => {
    const error = { response: { status: 422, data: new Blob(['{"detail":"模板不匹配"}']) } }
    const post = vi.fn().mockRejectedValue(error)
    await expect(createCustomerOrderScheduleApi({ get: vi.fn(), post }).organize360('huakang-a', new File(['x'], 'test.xlsx'))).rejects.toBe(error)
  })

  it('decodes the optional organize report without dropping Chinese warning text', async () => {
    const post = vi.fn().mockResolvedValue({ data: new Blob(['excel']), headers: {
      'x-schedule-organize-report': encodeURIComponent(JSON.stringify(organizeReport)),
    } })
    const response = await createCustomerOrderScheduleApi({ get: vi.fn(), post }).organize360('huakang-a', new File(['excel'], '360.xlsx'))
    expect(response.report).toEqual(organizeReport)
  })

  it.each([
    undefined, '%E0%A4%A', encodeURIComponent('broken-json'), encodeURIComponent('null'),
    encodeURIComponent(JSON.stringify({ ...organizeReport, warning_count: -1 })),
    encodeURIComponent(JSON.stringify({ ...organizeReport, sheets: { ITEM表: { moved_to_completed: '7', moved_to_pending: 0 } } })),
    encodeURIComponent(JSON.stringify({ ...organizeReport, warnings: [null] })), 'x'.repeat(5001),
  ])('still returns the downloaded workbook for missing or malformed optional report header %#', async (header) => {
    const blob = new Blob(['excel'])
    const post = vi.fn().mockResolvedValue({ data: blob, headers: { 'x-schedule-organize-report': header } })
    const response = await createCustomerOrderScheduleApi({ get: vi.fn(), post }).organize360('huakang-a', new File(['excel'], '360.xlsx'))
    expect(response).toEqual({ blob, fileName: '360_按验货日期整理.xlsx' })
  })

  it('bounds warning details even when a server sends more than three snippets', async () => {
    const report = { ...organizeReport, warnings: ['a'.repeat(120), 'b', 'c', 'd'] }
    const post = vi.fn().mockResolvedValue({ data: new Blob(['excel']), headers: { 'x-schedule-organize-report': encodeURIComponent(JSON.stringify(report)) } })
    const response = await createCustomerOrderScheduleApi({ get: vi.fn(), post }).organize360('huakang-a', new File(['excel'], '360.xlsx'))
    expect(response.report?.warnings).toEqual(['a'.repeat(100), 'b', 'c'])
    expect(response.report?.warning_count).toBe(5)
  })
})

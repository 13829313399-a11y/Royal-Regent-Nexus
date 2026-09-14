import { describe, expect, it, vi } from 'vitest'
import { createCustomerOrderHistoryApi } from '@/api/customerOrderHistory'

describe('customer order history api', () => {
  it('uses the independent history preview and explicit confirm multipart contracts', async () => {
    const get = vi.fn().mockResolvedValue({ data: { items: [{ code: 'buzzbee', name: 'BuzzBee' }] } })
    const post = vi.fn()
      .mockResolvedValueOnce({ data: { factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', file_name: 'history.xlsx', fingerprint: 'fp-1', rows: [], warnings: [], summary: { total: 0, blocked: 0, existing: 0 } } })
      .mockResolvedValueOnce({ data: { created_count: 1, existing_count: 0, items: [] } })
      .mockResolvedValueOnce({ data: { id: 'line-1', revision: 5 } })
    const api = createCustomerOrderHistoryApi({ get, post })
    const file = new File(['schedule'], 'history.xlsx')

    await api.customers('huaxing')
    await api.preview('huaxing', 'buzzbee', file)
    await api.confirm('huaxing', 'buzzbee', file, {
      fingerprint: 'fp-1', cutoff_date: '2026-09-30', reason: '迁入历史排期',
      selections: [{ id: 'row-1', status: 'active', opening_shipped_quantity: '0002.50' }],
    })
    await api.correctOpening('line-1', 'huaxing', { expected_revision: 4, opening_shipped_quantity: '0002.50', reason: '核对原排期' })

    expect(get).toHaveBeenCalledWith('/customer-order-ledger/history/customers?factory_id=huaxing')
    expect(post).toHaveBeenNthCalledWith(1, '/customer-order-ledger/history/preview', expect.any(FormData), expect.objectContaining({ headers: { 'Content-Type': 'multipart/form-data' } }))
    const previewForm = post.mock.calls[0]![1] as FormData
    expect(previewForm.get('factory_id')).toBe('huaxing')
    expect(previewForm.get('customer_code')).toBe('buzzbee')
    expect(previewForm.get('schedule_file')).toBe(file)
    expect(post).toHaveBeenNthCalledWith(2, '/customer-order-ledger/history/confirm', expect.any(FormData), expect.objectContaining({ headers: { 'Content-Type': 'multipart/form-data' } }))
    const confirmForm = post.mock.calls[1]![1] as FormData
    expect(confirmForm.get('confirmed')).toBe('true')
    expect(confirmForm.get('fingerprint')).toBe('fp-1')
    expect(confirmForm.get('cutoff_date')).toBe('2026-09-30')
    expect(confirmForm.get('reason')).toBe('迁入历史排期')
    expect(confirmForm.get('selections')).toBe(JSON.stringify([{ id: 'row-1', status: 'active', opening_shipped_quantity: '0002.50' }]))
    expect(post).toHaveBeenNthCalledWith(3, '/customer-order-ledger/lines/line-1/history-opening?factory_id=huaxing', {
      expected_revision: 4, opening_shipped_quantity: '0002.50', reason: '核对原排期',
    })
  })
})

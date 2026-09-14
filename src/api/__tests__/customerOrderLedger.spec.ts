import { describe, expect, it, vi } from 'vitest'
import { createCustomerOrderLedgerApi, customerOrderLedgerSourceUrl } from '@/api/customerOrderLedger'

describe('customer order ledger api', () => {
  it('uses the factory-scoped ledger list and capability contracts', async () => {
    const get = vi.fn()
      .mockResolvedValueOnce({ data: { read: true, write: true, dispatch: false, shipment_confirm: false, inbox_read: false, inbox_receive: false } })
      .mockResolvedValueOnce({ data: { items: [], total: 0, page: 1, page_size: 50, customers: [] } })
    const api = createCustomerOrderLedgerApi({ get, post: vi.fn() })

    await api.capabilities('huaxing')
    await api.list('huaxing', { customerCode: 'buzzbee', view: 'unshipped', q: '0009382481' })

    expect(get).toHaveBeenNthCalledWith(1, '/customer-order-ledger/capabilities?factory_id=huaxing')
    expect(get).toHaveBeenNthCalledWith(2, expect.stringContaining('/customer-order-ledger/lines?'))
    expect(get.mock.calls[1]![0]).toContain('factory_id=huaxing')
    expect(get.mock.calls[1]![0]).toContain('customer_code=buzzbee')
    expect(get.mock.calls[1]![0]).toContain('view=unshipped')
    expect(get.mock.calls[1]![0]).toContain('q=0009382481')
  })

  it('sends revisions and an idempotency key with mutable ledger actions', async () => {
    const post = vi.fn().mockResolvedValue({ data: { id: 'line-1' } })
    const api = createCustomerOrderLedgerApi({ get: vi.fn(), post })

    await api.amend('line-1', 'huaxing', { expected_revision: 4, quantity: '0100', requested_ship_date: '2026-10-01', note: '客户确认', reason: '客户改期' })
    await api.confirmShipment('line-1', 'huaxing', { expected_revision: 5, idempotency_key: 'shipment-1', quantity: '0020', ship_date: '2026-10-02', document_no: 'DN-001', note: '' })
    await api.reverseShipment('shipment-1', 'huaxing', { expected_revision: 6, reason: '单据录入错误' })

    expect(post).toHaveBeenNthCalledWith(1, '/customer-order-ledger/lines/line-1/amend?factory_id=huaxing', expect.objectContaining({ quantity: '0100', expected_revision: 4 }))
    expect(post).toHaveBeenNthCalledWith(2, '/customer-order-ledger/lines/line-1/shipments?factory_id=huaxing', expect.objectContaining({ idempotency_key: 'shipment-1', quantity: '0020' }))
    expect(post).toHaveBeenNthCalledWith(3, '/customer-order-ledger/shipments/shipment-1/reverse?factory_id=huaxing', { expected_revision: 6, reason: '单据录入错误' })
  })

  it('posts confirmed imports as multipart without client-side order JSON', async () => {
    const post = vi.fn().mockResolvedValue({ data: { items: [], created_count: 0, existing_count: 0, reconciled_count: 1 } })
    const api = createCustomerOrderLedgerApi({ get: vi.fn(), post })
    const payload = new FormData()
    payload.append('factory_id', 'huaxing')
    payload.append('confirmed', 'true')

    const result = await api.importConfirmed('buzzbee', payload)

    expect(post).toHaveBeenCalledWith('/customer-order-ledger/imports/buzzbee', payload, expect.objectContaining({ headers: { 'Content-Type': 'multipart/form-data' } }))
    expect(result.reconciled_count).toBe(1)
    expect(customerOrderLedgerSourceUrl('source 1', 'huaxing')).toContain('/customer-order-ledger/sources/source%201?factory_id=huaxing')
  })
})

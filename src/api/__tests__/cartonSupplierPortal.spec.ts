import { describe, expect, it, vi } from 'vitest'

const post = vi.hoisted(() => vi.fn())
const get = vi.hoisted(() => vi.fn())
vi.mock('@/lib/http', () => ({ http: { post, get } }))

import { cartonSupplierPortalApi } from '../cartonSupplierPortal'

describe('supplier document export request', () => {
  it('queries receipt candidates in the selected factory and submits both revisions with a durable request ID', async () => {
    get.mockResolvedValueOnce({ data: [] })
    await cartonSupplierPortalApi.receiptOptions('huaxing', 'note/a')
    expect(get).toHaveBeenLastCalledWith('/carton-supplier/internal/shipments/note%2Fa/receipt-options', { params: { factory_id: 'huaxing' } })
    const payload = { factory_id: 'huaxing', expected_revision: 2, receipt_id: 'receipt-a', expected_receipt_revision: 3, reason: '已经手工入库后补凭证' }
    post.mockResolvedValueOnce({ data: { id: 'note/a', linked_existing_receipt: true } })
    await cartonSupplierPortalApi.linkReceipt('note/a', payload)
    expect(post).toHaveBeenLastCalledWith('/carton-supplier/internal/shipments/note%2Fa/link-receipt', { ...payload, request_id: expect.any(String) })
  })
  it('requests scoped paged activity with all query fields before displaying results', async () => {
    const page = { items: [], total: 112, limit: 50, offset: 50 }
    get.mockResolvedValueOnce({ data: page })
    const query = { factory_id: '', search: 'DN-100%', event_type: 'SUPPLIER_SHIPMENT_CREATED',
      date_from: '2026-09-01', date_to: '2026-09-30', sort: 'ASC', limit: 50, offset: 50 }
    expect(await cartonSupplierPortalApi.activityPage(query)).toEqual(page)
    expect(get).toHaveBeenLastCalledWith('/carton-supplier/activity-page', { params: query })
  })
  it('scopes original carton-mark list and download to the supplier API', async () => {
    const signal = new AbortController().signal
    get.mockResolvedValueOnce({ data: [] })
    await cartonSupplierPortalApi.markAssets('huaxing', signal)
    expect(get).toHaveBeenLastCalledWith('/carton-supplier/carton-mark/assets', { params: { factory_id: 'huaxing' }, signal })
    get.mockResolvedValueOnce({ data: 'original-bytes' })
    expect(await cartonSupplierPortalApi.downloadMarkAsset('asset/a', 'huaxing', signal)).toBe('original-bytes')
    expect(get).toHaveBeenLastCalledWith('/carton-supplier/carton-mark/assets/asset%2Fa/document', { params: { factory_id: 'huaxing' }, responseType: 'blob', signal })
  })
  it('submits only the identifiers accepted by the export endpoint', async () => {
    const listedDocument = {
      factory_id: 'huaxing', kind: 'DELIVERY' as const, id: 'shipment-1',
      document_no: 'DN-001', lines: [{ quantity: '10' }],
    }
    post.mockRejectedValueOnce(new Error('request captured'))

    await expect(cartonSupplierPortalApi.exportDocuments([listedDocument])).rejects.toThrow('request captured')
    expect(post).toHaveBeenCalledWith('/carton-supplier/documents/export.xlsx', {
      documents: [{ factory_id: 'huaxing', kind: 'DELIVERY', id: 'shipment-1' }],
    }, { responseType: 'blob' })
  })
})

import { describe, expect, it, vi } from 'vitest'

const post = vi.hoisted(() => vi.fn())
const get = vi.hoisted(() => vi.fn())
vi.mock('@/lib/http', () => ({ http: { post, get } }))

import { cartonSupplierPortalApi } from '../cartonSupplierPortal'

describe('supplier document export request', () => {
  it('uploads mixed originals with only the selected factory and issued order identifiers', async () => {
    post.mockResolvedValueOnce({ data: [] })
    const signal = new AbortController().signal
    const files = [new File(['x'], 'contract.xlsx'), new File(['p'], 'contract.pdf'), new File(['i'], 'photo.png')]
    const order = { id: 'order-a', issue_id: 'issue-a', customer_name: 'private', contract_no: 'C', customer_po: 'PO', item_no: 'I' }
    await cartonSupplierPortalApi.uploadMarkAssets('huaxing', files, order, signal)
    const [path, body, options] = post.mock.lastCall!
    expect(path).toBe('/carton-supplier/carton-mark/assets/upload')
    expect([...body.keys()]).toEqual(['factory_id', 'order_id', 'issue_id', 'files', 'files', 'files'])
    expect(body.getAll('files')).toEqual(files); expect(options).toEqual({ headers: { 'Content-Type': 'multipart/form-data' }, signal, timeout: 300000 })
  })
  it('selects an existing PDF by server ID and revision without sending a file or metadata', async () => {
    post.mockResolvedValueOnce({ data: { id: 'check' } })
    await cartonSupplierPortalApi.createMarkCheck({ factory_id: 'huaxing', order_id: 'order-a', issue_id: 'issue-a', excel_asset_id: 'excel-a', expected_revision: 2, pdf_asset_id: 'pdf-a', expected_pdf_revision: 4 })
    const body = post.mock.lastCall![1] as FormData
    expect([...body.keys()]).toEqual(['factory_id', 'order_id', 'issue_id', 'excel_asset_id', 'expected_revision', 'pdf_asset_id', 'expected_pdf_revision'])
    expect(body.get('print_pdf')).toBeNull(); expect(body.get('expected_pdf_revision')).toBe('4')
  })
  it('only acknowledges the unaccepted-export warning after an explicit decision', async () => {
    const documents = [{ factory_id: 'huaxing', kind: 'PURCHASE' as const, id: 'ISSUE-A' }]
    post.mockRejectedValue(new Error('request captured'))
    await expect(cartonSupplierPortalApi.exportOrderImport(documents)).rejects.toThrow('request captured')
    expect(post).toHaveBeenLastCalledWith('/carton-supplier/documents/order-import.xlsx', {
      documents, acknowledge_unaccepted: false,
    }, { responseType: 'blob' })
    await expect(cartonSupplierPortalApi.exportOrderImport(documents, true)).rejects.toThrow('request captured')
    expect(post).toHaveBeenLastCalledWith('/carton-supplier/documents/order-import.xlsx', {
      documents, acknowledge_unaccepted: true,
    }, { responseType: 'blob' })
    post.mockReset()
  })
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
  it('uploads supplier PDF checks with source and issue versions, without editable identity fields', async () => {
    const file = new File(['%PDF-1.4'], 'print.pdf', { type: 'application/pdf' })
    post.mockResolvedValueOnce({ data: { id: 'checked' } })
    expect(await cartonSupplierPortalApi.createMarkCheck({ factory_id: 'huakang-b', order_id: 'order-b', issue_id: 'issue-b', excel_asset_id: 'excel-b', expected_revision: 3, print_pdf: file })).toEqual({ id: 'checked' })
    const [url, body, config] = post.mock.calls.at(-1)!
    expect(url).toBe('/carton-supplier/carton-mark/checks')
    expect(config).toEqual({ headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 })
    expect(Array.from((body as FormData).keys()).sort()).toEqual(['excel_asset_id', 'expected_revision', 'factory_id', 'issue_id', 'order_id', 'print_pdf'])
    expect((body as FormData).get('expected_revision')).toBe('3')
    expect((body as FormData).get('print_pdf')).toHaveProperty('name', 'print.pdf')
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

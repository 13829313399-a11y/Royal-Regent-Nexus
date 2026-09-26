import { describe, expect, it, vi } from 'vitest'

const post = vi.hoisted(() => vi.fn())
vi.mock('@/lib/http', () => ({ http: { post } }))

import { cartonSupplierPortalApi } from '../cartonSupplierPortal'

describe('supplier document export request', () => {
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
